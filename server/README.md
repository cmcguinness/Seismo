# seismo-server — the station data server

The **middleware** between the acquisition Pi and every downstream consumer. It
owns the pi5 data mirror and re-exposes it as one versioned HTTP/JSON contract,
so consumers (the dashboard, and any future ML / alert / correlation app) stop
reaching into `/data/*` file paths and stop knowing the Pi's LAN address.

This is the "pure server" half of the pi5 split. The **dashboard** and everything
after it become clients of this contract.

```
  Pi 2B (acquire)          pi5 (this server)              consumers
  ┌────────────┐  rsync   ┌──────────────────┐  HTTP     ┌───────────┐
  │ recorder → │ ───────► │ mirror  ─►  store │ ────────► │ dashboard │
  │ *.mseed    │  (1/min) │ /data/*    (façade)│  /v1/*   │ ML / alerts│
  │ events.log │          │            server │           │  …        │
  │ live ring  │ ─(3 s)─► │                    │           └───────────┘
  └────────────┘          └──────────────────┘
```

## Status (2026-08-26)

The owned data plane is BUILT: the station streams miniSEED records by UDP to
`udp_collector.py`, which owns `~/seismo-archive/` on pi5; `detector.py` re-runs STA/LTA
over that archive, dedupes near-duplicate triggers (±3 s), scores each trigger with the
Mac-trained classifier (`p_quake`, via `trigger_features.py` + `trigger_gbm.joblib`)
and pushes to ntfy at p ≥ 0.7; this server and the dashboards read the pi5 detector's
`events.log`, not the station's. The old `seismo-rsync.timer` still mirrors the station's
`data/`, `events.log`, `health.json` into `~/seismo-data/` for QC and the env node.
The public dashboard on apps02 is fed outbound from pi5 (see STATUS.md). The rest of this
file is the original design note and still describes the contract accurately.

## Why it exists

At the time of writing the transport was a **file mirror**: a host-level `seismo-rsync.timer` on the
pi5 pulls `seismo.local:~/seismo/{data,events.log,health.json}` every minute, plus
a faster pull of the live-ring npz. Every consumer opens those files itself. That
couples every app to (a) the mirror's directory layout and (b) the fact that data
arrives by rsync at all.

The mirror also has a hard latency floor: the archive path is **≥60 s stale**
because it is a batch pull. When we want near-real-time, the fix is to replace the
file backend with a **SeedLink stream** from the Pi — and no consumer should have
to change. That is exactly what the `SeismoStore` abstraction buys: only the store
touches the mirror; swap the backend there, the contract holds.

## The contract (v1)

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/` | this contract, as JSON |
| GET | `/v1/health` | station acquisition counters (rate, blocks, dropped, glitches, clock_err…) **plus** `mirror_age_s` — so a consumer can tell "station down" from "feed to me stale" |
| GET | `/v1/live` | rolling 30 s window: `uv` (microvolts, de-meaned), `fs`, `gain`, `pp`, `rms`, `t_end`, `age` |
| GET | `/v1/events` | detections, newest first. Params: `limit` (default 200), `since` (ISO-8601), `min_ratio`. **Unfiltered by default** — MIN_RATIO/WINDOW_H are display policy and belong to the consumer. Since 2026-08-26 rows with `peak_ratio ≥ 10` carry `p_quake` (0–1, the trigger classifier) |
| GET | `/v1/waveform` | recorded trace over a window. Params: `start`, `end` (ISO-8601, required), `format=json\|mseed`. `mseed` is the canonical currency (feed to ObsPy/Swarm/anything); `json` gives `{seed_id, fs, t0, counts, uv}` for browsers |

All responses send `Access-Control-Allow-Origin: *`. Read-only — no mutating routes.

## Layout

- `store.py` — `SeismoStore`, the backend-swappable archive/live façade. The **only**
  code that knows how data physically arrives. Live/events/health use stdlib + numpy;
  `waveform` lazily imports obspy.
- `seismo_server.py` — the HTTP layer. Thin: parse request → call store → serialize.
  stdlib `ThreadingHTTPServer`, no framework.
- `seismo-server.service` — systemd unit for the pi5.
- `requirements.txt` — numpy always; obspy only for `/v1/waveform`.

## Run

```bash
# local, against a mirror directory
SEISMO_DATA=./mirror/data SEISMO_EVENTS=./mirror/events.log \
SEISMO_HEALTH=./mirror/health.json SEISMO_RING=./mirror/seismo_live.npz \
python seismo_server.py
# -> http://localhost:8351/
```

Config is all environment (see the service unit for the pi5 paths):
`SEISMO_DATA`, `SEISMO_EVENTS`, `SEISMO_HEALTH`, `SEISMO_RING`, `SEISMO_SERVER_PORT`,
and the SEED id (`SEISMO_STATION/NETWORK/LOCATION/CHANNEL`) + `SEISMO_GAIN` for the
counts→µV conversion.

## What this draft deliberately leaves out (next steps)

1. **Migrate the consumers.** The dashboard still reads `/data/*` directly. Point
   `render.py` / `seismo_dashboard.py` at `/v1/*` and delete their file access +
   the `SEISMO_LIVE_URL` Pi proxy. That is the change that actually realizes the split.
2. **Absorb the helicorder envelope builder.** `heli_build.py` + the `heli_service`
   worker are a *server-side reduction* (miniSEED → per-interval min/max envelope
   npz), not presentation — the next app will want the same reduced drum data. Move
   the **builder** here and expose `GET /v1/heli/envelopes`; leave only the PNG
   *rendering* (`heli_render.py`) in the dashboard. Kept out of this first cut to
   avoid churning the working dashboard before the contract is proven.
3. **Derived live analytics** (`live_spectrum`, band-RMS) stay consumer-side for now:
   they pull scipy and are presentation-ish. Promote to the store if a second consumer
   needs them.
4. **SeedLink / FDSN backend.** The ~1-week upgrade: a `SeismoStore` backend that
   streams from the Pi instead of reading the batch mirror, plus a SeedLink server so
   the wider seismology toolchain plugs in. Contract unchanged.

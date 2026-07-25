# Helicorder v2 — precomputed-envelope drum

## Why

The old dashboard re-parsed and re-plotted the *entire growing day-file* with
ObsPy `dayplot` on **every request**. Cost scaled as `whole-day × viewers ×
refreshes`, and the critical path was always a cold ~2 s render — a cache only
helps the 2nd..Nth viewer within a minute, but the data (and page) refresh every
60 s, so almost every hit landed cold.

The instrument is a **streaming, append-only source**; the render should scale
with *new data*, computed **once**. That's what this does.

## Pipeline

```
mirrored miniSEED (/data/data, rsync'd every 60 s)
        │
        ▼  heli_build.py   (obspy ingest — INGEST half, backend)
   /data/heli/heli.YYYY.JJJ.HHMM.npz     one per 15-min interval
        │                                 mins[], maxs[] (float32 counts, de-meaned,
        │                                 high-passed; NaN = gap), env, sigma, t0
        ▼  heli_render.py  (numpy+matplotlib, NO obspy — DUMB/fast half)
   1920×1080 drum PNG bytes
        │
        ▼  heli_service.py (daemon thread: rebuild+re-render on mtime change)
   in-memory PNG  ──►  GET /helicorder.png   (O(1), always warm)
```

## Data model — the interval file

- **One npz per clock-aligned 15-min interval** (`:00/:15/:30/:45`). An interval
  is rebuilt every pull until data runs past its end (a stored `complete` flag) —
  otherwise it freezes ~1 min short, since the last build while it was *current*
  only had data up to `latest`. Once `complete`, it's immutable and skipped.
  Intervals before the window are pruned by the
  **interval time parsed from the filename**, NOT file mtime — a bulk rebuild
  (service restart) writes every file "now", so mtime can't distinguish old
  intervals from fresh ones.
- `mins[]`, `maxs[]`: **NPIX** (=1835, the plot-area width) float32 pairs — the
  per-pixel min/max **envelope**. Values are **de-meaned raw counts** after a high-
  pass (default 1 Hz, `SEISMO_HELI_HP`) that removes slow tilt/drift which would
  otherwise swamp the drum. `NaN` = no samples in that pixel (real gap, or the
  not-yet-reached tail of the current interval) → renderer draws nothing.
- `env`: median of per-pixel `max(|min|,|max|)` — the *typical drawn excursion*.
  The renderer scales on this, **not** `sigma`, because a pixel's min/max spans
  several σ of spiky noise, so σ-based scaling renders far too hot.
- `sigma`: interval RMS (kept for reference / future use).
- Units are counts, but the drum is **σ-relative**, so the counts→µV gain never
  enters — the file is gain-agnostic.

## Rendering

- Canvas **1920×1080**; margins L85/R15/T72/B48. The top margin holds a 3-line
  **webicorder-style header** (date · station · location) + a "data to HH:MM UTC"
  note; the bottom margin holds an x-axis with a **per-minute tick** (0–15) —
  each row spans one 15-min interval. Row labels sit 5 px from the left edge.
- **16 rows** (4 h ÷ 15 min, `SEISMO_HELI_HOURS`), ~62 px each; oldest at top,
  read top→bottom. Row + title labels sized for the 1920px image (16 / 22 pt).
- **Scale:** one global `k = row_h·ENV_FRAC / median(env)` — comparable across
  rows and across refreshes (not per-row auto-scale). `ENV_FRAC` default 0.15.
- **Clip** at ±`CLIP_ROWS` (=3) rows: a "big" event swings 3 lines up/down then
  clips — dramatic but not lossy (you still see it happened and its duration).
  Future: break clipped events into their own panel (see BACKLOG).
- Per pixel: draw the vertical min→max segment (via one `LineCollection`).
  4-colour row cycle (dark red · dark green · blue · black), per-row `HH:MM` UTC label.

## Knobs (env vars)

| var | default | meaning |
|-----|---------|---------|
| `SEISMO_DATA` | `/data/data` | mirrored miniSEED dir |
| `SEISMO_HELI` | `/data/heli` | interval-file output dir |
| `SEISMO_HELI_HP` | `1.0` | high-pass corner Hz (0 disables) |
| `SEISMO_HELI_NPIX` | `1835` | pairs per interval = plot-area px |
| `SEISMO_HELI_INTERVAL` | `900` | seconds per row |
| `SEISMO_HELI_HOURS` | `4` | window / retention (rows = hours×4) |
| `SEISMO_HELI_POLL` | `20` | service mtime-check period (s) |
| `ENV_FRAC` / `CLIP_ROWS` | 0.15 / 3 | render scale + clip (in heli_render.py) |

## Status

Built and verified end-to-end on the Mac against real sample day-files
(`analysis/data/`): build 0.33 s, render sub-second, full page renders in a
browser via the pre-rendered route. **Not yet deployed to pi5.** Amplitude
constants and the high-pass corner are by-eye defaults to re-tune on real 8 h
data. See BACKLOG "Helicorder v2" for open items.

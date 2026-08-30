#!/usr/bin/env python3
"""detector.py -- pi5-side STA/LTA earthquake detector over the OWNED archive (rev2 sec 9).

Moves detection off the station (which keeps only despike/QC, part of producing the clean
archive). Runs the SAME `StaLta` the station ran, but on the pi5 against the archive the
collector builds -- which unlocks RETROACTIVE re-detection: retune thresholds and re-run
over the whole archive. Every trigger to date is a false positive, so that re-run surface
is the point.

Modes:
  (default)         real-time service: every POLL_S, re-detect over the last WINDOW_S of
                    the current UTC day-file, emit new events (deduped by start-time).
  --file PATH       retroactive: detect over one miniSEED file, print events (JSON).
  --day YYYY.DDD    retroactive: same, over that archive day-file.
Thresholds are tunable (--trig/--detrig/--sta/--lta/--hp) for re-detection experiments.

Events (JSONL) -> <archive>/events.log, schema {start,end,duration_s,peak_ratio,peak_uv}
matching the station's so the dashboard / /v1/events can read either.

NOTE (parity): retroactive --file runs StaLta continuously over the day (one settle), so it
matches the station's inline detector closely. The real-time window re-primes the LTA each
poll, so triggers within ~LTA seconds of a window edge can differ -- fine for alerting
(latency is uncritical), and the retroactive path is the authoritative re-detection.
"""
import argparse
import datetime
import json
import os
import time
from pathlib import Path

import numpy as np
import simplemseed
from stalta import StaLta
from trigger_features import TriggerScorer, PRE, POST

ARCHIVE = Path(os.environ.get("SEISMO_ARCHIVE", str(Path.home() / "seismo-archive")))
GAIN = int(os.environ.get("SEISMO_GAIN", "64"))
FS = float(os.environ.get("SEISMO_RATE", "100"))
POLL_S = int(os.environ.get("SEISMO_DETECT_POLL_S", "60"))
WINDOW_S = int(os.environ.get("SEISMO_DETECT_WINDOW_S", "600"))
# SEED identity -- env-driven so the XX.OAKMT -> SS.OAKM1 cutover is a config
# change, not a code change. Must match station/recorder.py and server/store.py.
NET = os.environ.get("SEISMO_NETWORK", "SS")
STA = os.environ.get("SEISMO_STATION", "OAKM1")
LOC = os.environ.get("SEISMO_LOCATION", "00")
CHAN = os.environ.get("SEISMO_CHANNEL", "EHZ")
EVENTS = ARCHIVE / "events.log"
# Stage-1 trigger classifier (STATUS 2026-08-26): trained on the Mac, shipped here by
# deploy.sh. Absent file -> events go out without p_quake, nothing else changes.
MODEL = Path(os.environ.get("SEISMO_TRIGGER_MODEL", str(Path(__file__).parent / "trigger_gbm.joblib")))
# ntfy push when the classifier is confident (Charles, 2026-08-26): p_quake >= ALERT_P.
# Same server/topic/token as dc_watch, from /etc/seismo/ntfy.env via the unit file.
# One push per ALERT_HOLD_S at most: an aftershock cluster is one notification, not ten.
# How long to wait past the end of a trigger's scoring window before scoring it.
# The archive arrives from the station in ~10 s blocks with a few seconds of lag, so
# a hold of 2 s meant the last few seconds of the window often had not landed yet,
# _window() came up short of its 95% completeness bar and returned None, and the
# trigger was written out with no p_quake -- silently, so nothing said why. That is
# how the M1.8 of 2026-08-29 00:42:18 UTC (2.8 km away, STA/LTA 585, the largest in
# the archive) went out with no score and never raised an ntfy push: 7% of triggers
# with ratio >= 10 were being dropped this way, on poll timing alone, not on size.
SCORE_HOLD_S = float(os.environ.get("SEISMO_SCORE_HOLD_S", "15"))
ALERT_P = float(os.environ.get("SEISMO_ALERT_P", "0.7"))
ALERT_HOLD_S = float(os.environ.get("SEISMO_ALERT_HOLD_S", "300"))
NTFY_URL = os.environ.get("SEISMO_NTFY_URL"); NTFY_TOPIC = os.environ.get("SEISMO_NTFY_TOPIC")
NTFY_TOKEN = os.environ.get("SEISMO_NTFY_TOKEN")
PUBLIC_URL = os.environ.get("SEISMO_PUBLIC_URL", "https://seismo.mcguinness.ai")
_last_alert = [0.0]


def alert(ev, test=False) -> bool:
    """Push a probable-earthquake notification. Logs regardless; sends only if ntfy is
    configured and the hold-off has passed. Returns True if a push was attempted."""
    st = ev["start"].replace("+00:00", "")
    when = datetime.datetime.fromisoformat(ev["start"])
    hist = f"{PUBLIC_URL}/history?datetime={when:%Y%m%d%H}"
    title = ("TEST: " if test else "") + f"Probable earthquake  p={ev.get('p_quake', 0):.2f}"
    body = (f"{st} UTC  ·  STA/LTA {ev.get('peak_ratio')}  ·  peak {ev.get('peak_uv')} µV  ·  "
            f"{ev.get('duration_s')} s\nDrum: {hist}\nCatalog: https://earthquake.usgs.gov/earthquakes/map/")
    print(f"ALERT {title} -- {body.splitlines()[0]}", flush=True)
    if not (NTFY_URL and NTFY_TOPIC):
        return False
    now = time.time()
    if not test and now - _last_alert[0] < ALERT_HOLD_S:
        print("ALERT held (within hold-off)", flush=True)
        return False
    try:
        import requests
        headers = {"Title": title, "Priority": "high", "Tags": "earthquake" if not test else "test_tube",
                   "Click": hist}
        if NTFY_TOKEN:
            headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
        requests.post(f"{NTFY_URL.rstrip('/')}/{NTFY_TOPIC}", data=body.encode("utf-8"),
                      headers=headers, timeout=10)
        _last_alert[0] = now
        return True
    except Exception as exc:
        print("ALERT ntfy failed:", exc, flush=True)
        return False
UV = 2.5 * 2 / (GAIN * (2 ** 23 - 1)) * 1e6      # counts -> uV, matches recorder


def _read_sorted(path: Path) -> list:
    recs = []
    with open(path, "rb") as fh:
        for r in simplemseed.readMiniseed2Records(fh):
            recs.append((r.header.starttime.timestamp(), r))
    recs.sort(key=lambda x: x[0])
    return recs


def _iso(epoch):
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat(
        timespec="seconds")


def detect(recs, fs, params, reset_gap_s=60.0) -> list:
    """Events (absolute-UTC start/end) over sorted records.

    Feeds ONE StaLta continuously across small gaps -- exactly what the station's inline
    detector did (it processes the sample stream, so a dropped-sample block cut never
    re-primes the 30 s LTA). Only a *real* outage (> reset_gap_s, e.g. a station/link
    down) re-primes. Each record timestamps its own samples, so event times stay accurate
    even though many tiny gaps are bridged."""
    dt = 1.0 / fs

    def _fresh():
        return StaLta(fs, hp_hz=params["hp"], sta_s=params["sta"], lta_s=params["lta"],
                      trig=params["trig"], detrig=params["detrig"], uv_per_count=UV)

    det = _fresh()
    out, expected = [], None
    for te, r in recs:
        s = np.asarray(r.decompress(), dtype=np.int32)
        if expected is not None and abs(te - expected) > reset_gap_s:
            det = _fresh()                       # genuine outage -> re-prime
        for j in range(len(s)):
            ev = det.update(s[j])
            if ev:
                end = te + j * dt
                out.append({"start": _iso(end - ev["duration_s"]), "end": _iso(end), **ev})
        expected = te + len(s) * dt
    return out


def _dayfile(dt_utc) -> str:
    return f"{NET}.{STA}.{LOC}.{CHAN}.D.{dt_utc.year}.{dt_utc.timetuple().tm_yday:03d}.mseed"


# Re-detecting the last WINDOW_S every poll re-primes the LTA at the window edge, so
# the SAME burst can come back with a start 1-2 s different and a slightly different
# ratio (19:03:45 / 19:03:46, 2026-08-26 -- one event, two rows). Dedupe by proximity,
# not by exact start string.
DEDUPE_S = 3.0


def _emitted_keys() -> list:
    """Start times (epoch s) already written, for proximity dedupe."""
    keys = []
    if EVENTS.exists():
        for line in EVENTS.read_text().splitlines():
            try:
                keys.append(datetime.datetime.fromisoformat(json.loads(line)["start"]).timestamp())
            except Exception:
                pass
    return keys


def _seen_near(keys: list, t: float) -> bool:
    return any(abs(k - t) <= DEDUPE_S for k in keys[-500:])


def _window(recs, t0, t1, fs):
    """Raw counts for [t0, t1) stitched from sorted records, or None if incomplete."""
    out, expect = [], None
    for te, r in recs:
        s = np.asarray(r.decompress(), dtype=np.int32)
        t_end = te + len(s) / fs
        if t_end <= t0 or te >= t1:
            continue
        a = max(0, int(round((t0 - te) * fs))); b = min(len(s), int(round((t1 - te) * fs)))
        out.append(s[a:b])
    if not out:
        return None
    x = np.concatenate(out)
    need = int((t1 - t0) * fs)
    return x if len(x) >= need * 0.95 else None


def realtime(params) -> None:
    print(f"detector realtime: poll {POLL_S}s window {WINDOW_S}s -> {EVENTS}", flush=True)
    scorer = None
    if MODEL.exists():
        try:
            scorer = TriggerScorer(MODEL)
            print(f"trigger model {MODEL.name}: {scorer.meta}, floor ratio {scorer.min_ratio:g}", flush=True)
        except Exception as exc:
            print("trigger model NOT loaded:", exc, flush=True)
    emitted = _emitted_keys()
    while True:
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            path = ARCHIVE / _dayfile(now)
            if path.exists():
                cutoff = (now - datetime.timedelta(seconds=WINDOW_S)).timestamp()
                recs = [(t, r) for t, r in _read_sorted(path) if t >= cutoff]
                for ev in detect(recs, FS, params):
                    t_start = datetime.datetime.fromisoformat(ev["start"]).timestamp()
                    if not _seen_near(emitted, t_start):
                        # Hold the event until its scoring window has actually arrived
                        # (POST s after start, plus the mirror's block cadence and lag);
                        # the next poll picks it up. Latency is uncritical here.
                        if scorer is not None and now.timestamp() < t_start + POST + SCORE_HOLD_S:
                            continue
                        if scorer is not None:
                            try:
                                w = _window(recs, t_start - PRE, t_start + POST, FS)
                                if w is None:
                                    # Never silent: an unscored trigger cannot raise an
                                    # alert, so the reason has to be in the log.
                                    print(f"score skipped {ev['start']}: window incomplete "
                                          f"(ratio {ev['peak_ratio']})", flush=True)
                                p = scorer.score(ev, w, FS) if w is not None else None
                                if p is not None:
                                    ev["p_quake"] = round(p, 3)
                            except Exception as exc:
                                print("score error:", exc, flush=True)
                        emitted.append(t_start)
                        with open(EVENTS, "a") as f:
                            f.write(json.dumps(ev) + "\n")
                        if ev.get("p_quake", 0) >= ALERT_P:
                            alert(ev)
                        print(f"EVENT {ev['start']} dur {ev['duration_s']}s "
                              f"ratio {ev['peak_ratio']} peak {ev['peak_uv']}uV"
                              f"{'  p_quake ' + str(ev['p_quake']) if 'p_quake' in ev else ''}", flush=True)
        except Exception as exc:
            print("detect error:", exc, flush=True)
        time.sleep(POLL_S)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--file")
    p.add_argument("--day", help="archive day-file as YYYY.DDD")
    p.add_argument("--test-alert", action="store_true", help="send one TEST push to ntfy and exit")
    p.add_argument("--trig", type=float, default=4.0)
    p.add_argument("--detrig", type=float, default=1.5)
    p.add_argument("--sta", type=float, default=1.0)
    p.add_argument("--lta", type=float, default=30.0)
    p.add_argument("--hp", type=float, default=3.0)
    a = p.parse_args()
    if a.test_alert:
        ok = alert({"start": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                    "p_quake": 0.99, "peak_ratio": 62.0, "peak_uv": 84.0, "duration_s": 15.0}, test=True)
        print("test alert sent" if ok else "test alert NOT sent (ntfy not configured?)")
        raise SystemExit(0)
    params = {"trig": a.trig, "detrig": a.detrig, "sta": a.sta, "lta": a.lta, "hp": a.hp}
    if a.file or a.day:
        path = Path(a.file) if a.file else ARCHIVE / f"{NET}.{STA}.{LOC}.{CHAN}.D.{a.day}.mseed"
        evs = detect(_read_sorted(path), FS, params)
        print(f"{len(evs)} events over {path.name}  (trig {a.trig}/{a.detrig}, "
              f"STA {a.sta}s/LTA {a.lta}s, HP {a.hp}Hz)")
        for ev in evs:
            print(json.dumps(ev))
    else:
        realtime(params)

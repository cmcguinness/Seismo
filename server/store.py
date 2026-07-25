#!/usr/bin/env python3
"""store.py — the archive/live abstraction the server serves from.

This is the ONE place that knows how station data physically reaches the
consumers. Today that is the pi5 rsync mirror: a host-level `seismo-rsync.timer`
pulls `seismo.local:~/seismo/{data,events.log,...}` into a local directory every
minute, plus a faster pull of the live ring npz. Every consumer (the dashboard,
future ML/alert apps) currently reaches into those file paths itself; the point
of this module is that they stop, and go through one contract instead.

Why an abstraction and not just "open the files": the mirror is an implementation
detail with a hard floor -- the archive path is >=60 s stale because it is a
batch pull. The day we want near-real-time we replace the file backend with a
SeedLink stream from the Pi, and NOTHING downstream should have to change. So the
server talks to `SeismoStore`, and only `SeismoStore` talks to the mirror. Swap
the backend here; the HTTP contract in seismo_server.py stays put.

Kept deliberately lean: `live`, `events`, `health` use only stdlib + numpy and
run with zero heavy deps. Only `waveform` needs obspy, imported lazily -- the
service still starts and serves the real-time spine on a box without it.
"""
import datetime
import glob
import json
import os
from pathlib import Path

import numpy as np

# --- SEED identity (must match station/recorder.py) --------------------------
STATION = os.environ.get("SEISMO_STATION", "OAKMT")
NETWORK = os.environ.get("SEISMO_NETWORK", "XX")
LOCATION = os.environ.get("SEISMO_LOCATION", "00")
CHANNEL = os.environ.get("SEISMO_CHANNEL", "SHZ")

# --- mirror layout (what the pi5 rsync timers land) --------------------------
DATA_DIR = Path(os.environ.get("SEISMO_DATA", "/data/data"))          # *.mseed day-files
EVENTS = Path(os.environ.get("SEISMO_EVENTS", "/data/events.log"))    # JSONL detections
HEALTH = Path(os.environ.get("SEISMO_HEALTH", "/data/health.json"))   # acq counters
RING = Path(os.environ.get("SEISMO_RING", "/data/seismo_live.npz"))   # 30 s live window

# ADS1256 count -> microvolts. v_ref = 2.5 V (on-board LM285-2.5, present in every
# jumper position); factor 2 = differential +/- full scale; 2^23-1 = 24-bit signed
# full scale. This constant is duplicated in recorder.py / live_server.py / render.py;
# this is meant to become its single home once those move onto the contract.
def uv_per_count(gain: int) -> float:
    return (2.5 * 2 / (gain * (2 ** 23 - 1))) * 1e6


def _utc(epoch: float) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)


class SeismoStore:
    """Read-only view over the station's data, however it currently arrives.

    Every method returns plain JSON-able Python (dicts/lists/scalars) or, for
    `waveform`, raw bytes -- never obspy/numpy objects -- so the HTTP layer stays
    a dumb serializer.
    """

    def __init__(self, *, data_dir=DATA_DIR, events=EVENTS, health=HEALTH, ring=RING):
        self.data_dir = Path(data_dir)
        self.events_path = Path(events)
        self.health_path = Path(health)
        self.ring_path = Path(ring)

    # -- liveness -------------------------------------------------------------
    def mirror_age(self) -> float | None:
        """Seconds since the newest day-file changed -- the freshness of the
        archive path. A large value means the rsync timer or the recorder stalled.
        None if no data has ever mirrored."""
        import time
        files = glob.glob(str(self.data_dir / "*.mseed"))
        if not files:
            return None
        return time.time() - max(os.path.getmtime(f) for f in files)

    def health(self) -> dict:
        """Station acquisition counters (health.json) plus server-side liveness.
        The station publishes rate/blocks/dropped/glitches/clock_err; we add the
        mirror age so a consumer can tell 'station is fine but the feed to me is
        stale' apart from 'station is down'."""
        station = {}
        try:
            station = json.loads(self.health_path.read_text())
        except Exception:
            pass
        return {
            "seed_id": f"{NETWORK}.{STATION}.{LOCATION}.{CHANNEL}",
            "station": station,
            "mirror_age_s": self._round(self.mirror_age(), 1),
        }

    # -- live strip-chart -----------------------------------------------------
    def live(self) -> dict:
        """The rolling 30 s window as microvolts, de-meaned. Mirrors the payload
        render.live_ring_json produced, minus the derived spectrum/band-RMS (those
        pull scipy and are a consumer concern -- see README). `t_end` is the UTC
        epoch of the newest sample, stamped by the station's live_publisher, so
        `age` is real end-to-end latency, not the mirror's copy time."""
        import time
        empty = {"uv": [], "pp": 0.0, "rms": 0.0, "fs": 0.0, "gain": 0,
                 "age": None, "t_end": None}
        try:
            mtime = os.path.getmtime(self.ring_path)
            with np.load(self.ring_path) as d:
                counts = d["counts"].astype(float)
                fs = float(d["fs"])
                gain = int(d["gain"])
                t_end = float(d["t_end"]) if "t_end" in d.files else mtime
        except Exception:
            return empty
        uv = counts * uv_per_count(gain)
        if uv.size:
            uv = uv - uv.mean()
        return {
            "uv": [round(float(v), 2) for v in uv],
            "pp": float(np.ptp(uv)) if uv.size else 0.0,
            "rms": round(float(np.sqrt(np.mean(uv * uv))), 2) if uv.size else 0.0,
            "fs": fs, "gain": gain,
            "t_end": t_end, "age": round(time.time() - t_end, 1),
        }

    # -- detections -----------------------------------------------------------
    def events(self, *, limit=200, since=None, min_ratio=0.0) -> list[dict]:
        """Detections from events.log (JSONL), newest first. Deliberately UNfiltered
        by default: the dashboard's MIN_RATIO/WINDOW_H are display policy and belong
        to the consumer, not the middleware. `since` is an ISO-8601 lower bound on
        each event's `start`; `min_ratio` an optional STA/LTA floor."""
        try:
            lines = self.events_path.read_text().splitlines()
        except Exception:
            return []
        cutoff = None
        if since:
            try:
                cutoff = datetime.datetime.fromisoformat(since)
                if cutoff.tzinfo is None:
                    cutoff = cutoff.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                cutoff = None
        out = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if float(e.get("peak_ratio", 0) or 0) < min_ratio:
                continue
            if cutoff is not None:
                try:
                    t = datetime.datetime.fromisoformat(e.get("start", ""))
                except ValueError:
                    continue
                if t.tzinfo is None:
                    t = t.replace(tzinfo=datetime.timezone.utc)
                if t < cutoff:
                    continue
            out.append(e)
        out.sort(key=lambda e: e.get("start", ""), reverse=True)
        return out[:limit]

    # -- waveform slices ------------------------------------------------------
    def waveform(self, start: str, end: str, fmt: str = "json") -> tuple[bytes, str]:
        """Return the recorded trace over [start, end) as (body_bytes, content_type).

        fmt="mseed" -> standard miniSEED bytes (the canonical currency; feed it to
        ObsPy/Swarm/anything). fmt="json" -> {seed_id, fs, t0, counts, uv} for
        browser consumers that don't parse SEED.

        Only the day-file(s) covering the window are opened, chosen by the SEED
        filename convention -- so a request never decodes the whole archive. obspy
        is imported here, lazily, because it heals the early archive's mixed rates
        and per-block overlaps; the rest of the store needs none of it."""
        import obspy

        t0 = obspy.UTCDateTime(start)
        t1 = obspy.UTCDateTime(end)
        st = obspy.Stream()
        for path in self._files_covering(t0, t1):
            try:
                st += obspy.read(path, starttime=t0, endtime=t1)
            except Exception:
                continue
        if len(st):
            st.merge(method=1)
            st.trim(t0, t1)
        if fmt == "mseed":
            import io
            buf = io.BytesIO()
            if len(st):
                st.write(buf, format="MSEED")
            return buf.getvalue(), "application/vnd.fdsn.mseed"
        # JSON: first trace only (single channel here); gaps drop out of merge.
        if not len(st):
            body = {"seed_id": f"{NETWORK}.{STATION}.{LOCATION}.{CHANNEL}",
                    "fs": 0.0, "t0": None, "counts": [], "uv": []}
        else:
            tr = st[0]
            gain = self._gain_hint()
            counts = tr.data.astype(float)
            body = {
                "seed_id": tr.id,
                "fs": float(tr.stats.sampling_rate),
                "t0": tr.stats.starttime.isoformat(),
                "counts": [int(c) for c in tr.data],
                "uv": [round(float(c) * uv_per_count(gain), 3) for c in counts],
            }
        return json.dumps(body).encode(), "application/json"

    # -- internals ------------------------------------------------------------
    def _files_covering(self, t0, t1) -> list[str]:
        """Day-file paths whose UTC day intersects [t0, t1], by filename
        (NET.STA.LOC.CHA.D.YYYY.JJJ.mseed). Cheap: no file is opened to decide."""
        day = datetime.timedelta(days=1)
        d = datetime.datetime(t0.year, t0.month, t0.day, tzinfo=datetime.timezone.utc)
        last = datetime.datetime(t1.year, t1.month, t1.day, tzinfo=datetime.timezone.utc)
        paths = []
        while d <= last:
            fn = (f"{NETWORK}.{STATION}.{LOCATION}.{CHANNEL}.D."
                  f"{d.year}.{d.timetuple().tm_yday:03d}.mseed")
            p = self.data_dir / fn
            if p.exists():
                paths.append(str(p))
            d += day
        return paths

    def _gain_hint(self) -> int:
        """PGA gain for the counts->uV conversion. The recorder does not stamp gain
        into the archive (raw counts by SEED convention), so we read it from
        health.json, falling back to the deployment default."""
        try:
            g = json.loads(self.health_path.read_text()).get("gain")
            if g:
                return int(g)
        except Exception:
            pass
        return int(os.environ.get("SEISMO_GAIN", "64"))

    @staticmethod
    def _round(x, n):
        return None if x is None else round(x, n)

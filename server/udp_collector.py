#!/usr/bin/env python3
"""udp_collector.py -- pi5 ingest: receive the station's UDP record stream + heartbeat
and build the OWNED miniSEED archive (rev2-data-plane.md sec 1/3/6/14).

Phase-1 steps 1-2, running ALONGSIDE the existing rsync mirror (nothing retired):

  * DATA (port 48317): MAGIC 'SZ' | ver | n_records | seq(u32) | N x 512B record.
    Records deduped by (day-file, start-time) -- N=2 sends each twice -- appended to
    day-files under SEISMO_ARCHIVE. Restart-safe (rebuilds the seen-set by scanning
    the day-file).
  * HEARTBEAT (port 48318): station->pi5 JSON pulse ~1 s (sec 6). Written atomically to
    <archive>/station_health.json -- the eventual replacement for the health.json rsync.
    Its absence/gaps are the liveness signal.
  * BACKFILL (sec 14.4): lazy, pi5-initiated. On startup and hourly, rsync the station's
    recent local day-files and merge any records missing from the archive (dedup by
    start-time absorbs the overlap). This is the archive-completeness layer for the rare
    fade N=2 misses and for pi5 downtime -- NOT routine per-packet plumbing.

Best-effort ingest: a malformed datagram or a failed backfill is logged, never fatal.
"""
import csv
import datetime
import json
import os
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

import simplemseed

MAGIC = b"SZ"
RECLEN = 512
HDR = struct.Struct("!2sBBI")   # magic, version, n_records, seq

ARCHIVE = Path(os.environ.get("SEISMO_ARCHIVE", str(Path.home() / "seismo-archive")))
PORT = int(os.environ.get("SEISMO_UDP_PORT", "48317"))
HB_PORT = int(os.environ.get("SEISMO_HB_PORT", "48318"))
BIND = os.environ.get("SEISMO_UDP_BIND", "0.0.0.0")
STATION_HOST = os.environ.get("SEISMO_STATION_HOST", "seismo.local")
STATION_DATA = os.environ.get("SEISMO_STATION_DATA", "seismo/data")   # rel. to station home
BACKFILL_S = int(os.environ.get("SEISMO_BACKFILL_S", "3600"))         # hourly reconcile
STATION_HEALTH = ARCHIVE / "station_health.json"
# station_health.json is a SNAPSHOT -- overwritten every heartbeat, so the instrument's own
# history was being discarded a second at a time. That is the one stream here that cannot
# be reconstructed: rate_est is the crystal rate and wanders with temperature (there is a
# matching env series to correlate against), clock_err_ms records how good the timestamp
# on any given event actually was, and the counters say whether the station was healthy
# when it recorded something. Without a history you cannot answer "was the instrument
# sound when event X arrived?" for any past event -- which is exactly the provenance a
# defensible dataset needs. One row a minute is ~1440/day, well under 200 KB.
HEALTH_DIR = Path(os.environ.get("SEISMO_HEALTH_DIR", str(ARCHIVE / "health")))
HEALTH_EVERY_S = int(os.environ.get("SEISMO_HEALTH_EVERY_S", "60"))
HEALTH_COLS = ["t", "hb_seq", "mode", "rate", "blocks", "rate_est", "clock_err_ms",
               "lag_ms", "dropped", "filled", "tossed", "padded", "glitches", "spikes",
               "stalls", "resyncs", "udp_sent", "udp_dropped", "hi_seq"]
_health_last = [0.0]


def _append_health(hb: dict) -> None:
    """Append one heartbeat to a daily CSV, mirroring how the env series is kept."""
    now = time.time()
    if now - _health_last[0] < HEALTH_EVERY_S:
        return
    _health_last[0] = now
    try:
        HEALTH_DIR.mkdir(parents=True, exist_ok=True)
        day = (hb.get("t") or "")[:10] or datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%d")
        f = HEALTH_DIR / f"health-{day}.csv"
        new = not f.exists()
        with open(f, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(HEALTH_COLS)
            w.writerow([hb.get(c, "") for c in HEALTH_COLS])
    except Exception as exc:
        print(f"  health append failed (ignored): {exc}", flush=True)

_lock = threading.Lock()
_seen: dict = {}    # day-file name -> set of record start-time ISO strings
_fh: dict = {}      # day-file name -> open append handle


def _dayfile(h) -> str:
    t = h.starttime
    return (f"{h.network}.{h.station}.{h.location}.{h.channel}.D."
            f"{t.year}.{t.timetuple().tm_yday:03d}.mseed")


def _load_seen(fn: str) -> set:
    """Rebuild the start-time set for an existing day-file (restart safety)."""
    seen = set()
    p = ARCHIVE / fn
    if p.exists():
        with open(p, "rb") as fh:
            for rec in simplemseed.readMiniseed2Records(fh):
                seen.add(rec.header.starttime.isoformat())
    return seen


def _handle_record(rec_bytes: bytes) -> bool:
    """Append one 512B record if unseen. Thread-safe. Returns True if newly written."""
    rec = simplemseed.unpackMiniseedRecord(rec_bytes)
    fn = _dayfile(rec.header)
    key = rec.header.starttime.isoformat()
    with _lock:
        if fn not in _seen:
            _seen[fn] = _load_seen(fn)
        if key in _seen[fn]:
            return False
        if fn not in _fh:
            _fh[fn] = open(ARCHIVE / fn, "ab")
        _fh[fn].write(rec_bytes)
        _fh[fn].flush()
        _seen[fn].add(key)
        return True


# --- heartbeat (sec 6) -------------------------------------------------------------

def _heartbeat_listener() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((BIND, HB_PORT))
    print(f"heartbeat listener on {BIND}:{HB_PORT}", flush=True)
    n = 0
    last = None
    while True:
        try:
            data, _ = sock.recvfrom(65535)
            hb = json.loads(data.decode())
        except Exception:
            continue
        n += 1
        now = time.monotonic()
        if last is not None and now - last > 5.0:      # liveness: a gap in the pulse
            print(f"  heartbeat resumed after {now - last:.1f}s gap", flush=True)
        last = now
        try:                                           # publish for downstream /v1/health
            tmp = f"{STATION_HEALTH}.tmp"
            Path(tmp).write_text(json.dumps(hb))
            os.replace(tmp, STATION_HEALTH)
        except Exception:
            pass
        _append_health(hb)
        if n % 60 == 0:
            print(f"  heartbeat #{n} hi_seq={hb.get('hi_seq')} rate={hb.get('rate')} "
                  f"udp_sent={hb.get('udp_sent')}", flush=True)


# --- backfill (sec 14.4) -----------------------------------------------------------

_SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]


def _recent_station_files(n: int = 2) -> list:
    """The station's n newest local day-files (*.mseed excludes *.epoch/*.bak)."""
    try:
        out = subprocess.run(
            _SSH + [STATION_HOST, f"ls -t {STATION_DATA}/*.mseed 2>/dev/null | head -{n}"],
            capture_output=True, text=True, timeout=40)
        return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def _backfill_once(tag: str = "") -> int:
    """Pull the station's recent day-files and merge any records missing locally."""
    total = 0
    for remote in _recent_station_files():
        name = os.path.basename(remote)
        tmp = f"/tmp/backfill_{name}"
        try:
            r = subprocess.run(
                ["rsync", "-az", "--timeout=40",
                 "-e", "ssh -o BatchMode=yes -o ConnectTimeout=15",
                 f"{STATION_HOST}:{remote}", tmp],
                capture_output=True, timeout=180)
            if r.returncode != 0:
                continue
            added = 0
            with open(tmp, "rb") as fh:
                for rec in simplemseed.readMiniseed2Records(fh):
                    if _handle_record(rec.pack()):
                        added += 1
            total += added
            if added:
                print(f"  backfill{tag} {name}: +{added} records", flush=True)
        except Exception as exc:
            print(f"  backfill{tag} {name}: {exc}", flush=True)
    return total


def _backfill_periodic() -> None:
    while True:
        time.sleep(BACKFILL_S)
        _backfill_once(" periodic")


# --- data ingest -------------------------------------------------------------------

def main() -> None:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((BIND, PORT))
    print(f"udp_collector listening on {BIND}:{PORT} -> {ARCHIVE}", flush=True)

    threading.Thread(target=_heartbeat_listener, daemon=True).start()
    # startup backfill runs in a thread so live data is never missed while it pulls
    threading.Thread(target=lambda: print(f"startup backfill: +{_backfill_once(' startup')} records",
                                          flush=True), daemon=True).start()
    threading.Thread(target=_backfill_periodic, daemon=True).start()

    pkts = writ = dup = bad = gaps = 0
    last_seq = None
    while True:
        try:
            data, _ = sock.recvfrom(65535)
        except Exception:
            continue
        if len(data) < HDR.size or data[:2] != MAGIC:
            bad += 1
            continue
        _, _ver, nrec, seq = HDR.unpack(data[:HDR.size])
        if last_seq is not None:
            d = (seq - last_seq) & 0xFFFFFFFF
            if 1 < d < 1000:                 # a jump => datagrams lost (seq is a hint only)
                gaps += d - 1
        last_seq = seq
        payload = data[HDR.size:]
        for off in range(0, nrec * RECLEN, RECLEN):
            chunk = payload[off:off + RECLEN]
            if len(chunk) < RECLEN:
                break
            try:
                if _handle_record(chunk):
                    writ += 1
                else:
                    dup += 1
            except Exception:
                bad += 1
        pkts += 1
        if pkts % 60 == 0:
            print(f"  pkts {pkts} written {writ} dup {dup} bad {bad} seq_gaps {gaps}",
                  flush=True)


if __name__ == "__main__":
    main()

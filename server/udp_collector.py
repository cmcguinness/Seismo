#!/usr/bin/env python3
"""udp_collector.py -- pi5 ingest: receive the station's UDP record stream and build
the OWNED miniSEED archive (rev2-data-plane.md sec 1/3/14).

Phase-1 step 1: runs ALONGSIDE the existing rsync mirror (nothing retired). Each
datagram is  MAGIC 'SZ' | ver | n_records | seq(u32) | N x 512B record  (sec 14.1).
Records are deduped by (day-file, record start-time) -- the N=2 sliding window sends
every record twice -- and appended to day-files under SEISMO_ARCHIVE. Restart-safe:
the seen-set for a day is rebuilt by scanning that day-file on first touch.

Best-effort ingest: a malformed datagram is dropped, never fatal. seq is only a
loss HINT here (dedup/gap truth is record start-time); real gap-fill is sec 14.4
backfill, added in Phase-1 step 2.
"""
import os
import socket
import struct
from pathlib import Path

import simplemseed

MAGIC = b"SZ"
RECLEN = 512
HDR = struct.Struct("!2sBBI")   # magic, version, n_records, seq
ARCHIVE = Path(os.environ.get("SEISMO_ARCHIVE", str(Path.home() / "seismo-archive")))
PORT = int(os.environ.get("SEISMO_UDP_PORT", "48317"))
BIND = os.environ.get("SEISMO_UDP_BIND", "0.0.0.0")

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
    """Append one 512B record if unseen. Returns True if newly written."""
    rec = simplemseed.unpackMiniseedRecord(rec_bytes)
    fn = _dayfile(rec.header)
    key = rec.header.starttime.isoformat()
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


def main() -> None:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((BIND, PORT))
    print(f"udp_collector listening on {BIND}:{PORT} -> {ARCHIVE}", flush=True)
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

#!/usr/bin/env python3
"""recorder.py — continuous seismic recorder: geophone -> rolling miniSEED.

Reads the differential geophone channel and writes miniSEED day-files to
DATA_DIR, ready for a helicorder / ObsPy / SeisComP. Uses simplemseed (pure
Python, numpy-only) rather than ObsPy: this is a lean 24/7 ACQUISITION daemon
on a 1 GB Pi 2B, and ObsPy's scipy/matplotlib weight belongs on the analysis
side (run that on the Mac against the files this produces).

RAW ADC counts are stored (miniSEED convention); volts-per-count and the
geophone response live in station metadata, applied at analysis time.

Format details (learned the hard way):
  - int32 encoding (code 3), uncompressed. ~19 MB/day at 56 sps -- fine on the
    9 GB free here; STEIM2 compression is a later optimisation.
  - 512-byte records hold ~114 int32 samples, so each block is chunked into
    100-sample records.
  - miniSEED2 stores rate as integer factor x mult, and simplemseed's auto-calc
    is broken -> we pass sampRateFactor/sampRateMult explicitly (integer rate).

Timing: the read path can't hold the DRATE nominal exactly (per-sample SYNC),
so we MEASURE the true rate at startup, declare the rounded integer, and
re-anchor every block to the wall clock (NTP-kept UTC). Absolute time stays
accurate; the <0.03 % rate error is a few-ms per-block sliver that never
accumulates. (A crystal-exact rate would need ADS1256 RDATAC mode -- later.)

Config via environment (all optional):
  SEISMO_STATION/NETWORK/LOCATION/CHANNEL   SEED id   default AM.OAKMT.00.SHZ
  SEISMO_GAIN     PGA gain                  default 64
  SEISMO_DRATE    ADS1256 data rate (sps)   default 60
  SEISMO_DATADIR  output directory          default ~/seismo/data
  SEISMO_BLOCK    seconds per flush         default 10

Ctrl-C / SIGTERM flushes the partial block and releases the ADC cleanly.
"""
import datetime
import os
import queue
import signal
import threading
from pathlib import Path

import numpy as np
from simplemseed import MiniseedHeader, MiniseedRecord

from adc_common import DIFF, measure_rate, open_ads

STATION = os.environ.get("SEISMO_STATION", "OAKMT")
NETWORK = os.environ.get("SEISMO_NETWORK", "AM")
LOCATION = os.environ.get("SEISMO_LOCATION", "00")
CHANNEL = os.environ.get("SEISMO_CHANNEL", "SHZ")
GAIN = int(os.environ.get("SEISMO_GAIN", "64"))
DRATE = int(os.environ.get("SEISMO_DRATE", "60"))
DATADIR = Path(os.environ.get("SEISMO_DATADIR", str(Path.home() / "seismo" / "data")))
BLOCK_S = int(os.environ.get("SEISMO_BLOCK", "10"))

SPR = 100                        # samples per 512-byte int32 record (<=114 fits)
ENC_INT32 = 3

_stop = threading.Event()
_q: queue.Queue = queue.Queue(maxsize=64)


def _write_records(fh, samples, start, rate):
    """Chunk one block into 100-sample int32 records, appending to fh."""
    for i in range(0, len(samples), SPR):
        chunk = np.asarray(samples[i:i + SPR], dtype=np.int32)
        t = start + datetime.timedelta(seconds=i / rate)
        hdr = MiniseedHeader(NETWORK, STATION, LOCATION, CHANNEL, t, len(chunk),
                             rate, encoding=ENC_INT32,
                             sampRateFactor=rate, sampRateMult=1)
        fh.write(MiniseedRecord(hdr, chunk).pack())


def writer(rate: int) -> None:
    """Consume (samples, starttime) blocks and append to UTC day-files."""
    while True:
        item = _q.get()
        if item is None:
            break
        samples, start = item
        fn = (f"{NETWORK}.{STATION}.{LOCATION}.{CHANNEL}.D."
              f"{start.year}.{start.timetuple().tm_yday:03d}.mseed")
        with open(DATADIR / fn, "ab") as fh:      # append -> growing day-file
            _write_records(fh, samples, start, rate)


def main() -> None:
    DATADIR.mkdir(parents=True, exist_ok=True)

    def stop(*_):
        _stop.set()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    ads = open_ads(GAIN, DRATE)
    wt = None
    try:
        fs = measure_rate(ads)                    # true rate; also primes cyclic read
        rate = max(1, round(fs))                  # integer rate for miniSEED2 fields
        block_n = max(1, round(fs * BLOCK_S))
        wt = threading.Thread(target=writer, args=(rate,), daemon=True)
        wt.start()
        print(f"recording {NETWORK}.{STATION}.{LOCATION}.{CHANNEL}  "
              f"{fs:.2f} sps -> declared {rate}, gain {GAIN}")
        print(f"  -> {DATADIR}  ({BLOCK_S}s blocks, {block_n} samples each)")
        print("Ctrl-C to stop.")

        buf = [0]
        block: list[int] = []
        start = datetime.datetime.now(datetime.timezone.utc)
        nblocks = 0
        while not _stop.is_set():
            block.append(ads.read_continue([DIFF], buf)[0])
            if len(block) >= block_n:
                _q.put((block, start))
                nblocks += 1
                block = []
                start = datetime.datetime.now(datetime.timezone.utc)
                if nblocks % 6 == 0:              # ~once/min at 10s blocks
                    print(f"  {nblocks} blocks written", flush=True)
        if block:                                 # flush partial block on stop
            _q.put((block, start))
    finally:
        if wt is not None:
            _q.put(None)                           # sentinel -> writer drains + exits
            wt.join(timeout=5)
        ads.stop_close_all()
        print(f"\nstopped. wrote to {DATADIR}")


if __name__ == "__main__":
    main()

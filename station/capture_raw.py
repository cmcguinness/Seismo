#!/usr/bin/env python3
"""capture_raw.py — grab N seconds of raw differential samples at a chosen data
rate, for diagnostics like the aliasing test (does a spectral line move when the
sample rate changes?). Saves raw counts + the measured rate to an .npz.

STOP the recorder service first -- it owns the ADC:
    sudo systemctl stop seismo-recorder

    python capture_raw.py <drate_sps> <seconds> <outfile.npz>
    e.g. python capture_raw.py 60 90 /tmp/cap60.npz
"""
import sys
import time

import numpy as np

from adc_common import DIFF, open_ads

drate = int(sys.argv[1])
secs = float(sys.argv[2])
out = sys.argv[3]

ads = open_ads(64, drate)
try:
    buf = [0]
    ads.read_oneshot(DIFF)                       # prime cyclic read
    samples = []
    t0 = time.time()
    while time.time() - t0 < secs:
        samples.append(ads.read_continue([DIFF], buf)[0])
    dt = time.time() - t0
    fs = len(samples) / dt
    np.savez(out, counts=np.array(samples, dtype=np.int32), fs=fs, drate=drate)
    print(f"captured {len(samples)} samples in {dt:.1f}s -> fs={fs:.3f} sps, saved {out}")
finally:
    ads.stop_close_all()

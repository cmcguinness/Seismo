#!/usr/bin/env python3
"""rdatac_noise_test.py — why is RDATAC ~10% noisier? Test the candidates.

RDATAC costs a flat ~0.057 uV/rtHz versus the legacy per-sample-SYNC path (derived
from robust band RMS in two bands, both implying the same density -- so it is an
INJECTED white source, not a change in the converter's averaging). Candidates:

  A  baseline      current implementation: CS held low, SPI 976 kHz
  B  cs-toggle     REFUTED BY EXPERIMENT, kept for the record: releasing CS between
                   reads aborts the RDATAC stream (measured: 3737/3737 samples came
                   back as all-zero frames). CS must stay asserted in continuous mode,
                   so "CS held low" is not an adjustable suspect.
  C  spi-fast      SPI at 1.95 MHz -- halves the burst duration, so if the coupling is
                   SCLK activity during the conversion window this should reduce it
  D  legacy        PiPyADC read_continue for reference, same session/conditions

Runs each for --seconds and reports the median of per-10 s band RMS (median, not
mean: single-sample glitches would otherwise dominate -- that mistake cost an hour).
Band powers come from numpy rfft, so the Pi needs no scipy/obspy.

Requires the recorder stopped:
    sudo systemctl stop seismo-recorder
    python rdatac_noise_test.py --seconds 150
    sudo systemctl start seismo-recorder
"""
import argparse
import time

import numpy as np

import waveshare_config
from adc_common import DIFF


def band_rms(x, fs, lo, hi):
    """RMS within [lo,hi] Hz via Parseval on the rfft -- no scipy needed."""
    x = np.asarray(x, float)
    x = x - x.mean()
    n = x.size
    f = np.fft.rfftfreq(n, 1 / fs)
    p = np.abs(np.fft.rfft(x)) ** 2
    sel = (f >= lo) & (f <= hi)
    # Parseval: sum(|X|^2)*2/n^2 over the selected one-sided bins
    return float(np.sqrt(2 * p[sel].sum() / n ** 2))


def robust_bands(counts, fs, uv):
    out = {}
    n = int(10 * fs)
    if n <= 0 or len(counts) <= n:
        return {(1, 15): float("nan"), (3, 15): float("nan"), (15, 28): float("nan")}
    for lo, hi in ((1, 15), (3, 15), (15, min(28, fs / 2 * 0.95))):
        vals = [band_rms(counts[i:i + n], fs, lo, hi) * uv
                for i in range(0, len(counts) - n, n)]
        out[(lo, round(hi))] = (float(np.median(vals)) if vals else float("nan"))
    return out


def run_case(case, seconds, gain, drate):
    """One configuration -> (counts array, achieved fs, notes)."""
    import importlib

    import adc_common
    importlib.reload(waveshare_config)          # fresh config per case
    if case == "spi-fast":
        waveshare_config.SPI_FREQUENCY = 1953125
    importlib.reload(adc_common)
    from rdatac import RdatacReader

    ads = adc_common.open_ads(gain, drate)
    got = []
    try:
        if case == "legacy":
            buf = [0]
            ads.read_oneshot(DIFF)
            t0 = time.time()
            while time.time() - t0 < seconds:
                got.append(ads.read_continue([DIFF], buf)[0])
            fs = len(got) / (time.time() - t0)
        else:
            reader = RdatacReader(ads, DIFF)
            if case == "cs-toggle":
                reader.hold_cs = False          # must be set BEFORE start()
            reader.start()
            t0 = time.time()
            glitches = 0
            while time.time() - t0 < seconds:
                v, _ = reader.read()
                if v is None:
                    glitches += 1
                    continue
                got.append(v)
            fs = len(got) / (time.time() - t0)
            reader.stop()
            print(f"    ({glitches} glitches filtered)")
    finally:
        ads.stop_close_all()
    return np.array(got, dtype=np.int64), fs


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=float, default=150)
    p.add_argument("--gain", type=int, default=64)
    p.add_argument("--drate", type=int, default=60)
    p.add_argument("--cases", default="baseline,spi-fast,legacy")
    a = p.parse_args()
    uv = 2.5 * 2 / (a.gain * (2 ** 23 - 1)) * 1e6

    print(f"{a.seconds:.0f}s per case, gain {a.gain}, DRATE {a.drate}\n")
    rows = []
    for case in a.cases.split(","):
        print(f"  running {case} ...", flush=True)
        counts, fs = run_case(case, a.seconds, a.gain, a.drate)
        if counts.size < int(30 * fs):
            print(f"    too few samples ({counts.size})")
            continue
        b = robust_bands(counts, fs, uv)
        rows.append((case, fs, counts.size, b))
        time.sleep(2)

    print(f"\n{'case':12s} {'fs':>8s} {'n':>7s} " +
          "  ".join(f"{lo}-{hi}Hz" for lo, hi in rows[0][3]) if rows else "")
    for case, fs, n, b in rows:
        print(f"{case:12s} {fs:8.3f} {n:7d} " +
              "  ".join(f"{v:8.4f}" for v in b.values()))
    print("\n(median of per-10s band RMS, uV)")

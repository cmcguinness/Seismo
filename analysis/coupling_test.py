#!/usr/bin/env python3
"""coupling_test.py — did taking the geophone off the plastic floor tile change anything?

On 2026-07-31 13:40 PDT the geophone was moved off the garage's plastic
interlocking tile and set directly on the concrete slab (BACKLOG "⚠️ COUPLING").
The prediction: if the ~19.95 / 40.97 Hz line pair is the hollow tile ringing,
it should shift or vanish; if the tile was also absorbing ground motion, the
in-band floor / cultural signals should come up.

Compares matched clock windows so time-of-day noise doesn't masquerade as the
effect: quiet night 20:00-22:00 PDT after vs the same window the night before,
plus midday before-the-move vs afternoon after-the-move on the same day.

  analysis/.venv/bin/python coupling_test.py            # uses local data/
  analysis/.venv/bin/python coupling_test.py --pull
"""
import argparse
from pathlib import Path

import numpy as np
import obspy
from scipy import signal
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from helicorder import LOCAL_DATA, load_day, pull
from spectrum import UV_PER_COUNT

OUT = Path(__file__).resolve().parent / "coupling_test.png"

# (label, day-file julian, UTC start, UTC end).  PDT = UTC-7.
#
# The usable post-move data is ONLY 14:20-16:35 PDT on Jul 31: the move is at
# 13:40 (+ ~35 min settling, [[settling-time-after-handling]]) and an unrelated
# front-end fault lands at 16:41 and never clears (see break_1641.py). Anything
# after 16:41 is instrument, not ground. So both "before" windows are matched to
# that same 14:20-16:35 clock slot -- same day (tile, 3 h earlier) and previous
# day (tile, same hour), which brackets drift and time-of-day noise.
WINDOWS = [
    ("before  Jul 30 14:20-16:35 (tile, same hour)", "2026.211", "2026-07-30T21:20:00", "2026-07-30T23:35:00"),
    ("before  Jul 31 11:00-13:15 (tile, same day)",  "2026.212", "2026-07-31T18:00:00", "2026-07-31T20:15:00"),
    ("after   Jul 31 14:20-16:35 (SLAB)",            "2026.212", "2026-07-31T21:20:00", "2026-07-31T23:35:00"),
]

BANDS = [("0.02-0.12 Hz", 0.02, 0.12), ("1-15 Hz", 1, 15),
         ("18-22 Hz", 18, 22), ("38-44 Hz", 38, 44)]


def asd_of(julian: str, t0: str, t1: str, nperseg: int):
    """Welch ASD in uV/sqrt(Hz) over one clock window (MEDIAN-averaged).

    Median averaging across Welch segments, not mean: a single loud minute in a
    135 min window (the 14:44 PDT transient) otherwise dominates the whole
    spectrum and paints an impulsive event as a raised broadband floor.

    The day-files are fragmented into ~10 s blocks separated by 20-30 ms
    (2-3 sample) gaps from the recorder's per-block wall-clock anchoring, so
    "longest gapless segment" is only ever ~10 s here. Bridge those gaps by
    interpolation -- 3 samples in 1000, far too little to bias a PSD below
    50 Hz -- and analyse the whole window.
    """
    st = load_day(LOCAL_DATA / f"XX.OAKMT.00.SHZ.D.{julian}.mseed")
    st = st.slice(obspy.UTCDateTime(t0), obspy.UTCDateTime(t1))
    if not len(st):
        return None
    st.merge(method=1, fill_value="interpolate")
    tr = max(st, key=lambda t: t.stats.npts)
    tr.detrend("demean")
    x = tr.data.astype(float) * UV_PER_COUNT
    fs = tr.stats.sampling_rate
    f, pxx = signal.welch(x, fs=fs, nperseg=min(nperseg, len(x)), average="median")
    return f, np.sqrt(pxx), tr.stats.npts / fs / 60.0, x, fs


def band_rms(f, asd, lo, hi):
    """RMS in a band = sqrt(integral of the PSD) -- ASD is sqrt(PSD)."""
    m = (f >= lo) & (f <= hi)
    return np.sqrt(np.trapezoid(asd[m] ** 2, f[m])) if m.sum() > 1 else float("nan")


def band_rms_median(x, fs, lo, hi, win_s=300):
    """Median of the per-5-min band RMS -- the honest ambient level.

    A whole-window Welch RMS is dominated by whatever single loud minute the
    window happens to contain (one 82 uV transient at 14:44 made the post-move
    1-15 Hz band look 3.8x worse than pre-move when the ambient floor was in
    fact unchanged). The median across 5-min blocks ignores that.
    """
    sos = signal.butter(4, [lo, hi], btype="band", fs=fs, output="sos")
    y = signal.sosfiltfilt(sos, x - x.mean())
    w = int(win_s * fs)
    blocks = [y[i * w:(i + 1) * w].std() for i in range(len(y) // w)]
    return float(np.median(blocks)) if blocks else float("nan")


def peak_near(f, asd, lo, hi):
    m = (f >= lo) & (f <= hi)
    i = np.argmax(asd[m])
    return f[m][i], asd[m][i]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--host", default="seismo.local")
    ap.add_argument("--nperseg", type=int, default=8192)
    args = ap.parse_args()
    if args.pull:
        pull(args.host)

    results = []
    for label, julian, t0, t1 in WINDOWS:
        r = asd_of(julian, t0, t1, args.nperseg)
        if r is None:
            print(f"{label}: NO DATA in window")
            continue
        f, asd, mins, x, fs = r
        results.append((label, f, asd))
        print(f"\n{label}   [{mins:.0f} min]")
        for name, lo, hi in BANDS:
            print(f"    {name:>12s} RMS {band_rms(f, asd, lo, hi):8.3f} uV   "
                  f"median-5min {band_rms_median(x, fs, lo, hi):7.3f} uV")
        for lo, hi in ((19.0, 21.0), (39.5, 42.5)):
            pf, pa = peak_near(f, asd, lo, hi)
            print(f"    peak {lo:g}-{hi:g} Hz at {pf:7.3f} Hz  {pa:7.4f} uV/rtHz")

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    colors = ["#888888", "#1f77b4", "#c0a000", "#d62728"]
    for (label, f, asd), c in zip(results, colors):
        style = "--" if label.startswith("before") else "-"
        for ax in axes:
            ax.loglog(f, asd, style, color=c, lw=1.2, label=label)
    axes[0].set_xlim(0.02, 50)
    axes[1].set_xlim(15, 50)
    axes[1].set_xscale("linear")
    for lo, hi in ((19.0, 21.0), (39.5, 42.5)):
        axes[1].axvspan(lo, hi, color="k", alpha=0.05)
    for ax in axes:
        ax.set_xlabel("frequency (Hz)")
        ax.set_ylabel(r"ASD ($\mu$V/$\sqrt{Hz}$)")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
    axes[0].set_title("full band")
    axes[1].set_title("tile-resonance suspects: 19.95 / 40.97 Hz")
    fig.suptitle("Coupling test — geophone moved off plastic tile onto slab, 2026-07-31 13:40 PDT")
    fig.tight_layout()
    fig.savefig(OUT, dpi=110)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""spectrum.py — power spectral density + spectrogram of the station data.

Runs on the Mac. Reuses helicorder.py's data pull, then computes a Welch
amplitude spectral density (ASD) and a spectrogram from the longest continuous
segment. Plotted in instrument-native uV/sqrt(Hz): honest without deconvolving
the geophone response, and every feature (the 4.5 Hz resonance, cultural tones,
the electronic floor) is visible regardless of units.

  python spectrum.py                 # pull latest, PSD of newest day-file
  python spectrum.py --no-pull       # use local copy
  python spectrum.py --date 2026.201
  python spectrum.py --nperseg 4096  # finer frequency resolution

Needs the analysis venv:  analysis/.venv/bin/python spectrum.py
"""
import argparse
import subprocess

import numpy as np
from scipy import signal
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from helicorder import LOCAL_DATA, load_day, pick_file, pull

# ADS1256 at gain 64, Vref 2.5: volts per count -> microvolts per count.
UV_PER_COUNT = (2.5 * 2 / (64 * (2 ** 23 - 1))) * 1e6      # ~0.00931 uV/count
SENS_V_PER_MS = 28.8                                        # geophone, flat band (>4.5 Hz)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="seismo.local")
    ap.add_argument("--date")
    ap.add_argument("--no-pull", action="store_true")
    ap.add_argument("--nperseg", type=int, default=2048)
    ap.add_argument("--latest", action="store_true",
                    help="use the most RECENT segment (current conditions) "
                         "instead of the longest")
    args = ap.parse_args()

    if not args.no_pull:
        pull(args.host)

    st = load_day(pick_file(args.date))    # read + normalize mixed rates + merge + split
    st.detrend("demean")
    if args.latest:
        tr = max(st, key=lambda t: t.stats.starttime)   # most recent segment
    else:
        tr = max(st, key=lambda t: t.stats.npts)        # longest continuous segment
    fs = tr.stats.sampling_rate
    x = tr.data.astype(float) * UV_PER_COUNT     # microvolts
    mins = tr.stats.npts / fs / 60.0
    print(f"{tr.id}  {fs:g} sps  longest segment {mins:.1f} min ({tr.stats.npts} samples)")

    nper = min(args.nperseg, len(x))
    f, pxx = signal.welch(x, fs=fs, nperseg=nper)
    asd = np.sqrt(pxx)                            # uV / sqrt(Hz)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 9))

    ax1.loglog(f[1:], asd[1:], "k", lw=0.8)
    ax1.axvline(4.5, color="r", ls="--", lw=1, label="4.5 Hz geophone corner")
    ax1.set_xlim(f[1], fs / 2)
    ax1.set_xlabel("frequency (Hz)")
    ax1.set_ylabel("amplitude spectral density (µV/√Hz)")
    ax1.set_title(f"{tr.id}   Welch ASD   ({mins:.1f} min @ {fs:g} sps, gain 64)")
    ax1.grid(True, which="both", alpha=0.3)
    ax1.legend()
    # secondary axis: ground velocity (valid only in the flat band above 4.5 Hz)
    sec = ax1.secondary_yaxis(
        "right",
        functions=(lambda uv: uv / SENS_V_PER_MS * 1e3,     # µV/√Hz -> (nm/s)/√Hz
                   lambda nv: nv * SENS_V_PER_MS / 1e3),
    )
    sec.set_ylabel("≈ ground velocity (nm/s/√Hz), flat band only")

    f2, t2, sxx = signal.spectrogram(x, fs=fs, nperseg=512, noverlap=384)
    m = ax2.pcolormesh(t2 / 60, f2, 10 * np.log10(sxx + 1e-12),
                       shading="gouraud", cmap="viridis")
    ax2.axhline(4.5, color="r", ls="--", lw=1)
    ax2.set_ylim(0, fs / 2)
    ax2.set_xlabel("time (min)")
    ax2.set_ylabel("frequency (Hz)")
    ax2.set_title("spectrogram (dB re µV²/Hz)")
    fig.colorbar(m, ax=ax2, label="dB")

    fig.tight_layout()
    out = LOCAL_DATA.parent / "spectrum.png"
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")
    subprocess.run(["open", "-a", "Preview", str(out)], check=False)   # view in Preview


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""microseism_specgram.py — the sub-Hz spectrogram with the buoy's 2/DPD drawn on it.

A band-RMS correlation (buoy_join.py) cannot tell a microseism from a 10 % wobble of
the electronics floor. A spectrogram can: the secondary microseism is a RIDGE at
twice the swell frequency, and if that ridge slides up and down the frequency axis in
step with NDBC 46013's dominant period, it is the ocean; if the spectrum is a flat
f^-2 floor with nothing riding on it, it is the amplifier.

Per 15-min interval: decimate 100 -> 10 sps, median-Welch (300 s segments), keep
0.03-2 Hz. Plots log10 PSD (counts^2/Hz) vs time, overlaid with 2/DPD (cyan) and
2/APD (white) from the buoy, night hours shaded. Also prints, per interval, the
frequency of the PSD maximum inside 0.1-0.8 Hz after removing the f^-2 trend -- the
ridge tracker -- and its Spearman correlation with 2/DPD.

    python analysis/microseism_specgram.py [first_jday] [last_jday]
Needs the day-files in analysis/data (eventcheck's pull leaves them there).
"""
import datetime as dt
import glob
import os
import sys

import numpy as np
import obspy
from scipy import signal, stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from buoy_join import load_ndbc, to_grid, S, HERE  # noqa: E402

INTERVAL_S = 900
TARGET_SPS = 10.0
FMIN, FMAX = 0.03, 2.0
RIDGE = (0.1, 0.8)
PDT = -7


def interval_psds(files):
    times, psds, freqs = [], [], None
    for path in files:
        st = obspy.read(path)
        st.merge(method=1, fill_value="interpolate")
        for tr in st:
            if tr.stats.sampling_rate < 50:
                continue
            tr.detrend("linear")
            fac = int(round(tr.stats.sampling_rate / TARGET_SPS))
            for f in (5, 2, 2):
                while fac % f == 0 and fac > 1:
                    tr.decimate(f, no_filter=False)
                    fac //= f
            fs = float(tr.stats.sampling_rate)
            t_start = tr.stats.starttime.timestamp
            data = tr.data.astype(np.float64)
            t0 = np.ceil(t_start / INTERVAL_S) * INTERVAL_S
            nper = int(fs * 300)
            while t0 + INTERVAL_S <= t_start + len(data) / fs:
                i0 = int(round((t0 - t_start) * fs))
                seg = data[i0:i0 + int(INTERVAL_S * fs)]
                if len(seg) >= nper * 2:
                    f, pxx = signal.welch(seg, fs=fs, nperseg=nper, noverlap=nper // 2,
                                          average="median", detrend="linear")
                    sel = (f >= FMIN) & (f <= FMAX)
                    if freqs is None:
                        freqs = f[sel]
                    times.append(t0)
                    psds.append(pxx[sel])
                t0 += INTERVAL_S
        print(f"  {os.path.basename(path)}: {len(times)} intervals", flush=True)
    return np.array(times), freqs, np.array(psds)


def ridge_freq(freqs, psd):
    """peak of the PSD inside RIDGE after dividing out a power-law fit to the whole
    0.03-2 Hz spectrum (the f^-2 floor), so a hump shows even on a steep slope."""
    lf, lp = np.log10(freqs), np.log10(psd)
    a, b = np.polyfit(lf, lp, 1)
    resid = lp - (a * lf + b)
    sel = (freqs >= RIDGE[0]) & (freqs <= RIDGE[1])
    i = np.argmax(resid[sel])
    return freqs[sel][i], resid[sel][i]


def main():
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 224
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    files = sorted(f for f in glob.glob(os.path.join(S, "*.mseed"))
                   if first <= int(f.split(".")[-2]) <= last)
    t, freqs, P = interval_psds(files)
    np.savez(os.path.join(S, "microseism_specgram.npz"), t=t, f=freqs, P=P)

    bt, hs, dpd, apd, pres = load_ndbc(os.path.join(S, "ndbc_46013.txt"))
    DPD = to_grid(bt, dpd, t)
    APD = to_grid(bt, apd, t)
    Hs = to_grid(bt, hs, t)

    rf = np.array([ridge_freq(freqs, p)[0] for p in P])
    rh = np.array([ridge_freq(freqs, p)[1] for p in P])
    hour_local = (t / 3600.0 + PDT) % 24
    night = (hour_local >= 0) & (hour_local < 5)
    ok = np.isfinite(DPD)
    for name, m in (("ALL", ok), ("NIGHT", ok & night)):
        r, p = stats.spearmanr(rf[m], 2.0 / DPD[m])
        r2, p2 = stats.spearmanr(rf[m], 2.0 / APD[m])
        print(f"[{name}] n={m.sum()}  ridge f vs 2/DPD rho {r:+.2f} (p {p:.2g});"
              f"  vs 2/APD rho {r2:+.2f} (p {p2:.2g});"
              f"  ridge height median {np.median(rh[m]):.2f} dex")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tt = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc) for x in t])
    fig, ax = plt.subplots(3, 1, figsize=(14, 11), sharex=True,
                           gridspec_kw=dict(height_ratios=[3, 1.2, 1]))
    L = np.log10(P).T
    vmin, vmax = np.percentile(L, [5, 99])
    im = ax[0].pcolormesh(tt, freqs, L, shading="nearest", cmap="magma",
                          vmin=vmin, vmax=vmax)
    ax[0].set_yscale("log"); ax[0].set_ylim(FMIN, FMAX)
    ax[0].plot(tt, 2.0 / DPD, "c-", lw=1.2, label="2/DPD (buoy dominant)")
    ax[0].plot(tt, 2.0 / APD, "w-", lw=0.8, alpha=0.8, label="2/APD (buoy average)")
    ax[0].axhline(4.5, color="0.5", lw=0.5)
    ax[0].set_ylabel("Hz"); ax[0].legend(loc="upper right", fontsize=8)
    ax[0].set_title("OAKMT median-Welch PSD per 15 min (log10 counts$^2$/Hz), "
                    "with Bodega Bay 46013 twice-swell-frequency overlaid")
    fig.colorbar(im, ax=ax[0], pad=0.01)
    ax[1].plot(tt, rf, "k.", ms=2, label="ridge: PSD peak in 0.1-0.8 Hz after f^-2 removal")
    ax[1].plot(tt, 2.0 / DPD, "c-", lw=1)
    ax[1].set_yscale("log"); ax[1].set_ylim(0.08, 1.0); ax[1].set_ylabel("Hz")
    ax[1].legend(loc="upper right", fontsize=8)
    ax[2].plot(tt, Hs, "k-", lw=1); ax[2].set_ylabel("Hs  m")
    for a in ax:
        a.grid(alpha=0.25)
        for i in range(len(tt)):
            pass
    # night shading
    for a in ax:
        d = tt[0].replace(hour=0, minute=0, second=0)
        while d < tt[-1]:
            n0 = d + dt.timedelta(hours=7); n1 = n0 + dt.timedelta(hours=5)
            a.axvspan(n0, n1, color="k", alpha=0.06, lw=0)
            d += dt.timedelta(days=1)
    fig.autofmt_xdate(); fig.tight_layout()
    out = os.path.join(HERE, "microseism_specgram.png")
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

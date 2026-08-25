#!/usr/bin/env python3
"""microseism_relative.py — the sub-Hz spectrogram DIVIDED BY its time-median.

The raw sub-Hz spectrogram (microseism_specgram.py) is a comb of fixed spectral lines
(0.05, 0.1, 0.2, 0.25, 0.5, 1.0 Hz ...) bright enough to hide anything under them.
Whatever they are, they do not move in time -- so dividing every interval's PSD by the
median PSD at that frequency across the whole run removes them exactly and leaves
only what CHANGES: a microseism ridge sliding with the buoy's 2/DPD, diurnal noise,
events. Reads the npz that microseism_specgram.py saved.

    python analysis/microseism_relative.py
"""
import datetime as dt
import os

import numpy as np
from scipy import stats

from buoy_join import load_ndbc, to_grid, S, HERE

RIDGE = (0.1, 0.6)
PDT = -7


def main():
    z = np.load(os.path.join(S, "microseism_specgram.npz"))
    t, f, P = z["t"], z["f"], z["P"]
    hour_local = (t / 3600.0 + PDT) % 24
    night = (hour_local >= 0) & (hour_local < 5)
    # normalise by the NIGHT median so daytime cultural noise shows as excess too
    ref = np.median(P[night], axis=0)
    R = np.log10(P / ref)                                  # dex above the quiet floor

    bt, hs, dpd, apd, pres = load_ndbc(os.path.join(S, "ndbc_46013.txt"))
    DPD = to_grid(bt, dpd, t); APD = to_grid(bt, apd, t); Hs = to_grid(bt, hs, t)
    fm = 2.0 / DPD

    # ridge tracker on the RELATIVE spectrum, smoothed 3 bins
    sel = (f >= RIDGE[0]) & (f <= RIDGE[1])
    Rs = np.apply_along_axis(lambda r: np.convolve(r, np.ones(3) / 3, "same"), 1, R)
    rf = f[sel][np.argmax(Rs[:, sel], axis=1)]
    rh = Rs[:, sel].max(axis=1)
    # excess AT the buoy-predicted frequency (+-15 %) vs the band's median excess
    at_pred = np.full(len(t), np.nan)
    for i in range(len(t)):
        if np.isfinite(fm[i]):
            w = (f >= fm[i] * 0.85) & (f <= fm[i] * 1.15)
            if w.sum():
                at_pred[i] = np.median(R[i, w]) - np.median(R[i, sel])

    ok = np.isfinite(DPD)
    for name, m in (("ALL", ok), ("NIGHT", ok & night)):
        r1, p1 = stats.spearmanr(rf[m], fm[m])
        r2, p2 = stats.spearmanr(rh[m], Hs[m] ** 2)
        r3, p3 = stats.spearmanr(at_pred[m], Hs[m] ** 2)
        print(f"[{name}] n={m.sum()}  ridge f vs 2/DPD rho {r1:+.2f} (p {p1:.2g}) | "
              f"ridge height vs Hs^2 rho {r2:+.2f} (p {p2:.2g}) | "
              f"excess at 2/DPD vs Hs^2 rho {r3:+.2f} (p {p3:.2g}); "
              f"median ridge height {np.median(rh[m]):+.2f} dex, "
              f"median excess at 2/DPD {np.nanmedian(at_pred[m]):+.3f} dex")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tt = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc) for x in t])
    fig, ax = plt.subplots(3, 1, figsize=(14, 11), sharex=True,
                           gridspec_kw=dict(height_ratios=[3, 1.2, 1]))
    im = ax[0].pcolormesh(tt, f, R.T, shading="nearest", cmap="RdBu_r", vmin=-0.5, vmax=0.5)
    ax[0].set_yscale("log"); ax[0].set_ylim(f.min(), f.max())
    ax[0].plot(tt, fm, "k-", lw=1.2, label="2/DPD (buoy dominant)")
    ax[0].plot(tt, 2.0 / APD, "g-", lw=0.8, alpha=0.8, label="2/APD (buoy average)")
    ax[0].set_ylabel("Hz"); ax[0].legend(loc="upper right", fontsize=8)
    ax[0].set_title("OAKMT sub-Hz PSD relative to the night-median floor (dex; red = excess), "
                    "Bodega 46013 twice-swell-frequency in black")
    fig.colorbar(im, ax=ax[0], pad=0.01)
    ax[1].plot(tt, rf, "k.", ms=2, label="ridge: peak of relative PSD in 0.1-0.6 Hz")
    ax[1].plot(tt, fm, "c-", lw=1, label="2/DPD")
    ax[1].set_yscale("log"); ax[1].set_ylim(0.08, 0.7); ax[1].set_ylabel("Hz")
    ax[1].legend(loc="upper right", fontsize=8)
    ax[2].plot(tt, Hs, "k-", lw=1); ax[2].set_ylabel("Hs  m")
    a2 = ax[2].twinx(); a2.plot(tt, at_pred, "r.", ms=2); a2.set_ylabel("excess at 2/DPD  dex", color="r")
    for a in ax:
        a.grid(alpha=0.25)
        d = tt[0].replace(hour=0, minute=0, second=0)
        while d < tt[-1]:
            n0 = d + dt.timedelta(hours=7); n1 = n0 + dt.timedelta(hours=5)
            a.axvspan(n0, n1, color="k", alpha=0.06, lw=0)
            d += dt.timedelta(days=1)
    fig.autofmt_xdate(); fig.tight_layout()
    out = os.path.join(HERE, "microseism_relative.png")
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""refstation_delay.py — does NP.1835 hear the P wave later than geometry says?

THE OBSERVATION (2026-09-03, the M3.5 under Larkfield-Wikiup, 12 km). Our first break
was +2.21 s after origin, 1835's +2.81 s: a lag of 0.60 s. The two stations are 1.64 km
apart and nearly in line with that epicentre, so the path difference is at most 1.64 km
and, for a source 7 km down, less: geometry allows about 0.25 s at Vp 5.19 km/s. The
other 0.35 s has to come from somewhere. The candidate is the ground under 1835: it sits
on the Santa Rosa plain (Qoa/Qhb alluvium, proxy Vs30 290-540 m/s per the ANSS site
compilation), we sit on a slab at the foot of the hills. A few hundred metres of slow
sediment costs a P wave a quarter of a second that bedrock does not.

ONE EVENT IS AN ANECDOTE. This measures the same thing on every confirmed event where
both stations have a clean onset, and asks whether the excess over geometry is
(a) consistent, which would make it a STATION DELAY TERM for 1835 relative to us, or
(b) azimuth-dependent, which would make it path. Either is a number the site-response
people at the NSMP would recognise.

METHOD. catch_picks.py's picker, run identically on both stations: a CAUSAL 1-15 Hz
band-pass (a zero-phase filter smears energy backwards and puts the pick early), the
arrival taken as the loudest thing in a window around each station's OWN predicted P, and
an AIC picker walking back from that peak to where noise ends and signal begins. A first
version used a threshold crossing instead and was worthless: 9 usable events of 35, and
two picks a full phase away. Both peaks must clear MIN_SNR x their own pre-event floor.

Geometric lag = harvest tp x (hypo_1835 / hypo_ours - 1), from the catalogue epicentre
(refstation_compare.ref_arrival_scale). Excess = measured lag - geometric lag.

    analysis/.venv/bin/python analysis/refstation_delay.py            # every usable event
    analysis/.venv/bin/python analysis/refstation_delay.py --k 20     # stricter threshold

Writes doc/refstation-delay.png and doc/refstation-delay.json. Reference waveforms are
raw HNZ counts cached under analysis/data/refcache/ (gitignored).
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from refstation import REF                                                     # noqa: E402
from refstation_compare import CSV, harvest_row, our_trace, ref_arrival_scale  # noqa: E402
from refstation_spectra import CACHE, usable_origins                           # noqa: E402

PNG_OUT = os.path.join(os.path.dirname(HERE), "doc", "refstation-delay.png")
JSON_OUT = os.path.join(os.path.dirname(HERE), "doc", "refstation-delay.json")

BAND = (1.0, 15.0)            # catch_picks.py's band
SEARCH = (-4.0, 4.0)          # seconds around the predicted P to look for the onset
NOISE = (-30.0, -6.0)         # pre-event floor window, relative to predicted P
MIN_SNR = 5.0                 # both peaks must reach this many floors, or the event is skipped

TEAL, INK, RED, BLUE, MUT = "#2f6f6b", "#16211f", "#c0392b", "#2c6e9b", "#6b7775"


def cached_raw_reference(o, t0, t1):
    """Raw 1835 HNZ counts (no response removal: onsets want a causal chain only)."""
    from obspy import read
    from obspy.clients.fdsn import Client
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{'.'.join(REF)}.{str(o)[:19].replace(':', '')}.raw.mseed")
    if os.path.exists(path):
        return read(path)[0]
    st = Client("NCEDC", timeout=60).get_waveforms(REF[0], REF[1], "*", REF[2], t0, t1)
    st.merge(fill_value="interpolate")
    tr = st[0]
    tr.data = tr.data.astype(np.float64)
    tr.write(path, format="MSEED", encoding="FLOAT64")
    return tr


def onset(tr, o, tp, k):
    """(onset_s_after_origin or None, snr): catch_picks.py's picker, so the two stations
    are measured the same way. Causal 1-15 Hz band-pass; the arrival is the LOUDEST thing
    in the search window around the predicted P (an earthquake inside a window centred on
    its own arrival needs no threshold); an AIC picker then finds where the noise ends and
    the signal begins, bracketing back from that peak. `k` is the minimum peak/floor."""
    from scipy import signal
    tr = tr.copy().detrend("demean")
    fs = float(tr.stats.sampling_rate)
    sos = signal.butter(4, [BAND[0] / (fs / 2), BAND[1] / (fs / 2)], "bandpass", output="sos")
    y = signal.sosfilt(sos, tr.data.astype(float))            # CAUSAL: no precursor
    w = max(1, int(0.3 * fs))
    env = np.convolve(np.abs(y), np.ones(w) / w, mode="same")
    t = tr.times(reftime=o)
    nm = (t >= tp + NOISE[0]) & (t < tp + NOISE[1])
    if nm.sum() < fs * 5:
        return None, 0.0
    floor = float(np.median(env[nm])) or 1e-9
    sm = np.flatnonzero((t >= tp + SEARCH[0]) & (t <= tp + SEARCH[1]))
    if not sm.size:
        return None, 0.0
    coarse = int(sm[int(np.argmax(env[sm]))])
    snr = float(env[coarse] / floor)
    if snr < k:
        return None, snr
    a0, a1 = max(0, coarse - int(4.0 * fs)), min(len(y), coarse + int(0.5 * fs))
    seg = y[a0:a1]
    n = len(seg)
    if n < 40:
        return None, snr
    aic = np.full(n, np.inf)
    for j in range(5, n - 5):
        v1, v2 = np.var(seg[:j]), np.var(seg[j:])
        if v1 > 0 and v2 > 0:
            aic[j] = j * np.log(v1) + (n - j - 1) * np.log(v2)
    return float(t[a0 + int(np.argmin(aic))]), snr


def one_event(origin, row, k):
    from obspy import UTCDateTime
    o = UTCDateTime(origin)
    tp = float(row["tp_s"])
    t0, t1 = o + tp + NOISE[0] - 5, o + tp + SEARCH[1] + 5
    ref = cached_raw_reference(o, t0, t1)
    mine = our_trace(o, t0, t1)
    scale = ref_arrival_scale(origin, float(row.get("depth_km") or 0))
    ours, snr_m = onset(mine, o, tp, k)
    theirs, snr_r = onset(ref, o, tp * (scale or 1.0), k)
    out = dict(origin=origin, mag=float(row["mag"]), place=row["place"],
               dist_km=float(row["dist_km"]), az_deg=float(row.get("az_deg") or "nan"),
               tp_pred=tp, our_onset=ours, ref_onset=theirs, snr_our=snr_m, snr_ref=snr_r,
               geom_scale=scale)
    if ours is None or theirs is None or scale is None or min(snr_m, snr_r) < MIN_SNR:
        out["usable"] = False
        return out
    out["usable"] = True
    out["lag_meas"] = theirs - ours
    out["lag_geom"] = tp * (scale - 1.0)
    out["excess"] = out["lag_meas"] - out["lag_geom"]
    out["our_resid"] = ours - tp
    return out


def figure(rows, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ex = np.array([r["excess"] for r in rows])
    az = np.array([r["az_deg"] for r in rows])
    di = np.array([r["dist_km"] for r in rows])
    mg = np.array([r["mag"] for r in rows])
    med, mad = float(np.median(ex)), float(np.median(np.abs(ex - np.median(ex))))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for ax, xv, xl in ((axes[0], az, "back-azimuth from OAKM1 (°)"),
                       (axes[1], di, "hypocentral distance (km)")):
        ax.axhline(0, color=MUT, lw=0.8, ls=":")
        ax.axhline(med, color=RED, lw=1.0, ls="--", label=f"median {med:+.2f} s (MAD {mad:.2f})")
        ax.scatter(xv, ex, s=18 + 12 * (mg - mg.min()) ** 2, c=TEAL, alpha=0.8, edgecolor="none")
        ax.set_xlabel(xl, color=INK)
        ax.grid(alpha=0.25)
    axes[1].set_xscale("log")
    # One wrong pick (a phase away) should not set the axis for eighteen right ones:
    # show +/-1 s and count what falls outside, rather than hiding it.
    off = int(np.sum(np.abs(ex) > 1.0))
    axes[0].set_ylim(-1.0, 1.0)
    if off:
        axes[0].text(0.99, 0.03, f"{off} off-scale (|excess| > 1 s), kept in the median",
                     transform=axes[0].transAxes, ha="right", va="bottom", fontsize=8.5, color=MUT)
    axes[0].set_ylabel("1835 onset lag beyond geometry (s)", color=INK)
    axes[0].legend(loc="upper left", fontsize=9, frameon=False)
    fig.suptitle(f"Does NP.1835 hear P later than geometry says?  {len(rows)} events with a "
                 f"clean first break at both stations", fontsize=12, color=INK)
    fig.text(0.5, 0.005, "lag = 1835 onset − OAKM1 onset (causal 1–15 Hz, AIC pick); "
             "geometry = harvest P × (hypo₁₈₃₅ / hypo_OAKM1 − 1); dot size ∝ magnitude",
             ha="center", fontsize=8.5, color=MUT)
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=150)
    return med, mad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=float, default=MIN_SNR, help="minimum peak / pre-event floor at BOTH stations")
    ap.add_argument("--out", default=PNG_OUT)
    args = ap.parse_args()
    rows = []
    for origin, _ in usable_origins():
        row = harvest_row(origin)
        if row is None:
            print(f"{origin}: not in {os.path.basename(CSV)}"); continue
        try:
            r = one_event(origin, row, args.k)
        except Exception as e:
            print(f"{origin}: skipped: {type(e).__name__}: {str(e)[:80]}"); continue
        rows.append(r)
        tag = (f"lag {r['lag_meas']:+.2f}  geom {r['lag_geom']:+.2f}  EXCESS {r['excess']:+.2f} s"
               if r["usable"] else
               f"unusable (onsets {r['our_onset']}, {r['ref_onset']}; snr {r['snr_our']:.0f}/{r['snr_ref']:.0f})")
        print(f"M{r['mag']:.1f} {r['dist_km']:5.1f} km az {r['az_deg']:5.1f}  {origin[:19]}  {tag}")
    good = [r for r in rows if r["usable"]]
    if not good:
        sys.exit("no usable events")
    med, mad = figure(good, args.out)
    ex = np.array([r["excess"] for r in good])
    print(f"\n{len(good)} usable of {len(rows)}: 1835 excess over geometry median {med:+.3f} s, "
          f"MAD {mad:.3f}, mean {ex.mean():+.3f} ± {ex.std(ddof=1)/np.sqrt(len(ex)):.3f} (s.e.)")
    ours = np.array([r["our_resid"] for r in good])
    print(f"our own first break vs harvest prediction: median {np.median(ours):+.2f} s")
    with open(JSON_OUT, "w") as fh:
        json.dump(dict(k=args.k, n_usable=len(good), n_total=len(rows),
                       excess_median_s=med, excess_mad_s=mad, events=rows), fh, indent=1)
    print(f"wrote {args.out} and {JSON_OUT}")


if __name__ == "__main__":
    main()

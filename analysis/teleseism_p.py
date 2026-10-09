#!/usr/bin/env python3
"""teleseism_p.py — did a distant (teleseismic) earthquake's P wave reach us?

The first teleseism this station recorded was the M7.7 Panama earthquake of
2026-10-09, at 5,409 km. Before it, STATUS-ARCHIVE said teleseisms were "structurally
impossible" here, on the evidence of one M5.5 at 4,438 km. That half of the claim
still stands: the surface waves (20–50 s period) arrive ~87 dB down the geophone's
f² roll-off and nothing can recover them. What the M5.5 did not test is a quake big
enough to push ~0.5–1.6 Hz P energy through. At 1 Hz the 4.5 Hz element is only ~20×
down, so a large enough P wave can clear the floor -- provided our own 1.04 Hz
electronics line, which sits in the middle of that band, is notched out (see P_BAND).

**Method.** The question is whether energy rises at the predicted P time, so every
number is a RATIO to the same station's own pre-event level. That way it needs no
calibration and works the same on our counts and on the reference's m/s.

1. P/PcP/PP/S times from iasp91 (`obspy.taup`). `eventcheck.py`'s local Vp fit is for
   crustal paths and means nothing at 50°.
2. Band-pass (and notch the 1.04 Hz line), then RMS in 10 s steps relative to the pre-event level, which is the
   MEDIAN of 30 s windows over P−600…P−30 s. Use a median, not one window: a single
   quiet minute inflates the ratio (the 2026-09-08 `snr` lesson).
3. Null distribution: the same P+30…P+90 s statistic, computed every 2 min across
   the whole day-file, skipping ±1 h around the event. If the observed value sits
   past every null window, the rise is not ordinary daytime variation.
4. A reference station (default BK.HOPS, a broadband 60 km north) gets the same
   treatment. A matching onset and envelope rules out a coincidental local source,
   such as a truck passing the garage at the wrong moment.

    analysis/.venv/bin/python analysis/teleseism_p.py --origin 2026-10-09T17:56:06 \
        --lat 7.587 --lon -80.769 --depth 12.6 --mag 7.7 \
        --label "12 km WSW of Pitaloza Arriba, Panama"

Origin time is UTC (the USGS page's UTC line). Times are NOT converted from local the
way eventcheck.py does it. Pull the day-file from pi5 first
(`rsync pi5:seismo-data/data/<file> analysis/data/`). It assumes the P arrival and
its 10 min lead-in fall inside one UTC day-file.
"""
import argparse
import warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from obspy import UTCDateTime, read
from obspy.clients.fdsn import Client
from obspy.geodetics import gps2dist_azimuth, kilometers2degrees
from obspy.taup import TauPyModel

from eventcheck import STA_LAT, STA_LON
from helicorder import day_path

warnings.filterwarnings("ignore", message="Inconsistent word order")

REPORTS = Path(__file__).resolve().parent.parent / "reports"
REF = ("BK", "HOPS", "00", "HHZ")
REF_CLIENT = "NCEDC"
# The P band, with our 1.04 Hz electronics line notched out of it. The line is ~680x the
# 0.4-1.5 Hz median in the Panama pre-event window, so without the notch it IS the noise
# floor in any band that contains it: 1-2 Hz read 1.09x (nothing) unnotched and the same
# P read 2.33x in 1.15-2 Hz. Chosen AFTER looking at the Panama event (0.5-1 Hz plain was
# the first look, at 1.68x), so treat it as fitted to n=1 until a second teleseism tests it.
P_BAND = (0.5, 1.6)
LINE_NOTCH = (0.98, 1.10)
BAND_LABEL = f"{P_BAND[0]}–{P_BAND[1]} Hz, {LINE_NOTCH[0]}–{LINE_NOTCH[1]} notched"
TABLE_BANDS = [(0.05, 0.1), (0.2, 0.5), (0.5, 1.0), (1.0, 2.0), (1.15, 2.0), (2.0, 5.0),
               (5.0, 15.0)]   # plain band-passes; the notched P band is the last row
STEP = 10.0                  # envelope step, s
NULL_EVERY = 120.0           # null-distribution stride, s
NULL_EXCLUDE = 3600.0        # keep the null this far from the event, s


class Ratios:
    """RMS of a band-passed trace, relative to a median pre-event level."""

    def __init__(self, tr, band, notch=None):
        t = tr.copy()
        t.detrend("demean")
        t.taper(0.05, max_length=30)   # 1% of a day-file is 14 min: would shrink early pre-event levels
        t.filter("bandpass", freqmin=band[0], freqmax=band[1], corners=4, zerophase=True)
        if notch:
            t.filter("bandstop", freqmin=notch[0], freqmax=notch[1], corners=4, zerophase=True)
        self.x = t.data.astype(float)
        self.t0 = t.stats.starttime
        self.sr = t.stats.sampling_rate

    def rms(self, a, b):
        i = max(0, int((a - self.t0) * self.sr))
        j = int((b - self.t0) * self.sr)
        s = self.x[i:j]
        # median of squares, like the pre-event level: robust to one-sample spikes
        return np.sqrt(np.median(s ** 2)) if len(s) else np.nan

    def pre(self, p):
        return np.median([self.rms(p - 600 + k * 30, p - 570 + k * 30) for k in range(19)])

    def ratio(self, a, b, p):
        return self.rms(a, b) / self.pre(p)

    def envelope(self, p, lead=60, span=300):
        pre = self.pre(p)
        starts = np.arange(-lead, span, STEP)
        return starts, np.array([self.rms(p + s, p + s + STEP) / pre for s in starts])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", required=True, help="UTC origin time, ISO")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--depth", type=float, required=True, help="km")
    ap.add_argument("--mag", type=float, required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", help="PNG path (default reports/teleseism-<date>-m<mag>.png)")
    ap.add_argument("--no-ref", action="store_true", help="skip the reference station")
    a = ap.parse_args()

    o = UTCDateTime(a.origin)
    m, _, _ = gps2dist_azimuth(STA_LAT, STA_LON, a.lat, a.lon)
    km = m / 1e3
    deg = kilometers2degrees(km)
    phases = {}
    for arr in TauPyModel("iasp91").get_travel_times(a.depth, deg, ["P", "PcP", "PP", "S", "SS"]):
        phases.setdefault(arr.name, o + arr.time)   # first arrival of each
    P = phases["P"]
    print(f"M{a.mag} {a.label}: {km:,.0f} km, {deg:.1f}°")
    for k, v in phases.items():
        print(f"  {k:4s} {v}  (P{v - P:+.0f} s)")

    st = read(str(day_path(P.strftime("%Y.%j"))))
    st.merge(fill_value="interpolate")       # ~10 s fragments; see analysis-window notes
    ours = st[0]
    print(f"  {ours.id}  {ours.stats.starttime} – {ours.stats.endtime}")

    ref = None
    if not a.no_ref:
        try:
            c = Client(REF_CLIENT, timeout=90)
            rs = c.get_waveforms(*REF, P - 700, P + 1800, attach_response=True)
            rs.merge(fill_value="interpolate")
            rs.remove_response(output="VEL")
            ref = rs[0]
        except Exception as e:   # the verdict on OUR data stands without it
            print(f"  reference {'.'.join(REF)} unavailable: {e}")

    # --- band table: where (if anywhere) did energy arrive? ---
    S = phases.get("S", P + 400)
    surf = (S + 300, S + 900)   # crude surface-wave window
    windows = [("P0–30", P - 5, P + 25), ("P30–90", P + 25, P + 85), ("surf", *surf)]
    print("\n  ratio to pre-event (median of 30 s windows, P−600…P−30)")
    print(f"  {'band Hz':>10s}  " + "  ".join(f"{'ours ' + w[0]:>12s}" for w in windows)
          + ("  " + "  ".join(f"{'ref ' + w[0]:>12s}" for w in windows) if ref else ""))
    for b, notch in [(b, None) for b in TABLE_BANDS] + [(P_BAND, LINE_NOTCH)]:
        row = [Ratios(ours, b, notch).ratio(w1, w2, P) for _, w1, w2 in windows]
        if ref is not None:
            rr = Ratios(ref, b, notch)
            row += [rr.ratio(w1, w2, P) for _, w1, w2 in windows]
        print(f"  {b[0]:>4}–{b[1]:<5}{'n' if notch else ' '} " + "  ".join(f"{v:12.2f}" for v in row))
    print("  (n = with the 1.04 Hz line notched out)")

    # --- the detection test, in the P band ---
    R = Ratios(ours, P_BAND, LINE_NOTCH)
    obs = R.ratio(P + 25, P + 85, P)
    null = []
    t = ours.stats.starttime + 620
    while t < ours.stats.endtime - 90:
        if abs(t - P) > NULL_EXCLUDE:
            null.append(R.ratio(t + 25, t + 85, t))
        t += NULL_EVERY
    null = np.array(null)
    n_ge = int((null >= obs).sum())
    print(f"\n  {BAND_LABEL}, P+25…P+85 s: {obs:.2f}× pre-event; "
          f"null n={len(null)}, p95 {np.percentile(null, 95):.2f}, "
          f"p99 {np.percentile(null, 99):.2f}, max {null.max():.2f}, {n_ge} ≥ observed")

    starts, env = R.envelope(P)
    corr = None
    if ref is not None:
        rstarts, renv = Ratios(ref, P_BAND, LINE_NOTCH).envelope(P)
        corr = np.corrcoef(env, renv)[0, 1]
        print(f"  10 s envelope correlation with {ref.id}, P−60…P+300: {corr:.2f}")

    # --- figure ---
    # The top two panels share one time axis, in minutes after the ORIGIN, so the
    # 8-odd minutes the wave spent crossing the mantle are visible as the flat stretch
    # between the earthquake line and the P line.
    tp = (P - o) / 60                       # P travel time, minutes
    xlo, xhi = -1.0, tp + 300 / 60
    fig = plt.figure(figsize=(11, 10))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.1, 1.1, 0.9])
    ax0 = fig.add_subplot(gs[0])
    ax1 = fig.add_subplot(gs[1], sharex=ax0)
    axes = [ax0, ax1, fig.add_subplot(gs[2])]
    fig.suptitle(f"M{a.mag} {a.label} — {o.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                 f"{km:,.0f} km ({deg:.1f}°) from {ours.id}: teleseismic P, {BAND_LABEL}", fontsize=12)

    def mark_times(ax, labels):
        ax.axvline(0, color="k", lw=1.4)
        for k, v in phases.items():
            x = (v - o) / 60
            if xlo <= x <= xhi:
                ax.axvline(x, color="C3" if k == "P" else "C1", lw=1, ls="--")
                if labels:
                    ax.text(x + 0.05, 0.97, k, color="C3" if k == "P" else "C1",
                            transform=ax.get_xaxis_transform(), va="top")

    ax = axes[0]
    tr = ours.copy().slice(o - 300, P + 400)
    tr.detrend("demean")
    tr.taper(0.05, max_length=30)
    tr.filter("bandpass", freqmin=P_BAND[0], freqmax=P_BAND[1], corners=4, zerophase=True)
    tr.filter("bandstop", freqmin=LINE_NOTCH[0], freqmax=LINE_NOTCH[1], corners=4, zerophase=True)
    tm = tr.times(reftime=o) / 60
    keep = (tm >= xlo) & (tm <= xhi)
    ax.plot(tm[keep], tr.data[keep], lw=0.35, color="0.15")
    mark_times(ax, labels=True)
    ax.text(0.05, 0.97, f"earthquake\n{o.strftime('%H:%M:%S')} UTC", transform=ax.get_xaxis_transform(),
            va="top", fontsize=9)
    ymax = np.abs(tr.data[keep]).max()
    ax.set_ylim(-1.45 * ymax, 1.45 * ymax)
    ax.annotate("", xy=(tp, -1.25 * ymax), xytext=(0, -1.25 * ymax),
                arrowprops=dict(arrowstyle="<->", color="0.3", lw=1))
    m_, s_ = divmod(round(P - o), 60)
    ax.text(tp / 2, -1.22 * ymax, f"{m_} min {s_} s for P to cross {km:,.0f} km of mantle "
            f"(arrives {P.strftime('%H:%M:%S')} UTC)", ha="center", va="bottom", fontsize=9, color="0.3")
    ax.set_ylabel(f"{ours.stats.station}, counts\n{BAND_LABEL}")
    ax.set_title("Our trace, band-passed with the 1.04 Hz line notched out. Nothing until P; "
                 "the panels below test what arrives", fontsize=9, loc="left")
    ax.tick_params(labelbottom=False)

    ax = axes[1]
    lead = STEP * np.ceil(((P - o) - xlo * 60) / STEP)   # keep the 10 s bins on the P grid
    pstarts, penv = R.envelope(P, lead=lead, span=300)
    mid = (P - o + pstarts + STEP / 2) / 60
    ax.step(mid, penv, where="mid", color="C0", lw=1.6, label=f"{ours.stats.station} (ours)")
    if ref is not None:
        _, prenv = Ratios(ref, P_BAND, LINE_NOTCH).envelope(P, lead=lead, span=300)
        ax.step(mid, prenv, where="mid", color="C2", lw=1.2,
                label=f"{ref.stats.network}.{ref.stats.station} broadband, 60 km N"
                      + (f"  (envelope r = {corr:.2f})" if corr is not None else ""))
    ax.axhline(1, color="0.5", lw=0.8)
    ax.axhline(np.percentile(null, 99), color="C0", lw=0.8, ls=":",
               label=f"our 99th-percentile null ({np.percentile(null, 99):.2f}×)")
    mark_times(ax, labels=False)
    ax.set_yscale("log")
    ax.set_xlim(xlo, xhi)
    ax.set_ylabel("10 s RMS ÷ pre-event")
    ax.set_xlabel("minutes after the earthquake (P, PcP, PP predicted by iasp91)")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title("Both stations rise in the same 10 s and fall back together. The "
                 "reference sees it several times more strongly", fontsize=9, loc="left")

    ax = axes[2]
    ax.hist(null, bins=40, color="0.6", label=f"every {NULL_EVERY / 60:.0f} min that day, "
            f"±{NULL_EXCLUDE / 3600:.0f} h excluded (n={len(null)})")
    ax.axvline(obs, color="C3", lw=2, label=f"at P: {obs:.2f}×  ({n_ge} null windows ≥)")
    ax.set_xlabel(f"P+25…P+85 s RMS ÷ pre-event, {BAND_LABEL}")
    ax.set_ylabel("windows")
    ax.legend(fontsize=8)
    ax.set_title("Null distribution: the same statistic at times when no P wave was "
                 "due", fontsize=9, loc="left")

    fig.tight_layout()
    out = Path(a.out) if a.out else REPORTS / f"teleseism-{o.strftime('%Y-%m-%d')}-m{a.mag}.png"
    fig.savefig(out, dpi=130)
    print(f"\n  wrote {out}")


if __name__ == "__main__":
    main()

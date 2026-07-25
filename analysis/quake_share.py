#!/usr/bin/env python3
"""quake_share.py — render a shareable, labeled hero image of an earthquake this
station recorded. Reusable across events: pass the catalog facts, get a social-
media-ready PNG of the actual waveform with P/S/peak annotations and the S–P
distance story.

Runs on the Mac against the analysis venv (obspy + matplotlib):
    analysis/.venv/bin/python analysis/quake_share.py --mseed <day.mseed> \\
        --origin 2026-07-25T11:31:41 --mag 2.5 \\
        --place "3 km E of St. Helena, California" \\
        --event-lat 38.507 --event-lon -122.435 --depth-km 6.2 \\
        --p 2.0 --s 4.4 --out eq_sthelena.png

Phase picks: --p/--s are the P and S onsets in SECONDS AFTER ORIGIN, eyeballed
off the trace. Pass ONLY the ones you can actually see. The tool draws just those and
does NOT predict arrivals from the catalog distance -- predicting P/S from a distance
and then "deriving" that distance back from them confirms nothing (it is circular).
The S-P bracket appears only when BOTH picks are given. For a small emergent local
event the P is usually buried in noise (not pickable), so typically pass only --s; the
distance shown is then the catalog's, not something we claim to have measured. Peak
amplitude is always measured. Distance is computed from the station and event
coordinates (haversine + depth); --dist-km overrides.

The day-file for an event can be pulled from the station, e.g.:
    scp seismo.local:'~/seismo/data/XX.OAKMT.00.SHZ.D.YYYY.JJJ.mseed' .
"""
import argparse
import math

import numpy as np
import obspy
from obspy import UTCDateTime

# --- station + model defaults (override via CLI) -----------------------------
STA_LAT, STA_LON = 38.435, -122.630          # Oakmont, Santa Rosa
STA_LABEL = "Charles McGuinness - Personal Seismometer, Santa Rosa, CA"
VP, VS = 6.0, 3.46                            # crustal velocities, km/s (Vp/Vs≈1.73)
SP_TO_KM = VP * VS / (VP - VS)               # S–P seconds -> distance km (≈8.2)
GAIN = 64

# palette (matches the dashboard's accent)
TEAL, INK, RED, BLUE, MUT = "#2f6f6b", "#16211f", "#c0392b", "#2c6e9b", "#6b7775"
AMBER = "#d97a1e"   # smoothed-envelope overlay


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main():
    ap = argparse.ArgumentParser(description="Render a shareable earthquake image.")
    ap.add_argument("--mseed", required=True, help="miniSEED day-file covering the event")
    ap.add_argument("--origin", required=True, help="origin time, ISO UTC (e.g. 2026-07-25T11:31:41)")
    ap.add_argument("--mag", type=float, required=True)
    ap.add_argument("--place", required=True, help='e.g. "3 km E of St. Helena, California"')
    ap.add_argument("--source", default="USGS",
                    help="catalog attribution for the mag/location/origin line")
    ap.add_argument("--event-lat", type=float, default=None)
    ap.add_argument("--event-lon", type=float, default=None)
    ap.add_argument("--depth-km", type=float, default=None)
    ap.add_argument("--dist-km", type=float, default=None, help="epicentral distance override")
    ap.add_argument("--p", type=float, default=None, help="P onset, s after origin (eyeballed)")
    ap.add_argument("--s", type=float, default=None, help="S onset, s after origin (eyeballed)")
    ap.add_argument("--expect-s", action="store_true",
                    help="overlay the catalog-PREDICTED S arrival (hypo/Vs) as a clearly-"
                         "labelled reference line -- honest because it's flagged as a prediction")
    ap.add_argument("--envelope", action="store_true",
                    help="overlay the smoothed amplitude envelope (Hilbert), which makes the "
                         "P hump -> dip -> S/coda hump shape legible at a glance")
    ap.add_argument("--env-smooth", type=float, default=1.0,
                    help="envelope smoothing window in seconds (default 1.0)")
    ap.add_argument("--gain", type=int, default=GAIN)
    ap.add_argument("--sta-lat", type=float, default=STA_LAT)
    ap.add_argument("--sta-lon", type=float, default=STA_LON)
    ap.add_argument("--sta-label", default=STA_LABEL)
    ap.add_argument("--title", default="Earthquake Report")
    ap.add_argument("--pre", type=float, default=8.0, help="seconds of trace before origin")
    ap.add_argument("--post", type=float, default=38.0, help="seconds of trace after origin")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, MultipleLocator

    origin = UTCDateTime(args.origin)
    origin_disp = origin.strftime("%Y-%m-%d %H:%M:%S")     # keep sub-second precision if given
    if origin.microsecond:
        origin_disp += ("." + f"{origin.microsecond // 1000:03d}").rstrip("0")
    st = obspy.read(args.mseed, starttime=origin - args.pre, endtime=origin + args.post)
    if not len(st):
        raise SystemExit(f"no data in {args.mseed} around {args.origin}")
    st.merge(method=1)
    tr = st[0]
    fs = float(tr.stats.sampling_rate)
    uvpc = 2.5 * 2 / (args.gain * (2 ** 23 - 1)) * 1e6
    tr.detrend("demean").filter("bandpass", freqmin=1.0,
                                freqmax=min(15.0, fs / 2 * 0.99), corners=4, zerophase=True)
    uv = tr.data * uvpc
    t = tr.times(reftime=origin)
    ipk = int(np.argmax(np.abs(uv)))
    tpk, pk = t[ipk], uv[ipk]

    # distance
    epi = args.dist_km
    if epi is None and args.event_lat is not None and args.event_lon is not None:
        epi = haversine_km(args.sta_lat, args.sta_lon, args.event_lat, args.event_lon)
    hypo = None
    if epi is not None:
        hypo = math.hypot(epi, args.depth_km) if args.depth_km else epi

    # phase picks: ONLY what was explicitly measured off the trace. Deliberately no
    # predicting arrivals from the catalog distance -- a graphic that predicts P/S from
    # a distance and then "derives" that distance back from them confirms nothing.
    p_t, s_t = args.p, args.s

    # --- figure ---
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#d5dbda"})
    fig = plt.figure(figsize=(12.0, 6.75), dpi=140)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.075, 0.155, 0.885, 0.60])
    ax.set_facecolor("white")
    ax.plot(t, uv, color=INK, lw=0.7)
    if args.envelope:                                # smoothed Hilbert envelope (the "shape")
        from obspy.signal.filter import envelope as _envelope
        env = _envelope(uv)
        w = max(3, int(args.env_smooth * fs))
        win = np.hanning(w)
        env_s = np.convolve(env, win / win.sum(), mode="same")
        ax.plot(t, env_s, color=AMBER, lw=2.4, alpha=0.9, solid_capstyle="round",
                label="amplitude envelope")
    ax.axvline(0, color=MUT, ls=":", lw=1.1)
    ylim = max(abs(uv)) * 1.18
    ax.set_ylim(-ylim, ylim)
    ax.set_xlim(t[0], t[-1])
    ax.text(0, ylim * 0.98, " origin", color=MUT, fontsize=9, va="top")

    for tt, lab, col in [(p_t, "P", BLUE), (s_t, "S", RED)]:
        if tt is None:
            continue
        ax.axvline(tt, color=col, ls="--", lw=1.2, alpha=0.85)
        ax.text(tt, ylim * 0.90, f" {lab}", color=col, fontsize=15, fontweight="bold", va="top")
    if p_t is not None and s_t is not None:          # S-P bracket only with BOTH picks
        yb = ylim * 0.66
        ax.annotate("", xy=(p_t, yb), xytext=(s_t, yb),
                    arrowprops=dict(arrowstyle="<->", color=TEAL, lw=1.4))
        ax.text((p_t + s_t) / 2, yb + ylim * 0.05, f"S–P ≈ {s_t - p_t:.1f} s",
                color=TEAL, fontsize=11.5, ha="center", fontweight="bold")
    if args.expect_s and hypo is not None:           # catalog-PREDICTED S, flagged as such
        s_exp = hypo / VS
        ax.axvline(s_exp, color=RED, ls=":", lw=1.6, alpha=0.55)
        ax.text(s_exp, ylim * 0.90, " S expected", color=RED, fontsize=10.5,
                alpha=0.85, va="top", fontstyle="italic")

    ax.annotate(f"peak ≈ {abs(pk):.0f} µV", xy=(tpk, pk),
                xytext=(tpk + 4.5, pk * 0.72), color=TEAL, fontsize=11.5, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=TEAL, lw=1.1, alpha=0.7))
    ax.set_xlabel(f"seconds after origin time  ({origin_disp} UTC)",
                  fontsize=11, color="#3a4744")
    ax.set_ylabel("ground motion  (µV, 1–15 Hz)", fontsize=11, color="#3a4744")
    ax.tick_params(colors="#3a4744", labelsize=9)
    # x ticks: every 1 s, elongated at 5 s multiples, labelled only at 10 s
    ax.xaxis.set_minor_locator(MultipleLocator(1))
    ax.xaxis.set_major_locator(MultipleLocator(5))
    ax.xaxis.set_major_formatter(
        FuncFormatter(lambda v, _p: f"{int(round(v))}" if round(v) % 10 == 0 else ""))
    ax.tick_params(axis="x", which="minor", length=3.5, color="#3a4744")
    ax.tick_params(axis="x", which="major", length=6.5, color="#3a4744")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#eef1f0", lw=0.8)

    # titles
    fig.text(0.075, 0.945, args.title, fontsize=25, fontweight="bold", color=TEAL)
    dist_txt = f"  ·  ~{epi:.0f} km from the epicenter" if epi else ""
    fig.text(0.075, 0.895,
             f"M {args.mag:g}  ·  {args.place}  ·  {origin_disp} UTC"
             f"  ·  source: {args.source}",
             fontsize=13.5, color=INK)
    fig.text(0.075, 0.862, f"recorded{dist_txt} at {args.sta_label}".replace("recorded  ·  ", "recorded "),
             fontsize=11.5, color=MUT)

    seed = f"{tr.stats.network}.{tr.stats.station}.{tr.stats.location}.{tr.stats.channel}"
    bits = [seed, "DIY Raspberry Pi + ADS1256 (ADC) + LGT-4.5 (Geophone)"]
    if args.depth_km:
        bits.append(f"depth {args.depth_km:g} km")
    nrms = float(np.sqrt(np.mean(uv[t < -1] ** 2))) if np.any(t < -1) else 0.0
    if nrms > 0:
        bits.append(f"SNR ≈ {abs(pk) / nrms:.0f}×")
    if args.p is not None and args.s is not None:
        est = (args.s - args.p) * SP_TO_KM
        lo, hi = est * 0.8, est * 1.2
        bits.append(f"the S–P delay alone places the source ~{lo:.0f}–{hi:.0f} km out")
    fig.text(0.075, 0.045, "  ·  ".join(bits), fontsize=9.5, color=MUT)

    out = args.out or f"eq_{origin.strftime('%Y%m%d_%H%M%S')}.png"
    fig.savefig(out, dpi=140, facecolor="white")
    print(f"saved {out}  (peak {abs(pk):.1f} µV at +{tpk:.1f}s"
          + (f", epi {epi:.1f} km, hypo {hypo:.1f} km" if epi else "") + ")")


if __name__ == "__main__":
    main()

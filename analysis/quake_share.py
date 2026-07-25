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

import specgram   # project-standard spectrogram (fixed colour scale, window, band)

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


def fetch_usgs_near(when, sta_lat, sta_lon, radius_km=500.0, min_mag=1.0):
    """Look up the catalog event near `when` (ISO, ~the station's trigger time) within
    radius_km of the station, via the USGS FDSN event API. No event id needed -- the
    trigger time is the key. Returns the matched event's fields; raises SystemExit with
    a clear message on no-match or network error. A no-match is itself informative: the
    trigger was probably cultural noise, not an earthquake."""
    import json
    import urllib.error
    import urllib.parse
    import urllib.request
    t = UTCDateTime(when)
    q = {"format": "geojson",
         "starttime": (t - 120).strftime("%Y-%m-%dT%H:%M:%S"),
         "endtime": (t + 60).strftime("%Y-%m-%dT%H:%M:%S"),
         "latitude": sta_lat, "longitude": sta_lon,
         "maxradiuskm": radius_km, "minmagnitude": min_mag, "orderby": "time"}
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query?" + urllib.parse.urlencode(q)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, ValueError, TimeoutError) as e:
        raise SystemExit(f"USGS query failed: {type(e).__name__}: {e}")
    feats = data.get("features") or []
    if not feats:
        raise SystemExit(f"no USGS event within {radius_km:g} km of the station near {when} "
                         f"(M>={min_mag:g}) -- cultural noise, or widen --usgs-radius / "
                         f"lower --usgs-minmag?")
    best = min(feats, key=lambda f: abs(f["properties"]["time"] / 1000.0 - t.timestamp))
    p, g = best["properties"], best["geometry"]["coordinates"]   # coords = [lon, lat, depth_km]
    return {"id": best["id"], "mag": round(float(p["mag"]), 1), "place": p["place"],
            "lon": float(g[0]), "lat": float(g[1]), "depth": round(float(g[2]), 1),
            "origin": UTCDateTime(p["time"] / 1000.0).isoformat()}


def main():
    ap = argparse.ArgumentParser(description="Render a shareable earthquake image.")
    ap.add_argument("--mseed", required=True, help="miniSEED day-file covering the event")
    ap.add_argument("--origin", default=None,
                    help="origin time, ISO UTC (e.g. 2026-07-25T11:31:41); or use --usgs-near")
    ap.add_argument("--mag", type=float, default=None, help="magnitude; or use --usgs-near")
    ap.add_argument("--place", default=None, help='e.g. "3 km E of St. Helena, CA"; or --usgs-near')
    ap.add_argument("--usgs-near",
                    help="fetch the event from the USGS catalog by TIME (ISO, roughly the "
                         "trigger time) -- auto-fills mag/place/lat/lon/depth/origin, no event "
                         "id or site-eyeballing needed. No match => probably cultural noise.")
    ap.add_argument("--usgs-radius", type=float, default=500.0,
                    help="--usgs-near search radius from the station, km (default 500)")
    ap.add_argument("--usgs-minmag", type=float, default=1.0,
                    help="--usgs-near minimum magnitude (default 1.0)")
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
    ap.add_argument("--envelope", action=argparse.BooleanOptionalAction, default=True,
                    help="overlay the smoothed Hilbert amplitude envelope (P hump -> dip -> "
                         "S/coda hump); ON by default, --no-envelope to hide")
    ap.add_argument("--env-smooth", type=float, default=1.0,
                    help="envelope smoothing window in seconds (default 1.0)")
    ap.add_argument("--spectrogram", action="store_true",
                    help="stack a time-frequency spectrogram panel below the waveform, in ONE "
                         "image (shows the P/S/coda frequency evolution + HF attenuation)")
    ap.add_argument("--gain", type=int, default=GAIN)
    ap.add_argument("--sta-lat", type=float, default=STA_LAT)
    ap.add_argument("--sta-lon", type=float, default=STA_LON)
    ap.add_argument("--sta-label", default=STA_LABEL)
    ap.add_argument("--title", default="Earthquake Report")
    ap.add_argument("--pre", type=float, default=8.0, help="seconds of trace before origin")
    ap.add_argument("--post", type=float, default=38.0, help="seconds of trace after origin")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.usgs_near:                               # pull catalog facts by time -- no event id
        ev = fetch_usgs_near(args.usgs_near, args.sta_lat, args.sta_lon,
                             args.usgs_radius, args.usgs_minmag)
        print(f"USGS {ev['id']}: M{ev['mag']:g}  {ev['place']}  depth {ev['depth']:g} km  "
              f"origin {ev['origin']}")
        if args.mag is None: args.mag = ev["mag"]
        if args.place is None: args.place = ev["place"]
        if args.event_lat is None: args.event_lat = ev["lat"]
        if args.event_lon is None: args.event_lon = ev["lon"]
        if args.depth_km is None: args.depth_km = ev["depth"]
        if args.origin is None: args.origin = ev["origin"]
    missing = [n for n, v in (("--origin", args.origin), ("--mag", args.mag),
                              ("--place", args.place)) if v is None]
    if missing:
        raise SystemExit(f"missing {', '.join(missing)} -- supply them or use --usgs-near <time>")

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
    uv_raw = (tr.data.astype(float) - float(tr.data.mean())) * uvpc  # full band, for the spectrogram
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
    s_exp = (hypo / VS) if (args.expect_s and hypo is not None) else None  # catalog-predicted S

    # --- figure --- (waveform alone, or waveform + spectrogram stacked in one image)
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#d5dbda"})
    if args.spectrogram:
        fig = plt.figure(figsize=(12.0, 9.0), dpi=140)
        ax = fig.add_axes([0.075, 0.46, 0.885, 0.38])                 # waveform (top)
        axsp = fig.add_axes([0.075, 0.14, 0.885, 0.28], sharex=ax)    # spectrogram (bottom)
    else:
        fig = plt.figure(figsize=(12.0, 6.75), dpi=140)
        ax = fig.add_axes([0.075, 0.155, 0.885, 0.60])
        axsp = None
    fig.patch.set_facecolor("white")
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
    if s_exp is not None:                            # catalog-PREDICTED S, flagged as such
        ax.axvline(s_exp, color=RED, ls=":", lw=1.6, alpha=0.55)
        ax.text(s_exp, ylim * 0.90, " S expected", color=RED, fontsize=10.5,
                alpha=0.85, va="top", fontstyle="italic")

    ax.annotate(f"peak ≈ {abs(pk):.0f} µV", xy=(tpk, pk),
                xytext=(tpk + 4.5, pk * 0.72), color=TEAL, fontsize=11.5, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=TEAL, lw=1.1, alpha=0.7))
    ax.set_ylabel("ground motion  (µV, 1–15 Hz)", fontsize=11, color="#3a4744")
    ax.tick_params(colors="#3a4744", labelsize=9)
    ax.grid(axis="y", color="#eef1f0", lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    # spectrogram panel (shares the time axis): shows the P/S/coda frequency evolution
    # and the high-frequency attenuation. Only the spectrogram -- not the noisy ASD.
    if axsp is not None:
        specgram.draw(axsp, uv_raw, fs, t0=t[0])     # project-standard spectrogram
        axsp.set_ylabel("frequency (Hz)", fontsize=11, color="#3a4744")
        axsp.axhline(4.5, color="#8fe9e9", ls=":", lw=1.0, alpha=0.9)
        axsp.text(t[0] + 0.4, 5.0, "4.5 Hz geophone", color="#cdefef", fontsize=8, va="bottom")
        for xt, col, ls in [(p_t, BLUE, "--"), (s_exp, RED, ":")]:
            if xt is not None:
                axsp.axvline(xt, color=col, ls=ls, lw=1.1, alpha=0.75)
        axsp.tick_params(colors="#3a4744", labelsize=9)
        spec_win_s = specgram.WINDOW_S               # window length -> the N.B. on the axis line

    # x-axis: per-second ticks (elongated at 5 s, labelled at 10 s) on the bottom panel
    bottom = axsp if axsp is not None else ax
    for a in ([ax, axsp] if axsp is not None else [ax]):
        a.xaxis.set_minor_locator(MultipleLocator(1))
        a.xaxis.set_major_locator(MultipleLocator(5))
        a.xaxis.set_major_formatter(
            FuncFormatter(lambda v, _p: f"{int(round(v))}" if round(v) % 10 == 0 else ""))
        a.tick_params(axis="x", which="minor", length=3.5, color="#3a4744")
        a.tick_params(axis="x", which="major", length=6.5, color="#3a4744")
    if axsp is not None:
        ax.tick_params(labelbottom=False)            # waveform shares x; labels on the spectrogram
    xlab = f"seconds after origin time  ({origin_disp} UTC)"
    if axsp is not None:
        xlab += (f"        N.B. spectrogram is over a {spec_win_s:.1f} s window; "
                 f"changes visually appear ~{spec_win_s / 2:.2f} s early")
    bottom.set_xlabel(xlab, fontsize=11, color="#3a4744")

    # titles
    fig.text(0.075, 0.945, args.title, fontsize=25, fontweight="bold", color=TEAL)
    dist_txt = f"  ·  ~{epi:.0f} km from the epicenter" if epi else ""
    depth_txt = f"  ·  focal depth {args.depth_km:g} km" if args.depth_km else ""
    fig.text(0.075, 0.895,
             f"M {args.mag:g}  ·  {args.place}{depth_txt}  ·  {origin_disp} UTC"
             f"  ·  source: {args.source}",
             fontsize=13.5, color=INK)
    fig.text(0.075, 0.862, f"recorded{dist_txt} at {args.sta_label}".replace("recorded  ·  ", "recorded "),
             fontsize=11.5, color=MUT)

    seed = f"{tr.stats.network}.{tr.stats.station}.{tr.stats.location}.{tr.stats.channel}"
    bits = [seed, "DIY Raspberry Pi + ADS1256 (ADC) + LGT-4.5 (Geophone)"]
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

#!/usr/bin/env python3
"""detection_map.py — how far can this station hear, by magnitude?

Draws Northern/Central California with detection-range rings around the Oakmont
station, one per magnitude, inverted from the SAME amplitude model the harvester
uses (`predict_uv`) after correcting it with what we have actually measured.

The chain, and where each number comes from:

  1. `predict_uv(M, r)` (harvest_events.py) scales the California ML attenuation
     off the anchor event, M2.5 @ 18.4 km -> 126 uV peak in 1-15 Hz.
  2. This station reads systematically QUIETER than that anchor predicts. Seven
     confirmed M<3 events over 28.8-45.9 km give a residual of -0.306 +/- 0.078
     dex (2.0x low) -- the site/coupling deficit. Applied to every ring.
  3. Large events are quieter STILL, because the source corner drops below the
     4.5 Hz geophone corner. The M4.2 Cloverdale read -0.633, i.e. 0.33 dex
     BEYOND the small-event deficit. Extrapolated linearly above M3 (n=1 -- the
     single most speculative number on the plot; it shrinks the M5/M6 rings hard).
  4. Detection floor = the faintest thing we have actually confirmed, expressed
     as a multiple of its own pre-event noise, times the archive's noise
     percentiles (quiet night / median / noisy day).

Everything past ~46 km is EXTRAPOLATION -- that is our furthest confirmed
detection. The map says so, and plots the one far-field test we have: the M3.4 at
348 km (Toms Place, 2026-07-30), which we looked for and did not see. That event
falls outside even its own best-case 338 km ring, so it CONFIRMS the model rather
than breaking it -- but it is a single point, and it only probes the M3-4 range.
Beyond ~150 km the surviving energy is low-frequency Lg, exactly where the 4.5 Hz
geophone is deaf, so treat the outer rings as upper bounds.

Usage:
    analysis/.venv/bin/python analysis/detection_map.py
    analysis/.venv/bin/python analysis/detection_map.py --out reports/foo.png

Map assets live in analysis/geo/. The state outlines are committed; the seismicity
dump is not (3 MB, gitignored) and the map degrades gracefully without it. Re-fetch:

    curl -o analysis/geo/seismicity.geojson \\
      "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson\\
&starttime=2011-01-01&endtime=2026-07-30&latitude=38.451817\\
&longitude=-122.621049&maxradiuskm=520&minmagnitude=3.0"
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon

from harvest_events import STA_LAT, STA_LON, ml_atten, predict_uv, REF_MAG, REF_DIST_KM

# Figure labels follow the station code so the map does not keep saying OAKMT
# after the XX.OAKMT -> SS.OAKM1 cutover.
STATION = os.environ.get("SEISMO_STATION", "OAKMT")

GEO = Path(__file__).parent / "geo"
CSV = Path(__file__).parent / "event_harvest.csv"

# The one event we have deliberately tested outside the confirmed range and did
# not see (2026-07-30 15:34:57Z, 16 km WSW of Toms Place). It is the only hard
# constraint we own on the far field, so it gets drawn.
NULL_TEST = dict(lat=37.501, lon=-118.842, mag=3.4, dist=347.7,
                 label="M3.4 Toms Place\n348 km — NOT seen")

# The positive counterpart to the null test: an event well outside the validated
# circle that we DID record and can prove. 2026-08-29 02:41:11Z, M4.84, 85 km W of
# Petrolia, 318.6 km NW. Pn arrived within 0.3 s of iasp91 and Sn within 0.4 s, its
# hf_lf was 0.40 against 1.2-3.3 for every other trigger that evening, the classifier
# gave p=0.991, and it is the only catalogued event within 700 km in a nine-minute
# window -- so the identification does not rest on amplitude at all.
#
# It is deliberately NOT in the calibration set. calibrate() rejects residuals below
# -1.2 dex as probable mis-associations and this one reads -1.22: 16x below the
# textbook amplitude, because at 319 km what is left is low-frequency Lg and that is
# exactly the band a 4.5 Hz geophone throws away. Letting it in would also make it the
# n=1 anchor for the corner penalty in place of the M4.2, reshaping every ring on this
# map from a single far-field point. It is drawn, not fitted.
FAR_CONFIRMED = dict(lat=40.450, lon=-125.272, mag=4.84, dist=318.6,
                     label="M4.8 Petrolia\n319 km — recorded")

CITIES = [
    ("San Francisco", 37.775, -122.419), ("Sacramento", 38.582, -121.494),
    ("San Jose", 37.339, -121.895), ("Fresno", 36.748, -119.772),
    ("Reno", 39.530, -119.814), ("Eureka", 40.802, -124.164),
    ("Bakersfield", 35.373, -119.019), ("Monterey", 36.600, -121.894),
    ("Redding", 40.586, -122.391), ("Mammoth Lakes", 37.649, -118.972),
]

MAGS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
RING_COLORS = ["#7b3294", "#2166ac", "#4393c3", "#1a9850", "#f46d43", "#b2182b"]


# ---------------------------------------------------------------- geodesy
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def dest(lat0, lon0, km, bearing_deg):
    """Point `km` away along `bearing_deg` — used to park ring labels off the pile-up."""
    x, y = circle(lat0, lon0, km, n=721)
    i = int(round(bearing_deg % 360 / 360 * 720))
    return x[i], y[i]


def circle(lat0, lon0, km, n=361):
    """True geodesic circle -- so the rings stay honest under the flat projection."""
    R = 6371.0
    d = km / R
    p1, l1 = math.radians(lat0), math.radians(lon0)
    brg = np.radians(np.linspace(0, 360, n))
    p2 = np.arcsin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * np.cos(brg))
    l2 = l1 + np.arctan2(np.sin(brg) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * np.sin(p2))
    return np.degrees(l2), np.degrees(p2)


# ------------------------------------------------------- calibration from data
def calibrate():
    """Derive the deficit, the corner penalty and the noise floors from the archive."""
    rows = [r for r in csv.DictReader(open(CSV)) if r["epoch"] == "100sps"]
    conf = [r for r in rows
            if float(r["snr"]) >= 3 and -1.2 < float(r["resid_log10"]) < 0.4
            and float(r["lo_hi"]) >= 1]
    if not conf:
        raise SystemExit("no confirmed events in the harvest CSV -- re-run harvest_events.py")

    small = [r for r in conf if float(r["mag"]) < 3.0]
    resid_med = float(np.median([float(r["resid_log10"]) for r in small]))
    resid_sd = float(np.std([float(r["resid_log10"]) for r in small]))

    # Corner penalty: the extra deficit the one big event shows, per magnitude
    # unit above M3. Pure n=1 extrapolation.
    big = sorted(conf, key=lambda r: -float(r["mag"]))[0]
    m_big, r_big = float(big["mag"]), float(big["resid_log10"])
    corner_slope = (resid_med - r_big) / (m_big - 3.0) if m_big > 3.0 else 0.0

    # Floor: the weakest confirmed detection, as a multiple of its own noise.
    k = min(float(r["peak_1_15"]) / float(r["pre_1_15"]) for r in conf)
    noise = np.percentile([float(r["pre_1_15"]) for r in rows], [10, 50, 90])
    reach = max(float(r["dist_km"]) for r in conf)

    return dict(resid_med=resid_med, resid_sd=resid_sd, n_small=len(small),
                corner_slope=corner_slope, m_big=m_big, r_big=r_big, k=k,
                noise=noise, floors=k * noise, reach=reach, conf=conf, n_conf=len(conf))


def deficit(mag, cal):
    """log10 correction from the textbook prediction to what this station reads."""
    extra = cal["corner_slope"] * max(0.0, mag - 3.0)
    return cal["resid_med"] - extra


def reach_km(mag, floor_uv, cal, resid_shift=0.0):
    """Largest distance at which this station clears `floor_uv` for `mag`. Bisection.

    `resid_shift` moves the deficit by +/-1 sigma of the event-to-event scatter, so
    the plotted band spans a realistic best case (quiet night + a loud event) to a
    realistic worst case, not just the noise range. Without it the M1.5 ring lands
    inside our own confirmed M1.46 at 28.8 km, which was both quiet and loud-for-M.
    """
    def excess(r):
        return (math.log10(predict_uv(mag, r)) + deficit(mag, cal) + resid_shift
                - math.log10(floor_uv))
    lo, hi = 1.0, 6000.0
    if excess(lo) < 0:
        return 0.0
    if excess(hi) > 0:
        return hi
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if excess(mid) > 0 else (lo, mid)
    return 0.5 * (lo + hi)


# ------------------------------------------------------------------- plotting
def load_states():
    out = []
    for f in sorted(GEO.glob("*.geojson")):
        if f.name == "seismicity.geojson":
            continue
        g = json.load(open(f))
        geom = g["geometry"] if g["type"] == "Feature" else g
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            out.append(np.array(poly[0]))
    return out


def load_seismicity():
    f = GEO / "seismicity.geojson"
    if not f.exists():
        return np.empty((0, 3))
    g = json.load(open(f))
    return np.array([[e["geometry"]["coordinates"][0], e["geometry"]["coordinates"][1],
                      e["properties"]["mag"] or 0] for e in g["features"]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/detection-range-map.png")
    ap.add_argument("--dpi", type=int, default=170)
    args = ap.parse_args()

    cal = calibrate()
    floor_q, floor_m, floor_n = cal["floors"]

    print(f"calibration from {cal['n_conf']} confirmed events "
          f"({cal['n_small']} of them M<3):")
    print(f"  site deficit          {cal['resid_med']:+.3f} dex "
          f"(+/-{cal['resid_sd']:.3f})  = {10**-cal['resid_med']:.1f}x quieter than textbook")
    print(f"  corner penalty        {cal['corner_slope']:.3f} dex per M above 3.0 "
          f"(from the M{cal['m_big']:.1f}, resid {cal['r_big']:+.3f})")
    print(f"  floor = {cal['k']:.2f} x noise; noise p10/p50/p90 = "
          f"{cal['noise'][0]:.2f}/{cal['noise'][1]:.2f}/{cal['noise'][2]:.2f} uV")
    print(f"  floors  quiet {floor_q:.1f}  median {floor_m:.1f}  noisy {floor_n:.1f} uV")
    print(f"  furthest confirmed detection: {cal['reach']:.1f} km\n")
    sd = cal["resid_sd"]

    def band(m):
        """(worst case, median, best case) reach in km."""
        return (reach_km(m, floor_n, cal, -sd), reach_km(m, floor_m, cal),
                reach_km(m, floor_q, cal, +sd))

    print(f"  {'M':>4} {'worst':>9} {'median':>9} {'best':>9}   (km)")
    radii = {m: band(m) for m in MAGS}
    for m in MAGS:
        rn, rm, rq = radii[m]
        print(f"  {m:>4.1f} {rn:>9.0f} {rm:>9.0f} {rq:>9.0f}")

    nb = band(NULL_TEST["mag"])
    fb = band(FAR_CONFIRMED["mag"])
    r_null = nb[1]

    def null_verdict(d, b):
        """What the miss actually tells us, given where it lands among the rings."""
        if d > b[2]:
            return ("outside even the best case, so the non-detection is exactly what the "
                    "model predicts")
        if d > b[1]:
            return ("outside the median ring but inside the best case, so the miss says the "
                    "best-case ring is an upper bound rather than a promise")
        return ("inside the median ring: the model expected to see it and we did not, which "
                "is a mark against the model, not against the event")

    nv = null_verdict(NULL_TEST["dist"], nb)
    print(f"  far check: M{FAR_CONFIRMED['mag']:.1f} at {FAR_CONFIRMED['dist']:.0f} km. "
          f"Model reach {fb[0]:.0f}/{fb[1]:.0f}/{fb[2]:.0f} km -> "
          f"{'inside' if FAR_CONFIRMED['dist'] <= fb[1] else 'outside'} the median ring; "
          f"recorded.")
    print(f"\n  null test: M{NULL_TEST['mag']} at {NULL_TEST['dist']:.0f} km. Model reach "
          f"{nb[0]:.0f}/{nb[1]:.0f}/{nb[2]:.0f} km (worst/median/best) -> the event sits "
          f"{nv}.")

    # ---- figure: regional panel + an inset for the local field, because the
    # M1.5-M2.5 rings are a few tens of km and vanish at continental scale.
    states, sm = load_states(), load_seismicity()
    conf_pts = confirmed_coords(cal["conf"])

    def draw(ax, mags, span_km, label_bearings, city_fs, dot_s, ring_lw, show_null):
        ax.set_facecolor("#eef3f7")
        for poly in states:
            ax.add_patch(MplPolygon(poly, closed=True, facecolor="#fbfaf6",
                                    edgecolor="#9aa7b1", lw=0.9, zorder=1))
        if len(sm):
            ax.scatter(sm[:, 0], sm[:, 1], s=1.6 ** (sm[:, 2] - 1.5), c="#c7ccd1",
                       alpha=0.55, lw=0, zorder=2)

        for m in mags:
            c = RING_COLORS[MAGS.index(m)]
            rn, rm, rq = radii[m]
            xo, yo = circle(STA_LAT, STA_LON, rq)
            xi, yi = circle(STA_LAT, STA_LON, rn)
            ax.fill(np.r_[xo, xi[::-1]], np.r_[yo, yi[::-1]], color=c, alpha=0.09,
                    lw=0, zorder=3)
            x, y = circle(STA_LAT, STA_LON, rm)
            ax.plot(x, y, color=c, lw=ring_lw, zorder=6)
            if rm > span_km * 0.97:          # ring is off this panel; its label would be too
                continue
            lx, ly = dest(STA_LAT, STA_LON, rm, label_bearings[m])
            box = dict(boxstyle="round,pad=0.26", fc=c, ec="none", alpha=0.95)
            if rm < span_km * 0.25:
                # Tight ring: the label would land under the station marker, so
                # pull it clear and point back at the ring.
                ax.annotate(f" M{m:g} · {rm:.0f} km ", (lx, ly), textcoords="offset points",
                            xytext=(-38, -26), ha="right", va="center", color="white",
                            fontsize=9.5, fontweight="bold", zorder=9, bbox=box,
                            arrowprops=dict(arrowstyle="-", color=c, lw=1.2))
            else:
                ax.text(lx, ly, f" M{m:g} · {rm:.0f} km ", color="white", fontsize=9.5,
                        fontweight="bold", ha="center", va="center", zorder=9,
                        clip_on=True, bbox=box)

        if show_null:
            x, y = circle(STA_LAT, STA_LON, nb[2])
            ax.plot(x, y, color="#d7191c", lw=1.2, ls=(0, (2, 3)), zorder=6)
            lx, ly = dest(STA_LAT, STA_LON, nb[2], 148)
            ax.text(lx, ly, f"M{NULL_TEST['mag']:g} best case · {nb[2]:.0f} km",
                    color="#8b0000", fontsize=8.5, fontweight="bold", ha="center",
                    va="center", rotation=32, zorder=9,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9))
            ax.scatter([NULL_TEST["lon"]], [NULL_TEST["lat"]], s=260, marker="X",
                       facecolor="#d7191c", edgecolor="white", lw=1.8, zorder=11)
            ax.annotate(NULL_TEST["label"], (NULL_TEST["lon"], NULL_TEST["lat"]),
                        textcoords="offset points", xytext=(16, -30), ha="left",
                        fontsize=9.5, fontweight="bold", color="#8b0000", zorder=11,
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#d7191c", lw=1.2))

        if show_null:
            ax.scatter([FAR_CONFIRMED["lon"]], [FAR_CONFIRMED["lat"]], s=300, marker="D",
                       facecolor="#19b35a", edgecolor="white", lw=1.8, zorder=11)
            ax.annotate(FAR_CONFIRMED["label"], (FAR_CONFIRMED["lon"], FAR_CONFIRMED["lat"]),
                        textcoords="offset points", xytext=(18, 12), ha="left",
                        fontsize=9.5, fontweight="bold", color="#0b6b3a", zorder=11,
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#19b35a", lw=1.2))

        # validated core: inside it is measured, outside is inference
        x, y = circle(STA_LAT, STA_LON, cal["reach"])
        ax.plot(x, y, color="#111", lw=2.2, ls=(0, (5, 2)), zorder=7)

        if len(conf_pts):
            ax.scatter(conf_pts[:, 0], conf_pts[:, 1], s=dot_s, marker="o",
                       facecolor="#19b35a", edgecolor="#08602f", lw=1.3, zorder=10)
        ax.scatter([STA_LON], [STA_LAT], s=dot_s * 5, marker="*", facecolor="#ffd400",
                   edgecolor="#222", lw=1.4, zorder=12)

        for name, la, lo in CITIES:
            ax.plot(lo, la, "s", ms=3.4, color="#55606a", zorder=8, clip_on=True)
            ax.text(lo + span_km / 2200, la + span_km / 4000, name, fontsize=city_fs,
                    color="#3a444d", zorder=8, clip_on=True)

        dlat = span_km / 111.0
        dlon = dlat / math.cos(math.radians(STA_LAT))
        ax.set_xlim(STA_LON - dlon, STA_LON + dlon)
        ax.set_ylim(STA_LAT - dlat, STA_LAT + dlat)
        ax.set_aspect(1.0 / math.cos(math.radians(STA_LAT)))
        ax.grid(alpha=0.18, lw=0.5)

    fig = plt.figure(figsize=(13.5, 14.5))
    ax = fig.add_axes((0.055, 0.155, 0.90, 0.765))
    draw(ax, [2.5, 3.0, 4.0, 5.0], max(radii[m][2] for m in MAGS) * 1.05,
         {2.5: 205, 3.0: 25, 4.0: 340, 5.0: 8}, 7.6, 95, 1.9, True)
    ax.set_xlabel("longitude", fontsize=9); ax.set_ylabel("latitude", fontsize=9)
    ax.tick_params(labelsize=8)

    axi = fig.add_axes((0.068, 0.672, 0.245, 0.245))
    draw(axi, [1.5, 2.0, 2.5, 3.0], 95.0,
         {1.5: 270, 2.0: 152, 2.5: 158, 3.0: 200}, 6.6, 62, 1.7, False)
    axi.set_xticklabels([]); axi.set_yticklabels([])
    axi.tick_params(length=0)
    for s in axi.spines.values():
        s.set_edgecolor("#222"); s.set_linewidth(1.6)
    axi.set_title("local field — the range that is actually measured\n"
                  f"(dashed = validated to {cal['reach']:.0f} km; green = the "
                  f"{cal['n_conf']} confirmed events)",
                  fontsize=8.6, fontweight="bold", pad=5)
    axi.annotate(STATION, (STA_LON, STA_LAT), textcoords="offset points",
                 xytext=(11, -21), ha="left", fontsize=9, fontweight="bold", zorder=13,
                 bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#222", lw=1.1))

    fig.suptitle(f"How far can {STATION} hear?\nDetection range by magnitude — "
                 "LGT-4.5 geophone / ADS1256, Oakmont, Santa Rosa",
                 fontsize=15, fontweight="bold", y=0.975)

    handles = [
        Line2D([], [], marker="*", ls="", ms=17, mfc="#ffd400", mec="#222", label="station"),
        Line2D([], [], marker="o", ls="", ms=9, mfc="#19b35a", mec="#0b5",
               label=f"confirmed detections ({cal['n_conf']})"),
        Line2D([], [], marker="X", ls="", ms=12, mfc="#d7191c", mec="white",
               label="tested and NOT detected"),
        Line2D([], [], marker="D", ls="", ms=10, mfc="#19b35a", mec="white",
               label="recorded beyond the validated range"),
        Line2D([], [], color="#111", lw=2.2, ls=(0, (5, 2)), label="validated range"),
        Line2D([], [], marker="o", ls="", ms=5, mfc="#c7ccd1", mec="none",
               label="M≥3 seismicity, 2011–2026 (USGS)"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=9, framealpha=0.94)

    note = (
        f"Rings invert the California ML attenuation, corrected by what this station "
        f"actually measures:  site deficit {cal['resid_med']:+.2f} dex "
        f"({10**-cal['resid_med']:.1f}× quiet, {cal['n_small']} events, ±{cal['resid_sd']:.2f}) "
        f"plus a {cal['corner_slope']:.2f} dex/M penalty above M3 for the 4.5 Hz corner "
        f"(n=1, from the M{cal['m_big']:.1f}).\n"
        f"Solid ring = median conditions; shaded band = worst case (noisy day, quiet event) to "
        f"best case (quiet night, loud event). Floor = {cal['k']:.1f}× the pre-event 1–15 Hz "
        f"noise, the weakest we have confirmed.\n"
        f"✓ Consistency check: the M{NULL_TEST['mag']:g} at {NULL_TEST['dist']:.0f} km "
        f"(2026-07-30) was looked for and not seen. It sits {nv}.\n"
        f"✓ And the other way: the M{FAR_CONFIRMED['mag']:.1f} at "
        f"{FAR_CONFIRMED['dist']:.0f} km (2026-08-29) sits inside its median "
        f"{fb[1]:.0f} km ring and WAS recorded — identified on arrival times, not "
        f"amplitude. It reads 16× below textbook, past the −1.2 dex cut this "
        f"calibration uses, so it is drawn here but not fitted.\n"
        f"⚠ Only the dashed {cal['reach']:.0f} km circle is measured; beyond it every ring is "
        f"extrapolation and untested. Past ~150 km the surviving energy is low-frequency Lg — the "
        f"band the 4.5 Hz geophone rejects — so the M4/M5 rings are upper bounds, not promises."
    )
    import textwrap
    wrapped = "\n".join(textwrap.fill(p, 158) for p in note.split("\n"))
    fig.text(0.5, 0.012, wrapped, ha="center", va="bottom", fontsize=8.6,
             color="#333", linespacing=1.6)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=args.dpi)
    print(f"\nwrote {out}")


def confirmed_coords(conf):
    """Confirmed events' epicentres, re-queried from USGS by origin time."""
    import urllib.parse, urllib.request
    from datetime import datetime, timedelta, timezone
    pts = []
    for r in conf:
        # A zero-width time window returns nothing from FDSN -- widen it to +/-5 s
        # and match on magnitude.
        t = datetime.strptime(r["origin"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        fmt = "%Y-%m-%dT%H:%M:%S"
        q = urllib.parse.urlencode(dict(
            format="geojson", starttime=(t - timedelta(seconds=5)).strftime(fmt),
            endtime=(t + timedelta(seconds=5)).strftime(fmt),
            latitude=STA_LAT, longitude=STA_LON, maxradiuskm=700))
        try:
            with urllib.request.urlopen(
                    f"https://earthquake.usgs.gov/fdsnws/event/1/query?{q}", timeout=30) as fh:
                g = json.load(fh)
            for e in g["features"]:
                if abs((e["properties"]["mag"] or 0) - float(r["mag"])) < 0.05:
                    c = e["geometry"]["coordinates"]
                    pts.append([c[0], c[1]])
                    break
        except Exception as exc:                       # network hiccup: skip the dot
            print(f"  (could not locate {r['origin']}: {exc})")
    return np.array(pts) if pts else np.empty((0, 2))


if __name__ == "__main__":
    main()

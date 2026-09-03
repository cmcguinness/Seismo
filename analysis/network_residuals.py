#!/usr/bin/env python3
"""network_residuals.py — one earthquake, every station within reach: who heard P when?

WHY. Two stations 1.64 km apart can only tell you they disagree. On the M3.5 under
Larkfield-Wikiup (2026-09-03) NP.1835's onset lagged ours by 0.60 s where geometry allowed
0.25, and the tidy story was the alluvium under 1835. Forty stations said otherwise: 1835
sat in the middle of the near-field crowd (+0.08 s) and WE were the early one (-0.20 s).
A location error moves every station's residual in a pattern; a site delay moves one
station alone; a velocity-model error grows with distance. You need the crowd to tell
them apart, and it is the same plot a network seismologist uses to check a location.

WHAT IT DOES. Catalogue hypocentre from USGS (matched on origin time), every station with
a vertical channel inside --radius from NCEDC's station service (one channel per station:
HHZ > EHZ > HNZ > BHZ), waveforms from NCEDC dataselect, our own day-file for OAKM1. Each
trace gets catch_picks.py's causal AIC picker (via refstation_delay.onset) in a window
around ITS predicted P; the window closes well before predicted S, because a +/-4 s window
at 20 km straddles S and the first version picked it seven times. Residual = onset minus
straight-line hypo / VP. Prints a table, writes a residual map and a residual-vs-distance
panel to doc/, and a JSON beside them.

READ IT AS: near-field scatter = location error (a 1 km automatic epicentre error is
0.2 s at 12 km); a trend with distance = velocity model (5.19 km/s is the shallow value,
deeper paths run faster, so far stations come in early); one station off by itself =
that station.

    analysis/.venv/bin/python analysis/network_residuals.py 2026-09-03T17:33:27
    analysis/.venv/bin/python analysis/network_residuals.py 2026-09-03T17:33:27 --radius 60 --vp 5.5

Waveforms and the station list are cached under analysis/data/refcache/netres/ (gitignored).
"""
import argparse
import json
import math
import os
import re
import sys
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harvest_events as he                                   # noqa: E402
from refstation_delay import onset                            # noqa: E402
from refstation_compare import our_trace                      # noqa: E402
from refstation_spectra import CACHE                          # noqa: E402

DOC = os.path.join(os.path.dirname(HERE), "doc")
NCEDC_STA = "https://service.ncedc.org/fdsnws/station/1/query"
PREF = {"HHZ": 0, "EHZ": 1, "HNZ": 2, "BHZ": 3, "SHZ": 4}
VP, VS = 5.19, 3.00
OURS = "SS.OAKM1.00.EHZ"
TEAL, INK, RED, BLUE, MUT = "#2f6f6b", "#16211f", "#c0392b", "#2c6e9b", "#6b7775"


def catalogue_event(origin):
    from obspy import UTCDateTime
    o = UTCDateTime(origin)
    feats = he.fetch(str(o - 3)[:19], str(o + 3)[:19], 600, 0)
    if not feats:
        sys.exit(f"no USGS event within 3 s of {origin}")
    f = feats[0]
    lon, lat, dep = f["geometry"]["coordinates"][:3]
    p = f["properties"]
    return dict(origin=str(UTCDateTime(p["time"] / 1000.0))[:23], lat=lat, lon=lon,
                depth_km=dep or 0.0, mag=p["mag"], place=p["place"], status=p.get("status"),
                id=p.get("ids", "").strip(","))


def hypo_km(lat, lon, elev_m, ev):
    dlat = (lat - ev["lat"]) * 111.32
    dlon = (lon - ev["lon"]) * 111.32 * math.cos(math.radians((lat + ev["lat"]) / 2))
    return math.hypot(math.hypot(dlat, dlon), ev["depth_km"] + elev_m / 1000.0)


def stations(ev, radius_km, cache_dir):
    """One vertical channel per station inside the radius, from NCEDC, cached."""
    path = os.path.join(cache_dir, "stations.json")
    if os.path.exists(path):
        return json.load(open(path))
    t0 = ev["origin"][:19]
    q = (f"?latitude={ev['lat']}&longitude={ev['lon']}&maxradius={radius_km / 111.0:.4f}"
         f"&level=channel&format=text&starttime={t0}&endtime={t0[:11]}23:59:59"
         f"&channel={','.join(PREF)}")
    with urllib.request.urlopen(NCEDC_STA + q, timeout=60) as r:
        lines = r.read().decode().splitlines()[1:]
    best = {}
    for line in lines:
        c = line.split("|")
        net, sta, loc, cha = c[0], c[1], c[2], c[3]
        lat, lon, elev = float(c[4]), float(c[5]), float(c[6] or 0)
        rank = (PREF[cha], 0 if loc in ("", "00") else 1)
        if (net, sta) not in best or rank < best[(net, sta)]["rank"]:
            best[(net, sta)] = dict(rank=rank, net=net, sta=sta, loc=loc, cha=cha,
                                    lat=lat, lon=lon, elev_m=elev)
    out = sorted(best.values(), key=lambda s: hypo_km(s["lat"], s["lon"], s["elev_m"], ev))
    json.dump(out, open(path, "w"), indent=1)
    return out


def waveform(s, o, cache_dir):
    from obspy import read
    from obspy.clients.fdsn import Client
    sid = f"{s['net']}.{s['sta']}.{s['loc'] or '--'}.{s['cha']}"
    path = os.path.join(cache_dir, sid + ".mseed")
    if os.path.exists(path):
        return read(path)[0]
    st = Client("NCEDC", timeout=60).get_waveforms(s["net"], s["sta"], s["loc"] or "*", s["cha"],
                                                    o - 45, o + 25)
    st.merge(fill_value="interpolate")
    tr = st[0]
    tr.data = tr.data.astype(np.float64)
    tr.write(path, format="MSEED", encoding="FLOAT64")
    return tr


def search_window(hypo):
    """Look from 2 s before predicted P to well short of predicted S."""
    sp = hypo * (1 / VS - 1 / VP)
    return (-2.0, max(0.5, min(3.0, 0.6 * sp)))


def measure(ev, sta_list, vp, k, cache_dir):
    from obspy import UTCDateTime
    o = UTCDateTime(ev["origin"])
    rows = []
    for s in sta_list + [None]:
        if s is None:                                   # ourselves, from the day-file
            lat, lon, elev = he.STA_LAT, he.STA_LON, he.STA_ELEV_M
            sid, net = OURS, "SS"
        else:
            lat, lon, elev = s["lat"], s["lon"], s["elev_m"]
            sid, net = f"{s['net']}.{s['sta']}.{s['loc'] or '--'}.{s['cha']}", s["net"]
        h = hypo_km(lat, lon, elev, ev)
        tp = h / vp
        row = dict(sid=sid, net=net, lat=lat, lon=lon, hypo_km=round(h, 2), tp_pred=round(tp, 3),
                   onset=None, resid=None, snr=None, note="")
        try:
            tr = our_trace(o, o - 45, o + 25) if s is None else waveform(s, o, cache_dir)
            if tr.stats.sampling_rate < 40:
                raise ValueError(f"{tr.stats.sampling_rate:g} sps")
            on, snr = onset(tr, o, tp, k, search=search_window(h))
            row["snr"] = round(float(snr), 1)
            if on is None:
                row["note"] = f"no pick (peak {snr:.0f}x floor)"
            else:
                row["onset"], row["resid"] = round(on, 3), round(on - tp, 3)
        except Exception as e:
            msg = str(e).splitlines()[0][:60]
            row["note"] = "no data" if "No data" in msg else msg
        rows.append(row)
    return rows


def figure(ev, rows, vp, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    good = [r for r in rows if r["resid"] is not None]
    res = np.array([r["resid"] for r in good])
    dist = np.array([r["hypo_km"] for r in good])
    lim = max(0.5, min(1.5, float(np.percentile(np.abs(res), 90)) * 1.2))
    fig, (axm, axd) = plt.subplots(1, 2, figsize=(13, 5.8), gridspec_kw=dict(width_ratios=[1.05, 1]))
    # --- map ---
    coslat = math.cos(math.radians(ev["lat"]))
    sc = axm.scatter([r["lon"] for r in good], [r["lat"] for r in good], c=res, cmap="coolwarm",
                     vmin=-lim, vmax=lim, s=70, edgecolor=INK, linewidth=0.5, zorder=3)
    axm.scatter([r["lon"] for r in rows if r["resid"] is None], [r["lat"] for r in rows if r["resid"] is None],
                marker="x", c=MUT, s=22, linewidth=0.8, zorder=2, label="no pick / no data")
    axm.scatter([ev["lon"]], [ev["lat"]], marker="*", s=260, c="#f1c40f", edgecolor=INK, zorder=4,
                label=f"M{ev['mag']:.1f} epicentre ({ev['status']})")
    for r in good:
        if r["sid"] == OURS or r["sid"].startswith("NP.1835"):
            axm.annotate(r["sid"].split(".")[1] + f"  {r['resid']:+.2f} s", (r["lon"], r["lat"]),
                         xytext=(7, 5), textcoords="offset points", fontsize=8.5, color=INK, weight="bold")
    axm.set_aspect(1 / coslat)
    axm.set_xlabel("longitude", color=INK)
    axm.set_ylabel("latitude", color=INK)
    axm.grid(alpha=0.25)
    axm.legend(loc="lower left", fontsize=8.5, frameon=False)
    cb = fig.colorbar(sc, ax=axm, fraction=0.04, pad=0.02)
    cb.set_label("P residual, onset − hypo/Vp (s)", color=INK)
    # --- residual vs distance ---
    axd.axhline(0, color=MUT, lw=0.8, ls=":")
    for r in good:
        col = RED if r["sid"] == OURS else (BLUE if r["sid"].startswith("NP.1835") else TEAL)
        axd.scatter(r["hypo_km"], r["resid"], c=col, s=60 if col != TEAL else 28, zorder=3,
                    edgecolor=INK if col != TEAL else "none", linewidth=0.5)
    if len(good) >= 4:
        a, b = np.polyfit(dist, res, 1)
        xs = np.linspace(dist.min(), dist.max(), 50)
        axd.plot(xs, a * xs + b, color=MUT, lw=1, ls="--",
                 label=f"trend {a * 100:+.2f} s per 100 km → Vp eff ≈ {vp / (1 + a * vp):.2f} km/s")
    axd.scatter([], [], c=RED, s=60, edgecolor=INK, label="SS.OAKM1 (this station)")
    axd.scatter([], [], c=BLUE, s=60, edgecolor=INK, label="NP.1835 (reference)")
    axd.set_ylim(-lim, lim)
    axd.set_xlabel("hypocentral distance (km)", color=INK)
    axd.set_ylabel("P residual (s)", color=INK)
    axd.grid(alpha=0.25)
    axd.legend(fontsize=8.5, frameon=False, loc="lower left")
    med = float(np.median(res))
    fig.suptitle(f"P residuals across the network: M{ev['mag']:.1f} {ev['place']} · {ev['origin'][:19]} UTC · "
                 f"{len(good)} picks of {len(rows)} stations · median {med:+.2f} s", fontsize=11.5, color=INK)
    fig.text(0.5, 0.005, f"straight-line Vp {vp} km/s from the USGS {ev['status']} hypocentre "
             f"({ev['depth_km']:.1f} km deep); causal 1–15 Hz band-pass, AIC onset in a window that "
             "closes before predicted S; a residual pattern is location, a trend is velocity, a loner is site",
             ha="center", fontsize=8.5, color=MUT)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    fig.savefig(out, dpi=150)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("origin", help="origin time, UTC ISO (matched to the catalogue within 3 s)")
    ap.add_argument("--radius", type=float, default=40.0, help="km from the epicentre")
    ap.add_argument("--vp", type=float, default=VP)
    ap.add_argument("--k", type=float, default=5.0, help="minimum peak / pre-event floor")
    ap.add_argument("--out-dir", default=DOC)
    args = ap.parse_args()
    ev = catalogue_event(args.origin)
    tag = ev["origin"][:19].replace(":", "")
    cache_dir = os.path.join(CACHE, "netres", tag)
    os.makedirs(cache_dir, exist_ok=True)
    print(f"M{ev['mag']:.1f} {ev['place']}  {ev['origin']}  {ev['lat']:.4f} {ev['lon']:.4f} "
          f"{ev['depth_km']:.1f} km  [{ev['status']}]")
    sta_list = [s for s in stations(ev, args.radius, cache_dir)
                if hypo_km(s["lat"], s["lon"], s["elev_m"], ev) <= args.radius + ev["depth_km"]]
    rows = measure(ev, sta_list, args.vp, args.k, cache_dir)
    rows.sort(key=lambda r: r["hypo_km"])
    print(f"\n{'station':22s} {'hypo km':>7s} {'pred':>6s} {'onset':>6s} {'resid':>6s}  snr")
    for r in rows:
        if r["resid"] is None:
            print(f"{r['sid']:22s} {r['hypo_km']:7.1f} {r['tp_pred']:6.2f}   ----   ----  {r['note']}")
        else:
            mark = "  <-- this station" if r["sid"] == OURS else ("  <-- reference" if r["sid"].startswith("NP.1835") else "")
            print(f"{r['sid']:22s} {r['hypo_km']:7.1f} {r['tp_pred']:6.2f} {r['onset']:6.2f} {r['resid']:+6.2f}  {r['snr']:.0f}{mark}")
    good = [r for r in rows if r["resid"] is not None]
    if len(good) < 3:
        sys.exit("fewer than three picks; nothing to plot")
    place = re.sub(r"[^a-z0-9]+", "-", re.sub(r"^\d+ km [NSEW]+ of ", "", ev["place"]).split(",")[0].lower()).strip("-")
    stem = f"network-residuals-{ev['origin'][:10]}-m{ev['mag']:.1f}-{place}"
    png = os.path.join(args.out_dir, stem + ".png")
    figure(ev, rows, args.vp, png)
    res = np.array([r["resid"] for r in good])
    near = [r["resid"] for r in good if r["hypo_km"] <= 20]
    print(f"\n{len(good)} picks: median {np.median(res):+.2f} s, MAD {np.median(np.abs(res - np.median(res))):.2f}; "
          f"near field (<=20 km, n={len(near)}) median {np.median(near):+.2f} s" if near else "")
    with open(os.path.join(args.out_dir, stem + ".json"), "w") as fh:
        json.dump(dict(event=ev, vp=args.vp, radius_km=args.radius, stations=rows), fh, indent=1)
    print(f"wrote {png} and .json")


if __name__ == "__main__":
    main()

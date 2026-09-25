#!/usr/bin/env python3
"""refnetwork.py — is NP.1835 loud, or is OAKM1 quiet?

The absolute calibration (`refstation.py`) says this station reads ~3.2x below its
28.8 V/(m/s) nameplate, measured against ONE reference: NP.1835, 1.64 km away. Charles,
2026-09-25: *could that be configuration error or drift at the fire station, and nothing
to do with us?*

The narrow version of that is already dead -- NP.1835's metadata is clean (213,775
counts/(m/s^2) = exactly +-4 g full scale on 24 bits, stable to 0.01 % since 2017). The
strong version is not: **NP.1835 is Santa Rosa Fire Station 7, and NSMP sites instruments
at structures on purpose.** If it sits on a building rather than free-field, structural
response at the very 5-15 Hz we compare in makes their record large and ours read low,
with nothing wrong at our end.

THE TEST. There are 13 professional stations within 11 km. For each event, measure the
5-15 Hz peak ground velocity at every station that heard it, fit the amplitude decay
across those stations, and take each station's residual from that fit. Average the
residuals per station over many events and you have a **station term** -- exactly the
quantity a location agency computes, and the honest way to ask whether one instrument
runs hot.

    analysis/.venv/bin/python analysis/refnetwork.py --events 14

TWO STATIONS CARRY EXTRA WEIGHT.
  - **NC.NTYB** has an **HH** broadband VELOCITY channel: the same physical quantity our
    geophone measures, no differentiation, and a different instrument class from every
    accelerometer in the comparison.
  - **NP.1767** is the OTHER NSMP fire station. If both fire houses sit high against the
    CE/NC sites, that is a fingerprint of NSMP structural siting rather than of our garage.

EXPECTED OUTCOME, RECORDED BEFORE RUNNING (BACKLOG, 2026-09-25): metadata this clean makes
a large instrumental bias unlikely, so a modest station term is more probable than the whole
3.2x. Modest still matters -- it multiplies every magnitude we publish.

RESULT, 2026-09-25 (20 strongest events, 13 stations with >= 3 measurements):

    NSMP fire station (NP)   5 sta   +0.154   1.42x
    CSMIP urban (CE)         4 sta   +0.003   1.01x
    broadband on rock (HH)   4 sta   -0.184   0.66x
    NP.1835 alone                    +0.195   1.55x above the CSMIP urban sites

Two things make this more than a pattern. **The method validates itself**: the rock-vs-town
split is 1.54x, which is textbook soil amplification with the right sign and a plausible
size -- an effect we were not looking for and did not put in. And **the comparison that
matters is clean**: NP vs CE is accelerometer against accelerometer, town site against town
site, so the 1.42x is neither an instrument-class artifact nor rock-vs-soil.

DIRECTION, since the first version of this file had it backwards. refstation.py measures
ratio = ref/ours ~ 3.26 and infers sens = 28.8/3.26 ~ 9.0 V/(m/s). If the reference reads k
times high, the true ratio is 3.26/k -- we are LESS low -- and sens = 9.0*k:

    vs all neighbours     k=1.33  ->  12.0 V/(m/s), shortfall 2.40x
    vs CSMIP urban only   k=1.55  ->  14.0 V/(m/s), shortfall 2.06x

⚠️ **THIS IS THE FLATTERING DIRECTION.** It says our instrument is better than we thought,
which is exactly the kind of conclusion CLAUDE.md warns needs more evidence than it feels
like it needs. Do not apply it. What it licenses is a change of METHOD -- see below -- not a
change of number.

CAVEATS, longer than the result:
  - **OAKM1 is not in the fit**, and cannot be: its response is the unknown under test.
    Treating it as a typical CSMIP urban site is an ASSUMPTION. Our garage may amplify too.
  - A station term lumps everything -- instrument, housing, structure, soil, topography. This
    cannot separate "NSMP buildings amplify" from "NSMP happens to sit on softer ground".
  - 20 events, all strong ones, and a simple per-event log-linear decay across a 17 km
    aperture. Crude, if unbiased.
  - The NetQuakes NC.N0xx stations contributed nothing -- they are triggered recorders, so
    they hold no data for most of these events. The urban sample is only 4 CE stations.

WHAT IT DOES LICENSE. `refstation.py` uses ONE reference because it is nearest (1.64 km),
chosen so the path is as similar as possible. Proximity bought path similarity and an
amplified site along with it. **The fix is a network of references rather than the closest
one** -- calibrate against the median of several, and the site terms largely cancel.

THE CALIBRATION RESULT KILLED THE FLATTERING ONE (2026-09-25, same day).
Fitting the network's decay per event and evaluating it at OAKM1's own distance -- the
multi-reference calibration, strictly more general than "median of several" because it
corrects for distance -- gives:

    n=20   median ratio 1.03x  (IQR 0.78-1.16)
      -> 8.74 V/(m/s), shortfall 3.29x
    single-reference NP.1835 gives 9.0 V/(m/s), shortfall 3.20x

**The same answer.** So the k-correction above (9.0 -> 12-14) was an INFERENCE that assumed
OAKM1 behaves like a network-median site, and the direct measurement contradicts it: our own
amplitudes agree with the network prediction at 9.0. The likeliest reading is that OAKM1 and
NP.1835, 1.6 km apart on one valley floor, carry SIMILAR site terms -- so they cancelled in
the original comparison and the nearest-station choice was accidentally fine.

**The 3.2x is not the yardstick.** It survives the change of method. Keep the station-term
table as a real observation about the local network; do not keep the correction it seemed to
imply. This is what "beware the comfortable conclusion" looks like when it is tested.

WHAT THIS CANNOT DO. It says nothing about whether OAKM1 itself is quiet: our station is not
in the fit (our response is the unknown under test). It compares the professionals with each
other. A large NP.1835 term moves the reference and therefore our sensitivity; a small one
eliminates a candidate and leaves the f0/zeta and the magnet.
"""
import argparse, json, math, os, pickle, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "netcache")
OAK = (38.451817, -122.621049)
BAND = (5.0, 15.0)
MAXRAD_DEG = 0.16            # ~18 km
REF = "NP.1835"


def gc_km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def cached(key, fn):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, key.replace("/", "_") + ".pkl")
    if os.path.exists(p):
        with open(p, "rb") as fh:
            return pickle.load(fh)
    v = fn()
    with open(p, "wb") as fh:
        pickle.dump(v, fh)
    return v


def station_table(client):
    """Every professional station near OAKM1, with coordinates, best band first."""
    inv = client.get_stations(latitude=OAK[0], longitude=OAK[1], maxradius=MAXRAD_DEG,
                              level="channel", channel="HH*,HN*,BH*,EH*",
                              starttime="2026-07-20", endtime="2026-09-26")
    out = {}
    for net in inv:
        for s in net:
            sid = f"{net.code}.{s.code}"
            # prefer a true velocity channel; fall back to strong motion
            bands = {c.code[:2] for c in s.channels if c.code.endswith("Z")}
            band = "HH" if "HH" in bands else ("BH" if "BH" in bands else
                                               ("EH" if "EH" in bands else "HN"))
            if not bands:
                continue
            out[sid] = dict(net=net.code, sta=s.code, lat=s.latitude, lon=s.longitude,
                            band=band, vel=band in ("HH", "BH", "EH"),
                            site=(s.site.name or "")[:34],
                            dist_oak=gc_km(OAK, (s.latitude, s.longitude)))
    return out


def usgs_origins(iso_times):
    """lat/lon/depth for each confirmed origin, from USGS ComCat."""
    from obspy.clients.fdsn import Client
    from obspy import UTCDateTime
    c = Client("USGS", timeout=60)
    out = {}
    for t in iso_times:
        def go(t=t):
            ev = c.get_events(starttime=UTCDateTime(t) - 20, endtime=UTCDateTime(t) + 20,
                              minmagnitude=0.5)
            if not len(ev):
                return None
            best = min(ev, key=lambda e: abs(e.preferred_origin().time - UTCDateTime(t)))
            o = best.preferred_origin()
            return dict(lat=o.latitude, lon=o.longitude,
                        depth_km=(o.depth or 0) / 1000.0, time=str(o.time))
        try:
            out[t] = cached("origin_" + t.replace(":", ""), go)
        except Exception as e:
            print(f"  origin {t}: {type(e).__name__}", file=sys.stderr)
    return out


def peak_vel(client, net, sta, band, origin, dist_km):
    """5-15 Hz peak ground velocity (um/s) in the body-wave window. None if deaf/absent."""
    from obspy import UTCDateTime
    t0 = UTCDateTime(origin)
    w0, w1 = t0 + dist_km / 8.0, t0 + dist_km / 2.5 + 25.0
    def go():
        inv = client.get_stations(network=net, station=sta, channel=band + "Z",
                                  level="response", starttime=w0 - 90, endtime=w1 + 30)
        st = client.get_waveforms(net, sta, "*", band + "Z", w0 - 90, w1 + 30)
        st.merge(fill_value="interpolate")
        st.attach_response(inv)
        st.remove_response(output="VEL", pre_filt=(1.0, 2.0, 40, 45), water_level=60)
        st.filter("bandpass", freqmin=BAND[0], freqmax=BAND[1], corners=4, zerophase=True)
        sig = st.copy().trim(w0, w1)
        noi = st.copy().trim(w0 - 90, w0 - 10)
        if not len(sig) or not len(noi) or sig[0].stats.npts < 100:
            return None
        pk = float(np.max(np.abs(sig[0].data))) * 1e6          # um/s
        nz = float(np.sqrt(np.mean(noi[0].data ** 2))) * 1e6
        return dict(peak=pk, noise=nz, snr=pk / nz if nz > 0 else 0.0)
    try:
        return cached(f"w_{net}.{sta}.{band}_{origin.replace(':','')}", go)
    except Exception:
        return None


# =============================================================================
# CALIBRATION AGAINST THE NETWORK, not against the nearest station
# =============================================================================
def our_peak(origin, dist_km, sens):
    """OAKM1's own 5-15 Hz peak ground velocity (um/s) in the same window.

    Uses `sens` V/(m/s) to convert; the ratio against the network's prediction is then
    the factor by which `sens` is wrong, so the answer does not depend on the guess.
    """
    import obspy
    from obspy import UTCDateTime
    from refstation import UV_PER_COUNT
    from night_compare import day_file
    t0 = UTCDateTime(origin)
    w0, w1 = t0 + dist_km / 8.0, t0 + dist_km / 2.5 + 25.0
    try:
        st = obspy.read(day_file(t0.julday, t0.year))
    except SystemExit:
        return None
    for tr in st:
        tr.stats.sampling_rate = 100.0
    st.merge(method=1, fill_value="interpolate")
    tr = st[0].slice(w0 - 90, w1 + 10)
    if tr.stats.npts < 100 * 60:
        return None
    tr.detrend("demean")
    tr.filter("bandpass", freqmin=BAND[0], freqmax=BAND[1], corners=4, zerophase=True)
    sig = tr.slice(w0, w1).data.astype(float)
    noi = tr.slice(w0 - 90, w0 - 10).data.astype(float)
    if sig.size < 100 or noi.size < 100:
        return None
    to_ms = UV_PER_COUNT * 1e-6 / sens                    # counts -> m/s
    pk = float(np.max(np.abs(sig))) * to_ms * 1e6         # um/s
    nz = float(np.sqrt(np.mean(noi ** 2))) * to_ms * 1e6
    return dict(peak=pk, noise=nz, snr=pk / nz if nz > 0 else 0.0)


def calibrate(rows, ev, origins, stations, sens_assumed, min_stations, min_snr):
    """Fit the network's decay per event, evaluate it at OAKM1's distance, compare.

    This is the multi-reference calibration. The old method took ONE station because it
    was nearest; nearness bought path similarity and that station's site term together.
    Fitting across the whole local network and predicting at our own distance uses every
    station and lets the site terms largely cancel -- and it is strictly more general
    than "the median of several", because it corrects for distance rather than assuming
    the references are all at ours.

    ⚠️ What comes out is instrument x OUR OWN site term, which cannot be separated here
    any more than it could before. The improvement is that it is now measured against a
    network baseline instead of against one amplified station.
    """
    out = []
    for e in ev:
        o = origins.get(e["origin"])
        if not o:
            continue
        sub = [r for r in rows if r[0] == e["origin"]]
        if len(sub) < min_stations:
            continue
        x = np.array([math.log10(r[2]) for r in sub])
        y = np.array([r[3] for r in sub])
        A = np.vstack([np.ones_like(x), -x]).T
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        d_oak = math.hypot(gc_km((o["lat"], o["lon"]), OAK), o["depth_km"])
        pred = 10 ** (coef[0] - coef[1] * math.log10(d_oak))      # um/s at OUR distance
        m = our_peak(e["origin"], d_oak, sens_assumed)
        if not m or m["snr"] < min_snr:
            continue
        out.append(dict(origin=e["origin"], mag=e["mag"], dist=d_oak, b=coef[1],
                        pred=pred, ours=m["peak"], snr=m["snr"],
                        ratio=pred / m["peak"], n_sta=len(sub)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--events", type=int, default=14,
                    help="how many of the strongest confirmed events to use")
    ap.add_argument("--min-snr", type=float, default=4.0)
    ap.add_argument("--min-stations", type=int, default=4,
                    help="an event needs this many stations to fit a decay")
    a = ap.parse_args()

    from obspy.clients.fdsn import Client
    ncedc = Client("NCEDC", timeout=90)

    ev = json.load(open(os.path.join(os.path.dirname(HERE),
                                     "dashboard", "catches", "confirmed.json")))["events"]
    ev = [e for e in ev if e.get("peak_uv")]
    ev.sort(key=lambda e: -e["peak_uv"])
    ev = ev[:a.events]
    print(f"{len(ev)} strongest confirmed events, "
          f"peak_uv {ev[-1]['peak_uv']:.0f}..{ev[0]['peak_uv']:.0f}\n")

    stations = cached("stations_v2", lambda: station_table(ncedc))
    print(f"{len(stations)} professional stations within {MAXRAD_DEG*111:.0f} km:")
    for sid, s in sorted(stations.items(), key=lambda kv: kv[1]["dist_oak"]):
        print(f"  {s['dist_oak']:5.1f} km  {sid:<12} {s['band']}Z "
              f"{'VEL ' if s['vel'] else 'ACC '} {s['site']}")

    origins = usgs_origins([e["origin"] for e in ev])

    # ---- measure -----------------------------------------------------------
    rows = []          # (origin, sid, dist_km, log10 peak)
    for e in ev:
        o = origins.get(e["origin"])
        if not o:
            continue
        for sid, s in stations.items():
            d = gc_km((o["lat"], o["lon"]), (s["lat"], s["lon"]))
            d = math.hypot(d, o["depth_km"])                  # hypocentral
            m = peak_vel(ncedc, s["net"], s["sta"], s["band"], e["origin"], d)
            if m and m["snr"] >= a.min_snr:
                rows.append((e["origin"], sid, d, math.log10(m["peak"]), m["snr"]))
        got = sum(1 for r in rows if r[0] == e["origin"])
        print(f"  M{e['mag']:<5.2f} {e['origin'][:16]}  {got:2d} stations above "
              f"snr {a.min_snr:g}")

    # ---- per-event decay fit, then per-station residual ---------------------
    # log10(A) = c - b*log10(r).  b is fitted PER EVENT, so source size and radiation
    # drop out; what remains at each station is its own offset from the local trend.
    terms = {}
    used_events = 0
    for e in ev:
        sub = [r for r in rows if r[0] == e["origin"]]
        if len(sub) < a.min_stations:
            continue
        used_events += 1
        x = np.array([math.log10(r[2]) for r in sub])
        y = np.array([r[3] for r in sub])
        A = np.vstack([np.ones_like(x), -x]).T
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        resid = y - A @ coef
        for r, rr in zip(sub, resid):
            terms.setdefault(r[1], []).append(float(rr))

    print(f"\n=== station terms: {used_events} events with >= {a.min_stations} stations ===")
    print("residual from each event's own amplitude-decay fit, in log10 units\n")
    print(f"{'station':<12} {'n':>3} {'term':>7} {'x':>6} {'scatter':>8}  note")
    out = []
    for sid, v in terms.items():
        if len(v) < 3:
            continue
        med = float(np.median(v))
        out.append((med, sid, len(v), float(np.percentile(v, 75) - np.percentile(v, 25))))
    for med, sid, n, iqr in sorted(out, reverse=True):
        s = stations[sid]
        tag = "<-- our reference" if sid == REF else (
            "VELOCITY broadband" if s["vel"] else ("other NSMP fire station"
                                                   if sid.startswith("NP.") else ""))
        print(f"{sid:<12} {n:3d} {med:+7.3f} {10**med:6.2f} {iqr:8.3f}  {tag}")

    # ---- group the stations, because the headline split is confounded ---------
    # Broadband velocity stations are sited on ROCK by design, away from buildings;
    # strong-motion stations are sited in towns on soil, often at structures. So a
    # velocity-vs-accelerometer split is mostly a rock-vs-soil split and says nothing
    # about instrument class. The comparison that matters for OAKM1 -- itself on valley
    # soil -- is NP.1835 against the OTHER URBAN SOIL sites, not against hilltops.
    import collections
    grp = collections.defaultdict(list)
    for med, sid, n, iqr in out:
        g = ("NSMP fire station (NP)" if sid.startswith("NP.") else
             "broadband on rock (HH)" if stations[sid]["vel"] else
             "CSMIP urban (CE)")
        grp[g].append((med, sid, n, iqr))
    print("\n=== by group ===")
    for g, v in sorted(grp.items(), key=lambda kv: -np.median([x[0] for x in kv[1]])):
        meds = [x[0] for x in v]
        iqrs = [x[3] for x in v]
        # standard error of the median, pooled: IQR/1.35 is ~1 sd, /sqrt(total n)
        ntot = sum(x[2] for x in v)
        se = float(np.mean(iqrs)) / 1.35 / math.sqrt(ntot)
        print(f"  {g:<24} n_sta={len(v)}  median {np.median(meds):+.3f} "
              f"({10**np.median(meds):.2f}x)  se~{se:.3f}")
    if "CSMIP urban (CE)" in grp and REF in terms:
        ce = float(np.median([x[0] for x in grp["CSMIP urban (CE)"]]))
        rm = float(np.median(terms[REF]))
        print(f"\n  NP.1835 vs the CSMIP urban sites: {rm - ce:+.3f} log10 "
              f"= {10**(rm-ce):.2f}x")
        print("  (the fairer comparison: both are town sites on valley soil, as OAKM1 is)")

    if REF in terms and len(out) > 2:
        ref_med = float(np.median(terms[REF]))
        others = float(np.median([m for m, sid, _, _ in out if sid != REF]))
        d = ref_med - others
        print(f"\nNP.1835 sits {10**d:.2f}x the median of its neighbours "
              f"({d:+.3f} log10 units).")
        # DIRECTION. Written out because the first version of this line had it backwards.
        # refstation.py measures ratio = ref/ours ~ 3.26 and infers sens = 28.8/3.26 ~ 9.0.
        # If the reference reads k times high, true ground is ref/k, so the true ratio is
        # 3.26/k -- we are LESS low, not more -- and sens = 28.8*k/3.26 = 9.0*k.
        for lab, k in (("vs all neighbours", 10 ** d),
                       ("vs CSMIP urban only", 10 ** (rm - ce)
                        if "CSMIP urban (CE)" in grp else None)):
            if k is None:
                continue
            print(f"  {lab:<22} k={k:.2f}  ->  sensitivity {9.0 * k:5.1f} V/(m/s), "
                  f"shortfall {28.8 / (9.0 * k):.2f}x  (was 9.0 and 3.2x)")
        print("\nNOT a correction to apply -- see the caveats in the docstring, and note")
        print("this is the FLATTERING direction, so it needs more than one analysis.")

    # ---- the multi-reference calibration ------------------------------------
    from refstation import EFFECTIVE_SENS, NOMINAL_SENS
    cal = calibrate(rows, ev, origins, stations, EFFECTIVE_SENS,
                    a.min_stations, a.min_snr)
    if not cal:
        return
    print(f"\n=== calibration against the NETWORK, not the nearest station ===")
    print(f"assumed {EFFECTIVE_SENS:.2f} V/(m/s); the ratio is the factor it is wrong by\n")
    print(f"{'event':<18} {'M':>5} {'km':>6} {'b':>5} {'network um/s':>13} "
          f"{'ours um/s':>10} {'ratio':>7} {'snr':>6}")
    for c in sorted(cal, key=lambda c: c["dist"]):
        print(f"{c['origin'][:16]:<18} {c['mag']:5.2f} {c['dist']:6.1f} {c['b']:5.2f} "
              f"{c['pred']:13.3f} {c['ours']:10.3f} {c['ratio']:7.2f} {c['snr']:6.1f}")
    r = np.array([c["ratio"] for c in cal])
    med = float(np.median(r))
    lo, hi = float(np.percentile(r, 25)), float(np.percentile(r, 75))
    sens = EFFECTIVE_SENS / med
    print(f"\n  n={len(r)}  median ratio {med:.2f}x  (IQR {lo:.2f}-{hi:.2f})")
    print(f"  -> sensitivity {sens:5.2f} V/(m/s), shortfall vs nameplate "
          f"{NOMINAL_SENS / sens:.2f}x")
    print(f"  the single-reference method gives {EFFECTIVE_SENS:.1f} V/(m/s) and "
          f"{NOMINAL_SENS / EFFECTIVE_SENS:.2f}x")
    print("\n  ⚠️ still instrument x OUR OWN site term -- that pair cannot be separated")
    print("     without the injector. What changed is the baseline, not the ambiguity.")



if __name__ == "__main__":
    main()

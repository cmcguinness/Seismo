#!/usr/bin/env python3
"""usgs_events.py — catalog events near the station, with a crude visibility guess.

Polls the USGS summary feed, keeps events within RADIUS_KM, and for each one works
out WHEN it should have arrived here and roughly HOW BIG it should have looked. The
drum then marks them so you can eyeball whether the station caught them. Nothing here
decides whether it actually did -- that is the point, the eye does it.

Uses the SUMMARY FEED (all_day.geojson), not the FDSN query endpoint: it is CDN-cached
and refreshed each minute, so polling it every couple of minutes is cheap and polite.
FDSN is the right call for historical backfill (see analysis/harvest_events.py) but
would be rude at this cadence.

CATALOG LATENCY IS INHERENT. Small events take minutes to hours to appear and are
revised afterwards, so the newest rows are always unmarked and marks show up
retroactively. This can never be a live "a quake is happening" indicator.

⚠️ THE AMPLITUDE MODEL IS CALIBRATED ON FIVE CONFIRMED EVENTS over 9.7-44.6 km, and
lands them within ~4x. That is why the drum shows coarse tiers rather than a number,
and why anything outside 5-150 km is reported as "unknown" instead of guessed.
"""
import json
import math
import os
import time
import urllib.request

FEED = os.environ.get(
    "SEISMO_USGS_FEED",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson")
STA_LAT = float(os.environ.get("SEISMO_STA_LAT", "38.451817"))
STA_LON = float(os.environ.get("SEISMO_STA_LON", "-122.621049"))
RADIUS_KM = float(os.environ.get("SEISMO_USGS_RADIUS_KM", "300"))
MIN_MAG = float(os.environ.get("SEISMO_USGS_MIN_MAG", "1.0"))
NOISE_UV = float(os.environ.get("SEISMO_NOISE_UV", "3.0"))   # 2-15 Hz, 0.5 s RMS
CACHE = os.path.join(os.environ.get("SEISMO_HELI", "/data/heli"), "usgs_events.json")
MAX_AGE_S = float(os.environ.get("SEISMO_USGS_MAX_AGE_S", "86400"))

# Measured at THIS station: onset = hypo/VP + 0.30 s, residuals <=0.3 s over
# 18.4-45.7 km across five confirmed events (analysis/eventcheck.py, STATUS.md).
VP = 5.19
T0_OFFSET = 0.30

# --- VISIBILITY -------------------------------------------------------------------
# log10(peak uV) = M - B*log10(R_km) + C, least-squares over CALIBRATION below. The
# magnitude coefficient is FIXED at 1.0 -- the ML definition, one unit = 10x amplitude
# -- so only the distance slope B and the station constant C are fitted.
#
# Add a row whenever an event is confirmed against the archive, and the fit improves
# on its own. Measure the peak the same way every time: 2-15 Hz, 0.5 s windows, peak
# absolute amplitude in uV.
CALIBRATION = [
    # (magnitude, hypocentral km, observed peak uV in 2-15 Hz, label)
    # EXCLUDED 2026-08-12: recorded 2026-07-25 11:31 UTC, i.e. in the PREVIOUS epoch --
    # the switch to 100 sps was that evening at 23:45 UTC. It is a 5.6x outlier against
    # the five 100-sps events and physically incoherent with them: an M2.5 at 18.4 km
    # cannot read 8x an M2.0 at 9.7 km. Different rate, different config, not
    # comparable. Row kept visible so nobody re-adds it.
    # (2.5, 18.4, 1406.0, "2026-07-25 M2.5 St Helena"),   # pre-100-sps epoch
    (2.8, 44.6, 69.3, "2026-08-11 M2.8 The Geysers"),
    (3.2, 43.4, 229.2, "2026-08-12 M3.2 The Geysers"),
    (3.2, 43.3, 238.3, "2026-08-12 M3.2 The Geysers (2nd, 108 s later)"),
    (2.0, 9.7, 171.5, "2026-08-12 M2.0 Glen Ellen"),
    (2.3, 22.5, 34.7, "2026-08-12 M2.3 Sebastopol"),
]
# The first fit used only the top two rows and gave B=4.18, which predicted 5904 uV
# for the M2.0 at 9.7 km against 171 uV observed -- 34x high. Two events at similar
# distance cannot constrain a distance slope; they were fitting their own radiation
# patterns. Five points spanning 9.7-44.6 km give B~2.1, which is physical
# (geometric spreading plus anelastic attenuation) and lands every point within ~4x.
# Residual scatter of 4x is honest for this: depth, focal mechanism and path all
# matter and none of them are in the model.

# Outside these ranges the fit is extrapolation and the tier is reported as "unknown"
# rather than a confident-looking guess.
CAL_MIN_KM, CAL_MAX_KM = 5.0, 150.0
# MAGNITUDE matters as much as distance and was missed first time round. Every anchor
# is M2.0-M3.2; the drum called an M1.2 at 13.5 km "likely" (predicted ~12 uV) and the
# station saw NOTHING -- peak in the P..coda window was 6.4 uV against a pre-event p90
# of 7.5, i.e. smaller than routine morning background (2026-08-13 14:32 UTC, Penngrove).
# That is a 6x amplitude extrapolation on a fit with ~2x scatter. Half a magnitude of
# slack either side of the anchors, then say "unknown".
CAL_MIN_MAG = 1.5                      # low end only; see tier()


def _fit(points=CALIBRATION):
    """Least-squares (B, C) for log10(A) = M - B*log10(R) + C. Needs >= 2 points."""
    if len(points) < 2:
        return 2.0, -1.0                     # geometric-spreading fallback
    xs = [math.log10(r) for _, r, _, _ in points]
    ys = [math.log10(a) - m for m, _, a, _ in points]   # y = -B*x + C
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else -2.0
    return -slope, my - slope * mx


B, C = _fit()


def predict_uv(mag, hypo_km):
    """Rough expected peak amplitude in uV. Order-of-magnitude at best."""
    if mag is None or hypo_km <= 0:
        return None
    return 10.0 ** (mag - B * math.log10(hypo_km) + C)


def tier(uv, noise_uv=NOISE_UV, hypo_km=None, mag=None):
    """Coarse visibility class. Thresholds are SNR against the measured floor:
    the confirmed M2.8 sat at 6.6x and was unmistakable; 3x is a confident visual
    pick; 2x is 'maybe, if you squint'."""
    if uv is None:
        return "unknown"
    if hypo_km is not None and not (CAL_MIN_KM <= hypo_km <= CAL_MAX_KM):
        return "unknown"          # extrapolation; say so instead of guessing
    # LOW end only. Extrapolating UP is safe -- an M4 at 45 km is certainly visible
    # (the M4.2 Cloverdale is in the archive), so calling it "strong" cannot mislead.
    # Extrapolating DOWN is what promises a detection that never arrives.
    if mag is not None and mag < CAL_MIN_MAG:
        return "unknown"
    snr = uv / max(noise_uv, 1e-9)
    if snr >= 6.0:
        return "strong"
    if snr >= 3.0:
        return "likely"
    if snr >= 1.5:
        return "marginal"
    return "unlikely"


def hypo_km(lat, lon, depth_km):
    dlat = (lat - STA_LAT) * 111.32
    dlon = (lon - STA_LON) * 111.32 * math.cos(math.radians((lat + STA_LAT) / 2))
    epi = math.hypot(dlat, dlon)
    return math.hypot(epi, depth_km or 0.0), epi


def fetch(url=FEED, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "seismo-oakmt/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.load(fh).get("features", [])


def build(features=None, noise_uv=NOISE_UV):
    """Catalog features -> the list the drum draws. Sorted by arrival time."""
    out = []
    for f in (features if features is not None else fetch()):
        p, g = f.get("properties", {}), f.get("geometry", {})
        coords = (g or {}).get("coordinates") or []
        if len(coords) < 3 or p.get("mag") is None or p.get("time") is None:
            continue
        lon, lat, depth = float(coords[0]), float(coords[1]), float(coords[2])
        mag = float(p["mag"])
        if mag < MIN_MAG:
            continue
        hyp, epi = hypo_km(lat, lon, depth)
        if epi > RADIUS_KM:
            continue
        origin = float(p["time"]) / 1000.0
        uv = predict_uv(mag, hyp)
        out.append({
            "id": f.get("id"),
            "mag": round(mag, 1),
            "place": p.get("place") or "",
            "origin": origin,
            # when the P should reach US, which is where the drum marks it
            "arrival": origin + hyp / VP + T0_OFFSET,
            "epi_km": round(epi, 1),
            "hypo_km": round(hyp, 1),
            "depth_km": round(depth, 1),
            "pred_uv": round(uv, 1) if uv else None,
            "tier": tier(uv, noise_uv, hyp, mag),
            "url": p.get("url"),
        })
    out.sort(key=lambda e: e["arrival"])
    return out


def refresh(path=CACHE, noise_uv=NOISE_UV):
    """Poll and write the cache. Returns the event list, or None if the fetch failed.

    A failed poll leaves the previous cache in place -- a network blip must not blank
    the marks off the drum.
    """
    try:
        events = build(noise_uv=noise_uv)
    except Exception as e:
        print(f"usgs_events refresh: {e}", flush=True)
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"updated": time.time(), "fit": {"B": round(B, 3), "C": round(C, 3)},
                   "noise_uv": noise_uv, "events": events}, fh)
    os.replace(tmp, path)                      # atomic: the renderer may be reading
    return events


def load(path=CACHE, max_age_s=MAX_AGE_S):
    """Cached events for the renderer. Never raises, never touches the network."""
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except Exception:
        return []
    now = time.time()
    return [e for e in doc.get("events", []) if now - e.get("arrival", 0) <= max_age_s]


if __name__ == "__main__":
    evs = refresh()
    print(f"fit: log10(uV) = M - {B:.2f}*log10(R) + {C:.2f}   noise {NOISE_UV} uV")
    for e in (evs or [])[-25:]:
        print(f"  {time.strftime('%H:%M:%S', time.gmtime(e['arrival']))}Z "
              f"M{e['mag']:<4} {e['epi_km']:>6.1f} km  pred {e['pred_uv']:>9} uV  "
              f"{e['tier']:<9} {e['place'][:44]}")

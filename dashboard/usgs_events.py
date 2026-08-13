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
import glob
import json
import math
import os
import time
import urllib.request

import numpy as np

FEED = os.environ.get(
    "SEISMO_USGS_FEED",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson")
STA_LAT = float(os.environ.get("SEISMO_STA_LAT", "38.451817"))
STA_LON = float(os.environ.get("SEISMO_STA_LON", "-122.621049"))
RADIUS_KM = float(os.environ.get("SEISMO_USGS_RADIUS_KM", "300"))
MIN_MAG = float(os.environ.get("SEISMO_USGS_MIN_MAG", "1.0"))
NOISE_UV = float(os.environ.get("SEISMO_NOISE_UV", "3.0"))   # fallback only; see floor_at()
GAIN = int(os.environ.get("SEISMO_GAIN", "64"))
HELI_DIR = os.environ.get("SEISMO_HELI", "/data/heli")
ENV_TO_BASELINE = 2.65   # heli `env` (broadband >1 Hz) -> 2-15 Hz 0.5 s peak baseline
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
    # Unambiguous: peak 504 uV = 93x baseline, 66 s of shaking, P onset +16.0 s against
    # a predicted +17.2. Doubles the fitted distance range and the fit barely moves
    # (B 1.58 -> 1.58), which is the strongest evidence yet that the model is sound.
    (4.1, 87.7, 504.0, "2026-08-13 M4.1 San Leandro"),
    # ⛔ RETRACTED 2026-08-13. Byron M2.0 @105 km, "detected" at 46.3 uV. The M4.1 below
    # then showed the model is accurate to 1.02x at 87.7 km, so at 105 km an M2.0 really
    # should give ~3 uV. For Byron to be real the model would have to be 16x wrong at
    # 105 km while being 2% right at 88 km. Far likelier: that burst was morning noise
    # (it was only 2.0x the pre-event MAXIMUM) and the half-second timing match with the
    # predicted S was coincidence. The same trap as the "31 Hz lawn line".
    # (2.0, 105.2, 46.3, "2026-08-13 M2.0 Byron"),   # not a detection
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
CAL_MIN_KM, CAL_MAX_KM = 5.0, 90.0
# Was briefly 60, on the theory that the fit under-predicted far field -- evidence: a
# 105 km "detection" at Byron. The M4.1 at 87.7 km then landed at 1.02x predicted, the
# Byron event was retracted as noise, and the theory with it. 90 km is now the measured
# limit of validity: the farthest CONFIRMED anchor is 87.7 km.
# MAGNITUDE matters as much as distance and was missed first time round. Every anchor
# is M2.0-M3.2; the drum called an M1.2 at 13.5 km "likely" (predicted ~12 uV) and the
# station saw NOTHING -- peak in the P..coda window was 6.4 uV against a pre-event p90
# of 7.5, i.e. smaller than routine morning background (2026-08-13 14:32 UTC, Penngrove).
# That is a 6x amplitude extrapolation on a fit with ~2x scatter. Half a magnitude of
# slack either side of the anchors, then say "unknown".
CAL_MIN_MAG = 1.5                      # low end only; see tier()

# ⚠️ THE FIT IS AN ALONG-STRIKE MODEL, and always will be. Measured 2026-08-13 over the
# USGS catalogue, M>=1.5 within 100 km, two years, n=3268: 94% of events lie within 30
# degrees of the Hayward-Rodgers Creek strike (325/145), against 33% if azimuth were
# uniform. The Geysers geothermal field alone (with Cobb and Anderson Springs) supplies
# ~1980 of them up the NNW arm; San Ramon adds 319 down the SSE arm.
#
# So azimuth is a THIRD axis of extrapolation beside magnitude and distance, and the
# only off-strike anchor -- Sebastopol at 76 degrees -- came in at 0.51x, i.e. the model
# OVER-predicted by 2x. That is the direction that produces false "likely" marks.
# One point cannot justify a correction, so nothing is applied; instead every event
# records its azimuth and off-strike angle, so the question becomes answerable as
# anchors accumulate. Events far off strike deserve suspicion until then.
FAULT_STRIKE = 145.0


def _fit(points=CALIBRATION):
    """Least-squares (B, C) for log10(A) = M - B*log10(R) + C. Needs >= 2 points.

    Only points inside the guarded distance range take part: the model is a single
    power law and is only claimed over [CAL_MIN_KM, CAL_MAX_KM], so a far-field
    observation must not bend it. Raise CAL_MAX_KM and any qualifying rows join
    automatically.
    """
    points = [q for q in points if CAL_MIN_KM <= q[1] <= CAL_MAX_KM] or list(points)
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


def _uv_per_count(gain=GAIN):
    return 2.5 * 2 / (gain * (2 ** 23 - 1)) * 1e6


def floor_history(heli_dir=HELI_DIR):
    """[(t0, interval_s, floor_uV)] from the helicorder envelope files, oldest first.

    heli_build already banks exactly the number we need: `env` is the MEDIAN 0.49 s
    single-sided envelope excursion of each 15-minute interval, in counts, after a
    1 Hz high-pass. That is the same metric the tier thresholds were derived from --
    the M2.8's 6.6x was peak-over-median-0.5s-envelope -- so it drops straight in.

    Using it means an event is scored against the floor AT THE HOUR IT ARRIVED, not
    against whatever the station happens to be doing at poll time. A fixed 3.0 uV
    called an M1.2 "likely" at 07:32 when the real floor was ~4 uV with excursions to
    7.5 (2026-08-13, Penngrove -- not detected).

    ENV_TO_BASELINE converts it. `env` is broadband above 1 Hz, while the tier
    thresholds were derived from a 2-15 Hz 0.5 s peak baseline (the M2.8's 6.6x). The
    two differ by a stable factor: measured over 68 consecutive intervals spanning a
    97 -> 9 uV range, median 2.65, IQR 2.49-3.05. Without it every event is under-rated
    by ~2.65x.
    """
    out = []
    scale = _uv_per_count()
    for path in sorted(glob.glob(os.path.join(heli_dir, "heli.*.npz"))):
        try:
            with np.load(path) as d:
                env = float(d["env"])
                if env > 0 and np.isfinite(env):
                    out.append((float(d["t0"]), float(d["interval_s"]),
                                env * scale / ENV_TO_BASELINE))
        except Exception:
            continue
    out.sort()
    return out


def floor_at(t, hist, default=NOISE_UV):
    """Floor in uV for the interval containing epoch `t`, else `default`."""
    for t0, span, uv in hist:
        if t0 <= t < t0 + span:
            return uv
    return default


def off_strike_deg(az):
    """Angle between a back-azimuth and the fault line, 0 (along) to 90 (fault-normal)."""
    return abs((az - FAULT_STRIKE + 90) % 180 - 90)


def hypo_km(lat, lon, depth_km):
    dlat = (lat - STA_LAT) * 111.32
    dlon = (lon - STA_LON) * 111.32 * math.cos(math.radians((lat + STA_LAT) / 2))
    epi = math.hypot(dlat, dlon)
    az = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
    return math.hypot(epi, depth_km or 0.0), epi, az


def fetch(url=FEED, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "seismo-oakmt/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.load(fh).get("features", [])


def build(features=None, noise_uv=NOISE_UV, heli_dir=HELI_DIR):
    """Catalog features -> the list the drum draws. Sorted by arrival time."""
    try:
        hist = floor_history(heli_dir)
    except Exception:
        hist = []
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
        hyp, epi, az = hypo_km(lat, lon, depth)
        if epi > RADIUS_KM:
            continue
        origin = float(p["time"]) / 1000.0
        uv = predict_uv(mag, hyp)
        arrival = origin + hyp / VP + T0_OFFSET
        floor = floor_at(arrival, hist, noise_uv)
        out.append({
            "id": f.get("id"),
            "mag": round(mag, 1),
            "place": p.get("place") or "",
            "origin": origin,
            # when the P should reach US, which is where the drum marks it
            "arrival": arrival,
            "epi_km": round(epi, 1),
            "hypo_km": round(hyp, 1),
            "depth_km": round(depth, 1),
            "az_deg": round(az, 1),
            "off_strike_deg": round(off_strike_deg(az), 1),
            "pred_uv": round(uv, 1) if uv else None,
            "tier": tier(uv, floor, hyp, mag),
            "floor_uv": round(floor, 2),
            "url": p.get("url"),
        })
    out.sort(key=lambda e: e["arrival"])
    return out


def refresh(path=CACHE, noise_uv=NOISE_UV, heli_dir=HELI_DIR):
    """Poll and write the cache. Returns the event list, or None if the fetch failed.

    A failed poll leaves the previous cache in place -- a network blip must not blank
    the marks off the drum.
    """
    try:
        events = build(noise_uv=noise_uv, heli_dir=heli_dir)
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
              f"floor {e.get('floor_uv'):>6}  {e['tier']:<9} {e['place'][:40]}")

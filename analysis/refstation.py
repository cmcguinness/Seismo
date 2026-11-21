#!/usr/bin/env python3
"""refstation.py — absolute calibration against the co-located reference station.

NP.1835 "Santa Rosa Fire Station 7" is a USGS National Strong-Motion Project
accelerometer **1.64 km** from OAKMT, and NCEDC serves its waveforms with full
instrument response. That is as good a reference as this project will ever get: same
basin, same geology, same events, and no dependence on catalogue magnitudes.

Method: remove the reference response to VELOCITY, band-pass BOTH to 5-15 Hz -- safely
above the geophone's 4.5 Hz corner, where its 28.8 V/(m/s) is flat and no response
model is needed on our side -- and take the ratio over the shaking window. The result
is the factor by which OAKMT under- or over-reads.

Why this beats the alternatives: catalogue-magnitude inversion carries +-0.2-0.3 of
magnitude (1.5-2x in amplitude) plus radiation-pattern scatter, and ML is defined on
horizontals. This is a direct waveform comparison.

⚠️ The stations are 1.64 km apart, so site response is NOT identical -- at 5-15 Hz
local conditions can differ by ~2x on their own. One event gives a factor good to
maybe a factor of two; several events average that down. It also cannot separate a
deaf sensor from a lossy front end: that is what the bench injection is for.

⚠️ THE REFERENCE HAS A NOISE FLOOR. A strong-motion accelerometer is deaf where a
geophone is comfortable. Below roughly 0.5 um/s RMS in this band NP.1835 is measuring
itself, and the ratio becomes meaningless. REF_MIN_RMS rejects those. (The M2.0 Glen
Ellen was long cited here as the example -- 0.14 um/s, a "nonsense" 0.88x -- but that was
the WINDOW, not the floor: at 10 km its S is at +3.4 s and the old fixed +14..+60 s box
sat on coda. In its own P..S window FS7 reads 2.45 um/s and the ratio is 2.97x, in line
with the other anchors. Found 2026-11-20.) The 1.64 km separation still matters most at
short range.

    python analysis/refstation.py 2026-08-13T15:30:04
    python analysis/refstation.py 2026-11-20T06:49:16 --lat 36.607 --lon -121.208 --depth 6.4
    python analysis/refstation.py --all      # every anchor, with an epoch check

THE WINDOW follows the event: P - 2 s to S + 22 s (iasp91 via harvest_events), the same
box refstation_compare.py and the harvest use. The epicentre comes from --lat/--lon or,
failing that, from USGS ComCat by origin time. Until 2026-11-20 it was a fixed +14..+60 s
from origin -- right for the Geysers/San Leandro anchors it was written on, wrong past
~150 km: for the M5.0 Pinnacles at 240 km (S at +64 s) it caught P and missed S entirely.
--fixed-window restores the old box, so the historical anchor numbers can be reproduced.
"""
import argparse
import sys
import warnings

import epochs

warnings.filterwarnings("ignore")

import numpy as np
from obspy import UTCDateTime, read
from obspy.clients.fdsn import Client

UV_PER_COUNT = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
NOMINAL_SENS = 28.8          # V per m/s, flat above the 4.5 Hz corner
BAND = (5.0, 15.0)

# --- PROVISIONAL CALIBRATION -------------------------------------------------------
# Status: PROVISIONAL, in the sense signatures.json uses -- good enough to use, not
# good enough to trust to a second digit. Adopt it rather than the nominal 28.8, which
# is measurably wrong by a factor of three.
#
#   anchors: M2.8 Geysers 3.26x, M3.2 Geysers 3.15x, M2.99+M2.82 San Leandro 2.99x,
#            M4.1 San Leandro 4.46x   (2026-08-11..13, ONE amplitude epoch)
#   median 3.20x low  ->  effective sensitivity 9.0 V/(m/s) vs 28.8 nominal
#
# To convert this station's microvolts to ground velocity ABOVE 4.5 Hz:
#     m/s = uV * 1e-6 / EFFECTIVE_SENS        (or nominal / PROVISIONAL_FACTOR)
#
# Uncertainty is dominated by site response, not statistics: FS7 is 1.64 km away and
# 5-15 Hz site differences of ~2x are ordinary. Treat as "3x, maybe 2.5-4.5".
# It does NOT say where the loss is -- deaf element or lossy front end. Only the bench
# injection separates those, and this number tells it what answer to expect.
# Superseded if anything on the amplitude axis of analysis/epochs.py changes.
PROVISIONAL_FACTOR = 3.20
EFFECTIVE_SENS = NOMINAL_SENS / PROVISIONAL_FACTOR      # 9.0 V/(m/s)
PROVISIONAL_N = 4

REF_MIN_RMS = 0.12e-6     # m/s. Was 0.5e-6, set from ONE window and far too
                          # conservative: FS7 reaches 0.086 um/s RMS (5-15 Hz) on a
                          # quiet night, so it is a better instrument than that guard
                          # assumed. It rejected the M2.0 Glen Ellen, but that was
                          # the old fixed window sitting on coda (see the top).
REF = ("NP", "1835", "HNZ")  # vertical, to match our single vertical component


def our_trace(day_path, t0, t1):
    st = read(day_path)
    for t in st:
        t.stats.sampling_rate = 100.0
    st.merge(method=1, fill_value="interpolate")
    return st[0].slice(t0 - 60, t1 + 60)


def reference(t0, t1, client="NCEDC"):
    c = Client(client, timeout=60)
    inv = c.get_stations(network=REF[0], station=REF[1], channel=REF[2],
                         level="response", starttime=t0, endtime=t1)
    st = c.get_waveforms(REF[0], REF[1], "*", REF[2], t0 - 60, t1 + 60)
    st.merge(fill_value="interpolate")
    st.attach_response(inv)
    st.remove_response(output="VEL", pre_filt=(0.5, 1.0, 40, 45), water_level=60)
    return st[0]


FIXED_LEAD, FIXED_SPAN = 14.0, 46.0     # the pre-2026-11-20 box, seconds after origin


def usgs_location(o):
    """(lat, lon, depth_km) of the ComCat event nearest origin `o` (within 20 s), or None."""
    try:
        c = Client("USGS", timeout=30)
        ev = c.get_events(starttime=o - 20, endtime=o + 20, minmagnitude=0.5)
    except Exception as e:
        print(f"  USGS lookup failed: {type(e).__name__}: {str(e)[:80]}")
        return None
    if not len(ev):
        return None
    best = min(ev, key=lambda e: abs(e.preferred_origin().time - o))
    po = best.preferred_origin()
    return po.latitude, po.longitude, (po.depth or 0.0) / 1000.0


def event_window(o, loc):
    """(lead, span) seconds after origin: P - 2 to S + 22, or None without a location."""
    if loc is None:
        return None
    from harvest_events import arrivals_s, epi_km, hypo_km
    lat, lon, depth = loc
    epi = epi_km(lat, lon)
    tp, ts = arrivals_s(epi, depth, hypo_km(lat, lon, depth))
    print(f"  epicentral {epi:.1f} km  P +{tp:.1f} s  S +{ts:.1f} s  "
          f"-> window +{tp - 2:.1f}..+{ts + 22:.1f} s")
    return tp - 2.0, (ts + 22.0) - (tp - 2.0)


def compare(origin, day_path, lead=None, span=None, loc=None):
    """Returns (ratio_rms, ratio_peak) or None if the reference has no data.

    lead/span given -> that fixed box. Otherwise the box follows the event's P and S,
    from `loc` = (lat, lon, depth_km) or a USGS lookup; without either it falls back to
    the old fixed box and says so."""
    o = UTCDateTime(origin)
    if lead is None or span is None:
        win = event_window(o, loc or usgs_location(o))
        if win is None:
            print(f"  no location -- falling back to the fixed +{FIXED_LEAD:.0f}.."
                  f"+{FIXED_LEAD + FIXED_SPAN:.0f} s box")
            win = (FIXED_LEAD, FIXED_SPAN)
        lead, span = win
    a, b = o + lead, o + lead + span
    try:
        ref = reference(o, o + lead + span + 30)
    except Exception as e:
        print(f"  reference unavailable: {type(e).__name__}: {str(e)[:90]}")
        return None
    mine = our_trace(day_path, o, o + lead + span + 30)
    for tr in (ref, mine):
        tr.detrend("demean")
        tr.filter("bandpass", freqmin=BAND[0], freqmax=BAND[1], corners=4, zerophase=True)
    r = ref.slice(a, b).data.astype(float)                       # m/s
    k = mine.slice(a, b).data.astype(float) * UV_PER_COUNT * 1e-6 / NOMINAL_SENS
    if r.size < 100 or k.size < 100:
        print("  too little overlapping data")
        return None
    if r.std() < REF_MIN_RMS:
        print(f"  reference RMS {r.std()*1e6:.2f} um/s is below its noise floor "
              f"({REF_MIN_RMS*1e6:.1f}) -- REJECTED, ratio would be meaningless")
        return None
    rr, rp = r.std() / k.std(), np.abs(r).max() / np.abs(k).max()
    print(f"  reference  RMS {r.std()*1e6:>8.2f}  peak {np.abs(r).max()*1e6:>8.1f} um/s")
    print(f"  OAKMT      RMS {k.std()*1e6:>8.2f}  peak {np.abs(k).max()*1e6:>8.1f} um/s")
    print(f"  ratio      RMS {rr:>8.2f}x peak {rp:>8.2f}x   "
          f"-> implied {NOMINAL_SENS/rr:.2f} V/(m/s) vs {NOMINAL_SENS} nominal")
    return rr, rp


ANCHORS = [
    ("M2.8 Geysers", "2026-08-11T21:35:14"),
    ("M3.2 Geysers", "2026-08-12T10:28:21"),
    ("M2.0 Glen Ellen", "2026-08-12T09:06:38"),
    ("M4.1 San Leandro", "2026-08-13T15:30:04"),
    ("M2.4 Geysers", "2026-08-25T00:22:31"),   # same path as the first two: 4.49x
]


def _day_file(o):
    """The archive path for an origin's day, WHICHEVER identity it was written under.

    The 2026-08-30 cutover renamed XX.OAKMT.00.SHZ -> SS.OAKM1.00.EHZ. This was a
    hardcoded XX.OAKMT f-string in two places, so `--all` silently skipped every anchor
    after the cutover -- the same bug `night_compare.py` carried until 2026-09-22, found
    again here 2026-09-25. `refstation_compare.py`, which writes refstation.json, already
    globbed both and was never affected.
    """
    import glob as _g
    import os as _os
    here = _os.path.dirname(_os.path.abspath(__file__))
    hits = sorted(h for h in _g.glob(
        _os.path.join(here, "data", f"*.D.{o.year}.{o.julday:03d}.mseed"))
        if ".LDO." not in h)              # the env node's pressure channel, not the seismometer
    return hits[0] if hits else None


def run_all(fixed=False):
    """Every anchor, combined -- and refuse to average across an amplitude boundary."""
    import numpy as np
    from obspy import UTCDateTime
    ratios = []
    for label, origin in ANCHORS:
        o = UTCDateTime(origin)
        day = _day_file(o)
        print(f"{label}  {origin}")
        try:
            got = (compare(origin, day, FIXED_LEAD, FIXED_SPAN) if fixed
                   else compare(origin, day))
        except Exception as e:
            print(f"  skipped: {type(e).__name__}: {str(e)[:80]}")
            continue
        if got:
            ratios.append((label, origin, got[0]))
    if not ratios:
        return
    # An absolute-scale factor may only be averaged within ONE amplitude epoch. This is
    # the check that would have kept the M2.5 St Helena out of CALIBRATION.
    print()
    first = ratios[0][1]
    bad = [l for l, t, _ in ratios if epochs.crossed(first, t, "amplitude")]
    if bad:
        print(f"  ⚠️ REFUSING to average: {', '.join(bad)} sit in a different amplitude")
        print("     epoch from the first anchor. Report them separately.")
        for l, t, r in ratios:
            print(f"       {l:<20} {r:.2f}x")
        return
    vals = np.array([r for _, _, r in ratios])
    print(f"  {len(vals)} anchors, all in one amplitude epoch")
    print(f"  ratio  mean {vals.mean():.2f}x  median {np.median(vals):.2f}x  "
          f"spread {vals.min():.2f}-{vals.max():.2f}")
    print(f"  implied sensitivity {NOMINAL_SENS/np.median(vals):.2f} V/(m/s) "
          f"vs {NOMINAL_SENS} nominal")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Absolute calibration: OAKM1 against NP.1835 (Fire Station 7), "
                    f"{BAND[0]:g}-{BAND[1]:g} Hz, over the event's P..S window.")
    ap.add_argument("origin", nargs="?", default="2026-08-13T15:30:04",
                    help="origin time, ISO UTC (default: the M4.1 San Leandro anchor)")
    ap.add_argument("day", nargs="?", default=None,
                    help="our day-file (default: found in analysis/data)")
    ap.add_argument("--all", action="store_true",
                    help="every built-in anchor, with the amplitude-epoch check")
    ap.add_argument("--lat", type=float, help="epicentre latitude (default: USGS lookup)")
    ap.add_argument("--lon", type=float, help="epicentre longitude")
    ap.add_argument("--depth", type=float, default=None, help="depth km (default 0 with --lat/--lon)")
    ap.add_argument("--fixed-window", action="store_true",
                    help=f"use the old fixed +{FIXED_LEAD:g}..+{FIXED_LEAD + FIXED_SPAN:g} s "
                         "box instead of the event's P..S window")
    args = ap.parse_args(argv)
    if (args.lat is None) != (args.lon is None):
        ap.error("--lat and --lon go together")
    if args.all and (args.lat is not None or args.day is not None):
        ap.error("--all takes no origin, day-file or location")
    if args.fixed_window and args.lat is not None:
        ap.error("--fixed-window ignores the location; give one or the other")
    try:
        o = UTCDateTime(args.origin)
    except Exception:
        ap.error(f"not an ISO time: {args.origin!r}")

    if args.all:
        return run_all(fixed=args.fixed_window)
    day = args.day or _day_file(o)
    if day is None:
        raise SystemExit(f"no local day-file for {o.year}.{o.julday:03d} in analysis/data")
    loc = (args.lat, args.lon, args.depth or 0.0) if args.lat is not None else None
    print(f"{args.origin}  band {BAND[0]}-{BAND[1]} Hz")
    if args.fixed_window:
        compare(args.origin, day, FIXED_LEAD, FIXED_SPAN)
    else:
        compare(args.origin, day, loc=loc)


if __name__ == "__main__":
    raise SystemExit(main())

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
itself, and the ratio becomes meaningless -- the M2.0 Glen Ellen gave 0.14 um/s and a
nonsense 0.88x. REF_MIN_RMS rejects those. It also happens that the closest events are
worst-affected geometrically, since 1.64 km of separation matters most at short range.

    python analysis/refstation.py 2026-08-13T15:30:04
    python analysis/refstation.py --all      # every anchor, with an epoch check
"""
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
REF_MIN_RMS = 0.5e-6      # m/s; below this the reference is measuring its own noise
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


def compare(origin, day_path, lead=14.0, span=46.0):
    """Returns (ratio_rms, ratio_peak) or None if the reference has no data."""
    o = UTCDateTime(origin)
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
]


def run_all():
    """Every anchor, combined -- and refuse to average across an amplitude boundary."""
    import numpy as np
    from obspy import UTCDateTime
    ratios = []
    for label, origin in ANCHORS:
        o = UTCDateTime(origin)
        day = f"analysis/data/XX.OAKMT.00.SHZ.D.{o.year}.{o.julday:03d}.mseed"
        print(f"{label}  {origin}")
        try:
            got = compare(origin, day)
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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        raise SystemExit(run_all())
    origin = sys.argv[1] if len(sys.argv) > 1 else "2026-08-13T15:30:04"
    day = sys.argv[2] if len(sys.argv) > 2 else None
    if day is None:
        import glob
        o = UTCDateTime(origin)
        day = f"analysis/data/XX.OAKMT.00.SHZ.D.{o.year}.{o.julday:03d}.mseed"
        if not glob.glob(day):
            raise SystemExit(f"no local day-file {day}")
    print(f"{origin}  band {BAND[0]}-{BAND[1]} Hz")
    compare(origin, day)

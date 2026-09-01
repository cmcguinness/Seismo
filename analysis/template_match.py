#!/usr/bin/env python3
"""template_match.py — find the earthquakes STA/LTA was too deaf to trigger on.

WHY. The trigger classifier is starved of positives: 33 confirmed events against
thousands of cultural negatives, accumulating at ~5/week because that is simply how
often the ground moves inside our 89 km reach. Augmenting the 33 we have raises the
sample COUNT but not the information -- it is still 33 independent events. Template
matching is the only route that adds things that actually happened.

THE IDEA, which is standard practice and not ours. Earthquakes from the same source
volume radiate near-identical waveforms, because the path and the mechanism repeat. So
a known event is a matched filter for its own neighbourhood: cross-correlate it
through the continuous archive and coherent repeats stand up out of noise far below
what an amplitude trigger like STA/LTA can reach. Published studies routinely recover
5-10x the catalogue count this way.

WHY IT SHOULD WORK ESPECIALLY WELL HERE. 21 of our 33 confirmed events are one tight
cluster -- The Geysers / Cobb / Cloverdale at 36-46 km -- which is a geothermal field
with continuous induced seismicity. The catalogue holds the ones big enough for the
regional network to locate; the archive almost certainly holds many more that were too
small for us to trigger on but are still perfectly correlated with their larger
siblings.

>>> MEASURED RESULT: IT DOES NOT WORK ON THIS CATALOGUE, AND THE REASON IS PHYSICAL. <<<

Run `similarity` and it reports, over our 33 confirmed events: max off-diagonal
correlation 0.390, median 0.180, ZERO pairs above 0.4. Against a full day of archive
the templates recover their own source events at cc 0.97-1.00 -- so the machinery is
right -- and every other catalogue event that day, including forty Geysers events in
the same field as 21 of the templates, sits at cc 0.20-0.33, which is where plain
noise sits too. The "most similar" pairs are geographically unrelated (Kenwood with
Hidden Valley Lake), i.e. coincidence rather than resemblance.

Why. Template matching needs REPEATING events -- essentially the same patch of fault,
same mechanism -- not merely events from the same region. Waveform similarity survives
co-location to roughly a quarter wavelength. At 43 km, after attenuation, our dominant
frequency is ~3-8 Hz, so at 5 km/s the wavelength is 0.6-1.7 km and the requirement is
150-400 m. A geothermal field is abundant seismicity distributed through a VOLUME
several km across; two events both labelled "6 km NW of The Geysers" are routinely
kilometres and therefore many wavelengths apart. The two M3.2s of 2026-08-12, 109
seconds apart under the same label, do not correlate either. One vertical channel at
low SNR makes it harder still.

So the expectation this was built on -- the published 5-10x catalogue yield -- does not
transfer. Those results come from aftershock sequences and creeping-fault repeaters,
where multiplets genuinely exist.

KEEP IT ANYWAY, for the case it was actually designed for: an aftershock sequence on a
fault directly beneath us would produce real multiplets, and then this is exactly the
right tool and already validated. Re-run `similarity` as the catalogue grows -- the day
a pair clears ~0.6, this becomes worth scanning again.

WHAT IT WOULD NOT HAVE DONE EVEN IF IT WORKED. It finds events RESEMBLING the
templates, so it adds volume faster than diversity -- The Geysers would dominate, and
the yield would not be an unbiased sample of local seismicity.

The correlation itself is obspy's `correlate_template` (normalised, FFT-based), not
ours. EQcorrscan would be the specialist tool but its 0.5.2 packaging declares stdlib
modules as build requirements and will not install on Python 3.13.

    python analysis/template_match.py similarity   # <- run this FIRST; see above
    python analysis/template_match.py build
    python analysis/template_match.py scan --day 2026-08-12
    python analysis/template_match.py scan --all --out analysis/tm_detections.csv
"""
import argparse
import csv
import glob
import os
import sys

import numpy as np
from obspy import Stream, UTCDateTime, read
from obspy.signal.cross_correlation import correlate_template

HARVEST = "analysis/event_harvest.csv"
ARCHIVE = "analysis/data"
TEMPLATES = "analysis/templates.npz"

FS = 100.0
BAND = (2.0, 15.0)      # the station's detection band
PRE_P = 1.0             # template starts this far before the predicted P
POST_S = 6.0            # ...and ends this far after the predicted S
MAD_K = 9.0             # detection threshold, in MADs above the median of the CC trace.
                        # 8-12 is the usual range in the literature; 9 is mid-range and
                        # the yield is reported against a sweep so the choice is visible.
MIN_SEP_S = 10.0        # minimum separation between detections from one template
CC_FLOOR = 0.30         # absolute floor: below this a "detection" is not a waveform
                        # match however quiet the day happened to be


def confirmed_rows():
    rows = [r for r in csv.DictReader(open(HARVEST)) if r["epoch"] == "100sps"]
    return [r for r in rows
            if float(r["snr"]) >= 3 and -1.2 < float(r["resid_log10"]) < 0.4
            and float(r["lo_hi"]) >= 1 and float(r.get("sustain_s") or 0) >= 2.0]


def day_file(t):
    hits = sorted(glob.glob(f"{ARCHIVE}/*.D.{t.year}.{t.julday:03d}.mseed"))
    return hits[-1] if hits else None


def load_day(path):
    """A day-file as one continuous 100 sps trace, or None."""
    st = read(path)
    try:
        st.merge(method=1, fill_value="interpolate")
    except Exception:
        rates = [tr.stats.sampling_rate for tr in st]
        keep = max(set(rates), key=rates.count)
        st = Stream([tr for tr in st if tr.stats.sampling_rate == keep])
        st.merge(method=1, fill_value="interpolate")
    tr = max(st, key=lambda t: t.stats.npts)
    if abs(tr.stats.sampling_rate - FS) > 0.5:
        return None
    tr.detrend("demean")
    tr.filter("bandpass", freqmin=BAND[0], freqmax=BAND[1], corners=4, zerophase=True)
    return tr


def cmd_build(a):
    rows = confirmed_rows()
    print(f"{len(rows)} confirmed events")
    out = {}
    for r in rows:
        o = UTCDateTime(r["origin"])
        f = day_file(o)
        if not f:
            print(f"  skip {r['origin'][:19]}: no day-file")
            continue
        tp, ts = float(r["tp_s"]), float(r["ts_s"])
        t0, t1 = o + tp - PRE_P, o + ts + POST_S
        st = read(f, starttime=t0 - 5, endtime=t1 + 5)
        tr = load_day_slice(st)
        if tr is None:
            print(f"  skip {r['origin'][:19]}: unusable segment")
            continue
        seg = tr.slice(t0, t1)
        n = int((t1 - t0) * FS)
        if seg.stats.npts < n * 0.9:
            print(f"  skip {r['origin'][:19]}: short ({seg.stats.npts}/{n})")
            continue
        key = r["origin"][:19]
        out[key] = np.asarray(seg.data, float)
        out[key + "|meta"] = np.array([r["mag"], r["dist_km"], r["place"], str(t0)])
    np.savez_compressed(TEMPLATES, **out)
    n = sum(1 for k in out if not k.endswith("|meta"))
    print(f"wrote {TEMPLATES}: {n} templates, "
          f"{np.mean([len(v)/FS for k, v in out.items() if not k.endswith('|meta')]):.1f} s mean")
    return 0


def load_day_slice(st):
    try:
        st.merge(method=1, fill_value="interpolate")
    except Exception:
        rates = [tr.stats.sampling_rate for tr in st]
        keep = max(set(rates), key=rates.count)
        st = Stream([tr for tr in st if tr.stats.sampling_rate == keep])
        st.merge(method=1, fill_value="interpolate")
    if not len(st):
        return None
    tr = max(st, key=lambda t: t.stats.npts)
    if abs(tr.stats.sampling_rate - FS) > 0.5:
        return None
    tr.detrend("demean")
    tr.filter("bandpass", freqmin=BAND[0], freqmax=BAND[1], corners=4, zerophase=True)
    return tr


def detect(day, templates, mad_k=MAD_K, verbose=False):
    """Every template against one day. Returns detection dicts."""
    data = np.asarray(day.data, float)
    t0 = day.stats.starttime
    hits = []
    for name, tmpl in templates.items():
        if len(tmpl) >= len(data):
            continue
        cc = correlate_template(data, tmpl, mode="valid", normalize="full")
        cc = np.nan_to_num(cc)
        med = np.median(cc)
        mad = np.median(np.abs(cc - med)) * 1.4826
        thr = max(med + mad_k * mad, CC_FLOOR)
        idx = np.flatnonzero(cc > thr)
        if not idx.size:
            continue
        # keep the local maximum of each run, then enforce a minimum separation
        sep = int(MIN_SEP_S * FS)
        order = idx[np.argsort(-cc[idx])]
        taken = []
        for i in order:
            if all(abs(i - j) >= sep for j in taken):
                taken.append(int(i))
        for i in sorted(taken):
            hits.append(dict(template=name, t=str(t0 + i / FS), cc=round(float(cc[i]), 4),
                             thr=round(float(thr), 4), mad=round(float(mad), 5)))
        if verbose:
            print(f"    {name}: thr {thr:.3f}, {len(taken)} hit(s), max cc {cc[idx].max():.3f}")
    return hits


def cmd_similarity(a):
    """Do our events resemble each other at all? The premise the method rests on.

    Cheap, and it is the test that should gate any scan: if no pair of templates
    correlates, no unknown event will correlate with one either, and a scan can only
    return noise dressed up as detections.
    """
    z = np.load(TEMPLATES, allow_pickle=True)
    names = [k for k in z.files if not k.endswith("|meta")]
    n = len(names)
    M = np.eye(n)
    for i, ai in enumerate(names):
        for j, bj in enumerate(names):
            if i == j:
                continue
            x, y = z[ai], z[bj]
            if len(y) >= len(x):
                x, y = y, x
            cc = np.nan_to_num(correlate_template(x, y, mode="valid", normalize="full"))
            M[i, j] = float(np.abs(cc).max()) if cc.size else 0.0
    off = M[~np.eye(n, dtype=bool)]
    print(f"{n} templates, {n*(n-1)} ordered pairs")
    print(f"  max off-diagonal cc : {off.max():.3f}")
    print(f"  median              : {np.median(off):.3f}")
    for thr in (0.4, 0.5, 0.6):
        print(f"  pairs above {thr}     : {(off > thr).sum()}")
    ok = off.max() >= 0.6
    print("\n  -> " + ("multiplets present; a scan is worth running"
                       if ok else
                       "NO multiplets. A scan will return noise only -- see the "
                       "docstring. Re-run as the catalogue grows."))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="cut templates from the confirmed events")
    sub.add_parser("similarity", help="do the templates resemble each other? run first")
    s = sub.add_parser("scan", help="correlate the templates through the archive")
    s.add_argument("--day", help="YYYY-MM-DD (default: every day-file)")
    s.add_argument("--all", action="store_true")
    s.add_argument("--out", help="write detections to this CSV")
    s.add_argument("--mad-k", type=float, default=MAD_K)
    s.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        return cmd_build(a)
    if a.cmd == "similarity":
        return cmd_similarity(a)

    z = np.load(TEMPLATES, allow_pickle=True)
    templates = {k: z[k] for k in z.files if not k.endswith("|meta")}
    print(f"{len(templates)} templates")
    files = ([day_file(UTCDateTime(a.day))] if a.day
             else sorted(glob.glob(f"{ARCHIVE}/*.mseed")))
    files = [f for f in files if f]
    allhits = []
    for f in files:
        day = load_day(f)
        if day is None:
            print(f"{os.path.basename(f)}: not 100 sps, skipped")
            continue
        print(f"{os.path.basename(f)} {day.stats.starttime} "
              f"({day.stats.npts/FS/3600:.1f} h)", flush=True)
        h = detect(day, templates, a.mad_k, a.verbose)
        print(f"  {len(h)} raw detection(s)", flush=True)
        allhits += h
    print(f"\n{len(allhits)} raw detections over {len(files)} file(s)")
    if a.out and allhits:
        with open(a.out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(allhits[0].keys()))
            w.writeheader(); w.writerows(allhits)
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

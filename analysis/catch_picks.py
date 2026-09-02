#!/usr/bin/env python3
"""catch_picks.py — measure the P onset for every featured catch, off the trace.

WHY THIS EXISTS SEPARATELY. quake_share.py is explicit that `--p` must be an onset you
actually picked, never one predicted from catalogue distance: predicting P from a
distance and then "deriving" that distance back from it confirms nothing. So the catch
images cannot simply be re-rendered with taup arrivals stuffed into --p.

WHAT IS AND IS NOT CIRCULAR. Using the predicted arrival to decide WHERE TO LOOK is not
circular; using it as the answer is. So taup supplies a search window and nothing else,
the pick itself comes from the envelope crossing a multiple of the pre-event noise, and
the residual (pick - prediction) is reported so the difference between the two is
visible rather than assumed. A pick that lands suspiciously close to the prediction on
every event would be a sign this had gone wrong.

THE PICK, in two stages. A CAUSAL band-pass; the arrival is located as the LARGEST
excursion in the search window, then an AIC picker finds its onset.

Largest, not first-over-a-threshold. The threshold version put the M4.2 Cloverdale at
5.5 s against the +9.06 s the catches page records independently, because it fired on
ordinary cultural spikes at 4.2x and 4.8x the median floor -- on that night the noise's
own p99 was 3.75x the median, so any threshold low enough to catch a weak arrival was
already below the loud end of the background. The real arrival was unmistakable when
looked at: 13 uV to 538 uV in half a second. An earthquake inside a window centred on
its own predicted arrival is the biggest thing there; that needs no threshold.

Both details matter and the first one bit me. The obvious filter, `sosfiltfilt`, is
ZERO-PHASE, so it smears a loud transient BACKWARDS as pre-ringing -- and walking back
down the envelope then follows that precursor to a pick that is too early. On the M4.2
Cloverdale, the loudest event on the page, that produced 6.81 s against the +9.06 s the
catches page already records from an independent measurement. Causal filtering has no
precursor to follow. (This is the same acausal-smearing trap that calfinder.py hit from
the other direction, where it lifted the trigger onset EARLY at high SNR.)

The refinement is the standard Akaike Information Criterion picker: over a window
bracketing the coarse trigger, the onset is the sample that best splits the series into
"noise before, signal after", i.e. argmin of

    AIC(k) = k*log(var(x[:k])) + (n-k-1)*log(var(x[k:]))

It needs no threshold, which is the point -- a threshold is a knob that quietly encodes
the answer you expected.

    python analysis/catch_picks.py                 # measure and print
    python analysis/catch_picks.py --write         # ...and save picks.json
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
from obspy import Stream, UTCDateTime, read

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "dashboard"))
import catches                                                   # noqa: E402

ARCHIVE = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "catch_picks.json")
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
BAND = (1.0, 15.0)
SEARCH = (-4.0, 4.0)      # around the taup arrival: where to LOOK, never the answer.
                          # Tight on purpose. At +-15 s the "loudest excursion" was
                          # often the S arrival rather than P -- San Leandro at 88 km
                          # has S about 12 s behind P and far louder -- which put four
                          # picks 5-9 s late. taup is good to ~1-2 s locally, so +-4 s
                          # brackets the true onset while leaving S outside it.
TRIG = 3.5                # the arrival must clear this x the noise floor to be picked
NOISE_WIN = (-120.0, -15.0)

# Picks already recorded by hand and referenced in the catches prose. These WIN over the
# automated picker, because the prose is built on them -- the Cloverdale +9.06 s is one
# of the picks that originally pinned this station's 5.19 km/s crustal velocity, and
# silently moving it would invalidate the paragraph that explains where 5.19 came from.
# The picker agrees to within 0.44 s there, which is corroboration rather than conflict.
MANUAL = {"2026-07-29-m4.2-cloverdale": 9.06}


def trace_for(o, lo, hi):
    hits = sorted(glob.glob(f"{ARCHIVE}/*.D.{o.year}.{o.julday:03d}.mseed"))
    if not hits:
        return None
    st = read(hits[-1], starttime=o + lo, endtime=o + hi)
    try:
        st.merge(method=1, fill_value="interpolate")
    except Exception:
        rates = [t.stats.sampling_rate for t in st]
        keep = max(set(rates), key=rates.count)
        st = Stream([t for t in st if t.stats.sampling_rate == keep])
        st.merge(method=1, fill_value="interpolate")
    if not len(st):
        return None
    tr = max(st, key=lambda t: t.stats.npts)
    return tr if abs(tr.stats.sampling_rate - 100.0) < 0.5 else None


def pick(origin, tp_pred):
    o = UTCDateTime(origin)
    tr = trace_for(o, NOISE_WIN[0] - 10, tp_pred + SEARCH[1] + 30)
    if tr is None:
        return None, "no 100 sps day-file covering it"
    fs = float(tr.stats.sampling_rate)
    from scipy import signal
    x = np.asarray(tr.data, float) * UV
    x -= np.median(x)
    sos = signal.butter(4, [BAND[0] / (fs / 2), BAND[1] / (fs / 2)], "bandpass", output="sos")
    y = signal.sosfilt(sos, x)                      # CAUSAL: no precursor to walk back into
    env = np.convolve(np.abs(y), np.ones(int(0.3 * fs)) / int(0.3 * fs), mode="same")
    rel = np.arange(len(y)) / fs + (tr.stats.starttime - o)

    nm = (rel >= NOISE_WIN[0]) & (rel <= NOISE_WIN[1])
    if nm.sum() < fs * 20:
        return None, "not enough pre-event noise to set a floor"
    floor = float(np.median(env[nm]))

    sm = np.flatnonzero((rel >= tp_pred + SEARCH[0]) & (rel <= tp_pred + SEARCH[1]))
    if not sm.size:
        return None, "search window falls outside the data"
    coarse = int(sm[int(np.argmax(env[sm]))])        # the arrival IS the loudest thing here
    snr = float(env[coarse]) / floor
    if snr < TRIG:
        return None, f"loudest excursion is only {snr:.1f}x the noise floor"
    # AIC refinement: onset lies just BEFORE the peak, so bracket back from it
    a0, a1 = max(0, coarse - int(4.0 * fs)), min(len(y), coarse + int(0.5 * fs))
    w = y[a0:a1]
    n = len(w)
    if n < 40:
        return None, "window too short to refine"
    aic = np.full(n, np.inf)
    for k in range(5, n - 5):
        v1, v2 = np.var(w[:k]), np.var(w[k:])
        if v1 > 0 and v2 > 0:
            aic[k] = k * np.log(v1) + (n - k - 1) * np.log(v2)
    i = a0 + int(np.argmin(aic))
    return {"t": round(float(rel[i]), 2), "floor_uv": round(floor, 3),
            "snr": round(snr, 1), "peak_t": round(float(rel[coarse]), 2)}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    print(f"{'catch':<32}{'taup':>7}{'PICK':>8}{'resid':>8}{'snr':>7}  note")
    picks, resids = {}, []
    for c in catches.CATCHES:
        stem = c["img"].rsplit(".", 1)[0]
        row = catches._BY_ORIGIN.get(c["origin"][:19]) or {}
        tp = row.get("tp_s")
        if tp is None:
            print(f"{stem[:30]:<32}{'--':>7}  not in the confirmed table"); continue
        p, err = pick(c["origin"], float(tp))
        if stem in MANUAL:
            auto = p["t"] if p else None
            p = {"t": MANUAL[stem], "source": "recorded",
                 "auto_t": auto, "floor_uv": (p or {}).get("floor_uv"),
                 "snr": (p or {}).get("snr", 0)}
            err = None
            if auto is not None:
                print(f"{stem[:30]:<32}{float(tp):>7.2f}{p['t']:>8.2f}"
                      f"{p['t']-float(tp):>+8.2f}{p['snr']:>7.1f}  recorded pick; "
                      f"picker said {auto:.2f} ({abs(auto-p['t']):.2f} s apart)")
                picks[stem] = dict(origin=c["origin"], tp_taup=round(float(tp), 2), **p)
                resids.append(p["t"] - float(tp))
                continue
        if p is None:
            print(f"{stem[:30]:<32}{float(tp):>7.2f}{'--':>8}{'':>8}{'':>7}  {err}"); continue
        r = p["t"] - float(tp)
        resids.append(r)
        p.setdefault("source", "picked")
        picks[stem] = dict(origin=c["origin"], tp_taup=round(float(tp), 2), **p)
        print(f"{stem[:30]:<32}{float(tp):>7.2f}{p['t']:>8.2f}{r:>+8.2f}"
              f"{p['snr']:>7.1f}")
    if resids:
        print(f"\nresidual (pick - taup): median {np.median(resids):+.2f} s, "
              f"spread {np.std(resids):.2f} s over {len(resids)} events")
        print("a residual that was ~0 everywhere would mean the pick was just echoing")
        print("the prediction; scatter is the sign it is measuring something.")
    if a.write and picks:
        with open(OUT, "w") as fh:
            json.dump(picks, fh, indent=2, sort_keys=True)
        print(f"\nwrote {len(picks)} picks -> {os.path.relpath(OUT, os.path.join(HERE,'..'))}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""catch_audio.py — pre-render the audio clip behind each catch's play button.

WHY STATIC FILES rather than an endpoint that reads the archive. The public dashboard
on apps02 has no day-files -- that is the whole reason the catch images are static PNGs
too -- so anything the Catches page needs must be a committed artefact, not a live
render. These clips follow the images exactly: generated here on the Mac, checked in,
served as bytes.

WHAT THE WINDOW IS. Read from the image's own `.geom.json` sidecar, so the clip and the
picture it sits under span EXACTLY the same seconds. That is what lets the playhead be a
cross-reference to the figure above rather than a decoration: same window, same axes box,
same time at the same x.

Before the sidecars existed this computed its own window, anchored to the taup arrival.

That distinction was not academic. The first version hunted for the envelope peak in a
generous window after the origin, on the reasoning that an earthquake is the loudest
thing near its own origin time. It is not, reliably: the Geysers M3.2 of 2026-08-12
came back with its "arrival" at +125.7 s and the M2.8 of 08-11 at +188.3 s, when P for a
43 km event is at 7.5 s. Both had simply found a louder truck later in the search
window -- the same failure that has bitten eventcheck and the harvest on this project
before, arriving by yet another door. Anchoring to a predicted arrival cannot be fooled
that way.

The energy hunt survives only as a fallback for a catch that is not in the table.

CLIP_S is 50 s, inside the 60 s session cap the player already enforces, and PRE_S of
lead-in matters more than it looks: it is what lets you hear the ordinary background
FIRST, so the arrival has something to arrive against.

    python analysis/catch_audio.py
    python analysis/catch_audio.py --only middletown
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
import catches                                            # noqa: E402

ARCHIVE = os.path.join(HERE, "data")
PICKS = (json.load(open(os.path.join(HERE, "catch_picks.json")))
         if os.path.exists(os.path.join(HERE, "catch_picks.json")) else {})
OUT_DIR = os.path.join(HERE, "..", "dashboard", "catches", "audio")
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
PRE_S, CLIP_S = 12.0, 50.0        # lead-in, then the whole clip length
SEARCH_S = 200.0                  # how far after origin to hunt for the arrival
BAND = (1.0, 15.0)


def _trace(o):
    hits = sorted(glob.glob(f"{ARCHIVE}/*.D.{o.year}.{o.julday:03d}.mseed"))
    if not hits:
        return None
    st = read(hits[-1], starttime=o - 60, endtime=o + SEARCH_S + CLIP_S)
    try:
        st.merge(method=1, fill_value="interpolate")
    except Exception:
        rates = [t.stats.sampling_rate for t in st]
        keep = max(set(rates), key=rates.count)
        st = Stream([t for t in st if t.stats.sampling_rate == keep])
        st.merge(method=1, fill_value="interpolate")
    return max(st, key=lambda t: t.stats.npts) if len(st) else None


def clip_for(origin, tp=None, window=None):
    o = UTCDateTime(origin)
    tr = _trace(o)
    if tr is None:
        return None, "no day-file"
    fs = float(tr.stats.sampling_rate)
    if abs(fs - 100.0) > 0.5:
        return None, f"not 100 sps ({fs})"
    x = np.asarray(tr.data, float) * UV
    x = x - np.median(x)
    from scipy import signal
    sos = signal.butter(4, [BAND[0] / (fs / 2), BAND[1] / (fs / 2)], "bandpass",
                        output="sos")
    y = signal.sosfiltfilt(sos, x)
    rel = np.arange(len(y)) / fs + (tr.stats.starttime - o)
    env = np.convolve(np.abs(y), np.ones(int(fs)) / int(fs), mode="same")
    if window is not None:
        t0, t1 = window
        m = (rel >= t0) & (rel < t1)
        seg = y[m]
        want = int((t1 - t0) * fs)
        if len(seg) < want * 0.8:
            return None, f"short window ({len(seg)}/{want})"
        ei = env[m]
        return {"uv": [round(float(v), 1) for v in seg], "fs": fs,
                "t0": round(t0, 3), "t1": round(t1, 3), "anchor": "geom",
                "pre_s": None,
                "peak_in_clip_s": round(float(int(np.argmax(ei)) / fs), 2),
                "peak_uv": round(float(np.max(np.abs(seg))), 1)}, None
    if tp is not None:
        t_anchor, how = float(tp), "tp"
    else:
        hunt = (rel >= 0) & (rel <= SEARCH_S)
        if not hunt.any():
            return None, "no samples after origin"
        t_anchor, how = float(rel[hunt][int(np.argmax(env[hunt]))]), "energy"
    t0 = t_anchor - PRE_S
    m = (rel >= t0) & (rel < t0 + CLIP_S)
    seg = y[m]
    want = int(CLIP_S * fs)
    if len(seg) < want * 0.8:
        return None, f"short window ({len(seg)}/{want})"
    ei = env[m]
    return {"uv": [round(float(v), 1) for v in seg], "fs": fs,
            "anchor_s": round(t_anchor, 2), "anchor": how, "pre_s": PRE_S,
            "peak_in_clip_s": round(float(np.arange(len(ei))[int(np.argmax(ei))] / fs), 2),
            "peak_uv": round(float(np.max(np.abs(seg))), 1)}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="substring of the image name")
    a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    ok = 0
    for c in catches.CATCHES:
        if a.only and a.only not in c["img"]:
            continue
        stem = c["img"].rsplit(".", 1)[0]
        row = catches._BY_ORIGIN.get(c["origin"][:19]) or {}
        gp = os.path.join(OUT_DIR, "..", stem + ".geom.json")
        win, geom = None, None
        if os.path.exists(gp):
            geom = json.load(open(gp))
            win = (geom["t0"], geom["t1"])
        d, err = clip_for(c["origin"], row.get("tp_s"), win)
        if d is None:
            print(f"  SKIP {stem}: {err}")
            continue
        # Carry the figure's own geometry into the clip, so the page can inset the
        # waveform to exactly the axes box of the image above it and put the P marker
        # where the image puts it. Hardcoding 0.075/0.96 in the CSS would work today and
        # silently drift the day the figure layout changes.
        if geom:
            d["ax_x0"], d["ax_x1"] = geom["ax_x0"], geom["ax_x1"]
            pk = PICKS.get(stem, {}).get("t")
            if pk is not None:
                d["p_frac"] = round((pk - geom["t0"]) / (geom["t1"] - geom["t0"]), 5)
            # The S marker is the harvest's PREDICTED S (ts_s, from the local Vp/Vs), not
            # a pick -- there is no S picker -- so the page draws it dashed and says so.
            ts = row.get("ts_s")
            if ts not in (None, ""):
                sf = (float(ts) - geom["t0"]) / (geom["t1"] - geom["t0"])
                if 0.0 < sf < 1.0:
                    d["s_frac"] = round(sf, 5)
        p = os.path.join(OUT_DIR, stem + ".json")
        with open(p, "w") as fh:
            json.dump(d, fh, separators=(",", ":"))
        ok += 1
        w = (f"{d['t0']:+.1f}..{d['t1']:+.1f}s" if d.get("anchor") == "geom"
             else f"anchor {d.get('anchor')}")
        print(f"  {stem[:30]:<32} {w:>18}  peak {d['peak_uv']:7.1f} uV at "
              f"+{d['peak_in_clip_s']:5.2f}s into clip  {os.path.getsize(p)/1024:4.0f} KB")
    print(f"\n{ok} clip(s) -> {os.path.relpath(OUT_DIR, os.path.join(HERE,'..'))}")


if __name__ == "__main__":
    main()

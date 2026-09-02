#!/usr/bin/env python3
"""render_catches.py — re-render every featured catch image on ONE consistent frame.

WHY. The catch images were made ad hoc over weeks: different widths (1400 and 1150 px),
different time windows, different arguments. That is fine for a set of standalone
figures and fatal for anything that wants to overlay them -- the Catches page's playhead
cannot line up with a frame it has to guess at. A detector run over the old set on
2026-09-02 returned four outright failures and three impossible answers (the t=0 line
placed AFTER the P line).

THE FRAME. Every image spans [pick - PRE_P, pick + POST_P], anchored on that event's own
MEASURED P onset rather than on origin time. Anchoring on origin cannot work across this
set: Santa Rosa's P is 2.2 s after origin and Petrolia's is 45.2 s, so no fixed
origin-relative window frames both. Anchoring on P gives every catch the same shape --
lead-in, arrival, coda -- and keeps the span inside the 60 s cap the audio player
enforces, so image and clip can share one window exactly.

THE PICKS come from catch_picks.py and are MEASURED, never predicted; quake_share.py is
explicit that --p must be an onset picked off the trace. Where a pick was already
recorded by hand and referenced in the prose, that one wins.

    python analysis/render_catches.py --dry-run
    python analysis/render_catches.py
"""
import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "dashboard"))
import catches                                                   # noqa: E402

PICKS = os.path.join(HERE, "catch_picks.json")
OUTDIR = os.path.join(HERE, "..", "dashboard", "catches")
ARCHIVE = os.path.join(HERE, "data")
PRE_P, POST_P = 10.0, 40.0          # the shared frame, relative to the measured P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    picks = json.load(open(PICKS))
    from obspy import UTCDateTime
    done = skipped = 0
    for c in catches.CATCHES:
        stem = c["img"].rsplit(".", 1)[0]
        if a.only and a.only not in stem:
            continue
        p = picks.get(stem)
        if not p:
            print(f"  SKIP {stem}: no measured pick"); skipped += 1; continue
        o = UTCDateTime(c["origin"])
        day = sorted(glob.glob(f"{ARCHIVE}/*.D.{o.year}.{o.julday:03d}.mseed"))
        if not day:
            print(f"  SKIP {stem}: no day-file"); skipped += 1; continue
        pre, post = PRE_P - p["t"], p["t"] + POST_P
        cmd = [sys.executable, os.path.join(HERE, "quake_share.py"),
               "--mseed", day[-1], "--usgs-near", str(o), "--spectrogram",
               "--pre", f"{pre:.2f}", "--post", f"{post:.2f}",
               "--p", f"{p['t']:.2f}",
               "--out", os.path.join(OUTDIR, stem + ".png")]
        print(f"  {stem[:34]:<36} P={p['t']:>6.2f} ({p.get('source','picked')})  "
              f"window {-pre:+.1f}..{post:+.1f}s rel origin")
        if a.dry_run:
            continue
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"     FAILED: {(r.stderr or r.stdout).strip().splitlines()[-1][:110]}")
            skipped += 1
        else:
            done += 1
    print(f"\n{done} rendered, {skipped} skipped")


if __name__ == "__main__":
    main()

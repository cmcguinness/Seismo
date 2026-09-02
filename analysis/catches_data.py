#!/usr/bin/env python3
"""catches_data.py — the Catches page's table, as data rather than prose.

Writes dashboard/catches/confirmed.json: one row per catalogue event that
detection_map.py counts as confirmed (the same filter that draws the range map, so the
table and the map can never disagree about what is a catch), joined with the NP.1835
ratios from refstation.json where refstation_compare.py has produced one.

catches.py reads this file to build the summary table and the stat strip on each
featured catch. Nothing on that page is hand-typed from the harvest any more -- the
count went stale twice on 2026-09-02 alone when it was.

    analysis/.venv/bin/python analysis/catches_data.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detection_map import EXCLUDE_FROM_FIT, calibrate      # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dashboard", "catches")
REF_JSON = os.path.join(OUT, "refstation.json")
CONF_JSON = os.path.join(OUT, "confirmed.json")

# Which of the harvest's numbers the page shows. Rounded here so the page does no
# arithmetic; anything derived belongs in the analysis, not the dashboard.
FIELDS = dict(mag=("mag", 2), dist_km=("dist_km", 1), depth_km=("depth_km", 1),
              peak_uv=("peak_1_15", 1), floor_uv=("pre_1_15", 2), snr=("snr", 1),
              tp_s=("tp_s", 2), sustain_s=("sustain_s", 1), lo_hi=("lo_hi", 2),
              resid_log10=("resid_log10", 2))


def main():
    cal = calibrate()
    try:
        with open(REF_JSON) as fh:
            ref = json.load(fh)
    except FileNotFoundError:
        ref = {}
    rows = []
    # The fit's exclusions (Petrolia) are confirmed catches that are kept out of the
    # range calibration; they belong in the table, flagged, not hidden.
    import csv
    from detection_map import CSV
    extra = [r for r in csv.DictReader(open(CSV))
             if r["origin"][:19] in EXCLUDE_FROM_FIT and r["epoch"] == "100sps"]
    for r in cal["conf"] + extra:
        key = r["origin"][:19]
        row = dict(origin=r["origin"], place=r["place"], az=r["az"],
                   triggered=r["triggered"] == "1",
                   in_fit=key not in EXCLUDE_FROM_FIT)
        for name, (col, nd) in FIELDS.items():
            try:
                row[name] = round(float(r[col]), nd)
            except (ValueError, KeyError):
                row[name] = None
        rr = ref.get(key)
        if rr:
            row["ref"] = dict(ratio_rms=rr["ratio_rms"], ratio_peak=rr["ratio_peak"],
                              ref_ok=rr["ref_ok"], amp_epoch_ok=rr["amp_epoch_ok"],
                              img=rr.get("img"))
        rows.append(row)
    rows.sort(key=lambda r: r["origin"], reverse=True)

    # Headline numbers for the reference section: the anchors' median, over rows the
    # reference could actually see, inside the calibration's amplitude epoch.
    good = [r["ref"]["ratio_rms"] for r in rows
            if r.get("ref") and r["ref"]["ref_ok"] and r["ref"]["amp_epoch_ok"]]
    import statistics
    summary = dict(n_conf=int(cal["n_conf"]), reach_km=float(cal["reach"]),
                   n_ref=len(good),
                   ref_median=round(statistics.median(good), 2) if good else None,
                   ref_min=round(min(good), 2) if good else None,
                   ref_max=round(max(good), 2) if good else None,
                   n_ref_all=sum(1 for r in rows if r.get("ref")))
    with open(CONF_JSON, "w") as fh:
        json.dump(dict(summary=summary, events=rows), fh, indent=1)
    print(f"wrote {CONF_JSON}: {len(rows)} events, {summary['n_ref_all']} compared to "
          f"NP.1835, {summary['n_ref']} usable, median residual {summary['ref_median']}x")


if __name__ == "__main__":
    main()

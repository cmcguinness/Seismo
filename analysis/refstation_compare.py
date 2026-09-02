#!/usr/bin/env python3
"""refstation_compare.py — side-by-side records: OAKM1 against USGS NP.1835.

The Catches page shows what this station recorded. This puts the same seconds from the
professional strong-motion instrument 1.64 km away next to it, on the same axes and in
the same units, so a reader (or a network operator) can judge the station against a
reference rather than against prose.

Method is refstation.py's, unchanged: NP.1835 HNZ from NCEDC with its response removed
to velocity; ours converted with the PROVISIONAL sensitivity (9.0 V/(m/s), itself
measured against this reference); both band-passed to 5-15 Hz, above the geophone's
4.5 Hz corner where no response model is needed on our side. If the calibration is right
the two traces sit on top of each other and the residual ratio printed on the figure is
~1. The signal window is the harvest's own P/S box for the event (event_harvest.csv), so
the comparison uses the same seconds the detection statistics do.

Two outputs, both under dashboard/catches/:
  ref-<date>-<slug>.png   one figure per requested event (the featured catches)
  refstation.json         per-origin ratios for EVERY event compared, figure or not,
                          read by catches_data.py into the page's table

    analysis/.venv/bin/python analysis/refstation_compare.py 2026-09-02T03:49:01 ...
    analysis/.venv/bin/python analysis/refstation_compare.py --harvest   # ratios only,
                                          every confirmed 100 sps event, no figures

Two honesty flags travel with each ratio: `ref_ok` (the reference was above its own
noise floor, refstation.REF_MIN_RMS -- below it the ratio is meaningless and the figure
shows the accelerometer measuring itself) and `amp_epoch_ok` (no amplitude boundary in
analysis/epochs.py between the event and the calibration anchors, so the number is
comparable to the 3.2x in use). Neither flag suppresses the figure: a strong-motion
instrument being deaf to an M1.8 that a geophone hears at 67x SNR is itself the point.
"""
import argparse
import csv
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import epochs                                                   # noqa: E402
from refstation import (BAND, EFFECTIVE_SENS, PROVISIONAL_FACTOR, REF, REF_MIN_RMS,  # noqa: E402
                        UV_PER_COUNT, reference)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CSV = os.path.join(HERE, "event_harvest.csv")
OUT_DIR = os.path.join(os.path.dirname(HERE), "dashboard", "catches")
JSON_OUT = os.path.join(OUT_DIR, "refstation.json")
ANCHOR = "2026-08-11T21:35:14"            # first of the anchors the 3.2x was fitted on
STATION = os.environ.get("SEISMO_STATION", "OAKM1")

TEAL, INK, RED, BLUE, MUT = "#2f6f6b", "#16211f", "#c0392b", "#2c6e9b", "#6b7775"


def harvest_row(origin):
    """The harvest's row for this origin (matched to the second), or None."""
    key = origin[:19]
    with open(CSV) as fh:
        for r in csv.DictReader(fh):
            if r["origin"][:19] == key:
                return r
    return None


def our_trace(o, t0, t1):
    """Our record around [t0, t1] from whichever day-file(s) cover it, merged.

    Day-files changed SEED id at the 2026-08-30 cutover (XX.OAKMT -> SS.OAKM1) and both
    files exist for that day, so read every file for the julian day, keep the traces
    that overlap the window, and unify the id before merging.
    """
    from obspy import Stream, read
    files = sorted(glob.glob(os.path.join(DATA, f"*.D.{o.year}.{o.julday:03d}.mseed")))
    if not files:
        raise FileNotFoundError(f"no day-file in analysis/data for {o.date} (julday {o.julday})")
    st = Stream()
    for f in files:
        st += read(f, starttime=t0, endtime=t1)
    if not len(st):
        raise ValueError(f"day-file(s) hold no data in {t0}..{t1}")
    fs = float(st[0].stats.sampling_rate)
    if abs(fs - 100.0) > 1.0:
        raise ValueError(f"day-file is {fs:g} sps, not 100 -- pre-cutover epoch, not comparable")
    for tr in st:
        tr.id = f"SS.{STATION}.00.EHZ"
        tr.stats.sampling_rate = 100.0
    st.merge(method=1, fill_value="interpolate")
    return st[0]


def compare(origin, row, pre=10.0, post_extra=15.0):
    """Fetch, filter and window both records. Returns a dict of arrays + numbers."""
    from obspy import UTCDateTime
    o = UTCDateTime(origin)
    tp, ts = float(row["tp_s"]), float(row["ts_s"])
    w0, w1 = tp - 2.0, ts + 22.0                      # the harvest's P/S box
    t0, t1 = o - pre, o + w1 + post_extra
    ref = reference(o - pre - 60, t1 + 60)            # generous: the taper needs margin
    mine = our_trace(o, t0 - 60, t1 + 60)
    for tr in (ref, mine):
        tr.detrend("demean")
        tr.filter("bandpass", freqmin=BAND[0], freqmax=BAND[1], corners=4, zerophase=True)
        tr.trim(t0, t1)
    r_t = ref.times(reftime=o)
    r_v = ref.data.astype(float) * 1e6                                    # um/s, true
    m_t = mine.times(reftime=o)
    m_v = mine.data.astype(float) * UV_PER_COUNT / EFFECTIVE_SENS         # uV -> um/s
    rm = (r_t >= w0) & (r_t <= w1)
    mm = (m_t >= w0) & (m_t <= w1)
    if rm.sum() < 100 or mm.sum() < 100:
        raise ValueError("too little overlapping data in the signal window")
    r_rms, m_rms = float(r_v[rm].std()), float(m_v[mm].std())
    r_pk, m_pk = float(np.abs(r_v[rm]).max()), float(np.abs(m_v[mm]).max())
    # pre-event floor of each, same length window before the P box
    rpre = (r_t >= w0 - 12) & (r_t < w0 - 2)
    mpre = (m_t >= w0 - 12) & (m_t < w0 - 2)
    r_floor = float(r_v[rpre].std()) if rpre.sum() > 50 else float("nan")
    m_floor = float(m_v[mpre].std()) if mpre.sum() > 50 else float("nan")
    # The reference is usable when it is above refstation's absolute floor AND clearly
    # above its own pre-event level that night -- an accelerometer's floor moves with
    # the traffic just as ours does, and a fixed constant passed events where the
    # "signal" window was 1.2x the seconds before it.
    # RMS over a long far-field window dilutes a brief Sn burst (Petrolia: 60 s window,
    # 3 s of signal), so a clear peak counts as well -- noise peaks run ~3-4x its RMS.
    ref_ok = (r_rms * 1e-6) >= REF_MIN_RMS and (
        not np.isfinite(r_floor) or r_rms >= 2.5 * r_floor or r_pk >= 6.0 * r_floor)
    return dict(o=o, tp=tp, ts=ts, w0=w0, w1=w1, r_t=r_t, r_v=r_v, m_t=m_t, m_v=m_v,
                r_rms=r_rms, m_rms=m_rms, r_pk=r_pk, m_pk=m_pk,
                r_floor=r_floor, m_floor=m_floor,
                ratio_rms=r_rms / m_rms, ratio_pk=r_pk / m_pk, ref_ok=ref_ok,
                amp_epoch_ok=not epochs.crossed(ANCHOR, origin, "amplitude"))


def slug(row):
    place = re.sub(r"^\d+ km [NSEW]+ of ", "", row["place"]).split(",")[0]
    place = re.sub(r"[^a-z0-9]+", "-", place.lower()).strip("-")
    return f"{row['origin'][:10]}-m{float(row['mag']):.1f}-{place}"


def envelope(x, fs, s=1.0):
    n = max(1, int(s * fs))
    return np.convolve(np.abs(x), np.ones(n) / n, mode="same")


def figure(res, row, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#d5dbda"})

    mag, place, dist = float(row["mag"]), row["place"], float(row["dist_km"])
    fig, axes = plt.subplots(3, 1, figsize=(12.0, 8.4), dpi=100, sharex=True,
                             gridspec_kw=dict(height_ratios=[1, 1, 0.8], hspace=0.12))
    ymax = 1.15 * max(res["r_pk"], res["m_pk"])
    for ax, t, v, col, label, rms in (
            (axes[0], res["r_t"], res["r_v"], BLUE,
             f"NP.1835 · USGS strong-motion, 1.64 km away · response removed to velocity",
             res["r_rms"]),
            (axes[1], res["m_t"], res["m_v"], TEAL,
             f"SS.{STATION} · this station · counts × provisional 9.0 V/(m/s)",
             res["m_rms"])):
        ax.plot(t, v, color=col, lw=0.7)
        ax.set_ylim(-ymax, ymax)
        ax.axvspan(res["w0"], res["w1"], color="#000", alpha=0.035, lw=0)
        ax.set_ylabel("µm/s")
        ax.text(0.01, 0.95, label, transform=ax.transAxes, va="top", fontsize=10, color=INK)
        ax.text(0.99, 0.95, f"RMS in window {rms:.2f} µm/s", transform=ax.transAxes,
                va="top", ha="right", fontsize=9, color=MUT)
        for x, name in ((res["tp"], "P pred."), (res["ts"], "S pred.")):
            ax.axvline(x, color=RED, lw=0.8, ls=":", alpha=0.8)
            ax.text(x, -ymax * 0.92, f" {name}", color=RED, fontsize=8, va="bottom")
    ax = axes[2]
    ax.plot(res["r_t"], envelope(res["r_v"], 100.0), color=BLUE, lw=1.2, label="NP.1835")
    ax.plot(res["m_t"], envelope(res["m_v"], 100.0), color=TEAL, lw=1.2, label=f"SS.{STATION}")
    ax.set_yscale("log")
    lo = max(1e-3, 0.5 * min(np.nanmin(envelope(res["r_v"], 100.0)[100:-100]),
                             np.nanmin(envelope(res["m_v"], 100.0)[100:-100])))
    ax.set_ylim(lo, 2 * ymax)
    ax.axvspan(res["w0"], res["w1"], color="#000", alpha=0.035, lw=0)
    ax.set_ylabel("1 s envelope, µm/s")
    ax.set_xlabel("seconds after origin")
    ax.legend(loc="upper right", fontsize=9, frameon=False)
    ax.text(0.01, 0.95, "envelopes overlaid: the calibration says these should coincide",
            transform=ax.transAxes, va="top", fontsize=9, color=MUT)
    for a in axes:
        a.grid(True, color="#e6ebea", lw=0.5)
        a.set_xlim(res["r_t"][0], res["r_t"][-1])

    verdict = (f"ratio in window (5–15 Hz): RMS {res['ratio_rms']:.2f}×, "
               f"peak {res['ratio_pk']:.2f}× (1.0 = calibration exact)")
    notes = []
    if not res["ref_ok"]:
        notes.append("reference at its own noise floor — ratio not meaningful")
    if not res["amp_epoch_ok"]:
        notes.append("earlier front end than the calibration anchors — different amplitude epoch")
    fig.suptitle(f"M{mag:.1f} · {place} · {row['origin'][:19].replace('T', ' ')} UTC · "
                 f"{dist:.0f} km", fontsize=13, color=INK, x=0.075, ha="left", y=0.98)
    fig.text(0.075, 0.945, f"{BAND[0]:g}–{BAND[1]:g} Hz band, both instruments · "
             "shaded = the harvest's P/S window around the predicted arrivals",
             fontsize=9.5, color=MUT)
    fig.text(0.075, 0.92, verdict + ("" if not notes else " · " + " · ".join(notes)),
             fontsize=9.5, color=RED if notes else MUT)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.885, bottom=0.075)
    fig.savefig(out)
    plt.close(fig)


def load_json():
    try:
        with open(JSON_OUT) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def record(store, origin, row, res, img):
    store[origin[:19]] = dict(
        origin=row["origin"], mag=float(row["mag"]), place=row["place"],
        dist_km=float(row["dist_km"]), img=img, band=list(BAND),
        ratio_rms=round(res["ratio_rms"], 3), ratio_peak=round(res["ratio_pk"], 3),
        ref_rms_ums=round(res["r_rms"], 4), our_rms_ums=round(res["m_rms"], 4),
        ref_peak_ums=round(res["r_pk"], 3), our_peak_ums=round(res["m_pk"], 3),
        ref_floor_ums=round(res["r_floor"], 4), our_floor_ums=round(res["m_floor"], 4),
        ref_ok=bool(res["ref_ok"]), amp_epoch_ok=bool(res["amp_epoch_ok"]),
        sens_v_per_ms=round(EFFECTIVE_SENS, 2), provisional_factor=PROVISIONAL_FACTOR,
        ref_id=".".join(REF))


def confirmed_origins():
    """Every harvest row detection_map.py counts as confirmed, 100 sps epoch only."""
    from detection_map import calibrate
    return [r["origin"] for r in calibrate()["conf"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("origins", nargs="*", help="origin times (UTC ISO) to render figures for")
    ap.add_argument("--harvest", action="store_true",
                    help="ratios only (no figures) for every confirmed event in the harvest")
    ap.add_argument("--out-dir", default=OUT_DIR)
    args = ap.parse_args()
    store = load_json()
    todo = [(o, True) for o in args.origins]
    if args.harvest:
        todo += [(o, False) for o in confirmed_origins() if o[:19] not in {t[0][:19] for t in todo}]
    if not todo:
        ap.error("give origin times, or --harvest")
    for origin, want_fig in todo:
        row = harvest_row(origin)
        if row is None:
            print(f"{origin}: not in event_harvest.csv -- re-run harvest_events.py"); continue
        label = f"M{float(row['mag']):.1f} {row['place']} {row['origin'][:19]}"
        try:
            res = compare(origin, row)
        except Exception as e:
            print(f"{label}: skipped: {type(e).__name__}: {str(e)[:100]}"); continue
        img = None
        if want_fig:
            img = f"ref-{slug(row)}.png"
            figure(res, row, os.path.join(args.out_dir, img))
        elif origin[:19] in store:
            img = store[origin[:19]].get("img")
        record(store, origin, row, res, img)
        flags = ("" if res["ref_ok"] else " [ref at floor]") + ("" if res["amp_epoch_ok"] else " [amp epoch]")
        print(f"{label}: ref {res['r_rms']:.3f} / ours {res['m_rms']:.3f} um/s RMS -> "
              f"{res['ratio_rms']:.2f}x (peak {res['ratio_pk']:.2f}x){flags}"
              + (f"  -> {img}" if want_fig else ""))
    with open(JSON_OUT, "w") as fh:
        json.dump(dict(sorted(store.items())), fh, indent=1)
    print(f"wrote {JSON_OUT} ({len(store)} events)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""test_dc_watch.py — fixtures for the DC watchdog. Plain script, no pytest.

    python test_dc_watch.py

The thresholds in `dc_watch` are tuned against the station's real behaviour, which
means they are exactly the kind of number that gets "improved" later by someone
reasoning from first principles. This file is the argument against that: every case
here is a thing that actually happens (or actually happened), and two of them caught
real mistakes when the watchdog was written --

  * scaling the step test on the MEDIAN hourly move made an ordinary fast-warming
    evening read as a step (the "hot day" fixtures);
  * measuring excursion from the CENTRE of the band spent most of the margin on the
    daily cycle the watchdog is supposed to ignore (the ratios printed per case).

Uses the real DC series from `analysis/data/subhz.csv` when it is there (that dir is
gitignored, so it usually is not on a fresh clone) and falls back to a synthetic
diurnal series with the same shape: ~3800 counts peak-to-peak on ~324k, an evening
ramp an order of magnitude steeper than the small hours.
"""
import csv
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dc_watch                                                    # noqa: E402

CENTRE = 324229.0                # the station's DC level, counts (~3.02 mV)
REAL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "analysis", "data", "subhz.csv")


def real_series():
    """[(t0, dc)] from the 2026-08 reduction, which is day-detrended -- put the
    absolute level back so the fixtures look like what heli_build now stores."""
    rows = [(float(r["t0"]), float(r["dc_counts"]) + CENTRE)
            for r in csv.DictReader(open(REAL))]
    return sorted(rows)


def synthetic_series(days=8, t_end=1787000000.0):
    """Same shape, no data file: a diurnal cycle that warms fast in the evening and
    drifts slowly through the small hours, plus a little noise."""
    rng = np.random.default_rng(11)
    n = int(days * 96)
    t = t_end - np.arange(n)[::-1] * 900.0
    hod = (t / 3600.0) % 24
    # skewed cycle: slow decay overnight, steep rise in the late afternoon
    cycle = 1900 * np.sin(2 * np.pi * (hod - 4) / 24) ** 3
    return list(zip(t, CENTRE + cycle + rng.normal(0, 60, n)))


def make(rows, tag):
    d = tempfile.mkdtemp(prefix="heli_" + tag + "_")
    for t0, dc in rows:
        np.savez(os.path.join(d, "heli.%.0f.npz" % t0),
                 t0=np.float64(t0), dc=np.float32(dc), env=np.float32(100.0))
    dc_watch._cache.clear()
    return d


FAILS = []


def run(label, rows, now, expect):
    """`expect` may be a tuple: for an offset near the alarm threshold, WHICH alarm
    fires depends on whether it reads as sudden (STEP) or sustained (EXCURSION), and
    that turns on the exact swing of the fixture. The guarantee under test is that it
    alarms at all -- pinning the label there would be testing the fixture."""
    d = make(rows, label.replace(" ", "_")[:20])
    got = dc_watch.check(d, now=now)
    want = expect if isinstance(expect, tuple) else (expect,)
    ok = got["state"] in want
    FAILS.append(None if ok else f"{label}: {got['state']} not in {want}")
    margin = ""
    if "excess" in got:
        margin = f"[excess {got['excess']:7.2f}  step {got['step'] / got['typical']:5.2f}] "
    print(f"[{'ok ' if ok else 'FAIL'}] {label:<30} -> {got['state']:<9} {margin}")
    shutil.rmtree(d)
    return got


def main():
    src = "analysis/data/subhz.csv" if os.path.exists(REAL) else "synthetic"
    rows = real_series() if os.path.exists(REAL) else synthetic_series()
    now = rows[-1][0] + 900
    week = [r for r in rows if r[0] >= now - 7 * 86400]
    print(f"fixture: {src}, {len(week)} intervals, {(week[-1][0] - week[0][0]) / 3600:.0f} h\n")

    run("healthy week", week, now, "OK")
    run("only 6 h of history", week[-24:], now, "WARMING")
    run("no fresh data (3 h old)", week, now + 3 * 3600, "STALE")

    # 2026-07-31: DC path lost on an input leg, baseline to -2.2M counts, false EVENTs
    # for hours. The whole reason this module exists; must be unmissable.
    faulted = week[:-4] + [(t, -2_200_000.0) for t, _ in week[-4:]]
    run("2026-07-31 fault replay", faulted, now, "EXCURSION")

    # Sensitivity floor. The station's own wander reaches ~2000 counts/h at its
    # steepest, so anything under a few thousand counts must NOT alarm -- and need
    # not, since the fault it guards against is 2.5 MILLION counts away.
    for delta, expect in ((300, "OK"), (1500, "OK"), (4000, "OK"),
                          (9000, ("EXCURSION", "STEP")), (20000, "EXCURSION")):
        run(f"offset {delta:+d} counts",
            week[:-4] + [(t, v + delta) for t, v in week[-4:]], now, expect)

    # Weather, not a fault: a day whose swing is much larger than the week's. This is
    # the false-alarm case that matters, because it is the one that recurs.
    for mult in (1.8, 2.5):
        hot = [(t, (v - CENTRE) * mult + CENTRE) if t > now - 86400 else (t, v)
               for t, v in week]
        run(f"unusually hot day ({mult}x swing)", hot, now, "OK")

    # --- notification hygiene: fire on transitions, not on every poll ------------
    print()
    dc_watch.STATE = os.path.join(tempfile.mkdtemp(prefix="dcstate_"), "state.json")
    sent = []
    dc_watch._notify = lambda title, *a, **k: sent.append(title) or True

    def shift(rs, dt_s):
        return [(t + dt_s, v) for t, v in rs]

    def fault(rs):
        return rs[:-4] + [(t, -2_200_000.0) for t, _ in rs[-4:]]

    # The fixture has to age with the clock, or the watchdog correctly reports STALE
    # rather than the fault -- which is what it did on this test's first run.
    dirs = [(make(week, "p_ok"), now, "OK"),
            (make(week, "p_ok2"), now, "OK"),
            (make(fault(week), "p_bad"), now, "EXCURSION"),
            (make(fault(week), "p_bad2"), now + 60, "EXCURSION"),
            (make(fault(shift(week, 13 * 3600)), "p_bad13"), now + 13 * 3600, "EXCURSION"),
            (make(shift(week, 14 * 3600), "p_ok14"), now + 14 * 3600, "OK")]
    notes = []
    for d, when, expect in dirs:
        dc_watch._cache.clear()
        got = dc_watch.poll(d, now=when)
        notes.append(got["notified"])
        ok = got["state"] == expect
        FAILS.append(None if ok else f"poll {expect}: got {got['state']}")
        print(f"[{'ok ' if ok else 'FAIL'}] poll -> {got['state']:<9} notified={got['notified']}")
        shutil.rmtree(d)
    want = [False, False, True, False, True, True]   # entry, silence, reminder, recovery
    FAILS.append(None if notes == want else f"notification pattern {notes} != {want}")
    print(f"[{'ok ' if notes == want else 'FAIL'}] notifications {notes}  sent={sent}")

    bad = [f for f in FAILS if f]
    print("\n" + (f"{len(bad)} FAILURE(S):\n  " + "\n  ".join(bad) if bad
                  else f"all {len(FAILS)} checks passed"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

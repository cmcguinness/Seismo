#!/usr/bin/env python3
"""floor_verdict.py — is the sub-corner band QUIET, or are we DEAF?

Compares a SHORTED night (the shorting box in place of the geophone,
`parts/shorting_box.py`) against ordinary live nights over the same clock hours.
With no sensor, whatever the recorder still sees is the instrument and the cable.
Everything above that floor, on a live night, is ground.

    analysis/.venv/bin/python analysis/floor_verdict.py <shorted_jday> <live_jday>...

Day-files must already be in analysis/data (scp them from pi5, as eventcheck.py does).

=============================================================================
PRE-REGISTERED, 2026-09-22, BEFORE THE SHORTED NIGHT WAS RECORDED.
=============================================================================
This exists to satisfy condition 2 of the detection-band decision rule in
`harvest_events.py` ("the shorted-input floor test has run and says the sub-corner
band is quiet rather than deaf"), which is judged on 2026-12-07. A verdict rule
chosen after seeing the number is worth very little, so the thresholds below are
fixed now, while the answer is unknown, and are not to be tuned afterwards.

THE MEASURE.  Median-Welch PSD over the same quiet window (default 07:00-12:00 UTC
= 00:00-05:00 PDT), integrated over 3-7 Hz -- the band `harvest_events.py` has
reserved. Median rather than mean, because one loud minute hijacks a mean Welch
(see "analysis window traps"). Live nights are combined by taking the MEDIAN of
their band powers, so a single anomalous night cannot carry the verdict.

    excess_dB = 10 * log10( P_live(3-7 Hz) / P_shorted(3-7 Hz) )

THE RULE.
    excess >= 10.0 dB  -> QUIET. The instrument contributes <= 10% of the power we
                          record in this band; what we detect there is ground, and
                          the band's apparent advantage has a mechanism behind it.
    excess <= 3.0 dB   -> DEAF. The instrument is at least half the power. Any gain
                          from re-banding here is an artifact of not hearing, and
                          the band hypothesis should be abandoned on this evidence.
    in between         -> AMBIGUOUS. Emit the number, change no verdict, and say so.
                          Do NOT go hunting for a sub-band where it looks better.

Three outcomes and an explicit undecided band, deliberately: the same shape as the
band rule itself, because a two-way rule invites reading a marginal result as a win.

WHAT THIS DOES NOT DECIDE.  Only condition 2. The band change also needs its held-out
detection rate and a clean re-harvest gate, and nothing here licenses touching
`resid_log10` or anything the calibration reads -- that needs f0 and zeta measured.

FREE WITH THE SAME DATA: the 1.05 Hz line. `CLAUDE.md` calls it the one unexplained
line in the spectrum. With the sensor disconnected, a line that is still present is
electronics, full stop; one that vanishes is not. Reported, not interpreted.
"""
import argparse
import csv
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from night_compare import BANDS, UV, band_table, load_window, robust_rms  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS_CSV = os.path.join(HERE, "path_checks.csv")

GATE_BAND = (3.0, 7.0)          # the band harvest_events.py reserved
QUIET_DB = 10.0                 # >= this: ground dominates. Fixed 2026-09-22.
DEAF_DB = 3.0                   # <= this: instrument dominates. Fixed 2026-09-22.
LINE_HZ = 1.05                  # the one unexplained spectral line
LINE_WIN = 0.06                 # +/- Hz around it


def band_power(f, p, lo, hi):
    """Integrated PSD over a band, in (uV)^2 -- power, not amplitude."""
    sel = (f >= lo) & (f < hi)
    return float(np.trapezoid(p[sel], f[sel]))


def line_strength(f, p, hz=LINE_HZ, win=LINE_WIN):
    """Power in a narrow window at `hz`, over the local median -- a line's prominence."""
    near = (f >= hz - win) & (f <= hz + win)
    around = ((f >= hz - 10 * win) & (f <= hz + 10 * win)) & ~near
    if not near.any() or not around.any():
        return float("nan")
    return float(np.max(p[near]) / np.median(p[around]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("shorted", type=int, help="jday of the SHORTED night")
    ap.add_argument("live", type=int, nargs="+", help="jday(s) of ordinary live nights")
    ap.add_argument("--start-utc", type=int, default=7)
    ap.add_argument("--hours", type=float, default=5.0)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--temp-c", type=float, default=None,
                    help="garage temperature, for the path_checks.csv row")
    ap.add_argument("--no-log", action="store_true", help="do not append to path_checks.csv")
    a = ap.parse_args()

    def night(jday):
        tr, t0 = load_window(jday, a.start_utc, a.hours, a.year)
        f, p, bands = band_table(tr)
        return dict(jday=jday, t0=t0, f=f, p=p, bands=bands,
                    gate=band_power(f, p, *GATE_BAND),
                    line=line_strength(f, p),
                    rms=robust_rms(tr))

    sh = night(a.shorted)
    lives = [night(j) for j in a.live]

    _end = a.start_utc + a.hours
    print(f"\nwindow {a.start_utc:02d}:00-{int(_end):02d}:{int((_end % 1) * 60):02d} UTC, "
          f"median-Welch, {a.year}\n")
    print(f"{'band (Hz)':>12} {'shorted uV':>12} {'live uV (med)':>14} {'excess dB':>10}")
    for lo, hi in BANDS:
        s_rms = sh["bands"][(lo, hi)]
        l_rms = float(np.median([n["bands"][(lo, hi)] for n in lives]))
        db = 20 * np.log10(l_rms / s_rms) if s_rms > 0 else float("inf")
        print(f"{lo:5.0f}-{hi:<6.0f} {s_rms:12.3f} {l_rms:14.3f} {db:10.1f}")

    live_gate = float(np.median([n["gate"] for n in lives]))
    excess = 10 * np.log10(live_gate / sh["gate"]) if sh["gate"] > 0 else float("inf")

    print(f"\n1-15 Hz event-robust RMS: shorted {sh['rms'][0]:.3f} uV, "
          f"live median {np.median([n['rms'][0] for n in lives]):.3f} uV")
    print(f"{LINE_HZ} Hz line prominence: shorted {sh['line']:.2f}x local median, "
          f"live {np.median([n['line'] for n in lives]):.2f}x")
    print(f"  -> {'PRESENT with no sensor: the line is ELECTRONICS' if sh['line'] > 2 else 'absent with no sensor: NOT electronics'}")

    print(f"\n=== GATE: {GATE_BAND[0]:g}-{GATE_BAND[1]:g} Hz ===")
    print(f"excess over the shorted floor: {excess:.2f} dB "
          f"(quiet >= {QUIET_DB:g}, deaf <= {DEAF_DB:g}; fixed 2026-09-22)")
    if excess >= QUIET_DB:
        verdict = "QUIET"
        print("VERDICT: QUIET -- the instrument is <= 10% of the power here. What this "
              "station detects in the reserved band is ground, not its own floor.")
    elif excess <= DEAF_DB:
        verdict = "DEAF"
        print("VERDICT: DEAF -- the instrument is at least half the power here. Any "
              "re-banding gain is an artifact of not hearing. Abandon on this evidence.")
    else:
        verdict = "AMBIGUOUS"
        print("VERDICT: AMBIGUOUS -- between the thresholds. Change no verdict, and do "
              "NOT go looking for a sub-band where it reads better.")
    print("\nThis settles condition 2 of the harvest_events.py band rule ONLY. The "
          "held-out detection rate and the re-harvest gate are separate conditions.")

    if not a.no_log:
        new = not os.path.exists(CHECKS_CSV)
        with open(CHECKS_CSV, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["date_utc", "state", "jday", "temp_c", "rms_1_15_uv",
                            *[f"rms_{lo:g}_{hi:g}" for lo, hi in BANDS],
                            "gate_excess_db", "verdict", "line_1p05_x", "notes"])
            w.writerow([sh["t0"].strftime("%Y-%m-%d"), "elec_cable", a.shorted,
                        a.temp_c if a.temp_c is not None else "",
                        f"{sh['rms'][0]:.3f}",
                        *[f"{sh['bands'][b]:.3f}" for b in BANDS],
                        f"{excess:.2f}", verdict, f"{sh['line']:.2f}",
                        f"live={','.join(str(j) for j in a.live)}"])
        print(f"\nappended a row to {os.path.relpath(CHECKS_CSV, os.path.dirname(HERE))}")


if __name__ == "__main__":
    main()

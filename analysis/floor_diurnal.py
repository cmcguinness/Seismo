#!/usr/bin/env python3
"""floor_diurnal.py — does the INSTRUMENT's own noise floor have a daily cycle, and are
the HVAC lines reaching it electrically or through the sensor?

Runs over a span with the shorting box fitted (`parts/shorting_box.py`), so there is no
sensor in the circuit and everything recorded is the electronics plus the installed
cable. Reports band RMS hour by hour, and asks whether the known heat-pump lines survive
with the geophone disconnected -- but only over hours when the heat pump actually RAN.

    analysis/.venv/bin/python analysis/floor_diurnal.py            # the 24 h shorted span
    analysis/.venv/bin/python analysis/floor_diurnal.py --hours 8  # partial, mid-test

Day-files must be in analysis/data; the span may cross midnight UTC and the loader
stitches the day-files it needs. Env CSVs (the temperature witness) go in
analysis/data/env/, pulled from pi5:seismo-data/env/.

WHY. On 2026-09-24, comparing 07:00-12:00 UTC against 13:00-14:25 UTC on the SAME
shorted configuration showed the floor higher in the daytime, and the rise grew with
frequency: +0.2 dB at 1-3 Hz, +1.2 dB at 8-15, +2.0 dB at 15-30, +1.7 dB at 30-45.
That was two windows, one of them 85 minutes long. This is the full cycle.

IT IS NOT TEMPERATURE, and a number says so rather than an argument. Johnson noise goes
as sqrt(T) in KELVIN, so a 20 C garage swing (288 -> 308 K) buys 0.29 dB. To reach the
observed 2.0 dB thermally the front end would sit at 456 K = 183 C. A diurnal cycle of
this size in a SHORTED instrument is coupling, not thermal physics.

=============================================================================
THE WITNESS -- AND THERE IS NO PASSIVE ONE
=============================================================================
CLAUDE.md attributes the 41 / 40.6 / 37.65 / 19.3 / 20 Hz lines to the house heat pump,
on the evidence of a weather-driven duty cycle -- i.e. as something the GEOPHONE hears.
Disconnect the sensor and the obvious test is "are the lines still there?". It needs a
witness that the compressor was RUNNING, or absence means nothing. Two wrong answers got
as far as printing a verdict before this worked, both on 2026-09-24:

  1. Ran the test over 05:55-14:25 UTC and printed "ABSENT -> vibration path". That span
     is 22:55-06:55 PDT, the coolest hours of the day; the compressor never switched on.
     Charles caught it in under a minute. Absence while the source is off is not absence.
  2. Gated the verdict on an absolute env-node temperature threshold fitted to a
     reference day. It passed five hours whose REFERENCE prominence was 1.3-5.1x -- i.e.
     hours the AC did not run either. The same error, better dressed.

WITNESSES MEASURED AND REJECTED:
  - env node accelerometer `az_rms_ms2`. Over all of 2026-09-23 it spans 0.02020 ..
    0.02080 m/s2 -- a range of 1.03x -- and correlates +0.11 with the lines. The Clue's
    IMU cannot feel the compressor. A witness that does not move is not a witness.
  - env node `temp_C`, absolutely. The BMP280 is dominated by board self-heat
    (`env_node/clue/code.py`: "use DELTAS ONLY"), so a threshold does not transfer
    between days.
  - env node `temp_C`, as a within-day delta above the day's own minimum. On 2026-09-23
    the AC-ON hours sat +2.67 .. +4.25 C above the daily minimum, but AC-OFF hours
    reached +3.46 C. The distributions overlap; it cannot resolve the duty cycle hourly.

So: with the geophone out of the circuit there is NO passive witness, because the only
reliable indicator the compressor was running was the lines themselves. The test must be
CONTROLLED, and the operator is the instrument:

    --on 21:40-22:05        one or more UTC windows during which the compressor was
                            deliberately run, declared by whoever set the thermostat

That is the strongest witness available and the cheapest. Failing that, `--ref-jday`
supplies matched clock hours from a day with the geophone attached, and only hours whose
REFERENCE prominence clears `ON_PROM` are used -- contingent on the AC keeping similar
hours, which is stated in the output rather than assumed away.

=============================================================================
COMPARE LINE POWER, NOT ONLY PROMINENCE
=============================================================================
Prominence is a ratio against the local background, and the shorted background is ~5x
below the live one. A line of unchanged absolute amplitude therefore reads HIGHER in
prominence when shorted. That cuts the safe way -- if the lines were electrical, shorted
prominence should be at least as large as live, so a small shorted prominence is real
evidence -- but the honest comparison is absolute (uV)^2 at the line, and both are
printed. The same artifact explains why the 40.0 Hz mains alias looked *weaker* in the
2026-09-23 afternoon (3.7x) than overnight (39.7x): the background rose, not the line.

WHAT IT DECIDES: nothing gated. `floor_verdict.py` owns condition 2 of the
`harvest_events.py` band rule and already read AMBIGUOUS. This characterises.
"""
import argparse
import csv
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import obspy
from obspy import UTCDateTime
from scipy import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from night_compare import BANDS, UV, day_file  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ENV = os.path.join(HERE, "data", "env")

# The house heat pump, per CLAUDE.md. 40.0 is NOT in this group: it is the 60 Hz mains
# alias, carried separately as a load that has no duty cycle.
HVAC_HZ = (19.3, 20.0, 37.65, 40.6, 41.0)
MAINS_HZ = 40.0
LINE_HZ = 1.05                  # the instrumental line floor_verdict.py confirmed
LINE_WIN = 0.06
ON_PROM = 10.0                  # prominence that counts as "the compressor is running"
MIN_ON_MIN = 10.0               # a declared window shorter than this is not usable


# --------------------------------------------------------------------------- spectra
def line_prom(f, p, hz, win=LINE_WIN):
    """A line's peak power over the local median beside it -- its prominence (a RATIO)."""
    near = (f >= hz - win) & (f <= hz + win)
    around = ((f >= hz - 12 * win) & (f <= hz + 12 * win)) & ~near
    if not near.any() or not around.any():
        return float("nan")
    return float(np.max(p[near]) / np.median(p[around]))


def line_power(f, p, hz, win=LINE_WIN):
    """Absolute peak PSD at a line, (uV)^2/Hz -- comparable across different backgrounds."""
    near = (f >= hz - win) & (f <= hz + win)
    return float(np.max(p[near])) if near.any() else float("nan")


def hour_spectrum(tr, t_start):
    x = tr.copy().trim(t_start, t_start + 3600)
    if x.stats.npts < 300 * x.stats.sampling_rate:       # < 5 min of data
        return None
    x.detrend("linear")
    f, p = signal.welch(x.data * UV, fs=x.stats.sampling_rate,
                        nperseg=int(30 * x.stats.sampling_rate), average="median")
    bands = {}
    for lo, hi in BANDS:
        sel = (f >= lo) & (f < hi)
        bands[(lo, hi)] = float(np.sqrt(np.trapezoid(p[sel], f[sel])))
    return dict(bands=bands,
                hvac=float(np.mean([line_prom(f, p, z) for z in HVAC_HZ])),
                hvac_pw=float(np.mean([line_power(f, p, z) for z in HVAC_HZ])),
                mains=line_prom(f, p, MAINS_HZ),
                line=line_prom(f, p, LINE_HZ),
                hours=x.stats.npts / x.stats.sampling_rate / 3600)


def load_span(start, hours):
    """Read a UTC span, stitching whatever day-files it crosses."""
    t0, t1 = UTCDateTime(start), UTCDateTime(start) + hours * 3600
    st, jd = obspy.Stream(), UTCDateTime(start).julday
    while UTCDateTime(year=t0.year, julday=jd) < t1:
        st += obspy.read(day_file(jd, t0.year))
        jd += 1
    st = st.trim(t0, t1)
    st.merge(method=1, fill_value="interpolate")
    if len(st) == 0:
        raise SystemExit(f"no data in {t0} .. {t1}")
    return st[0], t0, t1


def hourly_span(start, hours):
    tr, t0, t1 = load_span(start, hours)
    rows = []
    for h in range(int(np.ceil(hours))):
        r = hour_spectrum(tr, t0 + h * 3600)
        if r:
            r["utc"] = t0 + h * 3600
            r["h"] = h
            rows.append(r)
    return rows, t0, t1, tr


def hourly_day(jday, year=2026):
    """Whole-UTC-day hourly spectra, keyed by UTC hour. The reference day."""
    st = obspy.read(day_file(jday, year))
    st.merge(method=1, fill_value="interpolate")
    tr, t0 = st[0], UTCDateTime(year=year, julday=jday)
    out = {}
    for h in range(24):
        r = hour_spectrum(tr, t0 + h * 3600)
        if r:
            out[h] = r
    return out


# --------------------------------------------------------------------------- witness
def env_hourly(date):
    """Hourly median temperature from the env node, keyed by UTC hour. None if absent."""
    path = os.path.join(ENV, f"env-{date}.csv")
    if not os.path.exists(path):
        return None
    acc = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            try:
                acc.setdefault(int(row["utc"][11:13]), []).append(float(row["temp_C"]))
            except (ValueError, KeyError, IndexError):
                pass
    return {h: float(np.median(v)) for h, v in acc.items() if v}


def ref_on_hours(ref_spec):
    """UTC hours on the reference day whose lines say the compressor was running.

    This replaces a temperature threshold, which was measured on 2026-09-24 and does not
    separate ON from OFF (see the docstring). Returns [] if the reference day never ran
    the AC, in which case there is nothing to match against and the test is UNTESTED.
    """
    return [h for h in sorted(ref_spec) if ref_spec[h]["hvac"] >= ON_PROM]


def parse_on(specs, day0):
    """`--on 21:40-22:05` (UTC) -> [(UTCDateTime, UTCDateTime)], operator-declared."""
    out = []
    for spec in specs or []:
        try:
            a, b = spec.split("-")
            ta = UTCDateTime(f"{day0.strftime('%Y-%m-%d')}T{a.strip()}")
            tb = UTCDateTime(f"{day0.strftime('%Y-%m-%d')}T{b.strip()}")
        except Exception:
            raise SystemExit(f"--on wants UTC HH:MM-HH:MM, got {spec!r}")
        if tb <= ta:
            tb += 86400                      # crossed midnight UTC
        if (tb - ta) / 60.0 < MIN_ON_MIN:
            raise SystemExit(f"--on {spec}: {(tb-ta)/60:.0f} min is too short to trust; "
                             f"need >= {MIN_ON_MIN:g} min of compressor time")
        out.append((ta, tb))
    return out


def declared_spectrum(tr, windows):
    """Median-Welch over just the operator-declared ON windows, concatenated."""
    segs = []
    for ta, tb in windows:
        x = tr.copy().trim(ta, tb)
        if x.stats.npts > 60 * x.stats.sampling_rate:
            x.detrend("linear")
            segs.append(x.data.astype(float) * UV)
    if not segs:
        return None
    d = np.concatenate(segs)
    fs = tr.stats.sampling_rate
    f, p = signal.welch(d, fs=fs, nperseg=int(30 * fs), average="median")
    return dict(hvac=float(np.mean([line_prom(f, p, z) for z in HVAC_HZ])),
                hvac_pw=float(np.mean([line_power(f, p, z) for z in HVAC_HZ])),
                mains=line_prom(f, p, MAINS_HZ), line=line_prom(f, p, LINE_HZ),
                minutes=len(d) / fs / 60.0)


# --------------------------------------------------------------------------- report
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="2026-09-24T05:55",
                    help="UTC start (default: the epochs.py MASKED start)")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--on", action="append", metavar="HH:MM-HH:MM",
                    help="UTC window(s) when the compressor was DELIBERATELY run. The "
                         "only trustworthy witness; repeatable.")
    ap.add_argument("--ref-jday", type=int, default=266,
                    help="a day with the GEOPHONE ATTACHED, for matched-hour comparison")
    ap.add_argument("--ref-date", default="2026-09-23", help="env CSV date for --ref-jday")
    ap.add_argument("--png", default=os.path.join(HERE, "floor_diurnal.png"))
    a = ap.parse_args()

    rows, t0, t1, tr = hourly_span(a.start, a.hours)
    if len(rows) < 4:
        raise SystemExit(f"only {len(rows)} usable hours; need at least 4")
    temp = env_hourly(t0.strftime("%Y-%m-%d")) or {}
    temp2 = env_hourly((t0 + 86400).strftime("%Y-%m-%d")) or {}

    def temp_at(u):
        src = temp2 if u.strftime("%Y-%m-%d") != t0.strftime("%Y-%m-%d") else temp
        return src.get(u.hour)

    print(f"\n{t0} .. {t1}   "
          f"({tr.stats.npts / tr.stats.sampling_rate / 3600:.2f} h of data)")
    print("SHORTED input -- no sensor. Local time = UTC - 7 (PDT).\n")

    hdr = (f"{'UTC':>5} {'PDT':>5} {'degC':>6} "
           + " ".join(f"{lo:g}-{hi:g}".rjust(7) for lo, hi in BANDS)
           + f" {'HVACx':>6} {'40.0x':>6} {'1.05x':>7}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        u, tc = r["utc"], temp_at(r["utc"])
        print(f"{u.hour:02d}:{u.minute:02d} {(u - 7*3600).hour:02d}:{u.minute:02d} "
              f"{(f'{tc:6.2f}' if tc is not None else '     -')} "
              + " ".join(f"{r['bands'][b]:7.3f}" for b in BANDS)
              + f" {r['hvac']:6.1f} {r['mains']:6.1f} {r['line']:7.1f}")

    # ---- the diurnal swing --------------------------------------------------
    print("\nswing across the span (loudest hour / quietest hour):")
    worst = 0.0
    for b in BANDS:
        v = np.array([r["bands"][b] for r in rows])
        db = 20 * np.log10(v.max() / v.min())
        worst = max(worst, db)
        print(f"  {b[0]:>2}-{b[1]:<2} Hz  {db:5.2f} dB   "
              f"quietest {rows[int(v.argmin())]['utc'].hour:02d}Z, "
              f"loudest {rows[int(v.argmax())]['utc'].hour:02d}Z")
    t_need = 288.0 * 10 ** (worst / 10)
    print(f"\nlargest swing {worst:.2f} dB. Johnson noise ~ sqrt(T), so reaching that "
          f"thermally needs\n  {t_need:.0f} K = {t_need - 273:.0f} C at the front end "
          f"(a 20 C garage swing gives 0.29 dB). Not thermal.")

    # ---- the gated HVAC question -------------------------------------------
    print(f"\n=== are the HVAC lines {HVAC_HZ} electrical? ===")
    ref = hourly_day(a.ref_jday)
    ref_on = ref_on_hours(ref)
    if not ref_on:
        print(f"  reference day jday {a.ref_jday} never ran the AC either (no hour at "
              f"{ON_PROM:g}x).\n  Nothing to match against: UNTESTED.")
        return _plot(a, rows, temp_at)
    print(f"  reference jday {a.ref_jday} (geophone ATTACHED) had the lines at "
          + ", ".join(f"{h:02d}Z" for h in ref_on)
          + f"\n    (prominence "
          + ", ".join(f"{ref[h]['hvac']:.0f}x" for h in ref_on) + ")")

    # 1. The operator-declared window, if there is one. Strongest evidence.
    windows = parse_on(a.on, t0)
    dec = declared_spectrum(tr, windows) if windows else None
    if dec:
        r_pw = float(np.median([ref[h]["hvac_pw"] for h in ref_on]))
        print(f"\n  DECLARED compressor-on window(s): "
              + ", ".join(f"{x.strftime('%H:%M')}-{y.strftime('%H:%M')}Z"
                          for x, y in windows)
              + f"  ({dec['minutes']:.0f} min)")
        print(f"    shorted prominence {dec['hvac']:.1f}x, peak power {dec['hvac_pw']:.4g} "
              f"(uV)^2/Hz\n    reference (attached, AC on) {r_pw:.4g} -> "
              f"{10 * np.log10(dec['hvac_pw'] / r_pw):+.1f} dB")
        _verdict(dec["hvac"], "a window the compressor was deliberately run in")
        return _plot(a, rows, temp_at)

    # 2. Fall back to matched clock hours. Contingent, and says so.
    both = [r for r in rows if r["utc"].hour in ref_on]
    if not both:
        print(f"\n  UNTESTED. This span covers none of the reference AC hours, and no "
              f"--on window was\n  declared. Absence here would be an absence of "
              f"evidence, not evidence of absence.")
        return _plot(a, rows, temp_at)
    print(f"\n  matched clock hours (CONTINGENT on the AC keeping similar hours today;\n"
          f"  no --on window was declared, so this is the weaker test):")
    print(f"  {'UTC':>4} {'degC':>6} | {'shorted x':>10} {'ref x':>8} | "
          f"{'shorted pw':>11} {'ref pw':>10}   (pw = peak (uV)^2/Hz)")
    for r in both:
        h, tc = r["utc"].hour, temp_at(r["utc"])
        print(f"  {h:02d}Z {(f'{tc:6.2f}' if tc is not None else '     -')} | "
              f"{r['hvac']:10.1f} {ref[h]['hvac']:8.1f} | "
              f"{r['hvac_pw']:11.4g} {ref[h]['hvac_pw']:10.4g}")
    s_pw = float(np.median([r["hvac_pw"] for r in both]))
    r_pw = float(np.median([ref[r["utc"].hour]["hvac_pw"] for r in both]))
    print(f"\n  line POWER shorted / attached = {s_pw / r_pw:.3f} "
          f"({10 * np.log10(s_pw / r_pw):+.1f} dB)")
    _verdict(float(np.max([r["hvac"] for r in both])),
             f"matched hours against jday {a.ref_jday}", weak=True)
    _plot(a, rows, temp_at)


def _verdict(shorted_prom, basis, weak=False):
    print(f"\n  peak shorted prominence {shorted_prom:.1f}x, on {basis}.")
    if shorted_prom >= ON_PROM:
        print("  -> PRESENT with no sensor: the lines are ELECTRICAL coupling into the "
              "cable or\n     front end, not ground motion through the geophone. "
              "CLAUDE.md's attribution\n     needs amending, and cable pickup becomes "
              "the thing to fix.")
    else:
        print("  -> ABSENT with no sensor: the lines reach the record through the SENSOR, "
              "so\n     CLAUDE.md's vibration attribution stands and the daytime "
              "broadband rise is a\n     SEPARATE effect still unexplained. Prominence "
              "is a ratio and the shorted\n     background is ~5x lower, which inflates "
              "a shorted line -- so this reads the\n     conservative way.")
    if weak:
        print("     CAVEAT: no declared compressor window. Re-run with --on for a real "
              "answer.")


def _plot(a, rows, temp_at):
    """Into the repo, not the scratchpad -- Charles opens repo files in his IDE."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 9.5), sharex=True,
                                       gridspec_kw=dict(height_ratios=[2, 1, 1]))
    x = [r["h"] for r in rows]
    for b in BANDS:
        ax.plot(x, [r["bands"][b] for r in rows], marker="o", ms=3.5,
                label=f"{b[0]:g}-{b[1]:g} Hz")
    ax.set_ylabel("RMS (uV, median-Welch)")
    ax.set_title(f"Instrument noise floor, SHORTED input (no sensor)\n"
                 f"{rows[0]['utc'].strftime('%Y-%m-%d %H:%M')} UTC + {len(rows)} h",
                 fontsize=11)
    ax.legend(fontsize=8, ncol=5)
    ax.grid(alpha=.3)
    ax2.plot(x, [r["hvac"] for r in rows], marker="s", ms=3.5, color="#c62828",
             label=f"HVAC lines {HVAC_HZ} (mean prominence)")
    ax2.plot(x, [r["mains"] for r in rows], marker="^", ms=3.5, color="#37474f",
             label=f"{MAINS_HZ} Hz mains alias")
    ax2.axhline(ON_PROM, color="#c62828", ls=":", lw=.9)
    ax2.set_ylabel("x local median")
    ax2.set_yscale("log")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=.3)
    tc = [temp_at(r["utc"]) for r in rows]
    if any(v is not None for v in tc):
        ax3.plot(x, [np.nan if v is None else v for v in tc], marker="d", ms=3.5,
                 color="#ef6c00", label="env node temp_C (self-heated: deltas only)")
        ax3.legend(fontsize=8)
    ax3.set_ylabel("deg C")
    ax3.set_xlabel("hours from start  (UTC; PDT = UTC-7)")
    ax3.grid(alpha=.3)
    for _a in (ax, ax2, ax3):
        s = rows[0]["utc"]
        _a.axvspan(max(0, 7 - s.hour - s.minute / 60),
                   max(0, 12 - s.hour - s.minute / 60),
                   color="#90a4ae", alpha=.15, zorder=0)
    fig.tight_layout()
    fig.savefig(a.png, dpi=115, facecolor="white")
    print(f"\nwrote {os.path.relpath(a.png, REPO)}")


if __name__ == "__main__":
    main()

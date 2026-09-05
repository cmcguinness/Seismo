#!/usr/bin/env python3
"""env_mseed.py -- publish the environmental node's pressure as a real SEED channel.

    SS.OAKM1.20.LDO   1 sps   barometric pressure, centi-Pascals

Reads the CLUE day-file CSVs the env logger pushes to this host and writes miniSEED
day-files into the same archive as EHZ, so pressure and ground motion open in one
ObsPy Stream with one set of time handling.

WHY LOCATION 20. Location codes are [A-Z0-9] pairs and distinguish co-located
acquisition PACKAGES, not sensors: 00 is the geophone + ADS1256, 10 is reserved for
the ADXL355 strong-motion node, 20 is this environmental node. That is the convention
USGS NSMP uses at NP.1835 1.6 km away, where a whole second digitizer package lives
under location "2C" carrying its own accelerometers plus system temperature, voltage,
current and clock quality -- all at 1 sps, exactly like this. Environmental and
state-of-health channels belonging in the feed is professional practice, not a
stretch of one.

WHY LDO. Band L = 1 sps, instrument D = pressure, orientation O = outside. It is the
standard microbarograph code; nothing invented.

WHY centi-Pascals. The channel carries integers, and the sensor now resolves far
finer than a Pascal: per-read scatter is ~1.3 Pa and each sample averages ~12 reads,
so the mean is good to ~0.35 Pa. Storing whole Pa would throw away the resolution the
x16 oversampling was turned on to get. 1 count = 0.01 Pa, i.e. a stage-0 sensitivity
of 100 counts/Pa, and a 1000 hPa reading is ~1.0e7 counts -- comfortably inside int32.

THE HARD PART IS TIME, NOT FORMAT. miniSEED wants samples on a regular grid. These
samples are stamped by the USB host when the bytes arrive, which jitters, and the
CLUE's own clock is the only thing that knows when a sample was actually taken. So
host-UTC is fitted against the CLUE's monotonic clock and the samples are placed on
the grid that fit implies.

The offset is taken from a LOW PERCENTILE of the residuals, not the mean, because USB
delay is one-sided: a row can only arrive later than the instant it was measured,
never earlier. Least squares would chase that tail and put every sample systematically
late.

THE FIT IS PIECEWISE, and that is not premature. A single straight line over one
7.2-hour run looked like it had 112 ms of jitter; almost all of it was curvature. The
CLUE's crystal wandered between +6 and +59 ppm within that run -- 53 ppm of swing,
temperature-driven, on a board that measurably self-heats -- and the fit residuals
traced a smooth +105/-7 ms wander rather than scattering. Fitted in 10-minute windows
instead, the same data gives a p95 jitter of 5 ms, matching what short runs show. So
the clock model is a chain of local anchors with linear interpolation between them,
and every record is stamped from it: within one 100-second record the crystal cannot
drift more than ~6 ms even at the worst observed rate.

The per-window ppm spread is worth watching rather than hiding -- it is a thermometer
for the node, and if it ever collapses to a constant that means something changed.

This only became possible on 2026-09-05. Before that the node paced itself on
time.monotonic(), which is a 32-bit float whose resolution had decayed to 0.25 s at
40 days of uptime: clue_mono_s was quantised to whole seconds and 3.9% of samples
were being dropped outright. There was no clock to fit. Runs from before the fix are
still converted -- their grid is simply cruder, and the reported ppm will be
nonsense, so the log says so.

Regenerating a day is idempotent: the whole day-file is rebuilt from the CSV and
renamed into place, so re-running after a backfill or a repaired CSV is always safe.

Usage:  env_mseed.py [--days N | --all] [--dry-run]
Env:    SEISMO_ARCHIVE (default ~/seismo-archive), SEISMO_ENV_DIR (default
        ~/seismo-data/env), SEISMO_ENV_LOCATION (default 20)
"""
import argparse
import csv
import datetime as dt
import os
import sys
from pathlib import Path

import numpy as np
from simplemseed import MiniseedHeader, MiniseedRecord

NETWORK = os.environ.get("SEISMO_NETWORK", "SS")
STATION = os.environ.get("SEISMO_STATION", "OAKM1")
LOCATION = os.environ.get("SEISMO_ENV_LOCATION", "20")
CHANNEL = "LDO"
RATE = 1                                # sps, integer: miniSEED2 stores factor x mult
ENC_INT32 = 3
SPR = 100                               # samples per record -> 512-byte records
COUNTS_PER_HPA = 10000                  # 1 count = 0.01 Pa

ARCHIVE = Path(os.environ.get("SEISMO_ARCHIVE", str(Path.home() / "seismo-archive")))
ENV_DIR = Path(os.environ.get("SEISMO_ENV_DIR", str(Path.home() / "seismo-data" / "env")))

MAX_GAP_S = 5.0        # a longer jump in the CLUE clock starts a new run
MIN_RUN = 30           # runs shorter than this can't support a useful clock fit
OFFSET_PCT = 5.0       # percentile of residuals taken as the true offset (see above)
WINDOW = 600           # samples per local clock fit (10 min): short enough to track
                       # the crystal's thermal wander, long enough to average the
                       # one-sided USB delay down to a few ms


def read_csv(path):
    """-> (mono seconds, host UTC epoch, pressure hPa) as float arrays."""
    mono, utc, press = [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            p = row.get("press_hPa")
            m = row.get("clue_mono_s")
            u = row.get("utc")
            if not p or not m or not u:
                continue                       # legacy padding / partial line
            try:
                pv, mv = float(p), float(m)
                uv = dt.datetime.fromisoformat(u).timestamp()
            except ValueError:
                continue
            mono.append(mv)
            utc.append(uv)
            press.append(pv)
    o = np.argsort(np.asarray(utc))
    return (np.asarray(mono)[o], np.asarray(utc)[o], np.asarray(press)[o])


def split_runs(mono):
    """Contiguous stretches of one CLUE boot, split on gaps and on resets."""
    if len(mono) == 0:
        return []
    d = np.diff(mono)
    brk = np.where((d > MAX_GAP_S) | (d <= 0))[0] + 1
    return [(a, b) for a, b in zip(np.r_[0, brk], np.r_[brk, len(mono)]) if b - a >= MIN_RUN]


def fit_clock(mono, utc):
    """UTC ~= a*mono + b over one window. Slope least-squares, offset low-percentile.

    Returns (a, b, ppm, jitter_ms). ppm is the CLUE crystal's error against NTP;
    jitter_ms is the p95 of the one-sided USB arrival delay above the fit.
    """
    m0 = mono[0]
    x = mono - m0
    a = float(np.polyfit(x, utc, 1)[0]) if len(mono) > 1 else 1.0
    resid = utc - a * x
    b = float(np.percentile(resid, OFFSET_PCT))
    jitter = float(np.percentile(resid - b, 95)) * 1000.0
    return a, b - a * m0, (a - 1.0) * 1e6, jitter


def clock_model(mono, utc):
    """Piecewise clock map -> (anchors_mono, anchors_utc, ppm_lo, ppm_hi, jitter_ms).

    One local fit per WINDOW samples, each contributing an anchor at its own centre.
    The ends are extrapolated with the end windows' own slopes rather than clamped,
    so the first and last few minutes of a run are not placed with a flat clock.
    """
    am, au, ppm, jit = [], [], [], []
    for i in range(0, len(mono), WINDOW):
        mm, uu = mono[i:i + WINDOW], utc[i:i + WINDOW]
        if len(mm) < 5:                        # tail too short to fit: fold into prior
            break
        a, b, p, j = fit_clock(mm, uu)
        c = float(np.median(mm))
        am.append(c)
        au.append(a * c + b)
        ppm.append(p)
        jit.append(j)
    if not am:                                 # run shorter than one window
        a, b, p, j = fit_clock(mono, utc)
        return (np.array([mono[0], mono[-1]]),
                np.array([a * mono[0] + b, a * mono[-1] + b]), p, p, j)
    am, au = np.array(am), np.array(au)
    if len(am) == 1:
        a, b, p, j = fit_clock(mono, utc)
        am = np.array([mono[0], mono[-1]])
        au = np.array([a * mono[0] + b, a * mono[-1] + b])
    else:                                      # extrapolate the ends by local slope
        s0 = (au[1] - au[0]) / (am[1] - am[0])
        s1 = (au[-1] - au[-2]) / (am[-1] - am[-2])
        am = np.r_[mono[0] - 1.0, am, mono[-1] + 1.0]
        au = np.r_[au[0] - s0 * (am[1] - am[0]), au, au[-1] + s1 * (am[-1] - am[-2])]
    return am, au, float(np.min(ppm)), float(np.max(ppm)), float(np.median(jit))


def grid(mono, press, anchors_m, anchors_u):
    """Place samples on an exact 1 sps grid.

    -> (utc of every grid slot, [(slot index, int32 counts), ...]). Records are
    stamped from the per-slot UTC array, so each one is anchored by the local clock
    rather than by extrapolating a single start time across the whole run.
    """
    k = np.rint((mono - mono[0]) / 1.0).astype(np.int64)
    n = int(k[-1]) + 1
    vals = np.full(n, np.nan)
    vals[k] = press
    utc_grid = np.interp(mono[0] + np.arange(n, dtype=float), anchors_m, anchors_u)

    blocks = []
    good = ~np.isnan(vals)
    i = 0
    while i < n:
        if not good[i]:
            i += 1
            continue
        j = i
        while j < n and good[j]:
            j += 1
        blocks.append((i, np.rint(vals[i:j] * COUNTS_PER_HPA).astype(np.int32)))
        i = j
    return utc_grid, blocks


def write_day(day, blocks, dry_run=False):
    """Rebuild one day-file from scratch and rename it into place (idempotent)."""
    fn = (f"{NETWORK}.{STATION}.{LOCATION}.{CHANNEL}.D."
          f"{day.year}.{day.timetuple().tm_yday:03d}.mseed")
    out = ARCHIVE / fn
    if dry_run:
        return fn, sum(len(c) for _, _, c in blocks), 0
    tmp = out.with_suffix(".mseed.tmp")
    nrec = 0
    with open(tmp, "wb") as fh:
        for utc_grid, i0, counts in blocks:
            for i in range(0, len(counts), SPR):
                chunk = counts[i:i + SPR]
                t = dt.datetime.fromtimestamp(float(utc_grid[i0 + i]), dt.timezone.utc)
                hdr = MiniseedHeader(NETWORK, STATION, LOCATION, CHANNEL,
                                     t.replace(tzinfo=None), len(chunk), RATE,
                                     encoding=ENC_INT32, sampRateFactor=RATE,
                                     sampRateMult=1)
                fh.write(MiniseedRecord(hdr, chunk).pack())
                nrec += 1
    os.replace(tmp, out)
    return fn, sum(len(c) for _, _, c in blocks), nrec


def convert(path, dry_run=False):
    day = dt.date.fromisoformat(path.name[4:14])
    mono, utc, press = read_csv(path)
    runs = split_runs(mono)
    if not runs:
        print(f"{path.name}: no usable runs ({len(mono)} rows)")
        return
    blocks = []
    notes = []
    for a_i, b_i in runs:
        am, au, ppm_lo, ppm_hi, jit = clock_model(mono[a_i:b_i], utc[a_i:b_i])
        ug, bl = grid(mono[a_i:b_i], press[a_i:b_i], am, au)
        blocks += [(ug, i0, c) for i0, c in bl]
        quantised = np.all(np.abs(mono[a_i:b_i] - np.rint(mono[a_i:b_i])) < 1e-6)
        notes.append(f"{b_i - a_i}smp  {ppm_lo:+.1f}..{ppm_hi:+.1f} ppm  jit {jit:.0f} ms"
                     + ("  [clock quantised: pre-2026-09-05, ppm meaningless]"
                        if quantised else ""))
    fn, nsmp, nrec = write_day(day, blocks, dry_run)
    print(f"{fn}: {nsmp} samples in {len(blocks)} blocks, {nrec} records")
    for n in notes:
        print(f"    run: {n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=2, help="most recent N day-files")
    g.add_argument("--all", action="store_true", help="every day-file present")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not ENV_DIR.is_dir():
        sys.exit(f"no env dir: {ENV_DIR}")
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    # .v1.csv files are pre-schema-change fragments; they carry the same columns.
    files = sorted(ENV_DIR.glob("env-????-??-??.csv"))
    if not args.all:
        files = files[-args.days:]
    for p in files:
        convert(p, args.dry_run)


if __name__ == "__main__":
    main()

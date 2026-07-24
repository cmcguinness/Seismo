#!/usr/bin/env python3
"""collect_traffic.py — cheesy stopwatch for logging traffic-count labels.

Per interval:
  1. START beep.
  2. Watch the road; type one key per vehicle -> `z` = northbound, `/` = southbound.
     (Type them in a line; they echo. Spaces are ignored, so `zz/ z /` is fine.)
  3. STOP beep after --interval seconds (default 30).
  4. Hit RETURN.
  5. A row is appended: start_utc, end_utc, total, north, south.

The CSV is created with a header if missing. Column names match
traffic_features.py, so this feeds straight into the feature join.

  analysis/collect_traffic.py                       # default labels.csv, 30 s
  analysis/collect_traffic.py --out mynight.csv --interval 20 --say
  analysis/collect_traffic.py --continuous          # no per-interval Enter prompt

Keep your Mac clock on network time (it is by default) — the UTC stamps must line
up with the seismic archive. Don't touch the rig mid-session (gap/settling), and
keep the whole session in one hardware epoch.
"""
import argparse
import csv
import os
import platform
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone

_DEVNULL = subprocess.DEVNULL
_IS_MAC = platform.system() == "Darwin"
_SOUNDS = {"start": "/System/Library/Sounds/Tink.aiff",
           "stop": "/System/Library/Sounds/Submarine.aiff"}


def beep(kind, say=False):
    """Non-blocking audible cue. macOS voice/sound, else terminal bell."""
    word = {"start": "go", "stop": "stop"}[kind]
    if say and _IS_MAC and shutil.which("say"):
        subprocess.Popen(["say", word], stdout=_DEVNULL, stderr=_DEVNULL)
        return
    snd = _SOUNDS.get(kind)
    if _IS_MAC and shutil.which("afplay") and snd and os.path.exists(snd):
        subprocess.Popen(["afplay", snd], stdout=_DEVNULL, stderr=_DEVNULL)
        return
    sys.stdout.write("\a" + ("\a" if kind == "stop" else ""))
    sys.stdout.flush()


def append_row(path, start, end, north, south):
    new = not (os.path.exists(path) and os.path.getsize(path) > 0)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["start_utc", "end_utc", "total", "north", "south"])
        w.writerow([start.isoformat(), end.isoformat(), north + south, north, south])


def count_line(line):
    north = line.lower().count("z")
    south = line.count("/")
    stray = sum(1 for c in line if c not in "zZ/ \t")
    return north, south, stray


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="labels.csv", help="CSV to append to (default labels.csv)")
    ap.add_argument("--interval", type=float, default=30.0, help="seconds per interval")
    ap.add_argument("--continuous", action="store_true",
                    help="chain intervals without an Enter prompt between them")
    ap.add_argument("--say", action="store_true", help="speak 'go'/'stop' instead of sounds (macOS)")
    args = ap.parse_args()
    if args.interval <= 0:
        sys.exit("--interval must be positive")

    out = os.path.abspath(args.out)
    print("=" * 56)
    print(f"  TRAFFIC COUNTER   z=north  /=south   {args.interval:g}s intervals")
    print(f"  -> {out}")
    print("  Type keys during the interval, RETURN after the STOP beep.")
    print("  Ctrl-C (or 'q' at a prompt) to quit.")
    print("=" * 56)

    i = 0
    total_rows = 0
    try:
        while True:
            i += 1
            if not args.continuous:
                if input(f"\n[{i}] RETURN to start (q to quit): ").strip().lower() == "q":
                    break

            beep("start", args.say)
            start = datetime.now(timezone.utc)
            end = start + timedelta(seconds=args.interval)
            print(f"    GO  {start.astimezone().strftime('%H:%M:%S')} local "
                  f"— counting for {args.interval:g}s…")
            timer = threading.Timer(args.interval, beep, ("stop", args.say))
            timer.start()
            try:
                line = input()
            finally:
                timer.cancel()

            if datetime.now(timezone.utc) < end - timedelta(seconds=0.5):
                print("    ! you hit RETURN before the STOP beep — interval logged as "
                      f"the full {args.interval:g}s window anyway; discard this row if you stopped early.")

            north, south, stray = count_line(line)
            append_row(out, start, end, north, south)
            total_rows += 1
            warn = f"   ({stray} stray key(s) ignored)" if stray else ""
            print(f"    logged  N={north} S={south} total={north + south}"
                  f"   [{start.strftime('%H:%M:%S')}–{end.strftime('%H:%M:%S')} UTC]{warn}")
    except (KeyboardInterrupt, EOFError):
        print()
    print(f"\ndone — {total_rows} interval(s) appended to {out}")


if __name__ == "__main__":
    main()

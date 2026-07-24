#!/usr/bin/env python3
"""collect_traffic.py — stopwatch for logging traffic-count labels.

Two capture modes:

  DEFAULT (line mode): type z (north) / (south) during the interval, hit RETURN
  after the STOP beep. Records only the per-interval totals. Simple, works over a
  pipe, no terminal magic.

  --realtime (per-keystroke): each z / keypress is timestamped in UTC the instant
  you press it (cbreak terminal mode — readline can't do this, it's line-buffered).
  The interval auto-closes at --interval seconds; no RETURN needed. You get BOTH
  the interval totals AND an events file (one row per vehicle), which lets the
  analysis line up individual vehicles against individual seismic transients and
  separate heavy vehicles by per-event amplitude. Reaction lag (~0.3-0.8 s) sits
  inside a vehicle's multi-second transient, so a ±2-3 s search window on the
  analysis side absorbs it.

Per interval:
  1. START beep.
  2. z = northbound, / = southbound (one key per vehicle). Spaces ignored.
  3. STOP beep at --interval seconds (default 30).
  4. (line mode only) hit RETURN.
  5. Interval row appended: start_utc, end_utc, total, north, south.
     (--realtime also appends each keypress to <out>.events.csv: t_utc, dir.)

CSVs are created with headers if missing. Interval columns match traffic_features.py.

  analysis/collect_traffic.py                       # line mode, 30 s
  analysis/collect_traffic.py --realtime --say      # per-vehicle timestamps, voice cues
  analysis/collect_traffic.py --realtime --continuous

Keep your Mac clock on network time. Don't touch the rig mid-session; keep the
whole session in one hardware epoch.
"""
import argparse
import csv
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

_DEVNULL = subprocess.DEVNULL
_IS_MAC = platform.system() == "Darwin"
_SOUNDS = {"start": "/System/Library/Sounds/Tink.aiff",
           "stop": "/System/Library/Sounds/Submarine.aiff"}
_SILENT = False


def beep(kind, say=False):
    """Non-blocking audible cue. macOS voice/sound, else terminal bell."""
    if _SILENT:
        return
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


def append_events(path, start, end, events):
    """Self-contained timeline: an 'open' marker, each vehicle (N/S), a 'close'
    marker, in chronological order. `kind` distinguishes them so the events file
    fully defines the windows without a join back to the interval CSV."""
    new = not (os.path.exists(path) and os.path.getsize(path) > 0)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["t_utc", "kind"])
        w.writerow([start.isoformat(), "open"])
        for t, d in events:
            w.writerow([t.isoformat(), d])
        w.writerow([end.isoformat(), "close"])


def count_line(line):
    return line.lower().count("z"), line.count("/"), \
        sum(1 for c in line if c not in "zZ/ \t")


def interval_line_mode(interval, say):
    """Line-buffered: totals only, RETURN ends it. Returns (start, end, north, south)."""
    beep("start", say)
    start = datetime.now(timezone.utc)
    end = start + timedelta(seconds=interval)
    print(f"    GO  {start.astimezone().strftime('%H:%M:%S')} local — {interval:g}s…")
    timer = threading.Timer(interval, beep, ("stop", say))
    timer.start()
    try:
        line = input()
    finally:
        timer.cancel()
    if datetime.now(timezone.utc) < end - timedelta(seconds=0.5):
        print(f"    ! RETURN before STOP beep — window logged as full {interval:g}s anyway.")
    north, south, stray = count_line(line)
    if stray:
        print(f"    ({stray} stray key(s) ignored)")
    return start, end, north, south, []


def interval_realtime(interval, say):
    """cbreak per-keystroke capture. Returns (start, end, north, south, events)."""
    import termios
    import tty
    import select

    beep("start", say)
    start = datetime.now(timezone.utc)
    end = start + timedelta(seconds=interval)
    deadline = time.monotonic() + interval
    events = []
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)                              # char-at-a-time, keeps Ctrl-C
        a = termios.tcgetattr(fd)
        a[3] &= ~termios.ECHO                          # we draw our own status line
        termios.tcsetattr(fd, termios.TCSANOW, a)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            r, _, _ = select.select([sys.stdin], [], [], remaining)
            if not r:
                continue
            ch = sys.stdin.read(1)
            now = datetime.now(timezone.utc)
            if ch in ("z", "Z"):
                events.append((now, "N"))
            elif ch == "/":
                events.append((now, "S"))
            else:
                continue
            n = sum(1 for _, d in events if d == "N")
            s = len(events) - n
            sys.stdout.write(f"\r    ⏱ {interval - remaining:4.1f}s   "
                             f"N={n} S={s} total={n + s}      ")
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    sys.stdout.write("\n")
    beep("stop", say)
    n = sum(1 for _, d in events if d == "N")
    return start, end, n, len(events) - n, events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="labels.csv", help="interval CSV (default labels.csv)")
    ap.add_argument("--interval", type=float, default=30.0, help="seconds per interval")
    ap.add_argument("--realtime", action="store_true",
                    help="timestamp each keypress (cbreak); also writes <out>.events.csv")
    ap.add_argument("--continuous", action="store_true", help="no Enter prompt between intervals")
    ap.add_argument("--say", action="store_true", help="speak 'go'/'stop' (macOS)")
    ap.add_argument("--silent", action="store_true", help="no beeps (e.g. on a call)")
    args = ap.parse_args()
    if args.interval <= 0:
        sys.exit("--interval must be positive")
    if args.silent:
        global _SILENT
        _SILENT = True

    realtime = args.realtime
    if realtime and not sys.stdin.isatty():
        print("note: stdin is not a TTY — --realtime needs a real terminal; using line mode.")
        realtime = False

    out = os.path.abspath(args.out)
    events_out = os.path.splitext(out)[0] + ".events.csv" if realtime else None
    print("=" * 60)
    print(f"  TRAFFIC COUNTER   z=north  /=south   {args.interval:g}s   "
          f"[{'realtime' if realtime else 'line'} mode]")
    print(f"  intervals -> {out}")
    if events_out:
        print(f"  events    -> {events_out}")
    print("  Ctrl-C (or 'q' at a prompt) to quit.")
    print("=" * 60)

    i = 0
    rows = 0
    try:
        while True:
            i += 1
            if not args.continuous:
                if input(f"\n[{i}] RETURN to start (q to quit): ").strip().lower() == "q":
                    break
            run = interval_realtime if realtime else interval_line_mode
            start, end, north, south, events = run(args.interval, args.say)
            append_row(out, start, end, north, south)
            if events_out:
                append_events(events_out, start, end, events)
            rows += 1
            print(f"    logged  N={north} S={south} total={north + south}"
                  f"   [{start.strftime('%H:%M:%S')}–{end.strftime('%H:%M:%S')} UTC]"
                  + (f"   ({len(events)} timestamped)" if realtime else ""))
    except (KeyboardInterrupt, EOFError):
        print()
    print(f"\ndone — {rows} interval(s) -> {out}")


if __name__ == "__main__":
    main()

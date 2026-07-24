#!/usr/bin/env python3
"""log_event.py — jot a one-off notable event into an annotation log.

For known, discrete happenings worth marking against the seismic record: a street
sweeper, a garbage truck, a delivery, a helicopter, a door slam, someone walking
past the sensor. Each is a high-confidence labelled window you can pull features
from later — cleaner ground truth than aggregate traffic counts.

  log_event.py "street sweeper"                         # stamps NOW (UTC)
  log_event.py "garbage truck" --at 18:40 --dur 60      # today 18:40–18:41 UTC
  log_event.py "helicopter" --at 2026-07-24T19:05:00 --note "low, circling"
  log_event.py "neighbor's mower" --at 11:20 --offset-hours -7   # 11:20 LOCAL

Bare HH:MM / HH:MM:SS is taken as today (in the --offset-hours zone); full ISO is
used as-is. Appends to analysis/annotations.csv (cwd-independent): a header, then
t_start_utc, t_end_utc, label, note per row.
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent


def parse_when(s, offset_hours):
    """Flexible time -> aware UTC datetime. 'now', HH:MM[:SS] (today), or ISO."""
    s = (s or "").strip()
    now = datetime.now(timezone.utc)
    if not s or s.lower() == "now":
        return now
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(s, fmt).time()
        except ValueError:
            continue
        local_date = (now + timedelta(hours=offset_hours)).date()   # date in the given zone
        naive_local = datetime.combine(local_date, t)
        return naive_local.replace(tzinfo=timezone.utc) - timedelta(hours=offset_hours)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        sys.exit(f"can't parse time {s!r} — use 'now', HH:MM, HH:MM:SS, or ISO 8601")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc) - timedelta(hours=offset_hours)
    return dt.astimezone(timezone.utc)


def main():
    ap = argparse.ArgumentParser(description="Log a one-off notable event.")
    ap.add_argument("label", help="short event label, e.g. 'street sweeper'")
    ap.add_argument("--at", default="now", help="start time (default now); HH:MM, HH:MM:SS, ISO, or 'now'")
    ap.add_argument("--end", help="end time (same formats as --at)")
    ap.add_argument("--dur", type=float, help="duration seconds (alternative to --end)")
    ap.add_argument("--note", default="", help="freeform note")
    ap.add_argument("--offset-hours", type=float, default=0.0,
                    help="UTC offset of the times you type (default 0=UTC; -7=PDT)")
    ap.add_argument("--out", default=str(_SCRIPT_DIR / "annotations.csv"),
                    help="annotation CSV (default: annotations.csv beside the script)")
    args = ap.parse_args()

    start = parse_when(args.at, args.offset_hours)
    if args.end:
        end = parse_when(args.end, args.offset_hours)
    elif args.dur:
        end = start + timedelta(seconds=args.dur)
    else:
        end = start
    if end < start:
        sys.exit("end is before start")

    out = os.path.abspath(args.out)
    new = not (os.path.exists(out) and os.path.getsize(out) > 0)
    with open(out, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["t_start_utc", "t_end_utc", "label", "note"])
        w.writerow([start.isoformat(), end.isoformat(), args.label, args.note])

    span = f"–{end.strftime('%H:%M:%S')}" if end != start else ""
    print(f"logged: {start.strftime('%Y-%m-%dT%H:%M:%S')}{span} UTC  \"{args.label}\""
          + (f"  ({args.note})" if args.note else ""))
    print(f"  -> {out}")


if __name__ == "__main__":
    main()

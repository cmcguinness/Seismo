#!/usr/bin/env python3
"""helicorder.py — render a classic drum-plot (helicorder) from the station's
miniSEED. Runs on the Mac (NOT the Pi): pulls the day-files the recorder banks,
then plots with ObsPy's dayplot.

Architecture: the Pi *acquires* 24/7; this *views* on-demand. Nothing here runs
as a daemon -- run it whenever you want to look, or from a cron/launchd timer if
you want an always-fresh PNG.

Usage:
  python helicorder.py                     # pull latest, render newest day-file
  python helicorder.py --date 2026.201     # a specific YYYY.JJJ day-file
  python helicorder.py --interval 30       # 30 min per drum row
  python helicorder.py --highpass 0.7      # highpass (Hz) to knock down drift
  python helicorder.py --no-pull           # skip rsync, use local copy

Needs the analysis venv:  analysis/.venv/bin/python helicorder.py
"""
import argparse
import glob
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL_DATA = HERE / "data"
OUT = HERE / "helicorder.png"


def pull(host: str) -> None:
    """Mirror the Pi's miniSEED dir locally (rsync over passwordless ssh)."""
    LOCAL_DATA.mkdir(parents=True, exist_ok=True)
    print(f"pulling {host}:seismo/data/ -> {LOCAL_DATA} ...")
    subprocess.run(
        ["rsync", "-az", f"{host}:seismo/data/", f"{LOCAL_DATA}/"],
        check=True,
    )


def pick_file(date: str | None) -> Path:
    if date:
        matches = sorted(LOCAL_DATA.glob(f"*.D.{date}.mseed"))
    else:
        matches = sorted(LOCAL_DATA.glob("*.mseed"), key=lambda p: p.stat().st_mtime)
    if not matches:
        sys.exit(f"no miniSEED found in {LOCAL_DATA} (date={date}). Recording yet?")
    return matches[-1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="seismo.local")
    ap.add_argument("--date", help="YYYY.JJJ (julian day) to plot; default newest")
    ap.add_argument("--interval", type=int, default=15, help="minutes per drum row")
    ap.add_argument("--highpass", type=float, default=None, help="highpass corner (Hz)")
    ap.add_argument("--no-pull", action="store_true", help="use local data, skip rsync")
    args = ap.parse_args()

    if not args.no_pull:
        pull(args.host)

    # import obspy lazily so --help / rsync errors don't pay the import cost
    import obspy

    path = pick_file(args.date)
    st = obspy.read(str(path))
    st.merge(method=1)             # heal the ~ms per-block overlaps
    st = st.split()                # contiguous segments only -> real gaps render
                                   # blank on the drum, not as an interpolated line
    st.detrend("demean")           # drop the ADC DC bias (per segment)
    if args.highpass:
        st.filter("highpass", freq=args.highpass, corners=2, zerophase=True)

    start = min(tr.stats.starttime for tr in st)
    end = max(tr.stats.endtime for tr in st)
    print(f"{st[0].id}  {st[0].stats.sampling_rate:g} sps  "
          f"{start} -> {end}  ({(end - start) / 60.0:.1f} min, {len(st)} segment(s))")

    st.plot(
        type="dayplot",
        interval=args.interval,
        title=f"{st[0].id}   {start.date}",
        outfile=str(OUT),
        color=["k", "r", "b", "g"],
        one_tick_per_line=True,
        show_y_UTC_label=True,
    )
    print(f"wrote {OUT}")
    subprocess.run(["open", str(OUT)], check=False)   # macOS: pop it open


if __name__ == "__main__":
    main()

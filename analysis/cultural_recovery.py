#!/usr/bin/env python3
"""cultural_recovery.py — can a real quake be recovered from inside a cultural episode?

Charles asked what the faded columns on the helicorder cost us: when a section is
marked as local activity, are we blind to any seismic signal in those same seconds, or
can it still be fished out?

Method: superpose the real M2.8 Geysers waveform (44.6 km), scaled, onto the labelled
trash-can run of 2026-08-14 03:16-03:19 UTC, and onto a quiet control from the same
night. Two questions, deliberately separate:

  1. OFFLINE — how much sensitivity does the episode cost, band by band? Cultural noise
     is HF-dominated, so the penalty is much smaller in the band a real quake lives in.
     Criterion is SNR 3 on the peak envelope, matching detection_map.py.
  2. LIVE — what does the production StaLta do? The cans dominate amplitude, so the
     quake never gets its own trigger; the question is whether it drags the composite
     event's `hf_lf` below the 1.4 cultural cut, i.e. whether the episode gets
     RE-LABELLED as a quake.

Result (2026-08-14): fishing in 1-8 Hz costs 0.75 magnitude units (M0.97 -> M1.71 at
45 km); fishing at 15-30 Hz costs 1.06. The live classifier re-labels the episode once
the buried event reaches ~M2.4-2.5 at that distance.

⚠️ The template carries its own daytime ambient -- isolated hf_lf 1.22 against the 0.98
STATUS measures for the event proper (see TEMPLATE CHECK below, which is why the window
is cut tight). The crossover is therefore slightly conservative.

  analysis/.venv/bin/python analysis/cultural_recovery.py     # run from the repo root
"""
import sys

import numpy as np
from obspy import Stream, Trace, UTCDateTime, read

sys.path.insert(0, "station")
from stalta import StaLta                                    # noqa: E402

FS = 100.0
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
HP, LP, TRIG, CUT = 3.0, 15.0, 4.0, 1.4                      # production detector + cut
AT_S = 330.0                                                 # inject here, mid-run

CANS = (226, "2026-08-14T03:12:00", "2026-08-14T03:20:00")   # labelled trash-can run
QUIET = (226, "2026-08-14T04:30:00", "2026-08-14T04:38:00")  # quiet control, same night
EVENT = (223, "2026-08-11T21:35:20", "2026-08-11T21:35:45")  # the M2.8 itself, 25 s
EVENT_MAG = 2.8


def grab(day, t0, t1):
    """De-meaned counts for a window. Bridges the archive's sub-second micro-gaps."""
    from collections import Counter
    st = read(f"analysis/data/XX.OAKMT.00.SHZ.D.2026.{day}.mseed").slice(
        UTCDateTime(t0), UTCDateTime(t1))
    dom = Counter(round(t.stats.sampling_rate) for t in st).most_common(1)[0][0]
    st = Stream([t for t in st if round(t.stats.sampling_rate) == dom])
    st.merge(method=1, fill_value="interpolate")
    tr = max(st, key=lambda t: t.stats.npts)
    return tr.data.astype(float) - np.median(tr.data)


def band(x, lo, hi):
    t = Trace(np.asarray(x, dtype="float64"))
    t.stats.sampling_rate = FS
    t.detrend("demean")
    t.filter("bandpass", freqmin=lo, freqmax=hi, corners=4, zerophase=True)
    return t.data


def hf_lf(x):
    """Offline twin of StaLta's streaming classifier, for the template check."""
    return float(np.sqrt(np.sum(band(x, 15, 49) ** 2) / np.sum(band(x, 1, 8) ** 2)))


def run(bg, ev, i0, scale):
    """Production detector over background + scale*event. Returns (index, event) list."""
    x = bg.copy()
    x[i0:i0 + len(ev)] += scale * ev
    det = StaLta(FS, hp_hz=HP, lp_hz=LP, sta_s=1.0, lta_s=30.0, trig=TRIG,
                 detrig=1.5, uv_per_count=UV)
    out = []
    for k, v in enumerate(x):
        e = det.update(v)
        if e:
            out.append((k, e))
    return out


def main():
    cans, quiet, ev = grab(*CANS), grab(*QUIET), grab(*EVENT)
    i0, nq = int(AT_S * FS), len(ev)

    # -- why the template window is cut tight -------------------------------------
    print("TEMPLATE CHECK -- hf_lf of the M2.8 depends entirely on the window you cut")
    for t0, t1, lbl in (
            ("2026-08-11T21:35:20", "2026-08-11T21:35:45", "25 s: the event (used here)"),
            ("2026-08-11T21:35:15", "2026-08-11T21:36:15", "60 s: event + ambient tail"),
            ("2026-08-11T21:34:30", "2026-08-11T21:35:15", "45 s: PRE-event ambient")):
        print(f"  {lbl:<30} hf_lf {hf_lf(grab(223, t0, t1)):5.2f}")
    print("  (the floor is HF-dominated, so a loose window measures the ROOM, not the")
    print("   quake -- a 60 s template can never fall below the 1.4 cut when injected)")

    # -- 1. offline recoverability -------------------------------------------------
    print(f"\nOFFLINE RECOVERY -- smallest M{EVENT_MAG}-shaped event whose own peak reaches")
    print("3x the background RMS in the same seconds (1 magnitude unit = 10x amplitude)")
    print(f"{'band':>9} {'quiet ctrl':>12} {'in the cans':>12} {'penalty':>9} {'M units':>8}")
    for lo, hi in ((1, 8), (2, 5), (1, 15), (15, 30)):
        sig = np.abs(band(ev, lo, hi)).max()
        need = [3.0 * np.sqrt(np.mean(band(bg, lo, hi)[i0:i0 + nq] ** 2)) / sig
                for bg in (quiet, cans)]
        sq, sc = need
        print(f"{lo:>3}-{hi:<5} M{EVENT_MAG + np.log10(sq):11.2f}"
              f" M{EVENT_MAG + np.log10(sc):11.2f} {sc / sq:8.1f}x"
              f" {np.log10(sc / sq):8.2f}")

    # -- 2. what the live detector does --------------------------------------------
    print(f"\nLIVE DETECTOR -- injected at t={AT_S:.0f}s, mid-run (trig {TRIG}, cut hf_lf {CUT})")
    for scale in (0.0, 0.1, 0.18, 0.32, 0.56, 0.75, 1.0, 3.16, 10.0):
        evs = [(k, e) for k, e in run(cans, ev, i0, scale)
               if i0 - 500 <= k <= i0 + nq + 3000]
        if not evs:
            print("  no event overlapping the injection")
            continue
        _, e = max(evs, key=lambda t: t[1]["peak_ratio"])
        lbl = "cans alone" if not scale else f"cans + M{EVENT_MAG + np.log10(scale):.1f}"
        print(f"  {lbl:<14} ratio {e['peak_ratio']:9.1f}  dur {e['duration_s']:5.1f}s"
              f"  hf_lf {e['hf_lf']:5.2f} -> "
              f"{'QUAKE' if e['hf_lf'] < CUT else 'cultural'}")
    _, e = max(run(quiet, ev, i0, 1.0), key=lambda t: t[1]["peak_ratio"])
    print(f"  {'quiet + M2.8':<14} ratio {e['peak_ratio']:9.1f}  dur {e['duration_s']:5.1f}s"
          f"  hf_lf {e['hf_lf']:5.2f} -> {'QUAKE' if e['hf_lf'] < CUT else 'cultural'}")
    print("\n  peak_ratio barely moves -- the cans own the amplitude. hf_lf is what")
    print("  moves, because the quake adds energy only to the 1-8 Hz denominator.")


if __name__ == "__main__":
    main()

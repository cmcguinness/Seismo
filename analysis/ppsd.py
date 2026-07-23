#!/usr/bin/env python3
"""ppsd.py — probabilistic power spectral density for XX.OAKMT.00.SHZ.

Builds the standard station-characterization plot (McNamara & Buland 2004): every
segment of the archive reduced to a PSD, then histogrammed per frequency bin, so
you see the FULL distribution of noise at each frequency rather than one snapshot.
It answers "how noisy is this station, at what frequency, how often" — and it makes
claims about noise defensible instead of anecdotal (e.g. whether a spike population
is present in a given week).

Incremental by design: PPSD state is saved to an npz, so re-running only adds the
day-files it hasn't seen. Run it after each rsync and the statistics keep improving.

**PER-EPOCH, NEVER ACROSS.** The archive spans several different instruments in the
statistical sense -- office windowsill vs garage slab, WiFi dongle vs Ethernet
bridge, gain/DRATE changes, no isolator vs isolator. A PPSD accumulated across those
describes no configuration that ever existed: the histogram blends them and the
resulting wide bins masquerade as natural variability. So every run is scoped to one
epoch from EPOCHS below, with its own state file. Add an entry whenever the station
changes -- siting, cabling, gain, damping -- and start a fresh accumulation.

Response is ANALYTIC, not measured (see RESPONSE below). A geophone is a damped
harmonic oscillator whose voltage output is proportional to ground velocity above
its corner:

    H(s) = G * s^2 / (s^2 + 2*zeta*w0*s + w0^2)

so two zeros at the origin and two poles set by f0 and zeta. Above f0 the response
is flat at G, and that part of the curve is trustworthy. BELOW f0 the shape depends
on `zeta`, which is currently a datasheet-class guess (open-circuit ~0.28) and will
change when the shunt damping resistor is fitted -- so treat the sub-4.5 Hz end as
indicative until zeta is measured from an impulse response.

Usage:
    python ppsd.py                     # add any new day-files, save, replot
    python ppsd.py --rsync             # pull the archive from the Pi first
    python ppsd.py --data DIR --out DIR
"""
import argparse
import glob
import os
import subprocess
import sys
from collections import Counter

# --- station constants -------------------------------------------------------
F0 = 4.5                  # geophone corner, Hz
ZETA = 0.28               # open-circuit damping (NO shunt fitted yet -- see docstring)
VOLTS_PER_MPS = 28.8      # geophone flat-band sensitivity, V/(m/s)
ADC_GAIN = 64             # ADS1256 PGA setting the recorder runs
VREF = 2.5                # ADS1256 reference, V

REMOTE = "seismo.local:seismo/data/"

# --- configuration epochs ----------------------------------------------------
# label -> (start UTC, end UTC or None for "current", description)
# ONLY compare PPSDs within one epoch. Add a row whenever the station changes.
# Boundaries before 2026-07-23 are approximate -- the early archive mixes siting
# (office -> garage), networking (WiFi dongle -> Ethernet bridge) and settling
# transients, so it is NOT worth characterizing; it is listed for the record only.
EPOCHS = {
    "rdatac-60sps": ("2026-07-23T08:56:50", None,
                     "RDATAC continuous read: exactly 60 sps, gapless (0 gaps vs "
                     "41.2 s/hour lost on the legacy path). Garage slab, Ethernet "
                     "bridge + galvanic isolator, gain 64, NO shunt damping. "
                     "THIS is the epoch worth accumulating statistics on."),
    "garage-isolator": ("2026-07-23T07:13:00", "2026-07-23T08:56:50",
                        "garage slab, Ethernet bridge + galvanic isolator (reversed), "
                        "gain 64, DRATE_60, NO shunt damping. 1-15 Hz ~0.7 uV."),
    "garage-ethernet": ("2026-07-21T00:00:00", "2026-07-23T06:15:00",
                        "garage slab, Ethernet bridge, no isolator. 1-15 Hz ~1.15 uV."),
    "mixed-early": ("2026-07-19T00:00:00", "2026-07-21T00:00:00",
                    "DO NOT TRUST: office->garage move, WiFi dongle present part of "
                    "the time, config changes. Listed for the record, not for stats."),
}
DEFAULT_EPOCH = "rdatac-60sps"


def counts_per_volt(gain=ADC_GAIN, vref=VREF):
    """ADS1256 full-scale is +/-vref/gain over 2^23-1 codes."""
    volts_per_count = (vref * 2) / (gain * (2 ** 23 - 1))
    return 1.0 / volts_per_count


def response():
    """Poles/zeros/sensitivity dict in the form ObsPy's PPSD accepts as metadata.

    sensitivity is the FULL chain, counts per (m/s): geophone V/(m/s) times the
    digitizer's counts/V. gain (A0) is 1.0 because the paz above is already
    normalized to G in its flat band."""
    import numpy as np

    w0 = 2 * np.pi * F0
    # poles of s^2 + 2*zeta*w0*s + w0^2
    real = -ZETA * w0
    imag = w0 * (1 - ZETA ** 2) ** 0.5
    sens = VOLTS_PER_MPS * counts_per_volt()
    return {
        "gain": 1.0,
        "poles": [complex(real, imag), complex(real, -imag)],
        "zeros": [0j, 0j],
        "sensitivity": sens,
    }


def load_day(path):
    """Day-file -> Stream, normalizing the early archive's mixed sample rates
    (55/57 sps segments exist; ObsPy won't merge across rates).

    CRITICAL for PPSD: the recorder's wall-clock-per-block scheme leaves a ~68 ms
    gap at nearly every 10 s block boundary, so a plain merge+split yields ~10 s
    fragments and NO window long enough for a PSD segment -- PPSD.add() then
    silently processes zero segments. So micro-gaps are bridged by interpolation
    (fill_value='interpolate'), the same thing dashboard/render._load_recent does.

    The honest caveat: that interpolates ~0.5-1.7 s per minute of record. It is
    sub-noise and symmetric (see BACKLOG "Data-continuity / RDATAC"), so it does
    not bias a PSD meaningfully at 1-15 Hz, but it IS an interpolation and the real
    fix is ADS1256 continuous (RDATAC) mode."""
    import obspy

    st = obspy.read(path)
    if not len(st):
        return st
    dom = Counter(round(t.stats.sampling_rate) for t in st).most_common(1)[0][0]
    off = [t for t in st if round(t.stats.sampling_rate) != dom]
    if off:
        for t in off:
            t.resample(float(dom))
        for t in st:
            t.data = t.data.astype("float64")
    st.merge(method=1, fill_value="interpolate")
    return st


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=os.path.join(os.path.dirname(__file__), "data"))
    p.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--rsync", action="store_true", help="pull the archive from the Pi first")
    p.add_argument("--length", type=int, default=600,
                   help="PPSD segment length (s). 600 suits a short-period station; "
                        "ObsPy's 3600 default is tuned for broadbands.")
    p.add_argument("--reset", action="store_true", help="discard saved state and rebuild")
    p.add_argument("--epoch", default=DEFAULT_EPOCH, choices=sorted(EPOCHS),
                   help="configuration epoch to accumulate (never mix epochs)")
    args = p.parse_args()

    import obspy
    from obspy.signal import PPSD

    ep_start, ep_end, ep_desc = EPOCHS[args.epoch]
    t_start = obspy.UTCDateTime(ep_start)
    t_end = obspy.UTCDateTime(ep_end) if ep_end else None
    print(f"epoch '{args.epoch}': {ep_start} -> {ep_end or 'now'}\n  {ep_desc}\n")

    os.makedirs(args.data, exist_ok=True)
    if args.rsync:
        print(f"rsync {REMOTE} -> {args.data}")
        subprocess.run(["rsync", "-az", REMOTE, args.data + "/"], check=True)

    files = sorted(glob.glob(os.path.join(args.data, "XX.OAKMT*.mseed")))
    if not files:
        sys.exit(f"no XX.OAKMT day-files in {args.data} (use --rsync)")

    state = os.path.join(args.out, f"ppsd_OAKMT_{args.epoch}.npz")
    seen_path = os.path.join(args.out, f"ppsd_seen_{args.epoch}.txt")
    seen = set()
    if os.path.exists(seen_path) and not args.reset:
        seen = {l.strip() for l in open(seen_path) if l.strip()}

    ppsd = None
    if os.path.exists(state) and not args.reset:
        ppsd = PPSD.load_npz(state)
        print(f"loaded state: {len(ppsd.times_processed)} segments already processed")

    added = 0
    for path in files:
        name = os.path.basename(path)
        # The NEWEST file is still growing, so never mark it seen -- re-add it each
        # run. PPSD.add() silently skips segments it already holds, so re-adding a
        # partially-processed day is free and picks up only the new tail.
        newest = path == files[-1]
        if name in seen and not newest:
            continue
        st = load_day(path)
        if not len(st):
            continue
        st = st.slice(t_start, t_end)            # clip to the epoch -- never mix
        if not len(st):
            continue
        if ppsd is None:
            ppsd = PPSD(st[0].stats, metadata=response(), ppsd_length=args.length)
        before = len(ppsd.times_processed)
        for tr in st:
            ppsd.add(tr)
        gained = len(ppsd.times_processed) - before
        print(f"  {name}: +{gained} segments")
        added += gained
        if not newest:
            seen.add(name)

    if ppsd is None or not len(ppsd.times_processed):
        sys.exit("no segments processed -- check the response and the data")

    ppsd.save_npz(state)
    with open(seen_path, "w") as f:
        f.write("\n".join(sorted(seen)) + "\n")

    png = os.path.join(args.out, "ppsd_OAKMT.png")
    # period_lim in SECONDS: 0.02-20 s = 0.05-50 Hz, which brackets the geophone's
    # useful band. show_noise_models draws Peterson's NLNM/NHNM for reference -- a
    # 4.5 Hz element sits far above the NLNM at long period by construction, so
    # don't read that gap as a fault.
    ppsd.plot(filename=png, show_coverage=True, show_noise_models=True,
              period_lim=(0.02, 20.0))
    print(f"\nadded {added} segments this run; {len(ppsd.times_processed)} total")
    print(f"state: {state}\nplot:  {png}")

    # a couple of numbers worth having in the terminal, not just the picture
    import numpy as np
    per, modes = ppsd.get_mode()
    for target in (0.1, 0.2, 0.5, 1.0, 5.0):        # seconds of period
        i = int(np.argmin(np.abs(per - target)))
        print(f"  mode at {per[i]:6.3f} s ({1/per[i]:6.2f} Hz): {modes[i]:7.1f} dB "
              f"rel 1 (m/s^2)^2/Hz")


if __name__ == "__main__":
    main()

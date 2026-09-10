#!/usr/bin/env python3
"""eventcheck.py — did the station catch a catalog earthquake?

Give it a USGS event (origin time + epicenter + depth). It computes the
epicentral distance and P/S arrival times for our station, pulls the miniSEED,
windows around the predicted arrivals, band-passes out the microseism, and
plots raw + filtered with P/S markers — then prints a simple detection verdict
(signal-vs-noise in the P–S window).

Times: paste the USGS *local* time and it converts with --offset-hours
(default -7 = PDT). Epicenter/depth from the USGS page.

  python eventcheck.py --origin "2026-07-20T00:15:29" \
      --lat 38.824 --lon -122.812 --depth 2.8 --mag 0.7 --label "The Geysers"

Robust to the archive's mixed-rate/fragmented segments: it slices the window,
keeps the dominant sample rate, and merges that.

Needs the analysis venv:  analysis/.venv/bin/python eventcheck.py ...
"""
import argparse
import math

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from helicorder import LOCAL_DATA, pull

# Station location — Oakmont, Santa Rosa (measured at the sensor site).
#
# Full precision is PUBLISHED DELIBERATELY, in a public repo, and this note exists
# so nobody re-opens it as a privacy finding: the operator's address is already
# public record in the FCC ULS (amateur callsign KJ4NGS), so rounding here would
# withhold nothing while costing real accuracy. Vp below is measured against these
# coordinates, and every epicentral distance and P/S residual in the project is
# computed from them; degrading them to ~100 m would blur the very residuals the
# 5.19 km/s fit was derived from.
STA_LAT, STA_LON = 38.451817, -122.621049
STA_ELEV_M = 128.3   # above MSL; catalogue depths are from MSL, so it adds
# Local crustal P/S velocities (km/s). Vp is MEASURED at this station, not assumed:
# five confirmed events over 18.4-45.7 km give onset = dist/5.19 + 0.30 s with <=0.3 s
# residuals (2026-07-29, STATUS.md). Vp=6.0 predicted arrivals ~1.4 s early at 45 km.
VP, VS = 5.19, 3.00              # Vp/Vs≈1.73
T0_INTERCEPT = 0.30              # seconds; the fitted intercept of that same relation


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", required=True, help="origin time, ISO (e.g. 2026-07-20T00:15:29)")
    ap.add_argument("--offset-hours", type=float, default=-7.0,
                    help="UTC offset of --origin (default -7 = PDT); UTC = origin - offset")
    ap.add_argument("--lat", type=float, required=True, help="epicenter latitude")
    ap.add_argument("--lon", type=float, required=True, help="epicenter longitude")
    ap.add_argument("--depth", type=float, default=8.0, help="hypocenter depth km")
    ap.add_argument("--mag", type=float, help="magnitude (label only)")
    ap.add_argument("--label", default="event", help="event name for the title")
    ap.add_argument("--stalat", type=float, default=STA_LAT)
    ap.add_argument("--stalon", type=float, default=STA_LON)
    ap.add_argument("--gain", type=int, default=64)
    # 2-5, not the old 2-15. MEASURED, 2026-09-07, on the 38 confirmed events with a
    # local day-file plus a 300-window empirical null drawn from the same archive, all
    # scored with the same statistic (peak of a 2 s RMS envelope over the arrival box,
    # against the pre-event p99):
    #
    #        band     null p99   median event SNR   discrimination
    #      2-15 Hz      5.12           2.1              0.41x
    #       2-5 Hz      3.41           6.5              1.90x
    #       1-8 Hz      4.42           5.5              1.25x
    #
    # In 2-15 Hz the MEDIAN CONFIRMED CATCH scores below the null's 99th percentile --
    # the band was throwing away the events it exists to find. 5-15 Hz carries almost no
    # earthquake and a great deal of cultural noise, so dropping it lowers the false-
    # positive ceiling (5.12 -> 3.41) at the same time as it raises the signal. 2-5 Hz
    # wins on 18 of the 38 events outright and has the best median at every distance.
    # The effect is dramatic at range -- Petrolia 4.01x -> 28.21x, Ferndale 1.30x ->
    # 4.78x -- but it is NOT a far-field fix: the near-field median improves 3.1x too.
    #
    # ⚠️ THIS BAND IS ALMOST ENTIRELY BELOW THE 4.5 Hz CORNER. Know what that means:
    #   - The win is NOISE REJECTION, not signal capture. The floor falls 4.77 -> 0.55 uV
    #     because the geophone's f^2 rolloff suppresses the cultural noise that owns
    #     5-15 Hz. We are not finding more earthquake; we are hearing less traffic.
    #   - Response varies 6.25x across 2->5 Hz on that f^2 slope, and its shape near
    #     corner is set by f0 and zeta -- both still GUESSES in SS.OAKM1.xml. This band
    #     is therefore fine for DETECTION (is it there, yes/no) and wrong for AMPLITUDE.
    #     Do NOT re-band harvest_events.py on this evidence: resid_log10 is an amplitude
    #     comparison feeding the deficit, the corner penalty and the validated range, and
    #     below corner all of those become hostage to two unmeasured numbers.
    #   - Whether 2-5 Hz is quiet because the ground is quiet or because the INSTRUMENT
    #     IS DEAF there is not established. The 1-15 Hz floor is site-limited by ~10x
    #     (electronics ~0.12 uV vs 1.17-1.5 uV measured, doc/rev2-frontend.md), but the
    #     ADS1256's 1/f noise rises exactly here and the geophone's noise-equivalent
    #     GROUND MOTION climbs steeply below f0 even while its output voltage looks
    #     quiet. The shorted-input floor test is the clean separator; the calibrator's
    #     1/4" jack + plug-in shunt modules exist to make it runnable without a soldering
    #     iron (doc/BOM-calibrator.md, satisfying rev2-frontend.md's design-for-test
    #     rule), and station/capture_raw.py is the capture tool. When it runs, it now
    #     settles a detection-band question as well as a front-end one.
    ap.add_argument("--band", default="2,5", help="bandpass 'fmin,fmax' Hz")
    ap.add_argument("--pre", type=float, default=20.0, help="seconds before origin (plot)")
    ap.add_argument("--plot-post", type=float, default=0.0,
                    help="seconds after origin to PLOT (0 = auto: S + 40 s). The analysis "
                         "window is much longer -- the null needs ~900 s before and 600 s "
                         "after -- but plotting all of it compresses the arrivals into a "
                         "few pixels and hides the waveform, which is the point of looking")
    ap.add_argument("--noise-s", type=float, default=900.0,
                    help="how far before origin the null samples (default 900 s; 300 "
                         "was too short -- see the null comment)")
    ap.add_argument("--null-post", type=float, default=600.0,
                    help="seconds after S to keep for the forward half of the null")
    ap.add_argument("--null-pad", type=float, default=60.0,
                    help="seconds after the signal boxes before forward null windows "
                         "start, so the null does not sit on the event's own coda")
    ap.add_argument("--post", type=float, default=0.0, help="seconds after origin (0=auto)")
    ap.add_argument("--no-pull", action="store_true")
    args = ap.parse_args()

    from obspy import Stream, UTCDateTime, read

    origin = UTCDateTime(args.origin) - args.offset_hours * 3600.0     # -> UTC
    epi = haversine_km(args.stalat, args.stalon, args.lat, args.lon)
    hypo = math.hypot(epi, args.depth + STA_ELEV_M / 1000.0)
    # +T0_INTERCEPT on P: the measured relation is onset = dist/5.19 + 0.30 s (see the
    # VP comment above), and dropping the intercept drew every P marker 0.30 s EARLY,
    # which made real arrivals look systematically late on every plot (2026-08-12).
    # Travel times from iasp91 where it applies. The constant-velocity model below is
    # right locally -- it was MEASURED here -- but it has no Pn, so past ~150 km it
    # predicts arrivals several seconds late: for the M2.3 at 166 km on 2026-09-01 it
    # put P +4.8 s and S +7.5 s late, which slid the signal box off the actual arrivals
    # and onto the coda. harvest_events.arrivals_s() already solved this; use it.
    try:
        from harvest_events import arrivals_s
        tP, tS = arrivals_s(epi, args.depth, hypo)
        tt_src = "iasp91"
    except Exception:
        tP, tS = hypo / VP + T0_INTERCEPT, hypo / VS
        tt_src = f"Vp {VP}, Vs {VS} km/s"
    post = args.post if args.post > 0 else tS + 40.0
    fmin, fmax = (float(x) for x in args.band.split(","))
    uvpc = (2.5 * 2 / (args.gain * (2 ** 23 - 1))) * 1e6

    print(f"{args.label}  M{args.mag}  origin {origin} UTC")
    print(f"  epicentral {epi:.1f} km, hypocentral {hypo:.1f} km, depth {args.depth} km")
    print(f"  predicted P +{tP:.1f}s, S +{tS:.1f}s ({tt_src})")

    if not args.no_pull:
        pull("seismo.local")

    matches = sorted(LOCAL_DATA.glob(f"*.D.{origin.year}.{origin.julday:03d}.mseed"))
    if not matches:
        raise SystemExit(f"no day-file for {origin.year}.{origin.julday:03d} in {LOCAL_DATA}")
    st = read(str(matches[-1]))
    win = st.slice(origin - max(args.pre, args.noise_s + 20),
                   origin + max(post, tS + args.null_post))
    if not len(win):
        raise SystemExit("NO DATA in the event window (recorder gap at that time?)")
    # The archive is fragmented into many short segments by sub-second timing
    # micro-gaps. The old code split() the window and kept only the ONE segment
    # best overlapping the P-S window -- which discarded the adjacent fragments
    # holding the pre-event noise, so every event looked like it had a ~6s "gap"
    # over the P arrival (noise pp 0.0 -> bogus "NOT DETECTED"). Instead, bridge
    # the micro-gaps by interpolation into a single continuous trace.
    from collections import Counter
    dom = Counter(round(tr.stats.sampling_rate) for tr in win).most_common(1)[0][0]
    win = Stream([tr for tr in win if round(tr.stats.sampling_rate) == dom])
    win.merge(method=1, fill_value="interpolate")
    tr = max(win, key=lambda t: t.stats.npts)

    raw = tr.copy(); raw.detrend("demean")
    filt = tr.copy(); filt.detrend("demean")
    filt.filter("bandpass", freqmin=fmin, freqmax=fmax, corners=4, zerophase=True)
    t = raw.times() + (raw.stats.starttime - origin)
    bp = filt.data * uvpc
    sr = float(tr.stats.sampling_rate)

    def pp(lo, hi):
        seg = bp[(t > lo) & (t < hi)]
        return float(np.ptp(seg)) if seg.size else 0.0
    # THE VERDICT. The previous version compared peak-to-peak over an 18 s noise window
    # against peak-to-peak over a 44 s signal window, and peak-to-peak GROWS WITH WINDOW
    # LENGTH -- you sample the tail of the amplitude distribution more times -- so that
    # ratio ran above 1 whether or not an earthquake was present. It called the M2.3 at
    # 166 km on 2026-09-01 "LIKELY DETECTED, ratio 4.16" on a stretch where the noise
    # window's own peak-to-peak (21.0 uV) equalled the signal window's (20.5 uV).
    #
    # Three changes, each one a lesson already paid for elsewhere in this repo:
    #   - a SMOOTHED ENVELOPE, not raw peak-to-peak, so one sample cannot carry it;
    #   - compared against the noise window's 99th PERCENTILE, which is length-stable,
    #     rather than its extremum, which is not;
    #   - and SUSTAIN, the guard from detection_map.calibrate(): a real arrival is a
    #     train that holds for seconds, a door slam is one enormous sample. Every
    #     genuine catch in the harvest holds 3.4-7.9 s.
    env = np.convolve(np.abs(bp), np.ones(int(sr)) / int(sr), mode="same")
    nmask = (t >= -args.noise_s) & (t <= -10)
    smask = (((t >= tP - 2) & (t <= tP + 12)) | ((t >= tS - 4) & (t <= tS + 22)))
    if not nmask.any() or not smask.any():
        raise SystemExit("not enough data around the event to judge it")
    n99 = float(np.percentile(env[nmask], 99))
    speak = float(env[smask].max())
    ratio = speak / n99 if n99 else 0.0
    sustain = float((env[smask] > 2 * n99).sum() / sr)

    # AN EMPIRICAL NULL, because no single threshold survives daytime background.
    # Cultural noise is wildly non-stationary: for the M2.1 near Ukiah on 2026-09-01
    # the 2-6 Hz p99 was 0.78 uV over a 170 s noise window and 2.70 uV over 270 s,
    # purely because one burst fell outside the shorter one -- and the "2.9x detection"
    # that produced evaporated when the window grew. Any fixed multiple of any single
    # noise statistic inherits that instability.
    #
    # So ask the question non-parametrically instead: slide the EXACT two-box signal
    # mask back through the pre-event noise and count how often plain background
    # produces a peak as large. That is a p-value against the null "this is just a
    # quiet-ish stretch of the same noise", it needs no threshold, and it is robust to
    # whatever the neighbourhood happens to be doing.
    # ...AND THE NULL MUST BRACKET THE EVENT, NOT ONLY PRECEDE IT. Sliding the mask
    # only BACKWARDS asks "was the last few minutes quieter than this?", and on a
    # weekday afternoon the answer is often yes for reasons that have nothing to do with
    # an earthquake. Caught in the wild on 2026-09-07: the M3.7 Hydesville at 252 km,
    # which we did not record, returned p = 0.011 in FOUR different bands -- identical p
    # in every band, because the 300 s before origin were the quietest run of the whole
    # record. Widened to +-15 minutes the arrival ranked 11th of 64 windows. So the null
    # now slides FORWARD past the coda as well, and a pre-event lull can no longer carry
    # a verdict on its own.
    #
    # The forward windows start a full coda-length after S for the same reason the
    # backward ones start after the mask: a null window sitting on the event's own coda
    # is being compared against the earthquake, which is the mirror of the bug above.
    #
    # AND THE LOOKBACK HAD TO GROW. Measured on that same Hydesville non-detection: at
    # the old 300 s default the null gave p = 0.002, and at 900 s it gives p = 0.131,
    # because the genuinely loud stretches were five to ten minutes back. The old
    # default was not sampling the neighbourhood's noise, it was sampling one lull.
    # Note this cuts against a comment above: a longer window was once treated as
    # INSTABILITY because p99 moved 0.78 -> 2.70 uV between 170 s and 270 s. That was
    # the right observation and the wrong conclusion -- the short window was the
    # unrepresentative one, and the cure for a statistic that moves when you look
    # longer is to look longer still, not to look less.
    idx = np.flatnonzero(smask)
    # The smallest shift that clears the event entirely. For a NEARBY event P lands a
    # second or two after origin, so a fixed 20 s shift leaves the "null" window still
    # sitting on top of the earthquake -- which is how the M1.8 at 2.8 km, a textbook
    # detection at 12.8x, first came out AMBIGUOUS: it was being compared against
    # itself. The shift has to be derived from the mask's own extent, not assumed.
    k_min = int(idx.max() - np.searchsorted(t, -10.0)) + 1
    step = max(1, int(2 * sr))
    off = np.arange(max(k_min, step), int((args.noise_s - 20) * sr), step)
    null = [float(env[idx - k].max()) for k in off if (idx - k).min() >= 0]
    n_back = len(null)
    fwd0 = int((args.null_pad) * sr)                       # clear the coda
    off_f = np.arange(max(k_min, fwd0), int(args.null_post * sr), step)
    null += [float(env[idx + k].max()) for k in off_f if (idx + k).max() < len(env)]
    n_ge = sum(v >= speak for v in null)
    # With N null windows the smallest reachable p is 1/(N+1), so N must be big enough
    # that a real detection can actually clear the threshold: 18 windows floored p at
    # 0.105 and made "LIKELY DETECTED" unreachable by construction.
    pval = (n_ge + 1) / (len(null) + 1) if null else float("nan")

    # SUSTAIN IS REQUIRED FOR BOTH VERDICTS, not offered as an alternative to the
    # p-value. The old `weak` was an OR, so a p-value alone -- with the envelope holding
    # for literally zero seconds -- was enough to print AMBIGUOUS. That is precisely how
    # the Hydesville non-detection got dressed up as a maybe. harvest_events.py has
    # always required snr AND sustain together, and the audit in catch_audit.py is why:
    # a quiet lull inflates a ratio, but nothing except an actual wavetrain produces
    # seconds of sustained envelope.
    strong = pval <= 0.02 and sustain >= 2.0
    weak = pval <= 0.10 and sustain >= 1.0
    verdict = ("LIKELY DETECTED" if strong else
               "AMBIGUOUS" if weak else "NOT DETECTED (signal below floor)")
    print(f"  band {fmin}-{fmax} Hz: noise p99 {n99:.2f} uV, arrival-box peak "
          f"{speak:.2f} uV, ratio {ratio:.2f}x, sustain {sustain:.1f}s")
    print(f"    empirical null: {n_ge}/{len(null)} same-shape noise windows reach it "
          f"({n_back} before, {len(null) - n_back} after), "
          f"p={pval:.3f} -> {verdict}")

    fig, (a1, a2) = plt.subplots(2, 1, sharex=True, figsize=(11, 7))
    a1.plot(t, raw.data * uvpc, "k", lw=0.6); a1.set_ylabel("raw µV")
    mag = f"M{args.mag} " if args.mag is not None else ""
    a1.set_title(f"{tr.id}   {mag}{args.label} ({epi:.0f} km)   raw")
    a2.plot(t, bp, "b", lw=0.6); a2.set_ylabel(f"{fmin:g}-{fmax:g} Hz µV")
    # NOT "microseism removed": this station has essentially no microseism to remove.
    # The 4.5 Hz element is ~60 dB down at 0.07-0.15 Hz, and measurement agrees --
    # 0.454 uV in the 0.05-0.2 Hz band against 5.5 uV raw (2026-08-13). What the
    # filter actually discards here is mostly content ABOVE 15 Hz. That is why the
    # two panels look nearly identical, which is a property of the instrument, not
    # a bug -- so name the band and let the reader see it.
    a2.set_title(f"bandpass {fmin:g}-{fmax:g} Hz   ratio {ratio:.2f}x  "
                 f"sustain {sustain:.1f}s -> {verdict}")
    for a in (a1, a2):
        a.axvline(0, color="g", ls="--"); a.axvline(tP, color="r", ls=":")
        a.axvline(tS, color="orange", ls=":"); a.grid(alpha=0.3)
    # PLOT a human-readable window, not the whole analysis slice. The null samples
    # -900..-10 s and +pad..+600 s, so drawing all of it squeezed a 15-second P-to-S
    # into ~20 of 1200 pixels. The verdict still uses every sample; only the view is
    # cropped, and the caption below says how much the statistic actually saw.
    _pp = args.plot_post if args.plot_post > 0 else post
    a1.set_xlim(-args.pre, _pp)

    a2.set_xlabel(f"s after origin {origin.strftime('%H:%M:%S')} UTC   "
                  f"(green=origin  red=P+{tP:.1f}s  orange=S+{tS:.1f}s)\n"
                  f"view cropped to {-args.pre:.0f}..{_pp:.0f} s   |   "
                  f"the verdict used {args.noise_s:.0f} s before and "
                  f"{args.null_post:.0f} s after")
    fig.tight_layout()
    out = LOCAL_DATA.parent / "eventcheck.png"
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")
    import subprocess
    subprocess.run(["open", "-a", "Preview", str(out)], check=False)


if __name__ == "__main__":
    main()

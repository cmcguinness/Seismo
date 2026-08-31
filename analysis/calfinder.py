#!/usr/bin/env python3
"""calfinder.py — find calibration bursts in the archive by their signature.

WHY THIS EXISTS, AND WHY IT IS WRITTEN FIRST. The inline injector fires into the
geophone coil four times a day, forever, while the station is recording normally.
That means every burst lands in the archive as a real transient with a real STA/LTA
trigger. Left alone it would do two kinds of damage:

  1. Pollution. Four spurious triggers a day walk into `events.log`, and from there
     into the classifier's training set as unlabelled negatives -- except they look
     nothing like cultural noise, so they would teach the model a whole spurious
     class. ~1500/year against ~33 real positives; it would swamp the dataset.
  2. Waste. Each burst is also the single most useful 4.5 s in the day, because it is
     the only signal in the archive whose input is KNOWN. Those are the windows
     `ringdown.py measure --at` wants.

Same detector serves both: find the bursts, mask them out of detection, feed them to
the fitter. This is written before the hardware because it can be fully tested against
synthesised bursts today, and because it GATES first power-up -- there is no point
energising an injector whose output we cannot reliably tell apart from a truck.

THE SIGNATURE, and why each part of it is checkable. The firmware fires N_PULSES
current pulses of PULSE_S seconds, SPACING_S apart. Each pulse contributes TWO
transients -- a step on and an equal, opposite step off -- so the burst is a train of
alternating impulses whose shape we do not need to know in advance. The archive is
then searched for the one property no natural source has:

  * REPEATABILITY. The stimulus is identical each time, so the three SPACING_S-long
    units of a burst are near-identical waveforms. Cross-correlating them is
    shape-agnostic -- it does not care what f0 or zeta turn out to be, which matters
    because f0 and zeta are the unknowns we are firing the injector to measure. An
    earthquake never repeats itself three times at exactly 2.00 s.
  * ISOLATION. Exactly three units, then silence. This is the check that separates a
    burst from PERIODIC MACHINERY, which is the one plausible false positive: a pump
    ticking every 2.00 s with an identical signature would pass the repeatability test
    and fail this one, because its correlation does not stop after three. So the unit
    BEFORE and the unit AFTER the candidate must NOT correlate.
  * AMPLITUDE MATCH. Same current, same coil, so the three units are within a few
    percent. Cheap, and it catches a burst that overlapped something loud.

Timing tolerance is deliberately loose (TOL_S). The injector is a bare RC oscillator
on an ATtiny with no crystal, so SPACING_S drifts with temperature and cell voltage --
by design, since the burst is self-identifying by shape and does not need to keep
time. Do not tighten this to "exactly 2.000 s"; it will not be.

    python analysis/calfinder.py selftest
    python analysis/calfinder.py scan --archive analysis/data --day 2026-09-14
    python analysis/calfinder.py scan --archive analysis/data --all --json bursts.json
"""
import argparse
import glob
import json
import math
import os
import re
import sys

import numpy as np
from scipy import signal

# --- the signature. THESE MUST MATCH THE FIRMWARE. ---------------------------------
# Any change here is a change to calibrator firmware `burst()` and vice versa; they
# are two halves of one protocol. The values are chosen so that:
#   PULSE_S   is many decay time-constants (1/(zeta*w0) ~ 59 ms at zeta 0.6, f0 4.5),
#             so the ring from the step-on has died before the step-off releases.
#   SPACING_S leaves >= 1.5 s of quiet after each release for the fitter to work in.
#   N_PULSES  is 3 because two is a coincidence and four costs charge for nothing.
N_PULSES = 3
PULSE_S = 0.5
SPACING_S = 2.0

TOL_S = 0.20          # allowed drift in SPACING_S (uncalibrated RC oscillator)
TMPL_S = PULSE_S + 0.45   # template: long enough to hold BOTH the step-on and the
                          # step-off of one pulse, short enough to fit inside the
                          # shortest unit SPACING_S - TOL_S can produce
RHO_MIN = 0.90        # min pairwise correlation BETWEEN a burst's units
RHO_CONT = 0.60       # max correlation with the units either side -- half of the
                      # "exactly three, then stop" test that rejects periodic machinery
AMP_CONT = 0.50       # ...and the other half: a continuing source also has to keep
                      # its AMPLITUDE up in the next unit. Both must hold to reject
QUIET_MAX = 0.45      # a unit must fall SILENT after its two steps. This is what
                      # rejects narrowband oscillation -- see _score()
PULSE_TOL_S = 0.12    # tolerance on the measured step-on -> step-off separation
AMP_TOL = 1.30        # max/min of the three unit amplitudes
TRIG_K = 4.0          # envelope must exceed this x the rolling background
BAND = (0.5, 20.0)    # the injected transient lives at f0 ~ 4.5 Hz
ENV_S = 0.05          # envelope smoothing. Short on purpose: a well-damped element
                      # gives a ~20 ms spike, and smoothing it over 100 ms buries it
                      # below the trigger threshold entirely
BG_S = 120.0          # rolling-background window
PAD_S = 5.0           # mask padding either side of a burst

# The injector must put bursts at least this many times the background RMS, across
# all plausible damping. This is a REQUIREMENT ON THE HARDWARE, established by the
# sweep in selftest(), not a knob: RHO_MIN is what rejects decoys, and it cannot be
# relaxed to rescue a burst that was injected too weakly. See doc/BOM-calibrator.md.
SNR_SPEC = 50.0


def bandpass(x, fs, band=BAND):
    sos = signal.butter(4, [band[0] / (fs / 2), band[1] / (fs / 2)], "bandpass",
                        output="sos")
    return signal.sosfiltfilt(sos, x)


def envelope(y, fs, smooth_s=ENV_S):
    n = max(1, int(smooth_s * fs))
    return np.convolve(np.abs(y), np.ones(n) / n, mode="same")


def _rolling_median(a, n):
    """Background level: block medians, vectorised, then interpolated.

    A true sliding median over a day-file is far too slow and we do not need one --
    the background moves on a scale of minutes. An earlier version sampled exact
    medians on a decimated grid, which is correct but still O(N * window) because
    every grid point re-medians a full window: on 38 day-files that did not finish in
    ten minutes. Non-overlapping block medians are one vectorised `np.median` over a
    reshaped array, and a short median-of-blocks afterwards restores the smoothing
    that the overlap used to provide.
    """
    a = np.asarray(a, float)
    n = max(1, int(n))
    b = max(1, n // 4)
    nb = len(a) // b
    if nb < 3:
        return np.full(len(a), float(np.median(a)))
    bm = np.median(a[:nb * b].reshape(nb, b), axis=1)
    k = 2
    sm = np.array([np.median(bm[max(0, i - k):i + k + 1]) for i in range(nb)])
    centres = (np.arange(nb) + 0.5) * b
    return np.interp(np.arange(len(a)), centres, sm)


def normcorr(a, b):
    """Pearson correlation of two equal-length segments; 0 if either is flat."""
    n = min(len(a), len(b))
    if n < 8:
        return 0.0
    a = np.asarray(a[:n], float) - np.mean(a[:n])
    b = np.asarray(b[:n], float) - np.mean(b[:n])
    da, db = np.linalg.norm(a), np.linalg.norm(b)
    if da <= 0 or db <= 0:
        return 0.0
    return float(np.dot(a, b) / (da * db))


def _energy_mask(tmpl, fs, frac=0.80):
    """Columns of the template that actually carry signal.

    A unit is TMPL_S long but the energy in it is two short transients with dead time
    between them -- at zeta 0.85 the element barely rings, so ~85% of the template is
    pure noise. Correlating over all of it dilutes the match toward zero and pushes the
    detection floor up by the square root of that ratio. Correlating only where the
    template has energy is a sparse matched filter: same specificity (the mask comes
    from the candidate itself, so it cannot invent a match), much better sensitivity.
    """
    e = envelope(np.asarray(tmpl, float), fs, smooth_s=0.05)
    if e.max() <= 0:
        return np.ones(len(e), bool)
    # Keep the fewest samples holding `frac` of the template's energy -- NOT a
    # threshold on the peak, and not a fixed count either. A threshold looks
    # equivalent but is not: as SNR falls the noise lifts the envelope everywhere, the
    # mask dilates back toward the full template, and the sensitivity it was bought
    # for quietly evaporates in exactly the regime that needed it. A fixed count is
    # stable but wrong at both ends, because how many samples carry the signal depends
    # on the damping we are trying to measure: a lightly damped element rings for ~50
    # samples, a well-damped one gives two ~10-sample spikes. Energy fraction adapts.
    order = np.argsort(e)[::-1]
    cum = np.cumsum(e[order] ** 2)
    k = int(np.searchsorted(cum, frac * cum[-1]) + 1)
    k = int(np.clip(k, 10, max(10, len(e) // 2)))
    m = np.zeros(len(e), bool)
    m[order[:k]] = True
    return m


def _slide_corr(y, tmpl, lo, hi, mask=None):
    """Normalised correlation of `tmpl` against `y` at every lag in [lo, hi).

    Sample-resolution, not a grid search. This is the whole trick: the injected
    transient lives at ~4.5 Hz, where 50 ms of misalignment is 81 degrees of phase
    and destroys the correlation the detector depends on. Alignment therefore has to
    be MEASURED, never stepped over -- and measuring it is also what lets the
    oscillator drift freely, since the lag of the best match IS the pulse spacing.
    """
    T = len(tmpl)
    lo = max(0, lo)
    hi = min(len(y) - T, hi)
    if hi <= lo:
        return np.arange(0), np.zeros(0)
    win = np.lib.stride_tricks.sliding_window_view(y[lo:hi + T], T)[: hi - lo]
    t = np.asarray(tmpl, float)
    if mask is not None:
        win, t = win[:, mask], t[mask]
    win = win - win.mean(axis=1, keepdims=True)
    t = t - np.mean(t)
    nt = np.linalg.norm(t)
    nw = np.linalg.norm(win, axis=1)
    good = (nw > 0) & (nt > 0)
    r = np.zeros(len(win))
    r[good] = (win[good] @ t) / (nw[good] * nt)
    return np.arange(lo, hi), r


def _refine(y, fs, a0, u, tmpl_len):
    """Locate the burst's first step-on, and measure the on->off separation.

    Two reasons this is not just `a0`. First, `sosfiltfilt` is zero-phase, so the
    band-pass smears a loud transient BACKWARDS as pre-ringing; at high SNR that
    precursor clears the envelope threshold and the naive anchor lands up to a pulse
    width early. Second, the release instants are what `ringdown.py` fits, so an error
    here is fitted noise rather than a ring-down.

    The three units are stacked first (coherent, so signal adds and noise averages
    down by sqrt(N_PULSES)) and the onset taken from the stack.
    """
    if a0 + N_PULSES * u > len(y):
        return 0, float("nan")
    stack = np.mean([y[a0 + k * u: a0 + k * u + u] for k in range(N_PULSES)], axis=0)
    e = envelope(stack, fs, smooth_s=0.05)
    if e.max() <= 0:
        return 0, float("nan")
    pk = int(np.argmax(e))
    w = int(0.15 * fs)
    # is the biggest peak the step-on or the step-off? The two are PULSE_S apart and
    # of equal magnitude, so look one pulse width earlier for an equal partner.
    j = pk - int(PULSE_S * fs)
    lo, hi = max(0, j - w), max(0, j + w)
    if hi > lo and e[lo:hi].max() > 0.5 * e[pk]:
        on = lo + int(np.argmax(e[lo:hi]))
        off = pk
    else:
        on = pk
        j = pk + int(PULSE_S * fs)
        lo, hi = min(len(e) - 1, j - w), min(len(e), j + w)
        off = (lo + int(np.argmax(e[lo:hi]))) if hi > lo else pk + int(PULSE_S * fs)
    return int(on), (off - on) / fs


def _score(y, fs, a0, tmpl):
    """Full signature test for a candidate burst anchored near a0.

    Returns a dict of measurements, or None. The caller applies the gates.

    THE HARD FALSE POSITIVE, found by scanning real archive data rather than
    synthetic decoys: a NARROWBAND OSCILLATION. Searching for the spacing that
    maximises the repeat correlation is exactly the wrong thing to do to a signal that
    is self-similar at every lag near a multiple of its own period -- a sustained 2 Hz
    wavetrain correlates with itself at ~2.0 s about as well as a real burst does, and
    with ~40 candidate lags to choose from, something always fits. The first version
    of this file reported nine "bursts" in 5.6 h of archive with no injector attached,
    and gave away the diagnosis by scattering their spacings uniformly across the
    whole tolerance window instead of clustering.

    Correlation alone cannot see the difference, so this leans on two things we know
    because we DESIGNED the stimulus, and which no oscillation reproduces:

      QUIET. A unit is two steps PULSE_S apart and then silence for the rest of
      SPACING_S. Oscillation fills the whole unit. Comparing the tail's RMS with the
      head's is damping-agnostic -- it asks "did it stop?", not "what shape was it?"
      -- which matters because the damping is the unknown we are measuring.

      STRUCTURE. The two steps are PULSE_S apart, a number the firmware fixes and the
      ground has no reason to reproduce.
    """
    u_lo = int((SPACING_S - TOL_S) * fs)
    u_hi = int((SPACING_S + TOL_S) * fs)
    mask = _energy_mask(tmpl, fs)
    lo, hi = a0 - u_hi - 1, a0 + 3 * u_hi + 2
    lags, r = _slide_corr(y, tmpl, lo, hi, mask)
    if not len(lags):
        return None
    rr = {int(l): v for l, v in zip(lags, r)}
    # The isolation test uses the FULL template, never the mask. The two tests want
    # opposite things: the match test wants sensitivity, so it looks only where the
    # signal is; the isolation test wants a STABLE answer over noise, and a dozen
    # masked samples of noise correlate at +/-0.3 by chance -- which reads as a fourth
    # repeat and throws away the real burst. Full length, small variance.
    lags_f, r_f = _slide_corr(y, tmpl, lo, hi, None)
    rf = {int(l): v for l, v in zip(lags_f, r_f)}

    best = None
    for u in range(u_lo, u_hi + 1):
        vals = [rr.get(a0 + k * u) for k in range(1, N_PULSES)]
        if any(v is None for v in vals):
            continue
        rho_in = min(vals)
        if best is None or rho_in > best[1]:
            best = (u, rho_in)
    if best is None:
        return None
    u, rho_in = best

    d_on, pulse_meas = _refine(y, fs, a0, u, len(tmpl))
    onset = a0 + d_on
    if onset < 0 or onset + (N_PULSES + 1) * u > len(y):
        return None

    # Stack the FULL units (not just a template's worth) at the refined onset. Signal
    # adds coherently, noise averages down by sqrt(N_PULSES), and the tail we are
    # about to interrogate for silence is included.
    stack = np.mean([y[onset + k * u: onset + (k + 1) * u] for k in range(N_PULSES)],
                    axis=0)
    head_n = min(len(stack) - 1, int((PULSE_S + 0.3) * fs))
    head, tail = stack[:head_n], stack[head_n:]
    rms = lambda v: float(np.sqrt(np.mean(np.square(v)))) if len(v) else 0.0
    quiet = rms(tail) / max(rms(head), 1e-12)

    # Amplitudes by PROJECTION onto the stack -- not by peak |y|, and not onto unit 1.
    #
    # Not peak |y|, because a well-damped element's transient is a ~20 ms spike whose
    # peak sample is set as much by what the noise did there as by the injected
    # current; at SNR 30 that scattered the three amplitudes by 55% and failed
    # AMP_TOL on a perfectly good burst. A least-squares scale factor averages over
    # the whole waveform and is the lowest-variance estimate available.
    #
    # And not onto unit 1, because unit 1 is the template: it projects onto itself as
    # exactly 1.0 with its own noise included, while the others project as roughly
    # their correlation. That is a systematic bias, not scatter -- it made the ratio
    # ~1/rho and rejected bursts for being well correlated. The stack privileges no
    # unit, so every projection carries the same bias and the RATIO is clean.
    smask = _energy_mask(stack, fs)
    t = stack[smask] - np.mean(stack[smask])
    tt = float(np.dot(t, t)) or 1e-12

    def proj(i):
        seg = y[i: i + len(stack)]
        if i < 0 or len(seg) < len(stack):
            return 0.0
        seg = seg[smask]
        return abs(float(np.dot(seg - np.mean(seg), t) / tt))

    def peak(i):
        seg = y[max(0, i): i + len(stack)]
        return float(np.max(np.abs(seg))) if len(seg) else 0.0

    amps = [proj(onset + k * u) for k in range(N_PULSES)]
    ratio = max(amps) / max(min(amps), 1e-12)
    med = max(np.median(amps), 1e-12)
    amp_out = max(proj(onset - u), proj(onset + N_PULSES * u)) / med

    outs = [abs(rf.get(a0 - u, 0.0)), abs(rf.get(a0 + N_PULSES * u, 0.0))]
    return {
        "onset": onset, "u": u,
        "rho_in": rho_in, "rho_out": max(outs),
        "amp_ratio": ratio, "amp_out": amp_out,
        "quiet": quiet, "pulse_s_meas": pulse_meas,
        "counts": float(np.median([peak(onset + k * u) for k in range(N_PULSES)])),
    }


def find_bursts(x, fs, t0=0.0, verbose=False):
    """Locate calibration bursts in a trace. Returns a list of dicts.

    `t0` is the trace start time in seconds (or a UTCDateTime timestamp); burst times
    are reported as t0 + offset so callers get absolute instants.
    """
    y = bandpass(np.asarray(x, float), fs)
    env = envelope(y, fs)
    bg = _rolling_median(env, int(BG_S * fs))
    hot = env > TRIG_K * np.maximum(bg, 1e-12)
    if not hot.any():
        return []

    edges = np.flatnonzero(hot[1:] & ~hot[:-1]) + 1
    if hot[0]:
        edges = np.r_[0, edges]
    T = int(TMPL_S * fs)
    u_nom = int(SPACING_S * fs)

    out, claimed = [], []
    for e in edges:
        e = int(e)
        if any(abs(e - c) < (N_PULSES + 1) * u_nom for c in claimed):
            continue          # already inside a burst we found
        if e + T > len(y):
            continue
        got = _score(y, fs, e, y[e:e + T])
        if got is None:
            continue
        # A source that is still going has to look alike AND stay loud. Requiring both
        # matters at heavy damping: the element barely rings, so the template is two
        # narrow spikes with few effective degrees of freedom, and its correlation
        # against plain background scatters far more widely than the sample count
        # suggests. Correlation alone would veto real bursts on noise.
        continues = got["rho_out"] > RHO_CONT and got["amp_out"] > AMP_CONT
        if (got["rho_in"] < RHO_MIN
                or continues
                or got["amp_ratio"] > AMP_TOL
                or got["quiet"] > QUIET_MAX
                or abs(got["pulse_s_meas"] - PULSE_S) > PULSE_TOL_S):
            continue
        claimed.append(e)
        spacing = got["u"] / fs
        onset = got["onset"]
        rel = [(onset / fs) + PULSE_S + k * spacing for k in range(N_PULSES)]
        out.append({
            "start": t0 + onset / fs,
            "spacing_s": round(spacing, 4),
            "rho_in": round(got["rho_in"], 4),
            "rho_out": round(got["rho_out"], 4),
            "amp_ratio": round(got["amp_ratio"], 4),
            "amp_out": round(got["amp_out"], 3),
            "quiet": round(got["quiet"], 4),
            "pulse_s_meas": round(got["pulse_s_meas"], 3),
            "amp_counts": round(got["counts"], 1),
            "releases": [t0 + r for r in rel],
        })
        if verbose:
            print(f"  burst at +{onset/fs:8.2f}s  spacing={spacing:.3f}s "
                  f"rho_in={got['rho_in']:.3f} rho_out={got['rho_out']:.3f} "
                  f"quiet={got['quiet']:.2f} pulse={got['pulse_s_meas']:.2f} "
                  f"amp={got['counts']:.0f}")
    return out


def cal_windows(bursts, pad=PAD_S):
    """Mask intervals for the detector and the training-set builder.

    Anything overlapping one of these is the injector, not the ground. Padded because
    the STA/LTA's LTA is still contaminated for a few seconds after the last release.
    """
    return [(b["start"] - pad,
             b["start"] + N_PULSES * b.get("spacing_s", SPACING_S) + pad)
            for b in bursts]


# --- synthesis, for the self-test ---------------------------------------------------

def synth_burst(fs, f0=4.5, zeta=0.6, amp=5000.0, spacing_s=SPACING_S,
                pulse_s=PULSE_S, n=N_PULSES):
    """A geophone's output for a train of coil-current pulses.

    A step of force on a mass-spring-damper gives a velocity response
        v(t) = A * exp(-zeta*w0*t) * sin(w_d*t),
    and the coil's output voltage is proportional to velocity. The step OFF is the
    same shape inverted. This is exactly the model `ringdown.py` fits, which is the
    point: the self-test proves the finder hands the fitter something it can use.
    """
    total = int((n * spacing_s + 1.0) * fs)
    out = np.zeros(total)
    w0 = 2 * math.pi * f0
    wd = w0 * math.sqrt(max(1e-9, 1 - zeta ** 2))
    a = zeta * w0
    tail = np.arange(int(1.5 * fs)) / fs
    shape = np.exp(-a * tail) * np.sin(wd * tail)
    for k in range(n):
        for off, sign in ((0.0, +1.0), (pulse_s, -1.0)):
            i = int((k * spacing_s + off) * fs)
            j = min(total, i + len(shape))
            out[i:j] += sign * amp * shape[:j - i]
    return out


def _noise(nsamp, fs, rms=120.0, rng=None):
    """Red-ish background, closer to a real seismic floor than white noise."""
    rng = rng or np.random.default_rng(0)
    w = rng.standard_normal(nsamp)
    sos = signal.butter(2, min(0.45, 8.0 / (fs / 2)), "low", output="sos")
    y = signal.sosfilt(sos, w)
    return y / (np.std(y) or 1.0) * rms


def selftest():
    """Prove the finder catches bursts and, more importantly, refuses decoys."""
    fs = 100.0
    # Each trial draws from its OWN seeded stream. They shared one until adding three
    # decoys shifted every later noise realisation and made an unrelated test fail --
    # a test suite whose cases perturb each other cannot be trusted to localise a
    # regression to the thing that caused it.
    dur = 600
    fails = []

    def trial(name, x, expect, t_expect=None, **kw):
        got = find_bursts(x, fs, **kw)
        ok = len(got) == expect
        detail = ""
        if ok and t_expect is not None and got:
            err = abs(got[0]["start"] - t_expect)
            ok = err < 0.10
            detail = f" (start off by {err*1000:.0f} ms)"
        if ok and got:
            detail = f" rho_in={got[0]['rho_in']:.3f} rho_out={got[0]['rho_out']:.3f}"
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: found {len(got)}, "
              f"expected {expect}{detail}")
        if not ok:
            fails.append(name)
        return got

    print("finds real bursts (SNR = peak burst amplitude / background RMS):")
    for zeta in (0.3, 0.6, 0.85):
        for snr in (200.0, 100.0, SNR_SPEC):
            x = _noise(int(dur * fs), fs,
                       rng=np.random.default_rng(hash((zeta, snr)) % 9999))
            b = synth_burst(fs, zeta=zeta, amp=120.0 * snr)
            at = 300.0
            x[int(at * fs):int(at * fs) + len(b)] += b
            trial(f"zeta={zeta} snr={snr:g}", x, 1, t_expect=at)

    print("tolerates oscillator drift (the ATtiny has no crystal):")
    for sp in (1.85, 2.0, 2.15):
        x = _noise(int(dur * fs), fs, rng=np.random.default_rng(102))
        b = synth_burst(fs, amp=120.0 * SNR_SPEC, spacing_s=sp)
        x[int(300 * fs):int(300 * fs) + len(b)] += b
        trial(f"spacing={sp}s", x, 1, t_expect=300.0)

    print("rejects decoys:")
    # an earthquake: a growing, decaying, non-repeating wavetrain
    x = _noise(int(dur * fs), fs, rng=np.random.default_rng(103))
    t = np.arange(int(20 * fs)) / fs
    q = (np.exp(-((t - 3) ** 2) / 4.0) * 6000
         * np.sin(2 * math.pi * (2 + 4 * np.exp(-t / 6)) * t))
    x[int(300 * fs):int(300 * fs) + len(q)] += q
    trial("earthquake", x, 0)

    # three spikes at 2.00 s but each a different shape -- a truck over expansion joints
    x = _noise(int(dur * fs), fs, rng=np.random.default_rng(104))
    for k in range(3):
        i = int((300 + 2.0 * k) * fs)
        s = synth_burst(fs, f0=4.5 + 2.0 * k, zeta=0.3 + 0.2 * k, amp=5000.0, n=1)
        x[i:i + len(s)] += s
    trial("three mismatched spikes at 2 s", x, 0)

    # three IDENTICAL spikes but amplitudes 1.0 / 0.5 / 1.0
    x = _noise(int(dur * fs), fs, rng=np.random.default_rng(105))
    for k, sc in enumerate((1.0, 0.5, 1.0)):
        i = int((300 + 2.0 * k) * fs)
        s = synth_burst(fs, amp=5000.0 * sc, n=1)
        x[i:i + len(s)] += s
    trial("amplitude-mismatched triplet", x, 0)

    # THE ONE THAT ACTUALLY BIT, and only showed up against real archive data: a
    # sustained narrowband wavetrain. It is self-similar at every lag near a multiple
    # of its own period, so the spacing search will always find SOME lag that
    # correlates -- correlation cannot tell it from a burst. The quiet test can.
    for f_hz, name in ((2.0, "2 Hz"), (0.7, "0.7 Hz swell"), (4.5, "4.5 Hz at f0")):
        x = _noise(int(dur * fs), fs, rng=np.random.default_rng(106))
        t = np.arange(int(12 * fs)) / fs
        env_ = np.exp(-((t - 6) ** 2) / 18.0)
        x[int(300 * fs):int(300 * fs) + len(t)] += 6000 * env_ * np.sin(
            2 * math.pi * f_hz * t)
        trial(f"narrowband {name}", x, 0)

    # THE HARD ONE: periodic machinery, identical signature every 2.00 s, forever.
    # Passes repeatability; must fail isolation.
    x = _noise(int(dur * fs), fs, rng=np.random.default_rng(107))
    s = synth_burst(fs, amp=120.0 * SNR_SPEC, n=1)
    for k in range(60):
        i = int((200 + 2.0 * k) * fs)
        x[i:i + len(s)] += s
    trial("periodic machinery @2.00s", x, 0)

    # The known limit, asserted so that improving it shows up as a surprise rather
    # than passing silently. A near-critically-damped element barely rings, so a weak
    # burst leaves almost no waveform to correlate -- and the only way to catch it
    # would be to lower RHO_MIN, which is exactly what rejects the decoys above. The
    # answer is to inject harder, not to loosen the gate.
    print("documented limit (expected miss -- inject above SNR_SPEC instead):")
    x = _noise(int(dur * fs), fs, rng=np.random.default_rng(108))
    b = synth_burst(fs, zeta=0.85, amp=120.0 * 10.0)
    x[int(300 * fs):int(300 * fs) + len(b)] += b
    trial("zeta=0.85 snr=10", x, 0)

    # Where does it stop working? This number is a DESIGN REQUIREMENT ON THE
    # HARDWARE, not a property of the software: RHO_MIN is what buys the decoy
    # rejection above, and it cannot be relaxed to rescue a burst that was injected
    # too weakly. So measure the floor here and size the injection resistor to sit
    # comfortably above it. Heavier damping is the harder case -- a well-damped
    # element barely rings, so less of the template carries signal.
    print("detection floor vs SNR (sets the injection level, see BOM):")
    for zeta in (0.3, 0.6, 0.85):
        floor = None
        for snr in (2, 3, 4, 5, 6, 8, 10, 14, 20, 30, 40, 60, 90):
            hits = 0
            for seed in range(5):
                r2 = np.random.default_rng(1000 + seed)
                x = _noise(int(120 * fs), fs, rng=r2)
                b = synth_burst(fs, zeta=zeta, amp=120.0 * snr)
                x[int(60 * fs):int(60 * fs) + len(b)] += b
                hits += len(find_bursts(x, fs)) == 1
            if hits == 5:
                floor = snr
                break
        flag = "" if (floor and floor <= SNR_SPEC) else "   <-- above SNR_SPEC!"
        print(f"  zeta={zeta}: reliable from SNR >= "
              f"{floor if floor else '>90'}{flag}")
        if floor and floor > SNR_SPEC:
            fails.append(f"floor zeta={zeta} exceeds SNR_SPEC")

    print("finds several bursts in one day, and masks them:")
    x = _noise(int(6 * 3600 * fs), fs, rng=np.random.default_rng(4242) if 0 else np.random.default_rng(109))
    ats = [1800.0, 9000.0, 15000.0]
    for at in ats:
        b = synth_burst(fs, amp=120.0 * SNR_SPEC)
        x[int(at * fs):int(at * fs) + len(b)] += b
    got = trial("3 bursts in 6 h", x, 3)
    if len(got) == 3:
        w = cal_windows(got)
        ok = all(w[i][0] < ats[i] < w[i][1] for i in range(3))
        print(f"  [{'PASS' if ok else 'FAIL'}] mask windows cover all three")
        if not ok:
            fails.append("mask windows")

    # The firmware and this file are two halves of one agreement, and nothing at
    # runtime would notice them drifting apart -- the bursts would simply stop being
    # found, months later, silently. Check it here where it is cheap.
    print("firmware and finder agree on the signature:")
    fw = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "calibrator", "calibrator.c")
    try:
        src = open(fw).read()
        want = {"N_PULSES": N_PULSES,
                "PULSE_MS": int(PULSE_S * 1000),
                "SPACING_MS": int(SPACING_S * 1000)}
        for name, expect in want.items():
            m = re.search(rf"^#define\s+{name}\s+(\d+)", src, re.M)
            got = int(m.group(1)) if m else None
            ok = got == expect
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}: firmware {got}, "
                  f"calfinder {expect}")
            if not ok:
                fails.append(f"{name} mismatch")
    except FileNotFoundError:
        print(f"  [FAIL] {fw} not found")
        fails.append("firmware missing")

    print()
    if fails:
        print(f"FAILED: {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


def cmd_scan(a):
    from obspy import Stream, UTCDateTime, read

    pats = []
    if a.day:
        t = UTCDateTime(a.day)
        pats.append(f"{a.archive}/*.D.{t.year}.{t.julday:03d}.mseed")
    else:
        pats.append(f"{a.archive}/*.mseed")
    files = sorted({f for p in pats for f in glob.glob(p)})
    if not files:
        print(f"no day-files matched under {a.archive}", file=sys.stderr)
        return 1

    all_bursts = []
    for f in files:
        st = read(f)
        try:
            st.merge(method=1, fill_value="interpolate")
        except Exception:
            # The earliest day-files predate the exact 100 sps grid and carry
            # fragments at several sampling rates, which obspy refuses to merge.
            # Keep the dominant rate and move on -- that data is equipment testing.
            rates = [tr.stats.sampling_rate for tr in st]
            keep = max(set(rates), key=rates.count)
            print(f"{f}: mixed sampling rates {sorted(set(rates))}, keeping {keep}")
            st = Stream([tr for tr in st if tr.stats.sampling_rate == keep])
            st.merge(method=1, fill_value="interpolate")
        for tr in st:
            if tr.stats.npts < int(10 * N_PULSES * SPACING_S * tr.stats.sampling_rate):
                continue
            fs = float(tr.stats.sampling_rate)
            print(f"{f} {tr.id} {tr.stats.starttime} "
                  f"({tr.stats.npts/fs/3600:.1f} h)", flush=True)
            found = find_bursts(np.asarray(tr.data, float), fs,
                                t0=float(tr.stats.starttime.timestamp),
                                verbose=a.verbose)
            for b in found:
                b["start_utc"] = str(UTCDateTime(b["start"]))
                b["releases_utc"] = [str(UTCDateTime(r)) for r in b["releases"]]
                print(f"  BURST {b['start_utc']}  rho_in={b['rho_in']:.3f} "
                      f"rho_out={b['rho_out']:.3f} amp={b['amp_counts']:.0f} counts")
            all_bursts += found

    print(f"\n{len(all_bursts)} burst(s) over {len(files)} file(s)")
    if all_bursts:
        rel = [r for b in all_bursts for r in b["releases_utc"]]
        print("\nfeed the releases to the fitter:")
        print(f"  python analysis/ringdown.py measure --archive {a.archive} \\\n"
              "      --at " + " \\\n           ".join(rel[:12]))
        if len(rel) > 12:
            print(f"  ... and {len(rel)-12} more")
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(all_bursts, fh, indent=2)
        print(f"\nwrote {a.json}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="find bursts in archive day-files")
    s.add_argument("--archive", default="analysis/data")
    s.add_argument("--day", help="YYYY-MM-DD (default: every file in --archive)")
    s.add_argument("--all", action="store_true", help="explicit 'every file'")
    s.add_argument("--json", help="write the bursts to this file")
    s.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("selftest", help="synthetic bursts and decoys; no archive needed")

    a = ap.parse_args(argv)
    return selftest() if a.cmd == "selftest" else cmd_scan(a)


if __name__ == "__main__":
    sys.exit(main())

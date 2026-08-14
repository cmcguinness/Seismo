#!/usr/bin/env python3
"""stalta.py — streaming, band-limited STA/LTA earthquake trigger.

Classic short-term-average / long-term-average detector, O(1) per sample (recursive
EMAs + biquad sections), so it runs inline in the recorder's sample loop for negligible
cost and only touches disk on a real trigger.

Pipeline per sample:
  raw counts -> 1-pole HIGH-pass at SEISMO_HP (rejects microseism/tilt/settling that
  would otherwise dominate the energy) -> 4-pole Butterworth LOW-pass at 15 Hz
  -> square = energy characteristic function (CF) -> STA / LTA -> trigger at >= trig.
  In parallel and INDEPENDENTLY of that high-pass, 1-8 Hz and >15 Hz energies
  accumulate over the event and are reported as `hf_lf`, a source-distance
  discriminant.

The LTA is FROZEN while triggered, so a long event doesn't raise its own background
and self-terminate. `max_dur_s` caps a stuck trigger, after which the LTA re-adapts.

Feed raw ADC counts to update(); it returns an event dict on de-trigger, else None.
Pure stdlib (math only) so it's safe to import into the recorder.

BAND-LIMITING + hf_lf (2026-08-14). Until now the CF was high-passed only, so it
integrated up to Nyquist -- and the two source classes live in different bands:

    source                    1-8 Hz   8-15   15-30   30-45   HF/LF
    M4.1 San Leandro, 88 km     89.6    17.3     5.0     3.0    0.06
    M2.8 Geysers, 45 km         25.4    19.9    15.2    19.4    0.97
    door slam, ~3 m              3.9    35.5    14.8     6.5    4.12
    cans rolling, ~3 m           4.2     9.7    23.5    23.5    7.84

Path attenuation strips the high frequencies out of a real quake; a source three metres
away keeps all of them, so an unweighted CF handed the decision to the band where only
cultural noise lives. Measured: a labelled trash-can run on 2026-08-13 triggered EIGHT
times, peaking at ratio 256.7, while a confirmed M2.8 reached 4.0 -- a man with a
wheelie bin outranked a real earthquake by 64x.

Validated by `analysis/stalta_band.py`, which replays archive days 223-226 (5 confirmed
quakes, 4 labelled cultural episodes) through old and new AT THE PRODUCTION SEISMO_HP,
and reproduces the live events.log ratios exactly:

  - band-limiting alone lifts the marginal M2.8 from 4.0 to 10.7 and the others by
    1.5-3.5x. It does NOT separate on its own: rolling cans are genuine 1-15 Hz ground
    motion three metres away and still reach 307.
  - `hf_lf` does separate. Dominant-trigger values: quakes 0.09-0.98, cultural
    1.95-5.26. A 1.4 cut splits all nine labelled cases and rejects 80-95% of daily
    triggers (17.9-37.7/h -> 1.4-10.6/h).

`hf_lf` is REPORTED, not enforced here. The margin is only ~2x on n=9, so the consumer
decides; a mislabelled quake still in the log is recoverable, a deleted one is not.
See CULTURAL_HF_LF.

The classifier's own filters run on the RAW input, not on the trigger's high-passed
signal. The station runs SEISMO_HP=3.0, so sharing it would silently redefine the
"1-8 Hz" band as 3-8 Hz and make the calibration above a function of trigger tuning.
"""
import math

CULTURAL_HF_LF = 1.4   # hf_lf at or above this reads as near-field cultural noise


class _Biquad:
    """One RBJ biquad section, transposed direct form II. Pure stdlib.

    Cascade two of these (Q = 0.5412, 1.3066) for a 4-pole Butterworth. The cheap
    cascaded-RC filters this file used first were NOT good enough: a 2-pole RC
    high-pass at 15 Hz is only ~3.5x down at 8 Hz, so for a quake -- whose 1-8 Hz
    energy is ~30x its >15 Hz energy -- the leakage swamped the band it was supposed
    to measure, and every source collapsed to hf_lf ~ 1. Butterworth at 24 dB/octave
    puts 8 Hz 154x down in ENERGY, which is what makes the ratio mean something.
    """

    __slots__ = ("b0", "b1", "b2", "a1", "a2", "s1", "s2")

    def __init__(self, kind, f0, fs, q):
        w0 = 2.0 * math.pi * f0 / fs
        c, sn = math.cos(w0), math.sin(w0)
        alpha = sn / (2.0 * q)
        if kind == "lp":
            b0, b1, b2 = (1 - c) / 2, 1 - c, (1 - c) / 2
        else:
            b0, b1, b2 = (1 + c) / 2, -(1 + c), (1 + c) / 2
        a0, a1, a2 = 1 + alpha, -2 * c, 1 - alpha
        self.b0, self.b1, self.b2 = b0 / a0, b1 / a0, b2 / a0
        self.a1, self.a2 = a1 / a0, a2 / a0
        self.s1 = self.s2 = 0.0

    def __call__(self, x):
        y = self.b0 * x + self.s1
        self.s1 = self.b1 * x - self.a1 * y + self.s2
        self.s2 = self.b2 * x - self.a2 * y
        return y


BW4_Q = (0.54119610, 1.30656296)      # 4-pole Butterworth section Qs


def _bw4(kind, f0, fs):
    return [_Biquad(kind, f0, fs, q) for q in BW4_Q]


def _run4(sections, x):
    for s in sections:
        x = s(x)
    return x


class StaLta:
    """Band-limited STA/LTA with a source-distance classifier.

    `lp_hz=None` reproduces the pre-2026-08-14 detector exactly, for A/B replay.
    """

    def __init__(self, fs, *, hp_hz=1.0, lp_hz=15.0, sta_s=1.0, lta_s=30.0,
                 trig=4.0, detrig=1.5, min_dur_s=0.4, max_dur_s=180.0,
                 uv_per_count=1.0):
        dt = 1.0 / fs
        rc = 1.0 / (2 * math.pi * hp_hz)
        self._hp_alpha = rc / (rc + dt)                 # 1-pole HPF coefficient
        self._lp = None if lp_hz is None else _bw4("lp", lp_hz, fs)
        self._a_sta = 1.0 / max(1.0, sta_s * fs)        # EMA rates (~1/window_samples)
        self._a_lta = 1.0 / max(1.0, lta_s * fs)
        self.trig, self.detrig = trig, detrig
        self._min_dur = min_dur_s * fs                  # in samples
        self._max_dur = max_dur_s * fs
        self._uv = uv_per_count
        self._dt = dt
        self._n_prime = int(lta_s * fs)                 # let LTA settle before arming

        # --- band-ratio classifier: 4-pole Butterworth, on the RAW input ---
        # Deliberately NOT fed from the trigger's high-pass. The station runs
        # SEISMO_HP=3.0, so reusing `hp` would silently redefine the "1-8 Hz" band as
        # 3-8 Hz and make the classifier's calibration a function of trigger tuning --
        # a validate-one-thing-ship-another trap. Six biquads per sample is ~6 kflop/s
        # at 100 sps; the Pi 2B does not notice.
        self._lo = _bw4("hp", 1.0, fs) + _bw4("lp", 8.0, fs)   # 1-8 Hz
        self._hi = _bw4("hp", 15.0, fs)                        # >15 Hz (also kills DC)
        self._e_lo = self._e_hi = 0.0

        self._x_prev = self._hp = 0.0
        self._sta = self._lta = 0.0
        self._primed = 0
        self.triggered = False
        self._t = 0
        self._peak_ratio = self._peak_amp = 0.0
        self.ratio = 0.0

    def update(self, x):
        """Feed one raw count. Returns an event dict on de-trigger, else None."""
        x = float(x)
        hp = self._hp_alpha * (self._hp + x - self._x_prev)   # high-pass
        self._x_prev, self._hp = x, hp
        y = hp if self._lp is None else _run4(self._lp, hp)   # 4-pole LP -> 1-15 Hz CF
        cf = y * y                                            # energy CF

        # --- band energies for the classifier -------------------------------------
        # Reported as hf_lf = sqrt(E>15 / E[1-8]) accumulated over the event window.
        # By Parseval that is the same quantity an FFT band-ratio measures, but it
        # costs four filter states and two multiply-accumulates per sample instead of
        # a transform -- so the identical code runs inline in the recorder on a Pi 2B
        # and in the pi5 replay. Validating an FFT version and shipping a streaming
        # one is exactly the mistake the despiker made; this IS the shipped one.
        ylo = _run4(self._lo, x)                              # 1-8 Hz, from RAW x
        yhi = _run4(self._hi, x)                              # >15 Hz, from RAW x
        if self.triggered:
            self._e_lo += ylo * ylo
            self._e_hi += yhi * yhi

        self._sta += (cf - self._sta) * self._a_sta
        if not self.triggered:                               # freeze LTA during events
            self._lta += (cf - self._lta) * self._a_lta
        self.ratio = self._sta / self._lta if self._lta > 1e-12 else 0.0

        if self._primed < self._n_prime:                     # wait for LTA to settle
            self._primed += 1
            return None

        # Peak amplitude comes from the FILTERED signal, not the raw count: `x` carries
        # the front end's DC operating point (see server/stalta.py for the 2026-07-24
        # faux-detection story). With the low-pass in, `y` is the in-band amplitude,
        # which is also the number worth reporting.
        amp = abs(y) * self._uv
        if not self.triggered:
            if self.ratio >= self.trig:
                self.triggered = True
                self._t = 0
                self._peak_ratio, self._peak_amp = self.ratio, amp
                self._e_lo = self._e_hi = 0.0
            return None

        # in an event
        self._t += 1
        self._peak_ratio = max(self._peak_ratio, self.ratio)
        self._peak_amp = max(self._peak_amp, amp)
        if self.ratio <= self.detrig or self._t >= self._max_dur:
            self.triggered = False
            if self._t >= self._min_dur:
                hl = math.sqrt(self._e_hi / self._e_lo) if self._e_lo > 0 else float("inf")
                return {"duration_s": round(self._t * self._dt, 2),
                        "peak_ratio": round(self._peak_ratio, 2),
                        "peak_uv": round(self._peak_amp, 1),
                        "hf_lf": round(hl, 2)}
        return None

#!/usr/bin/env python3
"""stalta.py — streaming STA/LTA earthquake trigger.

Classic short-term-average / long-term-average detector, O(1) per sample
(recursive EMAs + a 1-pole high-pass), so it runs inline in the recorder's
sample loop for negligible cost and only touches disk on a real trigger.

Pipeline per sample:
  raw counts -> 1-pole HIGH-PASS (rejects microseism/drift that would otherwise
  dominate the energy) -> square = energy characteristic function (CF)
  -> STA (short EMA of CF) / LTA (long EMA of CF) -> trigger when ratio >= trig.

The LTA is FROZEN while triggered, so a long event doesn't raise its own
background and self-terminate. `max_dur_s` caps a stuck trigger (e.g. sustained
cultural noise), after which the LTA re-adapts to the new level.

Feed raw ADC counts to update(); it returns an event dict on de-trigger, else
None. Pure stdlib (math only) so it's safe to import into the recorder.
"""
import math


class StaLta:
    def __init__(self, fs, *, hp_hz=1.0, sta_s=1.0, lta_s=30.0,
                 trig=4.0, detrig=1.5, min_dur_s=0.4, max_dur_s=180.0,
                 uv_per_count=1.0):
        dt = 1.0 / fs
        rc = 1.0 / (2 * math.pi * hp_hz)
        self._hp_alpha = rc / (rc + dt)                 # 1-pole HPF coefficient
        self._a_sta = 1.0 / max(1.0, sta_s * fs)        # EMA rates (~1/window_samples)
        self._a_lta = 1.0 / max(1.0, lta_s * fs)
        self.trig, self.detrig = trig, detrig
        self._min_dur = min_dur_s * fs                  # in samples
        self._max_dur = max_dur_s * fs
        self._uv = uv_per_count
        self._dt = dt
        self._n_prime = int(lta_s * fs)                 # let LTA settle before arming

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
        cf = hp * hp                                          # energy CF

        self._sta += (cf - self._sta) * self._a_sta
        if not self.triggered:                               # freeze LTA during events
            self._lta += (cf - self._lta) * self._a_lta
        self.ratio = self._sta / self._lta if self._lta > 1e-12 else 0.0

        if self._primed < self._n_prime:                     # wait for LTA to settle
            self._primed += 1
            return None

        # Peak amplitude must come from the HIGH-PASSED signal, not the raw count:
        # `x` carries the front end's DC operating point, so abs(x) is dominated by
        # that offset whenever real signal is smaller than it. That produced the
        # long-standing "faux detection" population whose peak_uv clustered
        # implausibly tightly -- 204-219 uV when DC sat at 0.27% of FS (=211 uV),
        # then 3106-3130 uV when the 2026-07-24 epoch moved DC to 3.96% (=3094 uV).
        # The cluster WAS the offset. Detection itself was always driven by `hp`
        # via the CF, so triggering is unaffected; only the reported amplitude was
        # wrong. Fixed 2026-07-24.
        amp = abs(hp) * self._uv
        if not self.triggered:
            if self.ratio >= self.trig:
                self.triggered = True
                self._t = 0
                self._peak_ratio, self._peak_amp = self.ratio, amp
            return None

        # in an event
        self._t += 1
        self._peak_ratio = max(self._peak_ratio, self.ratio)
        self._peak_amp = max(self._peak_amp, amp)
        if self.ratio <= self.detrig or self._t >= self._max_dur:
            self.triggered = False
            if self._t >= self._min_dur:
                return {"duration_s": round(self._t * self._dt, 2),
                        "peak_ratio": round(self._peak_ratio, 2),
                        "peak_uv": round(self._peak_amp, 1)}
        return None

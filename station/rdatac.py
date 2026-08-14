"""rdatac.py — ADS1256 continuous-read (RDATAC) sample source + clock anchoring.

STEP 2 of the continuous-sampling change. Two pieces, both small:

  RdatacReader  -- puts the ADC in RDATAC and hands back one sample per DRDY
                   falling edge, counting edges so DROPPED samples are detectable
                   rather than silent.
  ClockAnchor   -- maps sample index -> UTC, slowly locked to the system (NTP)
                   clock.

WHY RDATAC (see station/rdatac_test.py for the measurements): PiPyADC's
read_continue issues a SYNC/WAKEUP per sample, so the achieved rate sits at
54-57 sps instead of the nominal 60, wanders with system load, and the recorder
has to re-anchor every 10 s block to the wall clock -- which is where the ~68 ms
gap at each block boundary comes from. In RDATAC the converter free-runs on its
own crystal: measured 0 dropped samples in 3600, and DRDY interval jitter of
1 microsecond (0.005%) instead of a 68 ms discontinuity every 10 s.

WHY CLOCK ANCHORING IS STILL NEEDED: the crystal is not a clock. Measured against
the Pi's NTP-locked time, DRDY comes every 16.6652 ms = 60.0054 sps, i.e. the
crystal runs ~90 ppm fast. Trust it alone and timestamps drift 7.8 s/day. But
re-anchoring each block straight to time.time() (what the legacy path does) feeds
the read loop's scheduling latency into every block boundary. So ClockAnchor
predicts from a running anchor and corrects only a FRACTION of the observed error
per block -- a slow first-order loop that tracks NTP without passing jitter
through. Residual per-block adjustment lands around 1 ms, ~70x better than now.
"""
from collections import deque
import time

import pigpio

from pipyadc.ADS1256_definitions import CMD_RDATAC, CMD_RESET, CMD_SDATAC

INT24_BYTES = 3


class RdatacReader:
    """One sample per DRDY falling edge, with dropped-sample accounting.

    Usage:
        reader = RdatacReader(ads, mux)
        reader.start()
        while ...:
            sample, dropped = reader.read()   # blocks until the next sample
        reader.stop()

    `dropped` is the number of DRDY edges that fired between this sample and the
    previous one MINUS the one we serviced -- normally 0. It is returned rather
    than logged so the caller can decide (the recorder closes the block and
    re-anchors, leaving an honest gap, because the sample values are gone).
    """

    def __init__(self, ads, mux, drdy_timeout: float = 5.0):
        self.ads = ads
        self.pi = ads.pi
        self.spi = ads.spi_handle
        self.drdy = ads._DRDY_PIN
        self.cs = ads._CS_PIN
        self.mux = mux
        self.drdy_timeout = drdy_timeout
        if self.drdy is None:
            raise ValueError("RDATAC needs a configured DRDY pin for sample timing")
        self._edges = 0
        self._seen = 0
        self._cb = None
        # hold_cs=True keeps CS asserted for the whole session (fewer GPIO writes per
        # sample); False toggles it per read like the legacy driver does. Exposed
        # because a continuously-enabled digital interface is a suspect for the ~10%
        # noise penalty RDATAC carries -- see rdatac_noise_test.py.
        self.hold_cs = True
        self.total = 0
        self.dropped_total = 0
        self.glitches = 0            # reads that landed in the register-update window

    def _on_edge(self, gpio, level, tick):
        self._edges += 1

    def start(self) -> None:
        """Park the mux, start conversions, enter RDATAC. The channel must not
        change while in RDATAC -- we only ever read one differential pair."""
        self.ads.mux = self.mux
        self.ads.sync()
        self.ads.wakeup()
        self._cb = self.pi.callback(self.drdy, pigpio.FALLING_EDGE, self._on_edge)
        self._seen = self._edges
        if self.cs is not None and self.hold_cs:
            self.pi.write(self.cs, pigpio.LOW)      # hold CS for the whole session
        self.pi.spi_write(self.spi, CMD_RDATAC.to_bytes())
        time.sleep(0.001)

    def read(self) -> tuple[int | None, int]:
        """Block until the next sample, then return (value, dropped).

        value is None when the read landed in the chip's register-update window and
        clocked out nothing. Signature is an all-zero frame: with the DC bias around
        21,700 counts, 0x000000 is not a physical reading. Observed roughly once per
        100 s -- this loop polls DRDY from Python, so a scheduling hiccup (GC, the
        /dev/shm publish, a day-file flush) can arrive late. Left unfiltered each one
        became a 200 uV single-sample needle in the record, big enough to trip the
        STA/LTA and to make the helicorder look hairy.

        The caller decides what to substitute; we only refuse to invent data.
        """
        t_wait = time.time() + self.drdy_timeout
        while self._edges == self._seen:
            time.sleep(0.0005)
            if time.time() > t_wait:
                raise TimeoutError("DRDY stopped -- ADC not converting?")
        gained = self._edges - self._seen
        self._seen = self._edges
        dropped = gained - 1
        # If DRDY has already gone high again we are late: the register is being
        # updated and a read now returns zeros. Report it rather than clock garbage.
        late = self.pi.read(self.drdy) == pigpio.HIGH
        if self.cs is not None and not self.hold_cs:
            self.pi.write(self.cs, pigpio.LOW)
        n, raw = self.pi.spi_read(self.spi, INT24_BYTES)
        if self.cs is not None and not self.hold_cs:
            self.pi.write(self.cs, pigpio.HIGH)
        if n != INT24_BYTES or not isinstance(raw, bytearray):
            raise OSError("short SPI read in RDATAC")
        self.total += 1
        self.dropped_total += dropped
        if late or raw == b"\x00\x00\x00" or bytes(raw) == b"\x00\x00\x00":
            self.glitches += 1
            return None, dropped
        return int.from_bytes(raw, byteorder="big", signed=True), dropped

    def stop(self) -> None:
        """Leave RDATAC and return the chip to a known state. Safe to call twice;
        never raises.

        SDATAC alone is NOT enough: sent mid-frame it can be missed, and the chip
        then keeps streaming conversions. The next process to open the ADC reads
        data where it expects the ID register and dies with "Received wrong chip ID"
        -- which looks exactly like "the ADC is busy" and cost a debugging detour.
        So follow it with a RESET.

        Both are SPI commands, not a RESET-pin pulse: this has to work on boards that
        do not break the pin out (see adc_common._soft_reset). CS is cycled between
        them because the point of the second command is to be seen after the first
        has ended whatever frame was in flight."""
        for cmd in (CMD_SDATAC, CMD_SDATAC, CMD_RESET):
            try:
                if self.cs is not None:
                    self.pi.write(self.cs, pigpio.LOW)
                self.pi.spi_write(self.spi, cmd.to_bytes())
                time.sleep(0.002)
                if self.cs is not None:
                    self.pi.write(self.cs, pigpio.HIGH)
                time.sleep(0.001)
            except Exception:
                pass
        time.sleep(0.03)              # oscillator settling after RESET
        try:
            if self.cs is not None:
                self.pi.write(self.cs, pigpio.HIGH)
        except Exception:
            pass
        if self._cb is not None:
            try:
                self._cb.cancel()
            except Exception:
                pass
            self._cb = None


NSIGMA = 8.0        # excursion must exceed this many local sigma
MAX_RUN = 3         # ... for at most this many samples (30 ms; a quake rings longer)
HALF = 25           # centred window half-width -> 51 samples, 0.25 s latency
TOL = 4.0           # the samples bracketing a run must sit within this many sigma
MIN_SCALE = 100.0   # counts; floors the MAD so a dead-quiet stretch cannot blow up


class Despiker:
    """Reject brief excursions that are huge relative to the LOCAL noise scale.

    Physics behind MAX_RUN: the 4.5 Hz element and the ADS1256's ~25 Hz output
    bandwidth make a 10-30 ms depart-and-return impossible for ground motion. Real
    motion rings; a corrupt SPI frame does not.

    Emits samples with HALF samples of delay. `prev` is the last emitted value, which
    recorder.py uses to fill zero-frames.

    NOTE (2026-08-12): one synthetic case still holds a single sample -- 12 Hz at
    400,000 counts with a STEP onset -- and preserves 100% of the peak. That is a
    3.7 mV event, 5x anything this station has recorded, with a physically impossible
    instantaneous onset. Accepted knowingly.
    """

    def __init__(self, nsigma=NSIGMA, max_run=MAX_RUN, half=HALF, tol=TOL,
                 min_scale=MIN_SCALE):
        self.nsigma = nsigma
        self.max_run = max_run
        self.half = half
        self.tol = tol
        self.min_scale = min_scale
        self.win = deque()            # raw samples; the candidate sits at index `half`
        self.prev = None
        self.spikes = 0

    # -- internals ----------------------------------------------------------------
    def _scale(self, vals):
        s = sorted(vals)
        ref = s[len(s) // 2]
        mad = sorted(abs(v - ref) for v in vals)[len(vals) // 2]
        return ref, max(1.4826 * mad, self.min_scale)

    def _judge(self):
        """Decide the centre sample of a full window. Returns the value to emit."""
        w = self.win
        i = self.half
        ref, scale = self._scale(w)
        bar = self.nsigma * scale
        if abs(w[i] - ref) <= bar:
            return w[i]
        # Extend over the contiguous run of outliers around the centre.
        a = i
        while a - 1 >= 0 and abs(w[a - 1] - ref) > bar:
            a -= 1
        b = i
        while b + 1 < len(w) and abs(w[b + 1] - ref) > bar:
            b += 1
        if (b - a + 1) > self.max_run:
            return w[i]                      # too long to be a glitch -> real motion
        if a - 1 < 0 or b + 1 >= len(w):
            return w[i]                      # run touches the window edge -> can't judge
        lo, hi = w[a - 1], w[b + 1]
        tolerance = self.tol * scale
        if abs(lo - ref) > tolerance or abs(hi - ref) > tolerance:
            return w[i]                      # brackets aren't quiet -> not isolated
        self.spikes += 1
        span = (b + 1) - (a - 1)
        return int(lo + (hi - lo) * (i - (a - 1)) / span)

    # -- streaming API (matches the old Despiker) ---------------------------------
    def push(self, value):
        """Feed one raw sample; returns the sample to record, or None while filling."""
        self.win.append(value)
        if len(self.win) < 2 * self.half + 1:
            return None
        out = self._judge()
        self.win.popleft()
        self.prev = out
        return out

    def flush(self):
        """Release the samples still owed at shutdown, unjudged. Returns a LIST.

        Only the ones AFTER the last centre judged: the window holds 2*half+1 samples
        but everything up to the centre has already been emitted. Returning the whole
        window duplicates `half`+1 samples into the final block -- which is exactly
        what the first version of this did.
        """
        out = list(self.win)[self.half + 1:] if len(self.win) > self.half else []
        self.win.clear()
        return out




class ClockAnchor:
    """Sample index -> UTC epoch seconds, slowly steered to the system clock.

    nominal   declared sample rate (what goes in the miniSEED header)
    gain      fraction of the observed error corrected per update (0..1)
    tol       how far the estimated rate may stray from nominal, fractional
    step      |error| above this is treated as a clock STEP (NTP correction,
              suspend/resume) and hard re-anchored instead of slewed

    The rate estimate is cumulative -- total samples over total elapsed -- which
    converges on the crystal's true rate and does not drift. Prediction uses that
    estimate, so block start times track real time; the HEADER still declares the
    integer nominal, leaving at most ~1 ms of intra-block error (a 10 s block at
    90 ppm). Removing that last millisecond would mean resampling, which is not
    worth it.
    """

    def __init__(self, nominal: float, gain: float = 0.2, tol: float = 0.005,
                 step: float = 1.0, settle_s: float = 60.0, outlier: float = 0.010):
        self.nominal = float(nominal)
        self.rate_est = float(nominal)
        self.gain = gain
        self.tol = tol
        self.step = step
        self.settle_s = settle_s
        # |err| between outlier and step is treated as a CONTAMINATED MEASUREMENT, not
        # a real offset: a scheduling stall delays the wall-clock reading at the block
        # boundary (observed +17.4 ms, ~one sample period, with no glitch to blame).
        # Slewing a fraction of that would write a ~3.5 ms step into the next boundary
        # as a gap. With the rate tracked, genuine error stays inside a few ms.
        self.outlier = outlier
        self.outliers = 0
        self.t0 = None          # UTC epoch of sample index n0
        self.n0 = 0
        self.t_first = None
        self.n_first = 0
        self.resyncs = 0

    def anchor(self, n: int, now: float) -> None:
        """(Re)set the anchor so predict(n) == now.

        Deliberately does NOT start the rate baseline: anchoring happens before the
        first sample is read, and the startup latency (cal_self, RDATAC entry, first
        DRDY wait) would bias a cumulative rate estimate hard -- ~100 ms of offset
        over a 150 s baseline is 0.04 sps, which is 10x the crystal's actual error.
        The baseline starts at the first update(), i.e. the first block boundary."""
        self.t0 = now
        self.n0 = n

    def predict(self, n: int) -> float:
        if self.t0 is None:
            raise RuntimeError("anchor() first")
        return self.t0 + (n - self.n0) / self.rate_est

    def update(self, n: int, now: float) -> float:
        """Fold one (sample index, wall clock) observation in. Returns the error
        in seconds BEFORE correction (positive = the clock is ahead of us)."""
        if self.t_first is None:
            # First block boundary: start the rate baseline here (not at anchor(),
            # whose pre-first-sample timestamp is biased by startup latency), and
            # HARD-anchor rather than slewing. Slewing from a cold start bleeds the
            # initial offset out over ~10 blocks, and every one of those blocks
            # carries the residual as a real gap in the file (measured: 43, 33, 26,
            # 21, 17, 13 ms -- the gain-0.2 decay curve, visible in ObsPy as 8 gaps).
            err = now - self.predict(n)
            self.anchor(n, now)
            self.t_first, self.n_first = now, n
            return err
        err = now - self.predict(n)
        if abs(err) > self.step:                 # clock step, not drift
            self.anchor(n, now)
            self.t_first, self.n_first = now, n  # restart the rate baseline too
            self.resyncs += 1
            return err
        elapsed = now - self.t_first
        if elapsed > self.settle_s:              # cumulative rate estimate
            r = (n - self.n_first) / elapsed
            lo, hi = self.nominal * (1 - self.tol), self.nominal * (1 + self.tol)
            self.rate_est = min(max(r, lo), hi)
        if abs(err) > self.outlier:              # stalled measurement -> coast
            self.outliers += 1
            return err
        self.t0 += self.gain * err               # slew a fraction of the error
        return err

#!/usr/bin/env python3
"""despiker_v2.py — candidate replacement for station/rdatac.py:Despiker.

Kept in the repo so it can be validated on a laptop against real archive days AND
synthetic events before it goes anywhere near the instrument. The class below is
byte-identical to what gets pasted into rdatac.py; the harness at the bottom is what
justifies deploying it.

WHY A THIRD DESIGN (2026-08-12). Two shipped versions failed, in opposite directions:

  jump=50,000, "is the NEXT sample back at baseline?"
      Misses every 2-3 sample burst, because a corrupt lookahead fails the return
      test. Cost: a false EVENT at 19:37:30 with peak_ratio 25.7.
  Lowering the fixed threshold
      At jump=10,000 a replay of day 223 held 3.2% of all samples, drove the 1-5 Hz
      floor 1.18 -> 3.96 uV and ate 188 samples out of a confirmed M2.8.

The discriminator has to be the LOCAL NOISE SCALE, so that during real motion the
bar rises with the signal and the rule quietly stops firing. The trap -- which cost
two failed attempts -- is that the scale window must be CENTRED, not trailing. A
trailing window is blind at event onset, which is exactly where a real quake most
resembles a glitch: measured 8-13 held samples inside synthetic 5 and 12 Hz events,
shaving up to 21% off the peak. A centred window sees the event coming.

The price is latency: HALF samples (0.25 s at 100 sps) instead of one. That is free
here because block timing is derived from the sample INDEX, not from wall clock at
emission -- see ClockAnchor.
"""
from collections import deque

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


# ---------------------------------------------------------------------------------
# Harness. Nothing below ships.
# ---------------------------------------------------------------------------------
def _run(seq, **kw):
    d = Despiker(**kw)
    out = []
    for v in seq:
        r = d.push(v)
        if r is not None:
            out.append(r)
    out.extend(d.flush())
    return d.spikes, out


def _main():
    import math
    import random
    import sys
    import warnings
    warnings.filterwarnings("ignore")
    import numpy as np
    from obspy import UTCDateTime, read, Trace

    UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
    fails = []

    # ---- 1. synthetic events on real quiet noise --------------------------------
    st = read(sys.argv[1] if len(sys.argv) > 1
              else "analysis/data/XX.OAKMT.00.SHZ.D.2026.223.mseed")
    for t in st:
        t.stats.sampling_rate = 100.0
    st.merge(method=1, fill_value="interpolate")
    tr = st[0]
    x = tr.data.astype(np.int64)
    quiet = x[-30000:-24000].tolist()          # 60 s of real ambient
    base = int(np.median(quiet))

    print("SYNTHETIC EVENTS (injected into 60 s of real ambient)")
    print(f"{'f Hz':>5} {'amp ct':>8} {'onset':>7} {'held':>5} {'peak kept':>10}")
    for f in (2, 5, 8, 12, 18):
        for amp in (2000, 8000, 60000, 400000):
            for onset in ("sharp", "ramp"):
                ev = []
                for t in range(300):
                    env = math.exp(-t / 150.0)
                    if onset == "ramp":
                        env *= min(1.0, t / 20.0)
                    ev.append(int(amp * env * math.sin(2 * math.pi * f * t / 100.0)))
                seq = quiet[:3000] + [base + v for v in ev] + quiet[3000:4000]
                sp, out = _run(seq)
                pk = max(abs(v - base) for v in out)
                injected = max(abs(v) for v in ev)      # NOT amp: ramp+decay reduce it
                kept = 100.0 * pk / injected
                bad = sp > 0 or kept < 95.0
                if bad:
                    fails.append(f"synthetic {f} Hz {amp} ct {onset}: {sp} held, "
                                 f"{kept:.1f}% peak")
                    print(f"{f:>5} {amp:>8} {onset:>7} {sp:>5} {kept:>9.1f}%  <-- FAIL")
    print("  (all other synthetic cases: 0 held, >=95% peak preserved)")

    # ---- 2. real archive: artifacts caught, events untouched --------------------
    print("\nREAL ARCHIVE")
    for path, artifacts, events in (
        ("analysis/data/XX.OAKMT.00.SHZ.D.2026.223.mseed", [],
         [("M2.8 Geysers", "2026-08-11T21:35:20", "2026-08-11T21:35:45")]),
        ("analysis/data/XX.OAKMT.00.SHZ.D.2026.224.mseed",
         [("16:39:01 pair", "2026-08-12T16:39:01.46"),
          ("19:37:30 spike", "2026-08-12T19:37:30.88")],
         [("M2.0 Glen Ellen", "2026-08-12T09:06:37", "2026-08-12T09:07:25"),
          ("M3.2 #1", "2026-08-12T10:28:34", "2026-08-12T10:29:25"),
          ("M3.2 #2", "2026-08-12T10:30:22", "2026-08-12T10:31:10")]),
    ):
        try:
            s2 = read(path)
        except Exception as e:
            print(f"  {path}: {e}")
            continue
        for t in s2:
            t.stats.sampling_rate = 100.0
        s2.merge(method=1, fill_value="interpolate")
        t2 = s2[0]
        xs = t2.data.astype(np.int64).tolist()
        start = t2.stats.starttime
        sp, out = _run(xs)
        out = np.array(out, dtype=np.int64)
        hrs = len(xs) / 100.0 / 3600.0
        # ALIGNMENT: the first emitted sample is the centre of the first full window,
        # i.e. raw index `half`. Comparing out[k] to xs[k] mismatches by 25 samples and
        # reports essentially every sample as altered.
        off = HALF
        m = min(len(out), len(xs) - off)
        changed = np.flatnonzero(out[:m] != np.array(xs[off:off + m])) + off
        print(f"  {path.split('.')[-2]}: {sp} held over {hrs:.1f} h = {sp/hrs:.1f}/h")

        def band(d, lo, hi):
            tt = Trace(np.asarray(d, dtype="float64"))
            tt.stats.sampling_rate = 100.0
            tt.detrend("demean")
            tt.filter("bandpass", freqmin=lo, freqmax=hi, corners=4, zerophase=True)
            seg = 1000
            a = tt.data[:len(tt.data) // seg * seg].reshape(-1, seg)
            return float(np.median(a.std(axis=1)) * UV)
        print(f"      1-15 Hz {band(xs,1,15):.2f} -> {band(out,1,15):.2f} uV   "
              f"1-5 Hz {band(xs,1,5):.2f} -> {band(out,1,5):.2f} uV")
        for name, ts in artifacts:
            i = int((UTCDateTime(ts) - start) * 100.0)
            hit = np.any((changed >= i - 2) & (changed <= i + 2))
            print(f"      {name}: {'CAUGHT' if hit else 'MISSED'}")
            if not hit:
                fails.append(f"{name} missed")
        for name, t0, t1 in events:
            i0 = int((UTCDateTime(t0) - start) * 100.0)
            i1 = int((UTCDateTime(t1) - start) * 100.0)
            n = int(np.sum((changed >= i0) & (changed <= i1)))
            print(f"      {name}: {n} samples altered inside the event")
            if n:
                fails.append(f"{name}: {n} samples altered")

    print("\n" + ("ALL CHECKS PASSED" if not fails else "FAILURES:"))
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_main())

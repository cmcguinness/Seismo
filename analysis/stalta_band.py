#!/usr/bin/env python3
"""stalta_band.py — candidate band-limited StaLta, plus the replay that justifies it.

THE BUG (found 2026-08-14 from a labelled trash-can run). The characteristic function
is `hp(x)**2` where hp is a 1-pole HIGH-pass at 1 Hz. There is no low-pass, so the CF
integrates everything from 1 Hz to Nyquist. But the two source classes live in
different bands:

    source                    1-8 Hz   8-15   15-30   30-45   HF/LF
    M4.1 San Leandro, 88 km     89.6    17.3     5.0     3.0    0.06
    M2.8 Geysers, 45 km         25.4    19.9    15.2    19.4    0.97
    door slam, ~3 m              3.9    35.5    14.8     6.5    4.12
    cans rolling, ~3 m           4.2     9.7    23.5    23.5    7.84

Path attenuation strips the high frequencies out of a real quake; a source three
metres away keeps all of them. Feeding both to an unweighted energy CF hands the
decision to the band where only cultural noise lives. Measured consequence: the
2026-08-13 trash-can run triggered EIGHT times, peaking at ratio 256.7, while a
confirmed M2.8 reached 3.7. A man with a wheelie bin outranked a real earthquake 70x.

THE FIX. Cascade a 4-pole Butterworth low-pass at 15 Hz onto the existing high-pass, so the CF
sees 1-15 Hz. One pole is not enough: at 30 Hz it is only 2x down, and the cans carry
as much energy at 30-45 Hz as at 15-30. Two poles give 12 dB/octave -- ~4x at 30 Hz,
~9x at 45 Hz -- which is what turns a 7.84 HF/LF ratio into a non-event.

Deliberately NOT changed: trig/detrig, sta/lta, and the 1 Hz high-pass. This is a
band change, and it is the only change, so the replay below attributes cleanly. Retune
thresholds afterwards if at all -- the despiker taught this project that shipping two
changes at once means learning nothing from either.

    python analysis/stalta_band.py            # replay every archive day with a label
"""
import math
import sys


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
    """Band-limited STA/LTA. `lp_hz=None` reproduces the shipped detector exactly.

    Everything except the two low-pass sections is byte-identical to server/stalta.py
    so the replay compares one variable.
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


# ---------------------------------------------------------------------------------
# Replay harness. Nothing below ships.
# ---------------------------------------------------------------------------------
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
PROD_HP = 3.0   # SEISMO_HP as the station actually runs it -- NOT the 1.0 class default
HF_GATE = 1.4   # >15 Hz / 1-8 Hz amplitude ratio above which an event reads as CULTURAL.
                # Set from the 9 labelled cases below: worst quake 1.02, best cultural
                # 1.98, so 1.4 is their geometric midpoint. That is only a ~40% margin
                # on each side with n=9 -- which is why hf_lf is REPORTED and used for
                # labelling, not used to delete events. A wrongly-binned quake that is
                # still in the log is recoverable; a deleted one is not.

# (day, label, kind, t_start, t_end) -- windows in which a trigger is expected/not.
# QUAKE windows are confirmed detections; CULTURAL are Charles's labelled activity.
WINDOWS = [
    ("223", "M2.8 Geysers 45 km",      "QUAKE",    "2026-08-11T21:35:14", "2026-08-11T21:36:10"),
    ("224", "M2.0 Glen Ellen 9.7 km",  "QUAKE",    "2026-08-12T09:06:37", "2026-08-12T09:07:30"),
    ("224", "M3.2 Geysers #1",         "QUAKE",    "2026-08-12T10:28:30", "2026-08-12T10:29:30"),
    ("224", "M3.2 Geysers #2",         "QUAKE",    "2026-08-12T10:30:18", "2026-08-12T10:31:15"),
    ("225", "M4.1 San Leandro 88 km",  "QUAKE",    "2026-08-13T15:30:04", "2026-08-13T15:31:30"),
    ("226", "footsteps",               "CULTURAL", "2026-08-14T03:16:10", "2026-08-14T03:16:50"),
    ("226", "two cans rolling",        "CULTURAL", "2026-08-14T03:16:50", "2026-08-14T03:17:40"),
    ("226", "third can rolling",       "CULTURAL", "2026-08-14T03:18:05", "2026-08-14T03:18:32"),
    ("226", "doors closing/locking",   "CULTURAL", "2026-08-14T03:18:32", "2026-08-14T03:19:15"),
]


def _replay(x, lp_hz, fs=100.0):
    """Run one config over a whole day; return (events, ratio_trace).

    Events carry the START index as well, so the spectral gate below can re-cut the
    raw window the trigger actually fired on.
    """
    d = StaLta(fs, hp_hz=PROD_HP, lp_hz=lp_hz, uv_per_count=UV)
    evs, ratio = [], []
    start = 0
    was = False
    for i, v in enumerate(x):
        e = d.update(v)
        if d.triggered and not was:
            start = i
        was = d.triggered
        ratio.append(d.ratio)
        if e:
            evs.append((start, i, e))
    return evs, ratio


def hf_lf(seg, fs=100.0):
    """Energy above 15 Hz over energy in 1-8 Hz. The source-distance discriminant.

    Path attenuation strips >15 Hz from anything more than a few km away, so this is
    small for a real quake (0.06 at 88 km, 0.97 at 45 km) and large for anything in
    the garage (7.8 for rolling cans). Computed on the RAW window, not the CF, so it
    is independent of whatever the trigger filtered.
    """
    import numpy as np
    if len(seg) < 64:
        return float("nan")
    w = np.asarray(seg, dtype=float)
    w = w - w.mean()
    f = np.fft.rfftfreq(len(w), 1.0 / fs)
    P = np.abs(np.fft.rfft(w * np.hanning(len(w)))) ** 2
    lo = P[(f >= 1) & (f <= 8)].sum()
    hi = P[(f > 15) & (f <= 45)].sum()
    return float(np.sqrt(hi / lo)) if lo > 0 else float("inf")


def _main():
    import warnings
    warnings.filterwarnings("ignore")
    import numpy as np
    from obspy import UTCDateTime, read

    days = sorted({w[0] for w in WINDOWS})
    peaks = {}            # (day,label) -> {lp: peak ratio in window}
    counts = {}           # day -> {lp: n events, hours}
    gates = {}            # day -> (n surviving the HF/LF gate, n triggered)
    hfs = {}              # (day,label,kind) -> HF/LF of the labelled window

    for day in days:
        path = f"analysis/data/XX.OAKMT.00.SHZ.D.2026.{day}.mseed"
        try:
            st = read(path)
        except Exception as e:
            print(f"{path}: {e}")
            continue
        for t in st:
            t.stats.sampling_rate = 100.0
        st.merge(method=1, fill_value="interpolate")
        tr = st[0]
        x = np.ma.filled(tr.data.astype(np.float64), 0.0)
        t0 = tr.stats.starttime
        hrs = len(x) / 100.0 / 3600.0
        print(f"day {day}: {hrs:.1f} h, replaying 2 configs...", flush=True)

        for lp in (None, 15.0):
            evs, ratio = _replay(x, lp)
            r = np.asarray(ratio)
            counts.setdefault(day, {})[lp] = (len(evs), hrs)
            if lp == 15.0:
                # Score the STREAMING hf_lf the detector itself reports -- not an FFT
                # recomputed offline, which is a different number.
                gated = sum(1 for _s, _e, ev in evs if ev["hf_lf"] < HF_GATE)
                gates[day] = (gated, len(evs))
                for d2, label, kind, wa, wb in WINDOWS:
                    if d2 != day:
                        continue
                    i0 = max(0, int((UTCDateTime(wa) - t0) * 100.0))
                    i1 = min(len(x), int((UTCDateTime(wb) - t0) * 100.0))
                    # every event overlapping the labelled window
                    ov = [ev for _s, _e, ev in evs if _s < i1 and _e > i0]
                    # Score the DOMINANT trigger -- the one with the largest ratio.
                    # A window can also contain weak coda fragments whose hf_lf is
                    # meaningless (little signal, so the ratio is measuring noise);
                    # taking the max over those said "SPLIT" for events that are in
                    # fact cleanly classified.
                    dom = max(ov, key=lambda e: e["peak_ratio"]) if ov else None
                    hfs[(day, label, kind)] = (
                        dom["hf_lf"] if dom else float("nan"),
                        dom["peak_ratio"] if dom else float("nan"),
                        len(ov),
                        hf_lf(x[i0:i1]))
            for d2, label, kind, wa, wb in WINDOWS:
                if d2 != day:
                    continue
                i0 = int((UTCDateTime(wa) - t0) * 100.0)
                i1 = int((UTCDateTime(wb) - t0) * 100.0)
                i0, i1 = max(0, i0), min(len(r), i1)
                pk = float(r[i0:i1].max()) if i1 > i0 else 0.0
                peaks.setdefault((day, label, kind), {})[lp] = pk

    print(f"\n{'window':<26}{'kind':<10}{'shipped':>10}{'banded':>10}{'change':>10}")
    for (day, label, kind), v in peaks.items():
        old, new = v.get(None, 0.0), v.get(15.0, 0.0)
        ch = f"{new/old:.2f}x" if old > 0 else "-"
        print(f"{label:<26}{kind:<10}{old:>10.1f}{new:>10.1f}{ch:>10}")

    print(f"\n{'day':<8}{'hours':>8}{'shipped ev':>12}{'banded ev':>12}{'/hour old':>11}{'/hour new':>11}")
    for day, v in counts.items():
        (no, hrs), (nn, _) = v[None], v[15.0]
        print(f"{day:<8}{hrs:>8.1f}{no:>12}{nn:>12}{no/hrs:>11.1f}{nn/hrs:>11.1f}")

    # The point of the exercise: does every confirmed quake now outrank every
    # labelled cultural episode?
    q = [v.get(15.0, 0.0) for (d, l, k), v in peaks.items() if k == "QUAKE"]
    c = [v.get(15.0, 0.0) for (d, l, k), v in peaks.items() if k == "CULTURAL"]
    qo = [v.get(None, 0.0) for (d, l, k), v in peaks.items() if k == "QUAKE"]
    co = [v.get(None, 0.0) for (d, l, k), v in peaks.items() if k == "CULTURAL"]
    print(f"\n{'window':<26}{'kind':<10}{'n ev':>5}{'dom ratio':>11}"
          f"{'hf_lf':>8}{'fft':>7}   gate < {HF_GATE}")
    for (day, label, kind), (hl, pr, n, ff) in hfs.items():
        want_keep = kind == "QUAKE"
        keep = n and hl < HF_GATE
        ok = "  ok" if bool(keep) == want_keep else "  <-- WRONG"
        print(f"{label:<26}{kind:<10}{n:>5}{pr:>11.1f}{hl:>8.2f}{ff:>7.2f}"
              f"   {'KEEP' if keep else 'REJECT'}{ok}")

    print(f"\n{'day':<8}{'triggered':>11}{'after gate':>12}{'/hour':>9}{'rejected':>10}")
    for day, (g, n) in gates.items():
        hrs = counts[day][15.0][1]
        print(f"{day:<8}{n:>11}{g:>12}{g/hrs:>9.1f}{100*(1-g/n):>9.0f}%")

    if q and c:
        print(f"\n  STAGE 1 (band-limited ratio only):")
        print(f"    shipped: weakest quake {min(qo):.1f} vs loudest cultural {max(co):.1f}"
              f"  -> {min(qo)/max(co):.3f}x  OVERLAPPING")
        print(f"    banded : weakest quake {min(q):.1f} vs loudest cultural {max(c):.1f}"
              f"  -> {min(q)/max(c):.3f}x  {'SEPARATED' if min(q)>max(c) else 'STILL OVERLAPPING'}")
        qh = [hl for (d,l,k),(hl,pr,n,f) in hfs.items() if k=="QUAKE" and n]
        ch = [hl for (d,l,k),(hl,pr,n,f) in hfs.items() if k=="CULTURAL" and n]
        if qh and ch:
            print(f"  STAGE 2 (streaming hf_lf gate):")
            print(f"    worst quake {max(qh):.2f}  vs  best cultural {min(ch):.2f}"
                  f"  -> margin {min(ch)/max(qh):.2f}x")
            print("    " + ("SEPARATED: a single threshold splits every labelled case"
                            if max(qh) < min(ch) else "OVERLAPPING -- gate is unsafe"))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

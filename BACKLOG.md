# BACKLOG — Seismo

Deferred work, not blocking. The current station records 24/7, is
Raspberry-Shake-class (~41 nm/s floor), and has real-time + helicorder + spectrum
tooling. These are improvements to fold in when convenient.

## Rev-2 geophone → ADC front-end (revised interface board)

The current front-end is a perfboard (2× 100 kΩ bias, shunt socket, XLR in). It
works. When we build a cleaner/permanent interface between the geophone and the
ADS1256, fold in these — roughly in order of payoff:

1. **Revisit the input buffer — the biggest noise-floor lever.**
   We run the ADS1256 with its input buffer OFF, which is intrinsically noisier.
   It was forced by common-mode range: with AVDD on the 3V3 jumper, the *buffered*
   CM range is only 0–1.3 V but our mid-supply bias sits ~1.5 V. Options:
   - Bias below 1.3 V (asymmetric, fine for a small bipolar signal) so the quieter
     buffer can be re-enabled, **or**
   - Resolve the **5 V AVDD** path (jumpering AVDD to 5 V crashed the Pi — suspected
     a 3-pin cap shorting 5 V↔3V3; investigate with the Pi OFF, pins verified).
   Buffer-on and/or 5 V AVDD is where real floor improvement lives.

2. **Input anti-alias RC + switched-cap charge reservoir.**
   With the buffer off, the ADS1256 input is a raw switched-capacitor sampler that
   pulls charge spikes off the source. Add, as a proper RC (not a bare cap — a bare
   cap on a switched-cap input can ring):
   - ~1 kΩ series R in **each** input leg (AD0, AD1), then
   - ~10–47 nF differential C across AD0/AD1 (optional smaller CM caps to AGND).
   Size for a corner ~60–80 Hz — well above the <30 Hz signal band so it doesn't
   touch the geophone response or the damping. Feeds the sampling spikes and
   rejects HF/EMI/aliasing. TI-recommended for unbuffered ADS1256. Does NOT lower
   the broadband thermal floor.

3. **Cleaner analog supply/reference (only if it matters).**
   Optional local AVDD/VREF filtering, or a dedicated low-noise LDO for the ADC's
   analog section isolated from the Pi's switching 3V3. **Gate this on data:** run
   the battery-vs-USB shorted-input floor test (`capture_raw.py`) first — our floor
   is currently flat/white (no supply spurs), so supply is probably NOT the limit
   and this may be wasted effort. A 10 µF∥100 nF across VCC/AGND is cheap hygiene
   regardless but won't move the floor.

4. **Ferrule the cable ends** (crimp kit inbound) for permanent screw-terminal
   termination — tinned strands cold-flow/loosen under screws.

Also related, tracked in STATUS: tune the **shunt damping** resistor (perfboard
socket) against a recorded impulse.

## Compute — faster Pi (upgrade consideration)

A faster Pi is a **scope-expansion enabler, not a fix** for current limits. Do the
free software wins FIRST; buy silicon only when expanding.

- **Won't fix**: the noise floor (analog) or the sample-rate ceiling. The ~57-92 sps
  cap is **driver-limited** (PiPyADC's fixed per-sample SYNC `time.sleep()` delays +
  ADC conversion time), not CPU-limited — a faster CPU barely moves it. **RDATAC**
  (free-running read, software) is the real rate/timing fix and runs on the current
  Pi 2B.
- **Helps modestly**: timing jitter / per-block gaps (more CPU headroom → more
  deterministic sampling loop). But most of that is free via RT scheduling on the
  current Pi (`chrt`/`nice` the recorder, or a PREEMPT_RT kernel) — try that before
  buying hardware.
- **Worth it when we EXPAND scope**: 3-component (3× read load), on-device real-time
  detection (STA/LTA), local helicorder rendering, a **SeedLink server** to push to
  networks, or running ObsPy on the box. Those want CPU *and* RAM.
- **Spec note**: a **1 GB Pi 4 is the worst pick** — same RAM as the 2B, so no
  headroom for on-device analysis (the thing that OOM-wedged ObsPy). Get **2-4 GB
  Pi 4 or a Pi 5** (also 64-bit / aarch64, longer OS-support horizon) when the time
  comes. No urgency for the current single-channel station.

## ADC upgrade (consideration — premature, but noted)

The ADS1256/Waveshare board is NOT the current weak link. Speed is irrelevant
(it does 30 ksps; we use ~57, and seismology wants 100-250). The axis that
matters is **noise + dynamic range**, not speed.

- **Not ADC-limited yet.** Measured floor ~1.17 µV RMS is ~2-3× *above* the
  ADS1256's own datasheet noise → excess is from buffer-off / reference / supply.
  Do the **Rev-2 front-end** work first (buffer, reference) — closes most of the
  gap without new silicon.
- **If ever chased**: a seismic-grade delta-sigma — **ADS1282** (~130 dB DR,
  ~21+ ENOB, used in pro digitizers) or **ADS1263** (32-bit, lower noise). Lower
  floor AND enough dynamic range to capture weak ambient + strong local motion at
  one gain (vs today's gain-64 clip at ±39 mV ≈ 1.35 mm/s). But this means a
  **custom board** — loses the Waveshare HAT convenience; a real hardware project.
- **Dynamic range is better solved by the accelerometer** (strong motion) than a
  premium ADC — geophone + accel covers weak-to-strong far more cost-effectively.
- **Oversampling note**: can't lower the floor with a faster external rate — the
  delta-sigma already oversamples internally (that's what the DRATE trade is).

## Other

- **STEIM2 compression** for the recorder (currently int32 uncompressed, ~19 MB/day).
- **Data-continuity / RDATAC**: the mixed-rate-across-restarts bug is FIXED (recorder
  now declares a fixed SEISMO_RATE=57, so day-files are single-rate/mergeable). Still
  open: the ~0.3 s per-block overlaps from the wall-clock-per-block scheme. A crystal-
  locked, gapless, exact-rate stream would need ADS1256 continuous (RDATAC) mode.
- **Enclosure**: walls + lid (base is done); power cutout +Y, dongle slot −X.

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

## 3-component (X/Y/Z) + azimuth alignment

Turns a "something happened" detector into "something happened *over there*"
(back-azimuth, particle motion). Two sensor paths:

- **Accelerometer (recommended for strong motion): ADXL355** — 3 axes in one
  DIGITAL chip (built-in ADC, SPI or I²C), so NO extra A/D and no analog front-end.
  Put it on the Pi's free I²C pins (GPIO 2/3; ADS1256 uses SPI0). ~$60. Strong-
  motion class; complements the geophone (weak motion). NOT a Pi HAT — a seismic
  sensor must be **rigidly ground-coupled and leveled**, so mount the breakout on
  the coupling base with the geophone, wired back to the Pi.
- **3-component geophone (weak motion)**: needs purpose-built HORIZONTAL elements
  (a vertical element can't lie on its side — ~12 mm gravity sag pins the coil to
  the stop) + 3 differential ADS1256 channels. Multiplexing 3 channels cuts per-
  channel rate → depends on the RDATAC fix. Elements ~$15–40 each.

**Azimuth alignment (base feature — the ask):** the horizontals must be oriented
to geographic N/E, so the base needs an alignment reference.
- **Do NOT embed a live compass near the sensors** — the geophone's magnet (plus
  steel screws, the Pi) will deflect it; Earth's field is only ~0.5 gauss and the
  magnet's leakage rivals it at 5–15 cm. (An electronic magnetometer/IMU heading
  fails for the same reason.) **Test** a compass at the intended spot next to the
  assembled sensor vs. far away before trusting anything embedded.
- **Instead, model an azimuth DATUM** into the base (engraved arrow / reference
  edge = the sensor N axis) and align it to true north with an external compass or
  phone held ~1 m away, or a landmark/sun sighting — both immune to the magnet. Or
  a **removable compass jig** keyed to the datum (align, then pull it).
- **Declination**: Santa Rosa ≈ **+13° E** (drifts ~0.1°/yr; verify NOAA for
  site/date). East declination → true N is ~13° *west* of magnetic N. Use a
  rotatable bezel (handles drift) or an engraved true-N-vs-magnetic-N offset index.
- CAD: build123d feature on the base — engraved true-north arrow aligned to the
  accel X-axis pocket + declination offset mark, positioned as far from the
  geophone pocket as the base allows.

## Long-period companion sensor — Lehman horizontal pendulum

Opens the **teleseismic / sub-microseism window** the 4.5 Hz geophone physically
can't reach. The geophone is a *local-earthquake* instrument (flat ~4.5–20 Hz,
12 dB/oct deaf below 4.5 Hz); by the microseism (~0.1–0.35 Hz) it's ~60 dB down,
and below that it shows only its own noise (why the dashboard spectrum is cropped
at 0.05 Hz). A different sensor class is needed to go lower — this is the DIY one.

- **What it is:** a "garden-gate" horizontal-boom pendulum — a mass on a near-
  vertical-axis boom, so the restoring force is a tiny fraction of gravity →
  very long natural period. Reaches **~15–30 s (0.03–0.06 Hz)** out of angle iron,
  a coil, and a magnet. The classic amateur long-period build (Lehman 1979).
- **What it buys:** **teleseismic surface waves** — you'd see **M6+ quakes from
  the other side of the planet** arriving as slow 15–20 s Rayleigh swells, plus
  the primary microseism. Complements the geophone: geophone owns 1–20 Hz local,
  Lehman owns 0.03–0.1 Hz distant. Genuinely different physics, different targets.
- **Sensing:** velocity pickup = coil-on-boom through a magnet (same principle as
  the geophone), OR a capacitive/LVDT displacement pickup with feedback. Output is
  tiny and low-frequency → wants a differential channel on the ADS1256 (spare
  channels exist) with heavy low-pass; NOT sharing the geophone's gain settings.
- **The hard parts (all long-period seismometers share these):**
  - **Thermal + draft isolation is everything.** At 20 s period a 0.1°C drift
    walks the boom off-scale; needs an insulated box, ideally buried/basement, far
    from HVAC. This dwarfs the mechanical build in difficulty.
  - **Tilt stability** — long-period = exquisitely tilt-sensitive; a settling slab
    or thermal tilt masquerades as ground motion. Solid pier, leveling feet.
  - **Period tuning** via boom-axis angle; damping via a magnet/copper-vane eddy
    brake (aim ~0.7 critical). Iterative.
- **Footprint:** it's a **~0.5–1 m horizontal instrument** — much bigger than the
  geophone puck; needs its own bench/pier space and orientation (measures ONE
  horizontal azimuth; two orthogonal booms for full horizontal motion).
- **Alternatives noted:** vertical long-period (Shackleton-Roberts, LaCoste
  zero-length spring) — harder to build; or a **used commercial broadband**
  (Trillium/STS-2/CMG-3T, ~$3–30k) buys the whole flat 0.008–50 Hz band at once
  with force-balance feedback, no thermal-box fuss, if the goal ever justifies it.
- **Integration:** same recorder/rsync/dashboard pipeline — a second channel
  (e.g. `XX.OAKMT.00.LHZ`/`LH1`) with its own ASD panel; the Welch/helicorder
  code is sensor-agnostic once the channel exists.

## Site characterization — H/V (HVSR) microtremor survey

Measure the site's fundamental resonance `f0` directly from ambient noise,
instead of inferring it from the (wildly contradictory) well logs. Three wells
in section 7N/7W-15 disagree completely — 6499 Hwy 12: rhyolite at 3 ft (rock);
6285 Hwy 12: 57 ft clay + soft tuff → rock ~360 ft; 6245 Melitta Rd (closest):
>132 ft clay/gravel, bedrock not reached (soft). Best guess for our spot: thick
clay alluvium, `f0` ~1–2 Hz — but only a measurement settles it.

- **Method (Nakamura's H/V):** record ~20–30 min ambient microtremor; compute
  `H/V(f) = sqrt(N²+E²)/V`; the peak = site fundamental `f0` (`f0 ≈ Vs/4H`).
  Dividing by V cancels the noise-source spectrum, isolating the site response.
  Passive, single-station, no earthquake needed. Flat/no-peak = rock site.
- **Prerequisites (both):**
  1. **3-component** — needs horizontals; the vertical-only geophone can't do H/V
     (see the 3-component entry above).
  2. **Ground-coupled** — on the windowsill it measures the *house* (those
     0.3–2.5 Hz spectral peaks are almost certainly the building). Must be on the
     actual soil/slab.
- **Tools:** Geopsy (standard HVSR software) or an ObsPy script. SESAME (2004)
  guidelines for acquisition/quality.
- **Payoff:** `f0` → sediment thickness / amplification; closes the geology loop
  (map → wells → prediction → instrument measures its own foundation) and tells
  us whether the ~1–2 Hz peaks we see are site or structure.

## Active-source survey (someday / "if I win the lottery" tier)

DIY seismic **refraction / MASW** — hit the ground with a source, record the
arrivals, invert for a Vs/depth profile (or image the bedrock interface). Real
citizen science, but it's a whole *separate* rig from the monitoring station and
a real time sink, hence the lottery tier. H/V + a short MASW line (below) answer
the site questions far more cheaply.

- **Prerequisites (all three):**
  1. **Fast sampling** — near-surface arrivals are milliseconds; need ~1000+ sps
     (sub-ms). Current ~57 sps is hopeless. RDATAC unlocks the single channel;
     a real survey wants a fast *multichannel* DAQ.
  2. **A geophone array** — a line of sensors at increasing offset (refraction/
     MASW build a travel-time / dispersion curve from the geometry). Single
     sensor can't image layers.
  3. **A real source** — sledgehammer on a steel plate (or weight drop) + a
     **trigger** (switch/geophone on the hammer for t=0). A transducer won't
     couple useful energy into the ground (impedance mismatch).
- **Geometry / distances** (refraction spread ≈ 4–5× target depth):
  - **150 ft (property diagonal)** → refraction sees only ~30–40 ft; but **MASW
    on 150 ft profiles Vs to ~50–150 ft → covers the top 30 m = Vs30** (the key
    site-class number). So a short property-scale line is genuinely useful.
  - **Deep bedrock (150–340 ft)** by refraction needs ~1400–1700 ft spread =
    "wiring the neighborhood." Not worth it — use H/V for whole-column depth.
- **Cheaper substitute for what you actually want:** H/V (single point → f0/whole
  column) + a 150-ft MASW line (→ Vs30). Both property-scale/near-single-sensor,
  no neighborhood cabling. The full-bedrock refraction *image* is the true
  lottery item.

## Broadcast via SeedLink (graduate from recording -> contributing)

Run a **SeedLink server** on the Pi so the real-time stream can be *subscribed to*
and *ingested* by aggregators — the step from a private recorder to a station on
"everybody's map" (ShakeNet-style). SeedLink is seismology's real-time pub/sub
standard (the APRS-IS / MQTT-broker analog).

- **How:** EarthScope/IRIS **`ringserver`** is the lightweight, Pi-friendly
  SeedLink server — point it at a miniSEED ring the recorder feeds. (SeisComP's
  seedlink is the heavyweight alternative.) The recorder would write into the ring
  buffer instead of / in addition to day-files.
- **Gated on metadata cleanup first** (a broadcast station needs to be legit):
  - **Stable sample rate** — the RDATAC fix (no 55/57 wander, no gaps).
  - **StationXML** — station/channel metadata + instrument response (coords done:
    38.451817, -122.621049; still need response: geophone 4.5 Hz, 28.8 V/m/s, ADC).
  - **A real network identity** — `XX` is fine for private/testing but NOT for
    contributing. Either register an FDSN network code, or just **be a Raspberry
    Shake** (auto-joins ShakeNet as `AM`, zero effort — the turnkey path).
  - **ShakeNet is CLOSED to DIY hardware.** ShakeNet/`AM` is device-gated — only
    Raspberry Shake's own hardware+software, because `AM` guarantees a *known,
    consistent instrument response* across the fleet (metadata integrity, not
    gatekeeping). Our homebrew rig can't join it. So the ONLY DIY route to the
    global aggregate is **the independent path**: register our own FDSN network +
    author our own **StationXML** (we can characterize our own response: 4.5 Hz /
    28.8 V/m/s geophone + ADC gain) + run SeedLink. Different map, same federation.
    (Or buy an actual Shake for ShakeNet, and dual-stream: `AM` copy to them + a
    self-labeled copy to our own network.)
- **The tension (already felt with the XX/AM choice):** "independent" and "on
  everybody's map" pull opposite ways. Private `XX` on disk vs. registered +
  SeedLink-broadcast + aggregated. This item is the deliberate choice to go public.
- **Payoff:** live on StationView-style maps, data queryable alongside pro
  networks, and you can pull your own stream with Swarm / ObsPy SeedLink client.

## ML detection (Jetson Orin Nano)

A GPU node (`ssh jetson`) is available for deep-learning seismology — a real
upgrade over the STA/LTA trigger.

- **SeisBench** (ML-seismology framework) with pretrained **EQTransformer** /
  **PhaseNet** — neural earthquake *detection* + P/S *phase picking*, far more
  sensitive than STA/LTA. Could catch sub-threshold events (the Geysers micro-
  quakes our trigger misses) and produce real phase picks -> better `eventcheck`.
- Runs on the mirrored miniSEED (same rsync pipeline); the Jetson pulls, runs
  inference on GPU, writes events back to the shared events store. Feeds the same
  dashboard/APRS pipeline the STA/LTA does, just smarter.
- **Distributed architecture this completes:** Pi 2B = acquisition · Pi 5 =
  render/serve (dashboard) · Jetson = ML inference. Three purpose-fit nodes.
- Also possible: DeepDenoiser (seismic denoising) to lower the effective floor.

## Other

- **STEIM2 compression** for the recorder (currently int32 uncompressed, ~19 MB/day).
- **Data-continuity / RDATAC**: the mixed-rate-across-restarts bug is FIXED (recorder
  now declares a fixed SEISMO_RATE=57, so day-files are single-rate/mergeable). Still
  open: the ~0.3 s per-block overlaps from the wall-clock-per-block scheme. A crystal-
  locked, gapless, exact-rate stream would need ADS1256 continuous (RDATAC) mode.
- **Enclosure**: walls + lid (base is done); power cutout +Y, dongle slot −X.

# BACKLOG — Seismo

Deferred work, not blocking. The current station records 24/7, is
Raspberry-Shake-class (~41 nm/s floor), and has real-time + helicorder + spectrum
tooling. These are improvements to fold in when convenient.

## ⚠️ COUPLING — the geophone is not on the slab (found 2026-07-26)

The garage has **inherited plastic interlocking tile**, so the station stands on a
compliant, hollow layer, not on concrete. `CLAUDE.md` already records the principle —
*"a compliant layer under a vertical geophone would low-pass the signal"* — and we were
careful to keep museum putty off the bottom of the element, then set the whole assembly
on plastic.

**Evidence it is doing something:** the ~19.95 Hz line and its second mode at 40.97 Hz
(ratio measured 2.03–2.07 in every window) sit at a **fixed** frequency across washer
spin, dryer, dead quiet, midday and afternoon — 0.6 % spread. That is a structural
resonance being excited, not a machine rate. Hollow tile is exactly the panel geometry
that rings in the tens of Hz with a harmonic pair. See `analysis/SOURCES.md`.

**Why it may matter more than buffer-on:** the absolute amplitude calibration reads
**7.5× low**, and STATUS lists shunt loading, element sensitivity and site response as
the candidates. Coupling loss through a compliant layer is a fourth, is not on that
list, and is free to test.

**The test:** lift or cut the tile under the station footprint, set the base directly on
concrete, re-measure. If 19.95 / 40.97 Hz shift or vanish, the attribution is confirmed.
If the in-band floor drops or a passing car reads larger, real sensitivity was recovered.
Cost is a utility knife rather than a parts order.

**Caveats:** it is a hardware touch → **new epoch** + the usual ~35 min settling
([[settling-time-after-handling]]). Everything measured to date (isolator 1.6×, the
100 sps switch, all noise floors) was measured through this coupling — still valid
*relative* to each other since the tile was constant, but the absolutes inherit it.

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
   This lands the corner in the **low kHz** (1 k×2 + 10–47 nF ≈ 1.7–8 kHz) — its
   job is the charge-reservoir + HF/RF/modulator-alias rejection; the ADS1256's
   digital SINC filter does the decimation anti-aliasing. (Earlier "~60–80 Hz"
   here was wrong: that would need ~25 kΩ series R, which wrecks gain accuracy
   and adds noise on the unbuffered switched-cap input — don't.) Well above the
   <30 Hz signal band, so it doesn't touch the geophone response or the damping.
   TI-recommended for unbuffered ADS1256. Does NOT lower the broadband thermal
   floor. Full schematic + BOM: `doc/rev2-frontend.md`.

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

### Custom PCB — do it, but only once Rev-2 is frozen

A fabbed board (JLCPCB, ~$25/5) is the right end state and a real win for a µV
front end — not just tidiness: a controlled layout (ground pour, short symmetric
AD0/AD1 pair, single-point star ground) lowers noise, and rigid-mounted parts kill
the microphonics/intermittents that rat's-nest wiring causes (ironic on a
seismometer). **But a PCB freezes the design and Rev-2 isn't frozen** (buffer/5 V-
AVDD, damping-R value, whether supply work is needed — all open above). Sequence:
prototype on perfboard → shorted-input floor test → lock values → *then* lay out.
Board is analog-only (XLR → AD0/AD1/AGND terminals; tap Waveshare AVDD/VREF/AGND
for bias ref; damping-R stays a socket; XLR shield to the one star ground).

## Digitize-at-the-sensor (architecture fork — Charles's idea, 2026-07-23)

The right long-term architecture, and what pro digitizers (Q330, Centaur) do: put
the ADC millimetres from the geophone, keep the analog run tiny, send only DIGITAL
home.

**Core rationale (Charles's framing): shrink the analog domain to the smallest
possible physical volume.** A µV analog conductor is an antenna for radiated EMI and a
plate for capacitive coupling; pickup scales with its length and loop area. Collapse
the analog extent to mm and you deny the noise a place to get in, rather than
rejecting it after the fact. Secondary benefit: once the signal is digital, a noisy
cable corrupts nothing (bit errors caught by framing/CRC, not summed into µV).

**Subtlety — "the analog stuff" is NOT mainly the geophone→ADC wire.** That link is
DIFFERENTIAL across a low-ish 375 Ω source, so common-mode rejection already protects
it (why a modest XLR run isn't the problem today). The vulnerable nodes are
high-impedance and single-ended: the 2×100 kΩ bias network and the ADC input, where
capacitive coupling dominates. So contain the WHOLE front end (geophone + bias +
anti-alias RC + ADC + MCU) in one small shielded can, with only isolated digital
crossing the boundary — not merely "ADC at the coil".

**What it does / doesn't fix:** attacks COUPLED/RADIATED noise (same class as the
isolator and the WiFi-TX event) — NOT the intrinsic floor (bias-R Johnson noise, ADC
input-referred noise, buffer-off penalty), which stays the Rev-2 buffer-on lever.
And note the MCU/ADC inside the can are themselves noise sources, so the single-point
star ground matters MORE in one shared box, not less.

**Caveat: SPI and I²C are the WRONG buses for the cable run.** They are on-board
buses (cm scale). SPI has no framing/CRC/differential and, at our ~1 MHz ADS1256
clock, a >tens-of-cm run reflects/skews and — worse — gives no way to DETECT a
corrupted sample (we measured SPI injecting noise with zero cable, 2026-07-23). I²C
is worse: open-drain, ~400 pF bus budget, ~1 m ceiling even with extender hacks.

**What actually implements the idea:** a small MCU at the sensor reads the ADC over
SHORT local SPI, then ships framed+checksummed samples home over a bus built for
distance — RS-485 (differential, 100s of m, cheapest robust option), Ethernet (what
pros use; drops onto our existing network pipeline), USB (≤~5 m; ESP32-S3/S2/C3 and
RP2040 all give native USB-CDC for a few dollars — Charles's point), or FIBRE (below).

**Fibre optics — the complete-isolation terminus (Charles's idea, 2026-07-23).** The
transport with NO copper at all: total galvanic isolation AND EMI/RFI immunity in one,
the full version of what the isolator / USB-isolator do partially. What vault-grade
installs use. Three caveats: (1) it is a TRANSPORT, not a digitiser — still need the
ADC+MCU to make bits; fibre just replaces RS-485/USB as the link home. (2) Cheap form
is right here: plastic optical fibre + optical-UART (Broadcom/Avago HFBR-series or
repurposed TOSLINK), framed UART over light, a few dollars, tens of metres — glass/SFP
is fine too if you fancy it. (3) Fibre carries NO POWER, which is a feature: powering the sensor side
from the Pi over copper would reintroduce the exact galvanic path fibre exists to kill,
so fibre FORCES local power — and battery+LDO is independently the cleanest supply
(see "Case design — power feed": "charge offline, not pass-through"), so the two wins
compound. Endgame node: geophone → ADC → MCU → optical TX → fibre → Pi, sensor side on
its own battery = a fully isolated, EMI-immune, clean-supply island.

**On "is it necessary" — wrong question (Charles, 2026-07-23).** This is a hobby; the
deliverable is the satisfaction of building it well, not the minimum that clears the
noise floor. "Overkill / more than the problem needs / premature" is the professional
filter and does NOT apply here. Fibre-linking a battery-powered digitiser node is a
genuinely beautiful build and "because it would be elegant" is a sufficient reason to
do it. The only real ordering constraint is practical: things that must be FROZEN
before the crawl-space move (iterative, bench-tunable) come first — see the crawl-space
sequencing note. Beyond that, build what is fun in whatever order pleases.

**The REAL payoff is deterministic acquisition, not cost.** The MCU services the
ADS1256 DRDY line in a tight ISR, doing nothing else — so the glitch/dropped-sample
classes we spent 2026-07-23 filtering (71 register-collision glitches + 10 drops in
6 h, all from a Python DRDY poll arriving late behind GC / the shm write / a day-file
flush) largely vanish AT SOURCE. The MCU free-runs the ADC on its own crystal (the
RDATAC timebase we already use), so USB transport jitter is irrelevant — timing lives
at the sensor, not in the Pi's scheduler. This is "move acquisition off the
multitasking Pi onto a dedicated MCU," which is a reliability win independent of the
cable-length argument.

**Two traps this project has already been bitten by:**
- **RADIO. An ESP32 is a WiFi/BT transmitter.** Our worst noise event
  ([[wifi-tx-corrupts-acquisition]]) was a WiFi dongle's TX current corrupting the
  ADS1256 via a shared rail; a live radio millimetres from the geophone recreates that
  at point-blank range. Use the ESP32 wired with the radio NEVER brought up — at which
  point an **RP2040 (native USB, ~$4, NO radio)** is the safer pick for exactly that
  reason. Wireless, if ever wanted, belongs far from the sensor.
- **USB reintroduces the galvanic path we just exiled.** USB carries 5 V + ground from
  the noisy Pi straight to a board on the sensor — the same ground-loop class the
  Ethernet isolator fixed. Design in a USB isolator (ADuM3160-class, ~$15-30) or power
  the sensor board locally and isolate the data lines.

**Two things make this more attractive than it first looks:**
- The **ADXL355** accelerometer already on the 3-component backlog is ALREADY digital
  (built-in ADC, SPI/I²C out) — so for that channel, digitize-at-sensor is free.
- The **Lehman** lives in its own thermal box, potentially metres from the Pi, where a
  long ANALOG run would be ruinous — that channel almost requires this.

**Scoping:** for the CURRENT single vertical geophone with a short run, this is more
than the present noise problem needs — buffer-on (Rev-2 item 1) is the bigger lever.
It becomes compelling only when sensor and Pi must SEPARATE: crawl-space siting with
the Pi elsewhere, 3-component, or the Lehman. Not a next step; a real fork to weigh
when the station layout changes.

## Env node on an ESP32-S2 — retire the Pi 4, and get TRUE ambient (2026-07-26)

**Deferred deliberately: the current CLUE → Pi 4 node works, and the question it
exists to answer (does pressure or tilt explain the 0.02–0.12 Hz undulation?) needs a
day-plus of undisturbed data first. Swapping the node restarts that clock.**

Charles has an **ESP32-S2-N16R8** spare. A 1 GB Pi 4 turning a serial stream into a
CSV is enormously oversized, and it is the least reliable part of the node — SD card,
boot time, a Linux userland for a job an MCU does better.

**The real reason to do it is not tidiness — it is temperature.** `env_node/README.md`
says "read changes, not the absolute" as though the deltas are safe. They are only safe
while the *cooling* is constant: open the garage door or get a draught and the CLUE's
self-heat offset moves, which is indistinguishable from a real temperature change. Same
error contaminates humidity (RH is temperature-dependent, so a self-heated sensor reads
systematically low). **Pressure is unaffected** — which is why the current node is fine
for its main job and this can wait.

**Shape, as worked out 2026-07-26:**
- **Discrete sensors, not the CLUE.** BME280 on a short cable in free air (pressure,
  true ambient temp, unbiased RH). Keeping the CLUE and feeding the S2 over UART works
  and costs no new parts — but it keeps the self-heat problem, which is the point.
- **3.3 V, not 5 V.** A 5 V breakout's LDO dumps its drop as heat millimetres from the
  temperature sensor — exactly the failure being escaped. 3.3 V also means no level
  shifting on a 3.3 V S2. (Cheap generic BME280 boards have no regulator at all: no
  `662K` SOT-23-5 next to VIN means 3.3 V only, and 5 V destroys them.)
- **Forced mode, one read per second.** Continuous conversion self-heats a couple of
  tenths of a degree. Do not spend the (ample) CPU headroom on oversampling.
- **Add slab temperature.** A DS18B20 on a cable against the floor beside the geophone.
  Thermal settling is plausibly driven by the mount, not the air — neither the CLUE nor
  a remote air sensor measures that. Probably the most informative channel available.
- **Mount the accelerometer rigidly.** Tilt tells you the tilt of whatever it is bolted
  to; on the CLUE it reports the tilt of a PCB lying in the garage, not of the floor the
  geophone sits on. If tilt is a real suspect this must be mechanically fixed down.

**Transport — no retry algorithm needed (Charles, 2026-07-26).** Send a sliding window
of recent readings in every datagram; a lost packet is covered by the next. Sized
against the 24 h UDP probe (0.0073 % loss, **worst fade 1.4 s**): ~17 rows of the
existing CSV schema fits a ~1400 B unfragmented datagram, so every reading is sent ~17×
and only a continuous 15 s outage loses anything — a 10× margin on the worst event in
864,000 packets.
- **Keep plain CSV, not a packed struct.** Not a compute question (the S2 idles at
  1 Hz) — a wire-format one. CSV is readable under `tcpdump -A`, reuses the collector's
  existing all-fields-numeric filter, and tolerates adding a slab-temp column later.
- **Stay under one MTU.** 120 s of CSV is ~10 KB → seven IP fragments, and losing one
  fragment loses the whole datagram. Fragmentation is the failure mode this avoids.
- Collector dedups by timestamp, exactly as `udp_collector.py` does for seismic records.
  S2 stamps its own UTC from SNTP, so the keys are clean.
- Does **not** cover the node rebooting. Accepted: it is a slow context channel.

**RADIO CAVEAT — see the "Digitize-at-the-sensor" section above.** That entry rightly
says an ESP32's radio near the geophone recreates [[wifi-tx-corrupts-acquisition]]. It
applies less here (the env node is a separate box on its own supply, ~1 m away, and the
Pi 4 it replaces is *already* a WiFi transmitter at that distance), but it is not zero:
give the S2 its own power, and take a before/after spectrum when swapping. We now have
mount resonances at 19.95 / 40.97 Hz and a still-unattributed 1.002 Hz line — do not
add an un-baselined transmitter next to the sensor without a comparison.

## Three-sensor ARRAY on the property — back-azimuth + gain against cultural noise (2026-07-27)

**Far off. Prerequisites first (see below) — this is pointless until the single station
is understood.** Recorded now because the design was worked through in detail.

**Why an array, not a better single station.** Two things a single vertical channel
can never do, both of which we hit this week:
- **Back-azimuth / direction of arrival.** Needed for the northbound-vs-southbound
  traffic question; geometry forbids it from one vertical component. Three
  non-collinear sensors solve a 2-D slowness vector — that is the minimum.
- **Gain against the noise that actually limits us.** Averaging co-located sensors
  only suppresses *incoherent* noise (electronics, coil thermal) — already ~10× below
  our measured floor, so worthless. Site ambient (Highway 12 traffic) is REAL ground
  motion, coherent across nearby sensors, and does not average down. Only a
  **spatially separated** array beamforms against it, and separation must exceed the
  noise correlation length ≈ one wavelength: at 10 Hz, Rayleigh ~300 m/s → **~30 m**.

**The site works.** Lot is a trapezoid, sides 26 / 36 / 36 / 41 m → sensors at three
corners give 25–35 m spacing, aperture ≈ 1λ at 10 Hz. Coarse but real. Traffic at
5–15 Hz (λ 20–60 m) sits in the useful range.

### Architecture A — cabled (cheaper, better, REJECTED on domestic grounds)
Geophones are **passive**: no power, no clock, no electronics at the sensor. Shielded
twisted pair back to one multi-chip digitizer in the garage. 30 m of 24 AWG adds ~2.5 Ω
against a 385 Ω coil (invisible, damping unaffected) and ~3 nF (pole at 138 kHz,
irrelevant). This is how exploration seismic has always worked.
- **Rejected because** it needs trenching, and the lawn service will cut anything not
  buried. Perimeter routing along fence lines under mulch would avoid turf entirely and
  is worth reconsidering if the digging ever becomes acceptable.

### Architecture B — autonomous solar nodes (Charles's spec, the live plan)
`solar → BMS → LiFePO4 → box (MCU + ADS1256 + WiFi) → short shielded cable → buried geophone`

- **TIMING IS GPS, NOT WIFI.** WiFi+NTP gives 1–10 ms with jitter that worsens exactly
  when the radio is busy; body waves across a 30 m aperture are only **5 ms** of moveout.
  A GPS module with PPS is $15–30, sub-µs, and **receive-only** — no transmitter. It also
  makes nodes fully independent, demoting WiFi to "moves bytes, may be laggy".
- **THE RADIO IS THE KNOWN ENEMY, NOW INSIDE THE BOX.** Our worst-ever noise event was a
  WiFi dongle's TX current corrupting the ADS1256 via a shared 5 V rail
  ([[wifi-tx-corrupts-acquisition]]). This design repeats it by construction. Mitigate
  with **store-and-forward**: record continuously to local flash, transmit in scheduled
  bursts, and **flag the samples inside each TX window** so contamination is known rather
  than mysterious. Separate regulators for analog and radio; antenna as far from the
  front end as the enclosure allows.
- **LiFePO4, not LiPo.** An outdoor enclosure in Santa Rosa summer reaches ~60 °C
  internally. Cobalt pouch cells degrade fast there and fail badly.
- **Power budget** — drives the Pi-vs-MCU choice:

  | | average | daily | panel / battery |
  |---|---|---|---|
  | Pi Zero 2W + WiFi | ~0.8 W | 19 Wh | 20 W, ~100 Wh |
  | MCU + ADS1256, duty-cycled radio | ~0.3 W | 7 Wh | 10 W, ~40 Wh |

  Pi reuses every line of existing acquisition code; MCU halves the solar hardware and
  drops the SD-card failure mode. Build node one on a Pi to prove it, then decide.
- **Bury the geophone 30–50 cm** (below most of the diurnal thermal wave) and shade the
  electronics box. The short cable separating them is doing real work — outdoor thermal
  cycling is far worse than the settling we already fight indoors.
- **Site sensors at the PERIMETER near hardscape** (footing, fence-post concrete, bed
  edges), not mid-lawn. Turf is topsoil + root mat + seasonal moisture — a compliant,
  variable medium, i.e. the floor-tile problem outdoors.
- **Geometry need only be KNOWN, not regular.** Beamforming solves from measured
  positions, so route around obstacles freely. 1 ms at 300 m/s = 0.3 m, so a tape
  measure at ±10 cm is ample — do NOT use GPS for the positions, a tape is better at 30 m.

### Rejected: FM telemetry (analog subcarrier)
Historically standard (VCO → FM subcarrier → VHF/phone line → discriminator; 1970s–90s
USGS practice), and it does make the link amplitude-insensitive. But: it **still needs
power at the sensor** so it solves nothing; analog FM telemetry delivers ~40–50 dB of
dynamic range against our ~126 dB, which is why the profession abandoned it; VCO thermal
drift adds a new sub-Hz error term of exactly the kind we are already chasing; and it
puts a transmitter next to the geophone.

### Prerequisites (the "long way to go")
1. **Coupling** — get off the floor tile (top of this file).
2. **Shunt damping resistor** — Phase 3, still unchecked; no honest response without it.
3. **Instrument response / report m/s** — needs 2.
4. **Shorted-input floor test** — tells us whether electronics matter at all.
5. **Simultaneous sampling within a node** — 3 components need multiple ADS1256 sharing
   CLKIN with tied SYNC (the MUX staggers channels and inter-channel skew destroys
   particle motion). Prove on the bench before committing to a board.
6. Only then: one solar node, validated against the garage station, before three.

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

## ADC upgrade (consideration — not the current bottleneck, but fair game)

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

## Higher sample rate — 60 → 100 sps (maybe, 2026-07-25)

**Why it's tempting:** the geophone is flat to ~100+ Hz but we sample at 60 sps, so
Nyquist caps *recorded* content at ~28 Hz. The M2.5 showed genuine, good-SNR earthquake
energy up in the 15–28 Hz band (the high-frequency noise floor is quiet, so the quake
stands out there), and a very-local event retains even more. 100 sps opens Nyquist to
50 Hz — where the sensor's high-frequency reach would actually pay off for close quakes.

**Capability confirmed (measured 2026-07-25):** a 5-min DRATE=100 RDATAC test on the live
Pi 2B hit **99.9 sps at ~0 ms clock error**, **~0.025 % drops** (honest 10 ms cut-blocks)
and ~0.07 % held-sample glitches — the Pi keeps up. The ADS1256 does 100 sps natively
(maxes at 30 ksps; 100 is a stock rate, well clear of its >2 kHz SPI-noise regime). So
neither the Pi nor the ADC is the wall.

**Why it's only a "maybe":**
- **Small quality cost** vs near-zero drops at 60 sps (the faster read loop stalls
  occasionally under load) — reducible with recorder priority (`nice`/RT sched) if pursued.
- **~2× data volume** (~40 MB/day) and proportionally more rsync/pull traffic.
- **New configuration epoch** — the declared archive rate changes, so 100 sps data won't
  merge with the 60 sps archive (a hard break, like the demo-jumper epoch).
- Most events are farther/regional, where the high frequencies are attenuated away anyway,
  so the payoff is mainly for **very local** quakes.

**If done:** bump `SEISMO_DRATE` + `SEISMO_RATE` to 100 in `seismo-recorder.service`,
declare the epoch, and consider recorder scheduling priority to trim the drop rate.

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
  Power-in scheme now specified — see "Case design — power feed" below.

## Target siting — crawl space on bare earth (design driver)

**Final home for the station (once tweaking is done): the under-house crawl space,
on bare earth.** Built into a hill, so part of the crawl is stand-up height, and
power is present. This is essentially a poor-man's vault and is the *fix* for the
environmental noise, not the electronics:

- **Thermal stability** (below grade, earth-coupled) → should retire the sub-Hz
  thermal-settling undulation seen in the garage.
- **No wind/drafts** → retires the garage draft/barometric buffeting.
- **Direct earth coupling + below-grade quiet** → lower cultural/microseism noise.
- Does NOT change the electronic noise floor (that's the Rev-2 front-end work).

**SEQUENCING: the crawl space is the TERMINAL step, not the next one** (Charles,
2026-07-23). Once it is under the house every iteration costs a belly-crawl, so
anything that needs a measure-adjust-remeasure loop must be FROZEN on the bench
first:
- **Settle before the move** (all iterative): buffer/AVDD decision, `Rd` damping
  tuned against recorded impulses, Rev-2 board built and validated, GPIO-header
  power feed + inline fuse, ferruled/sealed connectors.
- **Must be right first time** (cannot iterate down there): sealed enclosure +
  desiccant, paver bedded in tamped earth and levelled, conduit/critter protection,
  mesh-node Ethernet with no radio on the Pi.
- **Observability becomes a PREREQUISITE, not a nice-to-have.** Every problem found
  on 2026-07-23 -- the hairy drum, the 13:54 garbage frame, the isolator's
  improvement -- was found by Charles LOOKING at the station. That channel disappears
  once it is inaccessible. So the QC counters (`health.json`: dropped/glitches/
  spikes/stalls/resyncs, plus `qc.log`) must be surfaced on the dashboard, and
  ideally alerting, BEFORE the move. See "Acquisition QC" layers 3 and 4.

**Design implications to bake in NOW (enclosure is still open):**
1. **Humidity is the #1 hazard.** Bare-earth crawl = damp. Seal the electronics
   enclosure + **desiccant** (rechargeable silica), **vapor barrier** (poly) under
   the station, consider conformal-coating the boards. The **gold-contact / sealed
   connectors already specced (XLR-B, Powerpole) become essential here**, not
   optional — this is the humidity case they were chosen for.
2. **Coupling: NOT the flat plastic stand straight on soil.** `geophone_stand`'s
   flat base wants a hard flat surface; on damp/loose earth it rocks and settles.
   Set a **leveled concrete paver bedded in tamped earth**, stand on that (rigid
   broad earth coupling + moisture break + flat seat). Level it (vertical geophone).
   Site on undisturbed native soil **away from footings, furnace/water-heater,
   pumps/plumbing** — couple to ground, not the house's machinery.
3. **Network: no WiFi radio ON the Pi** (a USB dongle's TX current corrupts the
   ADS1256 reads via the shared 5 V rail — see memory; it's a conducted-noise
   problem, NOT coverage, so a strong mesh signal doesn't fix it). The wireless is
   fine as long as the radio lives elsewhere: **wire the Pi to the mesh node's
   Ethernet LAN port** (a node sits right above the spot), mesh does the backhaul —
   same as the deployed Ethernet-bridge fix, using the mesh node as the bridge. No
   spare LAN port → a small unmanaged switch or a WiFi client-bridge does it.
   Remote monitoring matters more (won't be eyeballed under the house).
   - **CURRENT STATE (2026-07-21):** dongle is GONE — Pi runs Ethernet to a WiFi
     bridge already. A **galvanic Ethernet isolator** is inbound (~2026-07-22) for
     that link: breaks any ground-loop / common-mode ingress from the bridge's
     supply back into the Pi over Ethernet (the network analog of grounding the
     shield at one end). Belt-and-suspenders — Ethernet PHYs are already ~1.5 kV
     isolated, so this mainly bites on shielded-cable shield loops or a noisy bridge
     wall-wart. Install **at the Pi end**; confirm it's **10/100** (Pi 2B is 100M).
     Does NOT replace Pi rail quality — the original corruption was internal 5 V
     rail, so the clean-supply + ADC-decoupling work is still the real robustness.
4. **Critters/cable protection** — rodents; conduit/protect the cable, critter-
   resistant enclosure.

## Case design — power feed (Pi + HAT enclosure)

Deferred to the enclosure CAD (build123d, `parts/`). The electrical reasoning is
settled; this is the mechanical/connector realization.

**Why not micro-USB:** the Pi 2B's micro-USB power jack is the weak link — thin
contacts, high/variable contact resistance, works loose. It was the original
brownout path (rail sag → fs drops / square-wave plateaus). We bypass it entirely.

**Feed the 5 V into the GPIO header, not micro-USB.** The Waveshare AD/DA board has
a **pass-through GPIO connector on top**, so we inject at the top of the stack
without unmounting the HAT — and it's a true straight-through, so that 5 V is the
same rail feeding both Pi and ADC, delivered right where it's consumed.
- Land on pins **2 + 4** (5 V, paralleled) and **two grounds** (6 + 9/14) to halve
  header/crimp contact resistance and keep the feed stiff. Pi ties 2/4 internally.
- **Crimped** connector (2×20 IDC shell or tight individual crimps), not loose
  Dupont — flaky Dupont on a power feed = new brownout.
- **micro-USB left unplugged** — exactly one source, never both fighting.
- Seat the pass-through header hard; a loose stacking header = intermittent =
  the same plateau artifact through a new door.

**Case-mounted connectors (to model):**
- **Anderson Powerpole** for power-in on the case wall (ham standard, genderless,
  positive detent). Model the panel cutout + retention off the actual PP15/30/45
  housing (shared body) when in hand.
- **Inline fuse holder** spliced into the +5 V lead between the Powerpole and the
  header pins — ~2 A (blade or barrel). Restores the over-current protection we
  lose by bypassing the Pi's input polyfuse. In-wire, so no panel cutout to model;
  just anchor/strain-relieve it inside the case. (A current-limited supply covers
  faults too, but the fuse is the visible, swappable belt-and-suspenders.)
- Internal wiring: **20 AWG stranded** (drop is negligible at ~1 A over <1 ft; 20
  AWG is the crimp-into-0.1″-housings sweet spot — heavier just fights the pins).

**Supply:** clean, **stiff** 5 V (linear-regulated preferred, ≥2 A) — stiffness
(low output-Z / transient response) matters as much as low ripple for brownout
margin. Battery + LDO is the cleanest if a supply spur ever shows in the spectrum
(charge offline, not pass-through). Gate the fancy supply on data — the front end
is differential/floating and rejects common-mode, so confirm a switching hump
exists before optimizing for it.

**Related — geophone case (separate enclosure):** XLR panel connector for
plug/unplug (male chassis NC3MD-L-B on the sensor, female NC3FD-L-B on the Pi end;
D-series 24 mm bore + 2×M3 @ 19 mm). Shunt **damping resistor lives inside the
geophone case**, across the coil. Shield (pin 1) bonded to ground **only at the Pi
end**. Connectors arriving ~2026-07-28.

## Helicorder v2 (precomputed-envelope drum) — follow-ups

The dashboard drum is now precomputed: `heli_build.py` reduces each 15-min interval
to a fixed-width (min,max) envelope npz; `heli_render.py` stacks them into a
1920×1080 drum with no obspy; `heli_service.py` rebuilds+re-renders once per data
change, off the request path. Design in `dashboard/HELICORDER.md`. Open items:

- **Event isolation & plotting** (Charles's ask): when the drum clips a big event,
  break it out into its own detail panel/plot (waveform + timing) rather than only
  the clipped drum trace. Ties into the existing STA/LTA detections (`events.log`).
- **The ~15-min periodic vertical streak**: the sample drum shows a full-scale
  transient at the *same phase* (~8–9 min) in every interval. Confirm it's a real
  periodic source (timer-driven appliance?) vs. a bucketing/high-pass artifact
  before trusting it. First check: does it appear in the raw waveform at those times?
- **~1–3 min "up spikes" — RAN DOWN 2026-07-21: real cultural motion, NOT an
  artifact.** 40-min analysis of the live day-file: spikes are **bipolar/
  oscillatory** (raw swings both ways, asym ≈ 0.4–1.0), **not phase-locked to any
  timer** (sec-past-min std 17.5 → rules out the 60 s rsync/housekeeping glitch),
  and **survive gap-bridging** (the 300× ~68 ms/10 s block gaps are symmetric &
  sub-noise → not the high-pass-rings-a-gap artifact I first suspected). Amplitude
  ~4–12 µV coil (~0.15–0.4 µm/s) = textbook cultural microtremor; a run of regular
  ~29 s intervals fingerprints a duty-cycling appliance for the more regular ones.
  Verdict: the drum is working — it's hearing the house/neighborhood. Reduce only
  via siting/isolation (enclosure), not code. (Distinct from the 15-min streak.)
  - **REOPENED 2026-07-23: this verdict may be wrong.** Charles noticed the spikes
    largely stopped after the galvanic Ethernet isolator went in. Measured (1–15 Hz
    envelope, ≥8 s apart), spikes/hour at matched LOCAL time: 00:14–00:56 last night
    no isolator = **128.6/h** (>2 µV) / 88.6/h (>3× median); 00:14–00:40 tonight with
    isolator = **0.0 / 7.1**. If real, these were conducted electrical ingress, not
    ground motion, and the "bipolar, not phase-locked, survives gap-bridging"
    reasoning that convinced me on 07-21 was insufficient — an intervention beats
    observational inference.
    **CONFOUND (Charles's, and it's a good one): HVAC.** The rate is wildly
    non-stationary on its own — last night, no isolator, it fell 128.6/h (00:14) →
    12.0/h (02:00 local), i.e. ~10× within one night, which is what a duty-cycled
    appliance looks like. A/C wasn't running tonight (not hot). So a between-night
    comparison cannot settle this.
    **HVAC CONFOUND TESTED AND LARGELY RETIRED (2026-07-23 07:44 UTC).** Charles
    forced the A/C on for ~3 min from the thermostat (condenser is on the SAME SLAB,
    other end of the garage — close enough that coupling was expected). With the
    isolator in: band 1–15 Hz **0.665 → 0.670 µV (+0.8%, i.e. nothing)**, asd 15–28 Hz
    0.091 → 0.096, broadband 1.33 → 1.48 (sub-Hz only, blower air/thermal). **No
    spikes at all** across 3 min, when they had been arriving every 1–3 min. So the
    A/C is not a meaningful seismic source here, and cannot explain the spikes as
    ground motion. Logical consequence: if the spikes HAD been HVAC-through-slab, the
    isolator could not block them and they would still be present — they aren't.
    Balance now favors **conducted electrical noise**. Lesson: the 07-21 verdict
    reasoned from waveform *character* (bipolar / not phase-locked / survives
    gap-bridging), which cannot distinguish ground motion from electrical ingress.
    Only an intervention can.
    **LABELLED NEGATIVE CONTROL (2026-07-23 08:20 UTC):** Charles wheeled **one
    loaded trash container** out past the garage (sensor side), time known to ±20 s.
    (The other two bins went out much earlier, at unrecorded times — so only this
    one is a usable labelled event.) Result: **nothing detectable in ANY band** — raw, 0.02–0.5, 0.5–3, 3–15,
    15–28 Hz all indistinguishable from neighbouring windows, and **zero STA/LTA
    triggers** in the surrounding 10 min.
    **BUT THIS IS WEAK EVIDENCE for the spike question, per Charles:** the cans live
    outside and roll only on the **driveway**, never on the garage slab, and the
    driveway is a separate pour with an **expansion joint** between it and the slab.
    A joint is a real mechanical discontinuity, so a null here is the *expected*
    result — it mainly demonstrates that the joint attenuates, not that cultural
    sources can't reach the sensor. Do NOT count this as a third line of evidence for
    electrical ingress (an earlier version of this note did; that was wrong).
    What it IS good for is a **site-coupling fact**: driveway-borne activity is
    strongly attenuated, while sources ON the garage slab or in the house structure
    are not. That also helps explain why this station is quieter than its siting
    suggests, and it means "cultural" candidates should be weighted by which pour
    they sit on.
    **STILL CHEAP TEST (no hardware trip): track spikes/hour over several nights with
    the isolator in.** If the 20:00–23:00 local window — which ran 130–180/h — stays near
    zero, cultural is dead and it was electrical. Note this is unlike the 1.63× RMS
    improvement, which IS solid because last night's RMS was flat (1.10–1.12 µV)
    across all the same hours.
- ~~**Day-boundary row truncates ~1 min (the UTC-midnight interval).**~~ **FIXED**
  (commit `e948e51`, deployed). `build()` now loads the last TWO day-files and merges,
  so a 4 h window can span the 00:00 UTC rollover (the 23:45 interval's tail minute
  lives in the prior day-file). **Verified 2026-07-22** on real data by rebuilding a
  6 h window straddling midnight: the 23:45 row comes out `complete=True` with 1.000
  pixel coverage (previously it froze ~1 min short once the recorder rolled files).
- **Suppress faux (cultural) detections.** Confirmed 2026-07-21: at threshold 20 the
  detections are overwhelmingly cultural impulses (broadband vertical-stripe
  spectrograms, no P-S, timing doesn't match catalog) — see the "1–3 min spikes"
  note. Key: **can't threshold it out** — sharp impulses produce the HIGHEST STA/LTA
  (saw 250, 1746), so raising the ratio rejects real quakes first.
  **DONE 2026-07-22 (first, cheapest lever):** raised the detector high-pass corner
  **1 → 3 Hz** (`SEISMO_HP` default in `recorder.py`; `seismo-recorder.service`
  restarted). Root-caused on the 02:13 event: at the trigger instant only 0.05–0.5 Hz
  tilt/settling energy was present (1–15 Hz was noise), and the old *gentle 1-pole*
  1 Hz HPF passed 0.3–0.5 Hz at only −7 to −11 dB → the ratio pinned at 4165 against a
  dead-quiet LTA. 3 Hz drops that sub-Hz leakage ~9 dB more (and the CF *squares* it →
  ~18 dB less trigger energy) while keeping the 4.5–15 Hz band the geophone actually
  hears (−1 to −2 dB there). Zero added CPU — only a startup coefficient changed.
  This kills the **low-frequency-onset** faux triggers; the remaining levers still
  handle genuinely broadband-impulsive cultural thumps. Further levers: (1)
  **physical** — finish crawl-space siting + stop handling the rig (the biggest
  offenders are us working on it); (2) ~~**frequency/character veto** (cheap)~~
  **DONE 2026-07-22** — the dashboard now scores each detection's waveform SHAPE and
  badges it `impulsive` / `sustained` / `near-threshold` (soft label, never a drop).
  **The HF/spectral-flatness premise written here was empirically WRONG** for this
  site: over 127 real triggers the impulsive population came out *lower* in HF
  fraction (median 0.09) than the sustained one (0.41) — these thumps are
  low-band-dominated, and a 0.3 s spike barely moves a 30 s window's spectrum anyway.
  What separates cleanly is **envelope kurtosis** (impulsive p10 45 vs sustained p90
  26, no overlap) plus duration-above-25%-of-peak and peak/median SNR. Thresholds,
  method and caveats: `dashboard/CHARACTER.md`. Still uncalibrated on the POSITIVE
  class — no confirmed quake yet (Phase 5), so `impulsive` means "shaped like a
  thump", NOT "not a quake"; (3) **ML phase picker** (EQTransformer/PhaseNet on pi5, triggered
  windows) — the real discriminator, ties to the Jetson ML-detection item; (4)
  **network association** vs a real-time feed — confirmation ✓ badge, has latency.
- **NEW 2026-07-23: a 28.6 s HARMONIC COMB dominates the sub-Hz spectrum.** Charles
  asked why the spectrum page shades an "ocean microseism" band if we cannot hear the
  microseism. Measuring a 4 h quiet window (despiked offline) settled it: the sub-Hz
  peaks are **narrow lines at 0.035 / 0.07 / 0.14 / 0.195 Hz**, i.e. a **28.6 s
  fundamental plus harmonics**, sitting on a smooth 1/f^0.8 instrument floor. A real
  microseism is a BROAD hump across 0.05–0.2 Hz, so this is machinery, not ocean. The
  comb is visible on the /spectrum chart continuing up through 0.28, 0.35, 0.55, 0.75,
  1.1 and ~2.2 Hz — so it reaches into the local-quake band.
  - **The 0.07 Hz harmonic lands squarely in the microseism band**, which is a
    coincidence trap worth remembering.
  - **28.6 s matches the "~29 s intervals" noted in the 1–3 min spike analysis above**
    — plausibly the same source, and a lead Charles can chase physically by switching
    things off and re-measuring. A periodic impulse train is what produces a comb.
  - Also learned: **one bad sample can bury a whole spectrum.** Before despiking, two
    isolated garbage frames (±6–7 M counts) in 864,000 samples raised the ENTIRE
    0.03–4.5 Hz spectrum to a flat ~12 µV/√Hz — 30× the true level. Always despike
    before spectral analysis, and treat a suspiciously flat spectrum as a spike
    signature rather than a noise measurement.
- **Final amplitude constant**: `ENV_FRAC`/`CLIP_ROWS` set by eye on the noisy
  garage-door-era 90-min sample; re-tune on real calm 8 h pi5 data.
- **Deploy to pi5**: fold `heli_build` deps (already have obspy) — the service runs
  in-app; verify `/data/heli` is writable in the mounted volume, then `ps:rebuild`.

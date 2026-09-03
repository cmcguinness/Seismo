# Toy seismometer — a giftable, self-contained ground-motion display

A small standalone unit: geophone → 24-bit ADC → ESP32-S3 with an LCD, in a printed
case, powered by USB-C. It draws a live scrolling trace of the ground under whatever
it is standing on. **No network, no app, no setup** — plug it in and it works.

It is a *toy* in the sense that it makes no scientific claim, not in the sense that it
is fake: the sensor and the front end are the same class of parts as the real station,
and it will comfortably see a person walking across the room.

> **Field variant.** The same board with a microSD logger, a record button and a hammer-switch
> input is the survey instrument for the refraction work: see
> [field-seismograph.md](field-seismograph.md). This document stays the gift; that one is
> the delta.

## What the recipient will actually see, and why it must be a geophone

This decides the whole design, and OAKMT's own labelled data settles it. A footstep
**three metres away** peaks at ~100 µV at the station, which is ~**100 µg** of
acceleration.

| candidate sensor | self-noise, 1–15 Hz | footstep at 3 m |
|---|---|---|
| MPU6050 / ICM-20948 | ~1100 µg RMS | invisible |
| ADXL355 | ~85 µg RMS | **SNR ≈ 1** — marginal, disappointing |
| **LGT-4.5 geophone + 24-bit ADC** | a few µV ⇒ SNR **20–50** | obvious |

A MEMS toy only responds to things touching its own table — you have to bang the desk.
The geophone version reacts when somebody walks into the room, which is the entire
gift. The sensor is also the cheapest way to buy that: ~$25.

## Bill of materials, ~$60/unit

| part | choice | why | ~$ |
|---|---|---|---|
| sensor | LGT-4.5 / EG-4.5-II, 375 Ω | same element as the station; known quantity | 25 |
| ADC | **ADS1220** 24-bit, PGA ×128, SPI | 1.9 nV LSB at PGA 128 — **no discrete preamp**, which removes the hardest part of the build | 10 |
| compute + display | **LilyGO T-Display-S3** (ESP32-S3, 320×170 ST7789) | one part instead of three; 320 px of landscape is exactly a scrolling drum row | 20 |
| analog LDO | any 3.3 V LDO + 10 µF/100 nF | see the radio note below | 1 |
| case | printed, build123d | already have the toolchain and a geophone-case precedent | 2 |

A round 240×240 (Waveshare ESP32-S3-LCD-1.28) looks lovelier as an object but is
cramped for a trace; landscape wins on legibility.

## Analog front end

Four passive parts around the ADC, and nothing else:

- **Bias**: two 1 MΩ resistors from each coil leg to VREF/2, to put the floating coil
  inside the PGA's common-mode range.
- **Shunt damping**: across the coil. ⚠️ Re-derive the value — do **not** copy the
  station's. `doc/shunt-damping.md` is the method, but the electrical load here is the
  ADS1220's PGA input impedance, which is not the station's front end, and ζ depends on
  the total load. Same measurement (`ringdown`), different answer.
- **Anti-alias RC** at ~40 Hz on each leg. The station still lacks one and it is a
  standing TODO there; on a fresh board it costs two resistors and two capacitors.
- **Sample rate** 250 sps, PGA 32–64. (The station runs 100 sps; 250 gives the display
  a smoother-looking trace for free and the ADS1220 does 1000.)

### The radio, correctly scoped

The Wi-Fi interference that plagued the station was **conducted, not radiated** — the
dongle's transmit current on a shared 5 V rail, into a chain with a 375 Ω coil, a metre
of cable, and µV signals. Here the coil sits ~20 mm from the ADC on the same board, so
the pickup loop is negligible and the mechanism largely does not apply. A separate LDO
for the analog side plus bulk decoupling handles the supply-sag path. This is a
power-integrity detail, not a design hazard — and it means the networked variant is far
more approachable than the station's history suggests.

## Firmware

Two cores, and it borrows the station's two best display ideas.

- **Core 0 — acquisition.** ADS1220 in continuous-conversion mode, DRDY interrupt, read
  over SPI into a ring buffer. One-pole high-pass at 1 Hz to kill drift and tilt (the
  same corner `heli_build` uses).
- **Core 1 — display.** Reduce to **one min/max pair per pixel column** — the
  helicorder envelope, exactly — and scroll right to left. Auto-scale to the *median*
  column excursion, not the peak (the drum's `ENV_FRAC` trick), so the trace always
  looks alive on a quiet desk and never clips when someone slams a door.
- **Readouts**: current peak in µV, and "biggest since you plugged it in".

No network in v1. Firmware in Arduino-ESP32 or ESP-IDF; Arduino is the faster route and
the performance headroom is enormous at 250 sps.

## Build order — running thing first

1. **Desktop simulator.** Display code driven by synthetic + recorded OAKMT data, so
   the whole rendering path is finished and demoable *before* any parts arrive. This is
   the one piece that can be built today.
2. **Breadboard**: geophone → ADS1220 → ESP32-S3, trace on the LCD. Ugly, working.
3. **Damping + anti-alias**, measured, not looked up.
4. **Case**, printed, one iteration expected.
5. Only then: a second unit, and think about a batch.

## Case notes

- Reuse the `geophone_case.py` pattern: a pocket that seats the element, three-point
  contact underneath.
- **Hard feet, no rubber.** It must couple to the desk — isolation is the enemy here,
  which is the exact opposite of what the real station wants.
- Mass helps. A steel washer stack or a sand-filled void in the base steadies it.
- Engrave the recipient's name and location on the front; the screen shows the same.

## Make it a gift, not a gadget

Print on the back, honestly:

> Detects footsteps, doors, and the occasional earthquake.

The delight is watching your own footsteps register from across the room — not waiting
months for an M4. Anything the packaging implies beyond that will disappoint, and it
does not need to.

---

## Variant B (2026-09-03): Pi + touchscreen + ADXL355, the household strong-motion box

The section above is right about a **slab**: on concrete a footstep at 3 m is ~100 µg and
the ADXL355 cannot see it. It is wrong about a **house**. On a shelf in a wood-frame home
the floor flexes and the same footstep is tens to hundreds of times larger; a door slam or
the washing machine's spin cycle is tens of mm/s². The MEMS box is deaf to distant
earthquakes (M2 at 40 km is below its ~1 mm/s² floor) and hears every felt one (M3+
within tens of km is 100–1000× above it), plus the whole life of the house. That is a
different gift from the geophone toy, not a worse one: no damping resistor, no coil, no
24-bit front end, no level to fuss, works on a bookshelf. The display, not the sensor,
sets the expectations: lead with the USGS feed, a "last time this box moved" card with a
catalogue match or "something in the house", and a felt-intensity readout in words; the
helicorder is the second panel and the picture they show people the day a real one
crosses it. Plan for the source classifier is in the 2026-09-03 STATUS entry: the
station's features unchanged on acceleration, plus H/V vs time from three components,
the touchscreen as the labelling tool, NCEDC strong-motion records as the positive class.

### Bill of materials, ~$190/unit

| part | why | ~cost |
|---|---|---|
| Raspberry Pi 4 Model B, 2 GB | fanless (a fan is a vibration source in the sensor's own box); the Pi 5 wants one and the Zero 2 W has no DSI port | $45 |
| Raspberry Pi Touch Display 2, 7" | the face of the thing and the labelling tool; DSI, powered from the Pi | $60 |
| EVAL-ADXL355Z | the sensor, on the board with corner mounting holes (not the -PMDZ, which is a Pmod plug) | $40 |
| BME280 breakout | temperature (the ADXL355's offset drifts with it, and the box should say so when the heater comes on) and pressure, which casual users like more than any of it; I²C, same header | $8 |
| Raspberry Pi 27 W USB-C supply | the display adds current; cheap adapters brown out | $12 |
| 32 GB high-endurance microSD | it writes day-files all day; endurance grade, not speed | $12 |
| 7-way 0.1" female leads, 15 cm | 3V3, GND, SCLK, MOSI, MISO, CS, INT1 — sensor to header, so the chip is NOT plugged into the Pi and does not feel the screen being poked | $3 |
| M2.5 standoffs, screws, nuts | four corners of the eval board to the case floor | $5 |
| 10 µF ceramic | across the sensor supply | — |
| four hard feet | rubber feet decouple from the shelf, the opposite of what you want | $2 |
| printed case | bezel for the display, Pi behind it, sensor screwed to a flat floor away from the ribbon; the SmartiPi Touch case is the $30 shortcut but tilts on a stand (a lever arm) and has nowhere to bolt the sensor | filament |

Not needed: RTC or GPS (NTP over the house WiFi; if it drops, count samples and re-sync),
a separate ADC, level shifting (both sides are 3.3 V), a fan.

### Wiring and rates

ADXL355 on SPI0 (CE0), INT1 → a GPIO for FIFO drain on interrupt; run the chip at
250 sps with its 62.5 Hz low-pass and decimate to 100 in software so its day-files are
byte-for-byte the shape of OAKM1's location-10 channel and every analysis and dashboard
tool runs on both. BME280 on I²C1, read once a minute. Same reader pattern as
`station/adsreader`, same recorder, dashboard on the local screen.


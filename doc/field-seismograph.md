# Field seismograph — the toy's electronics, with a memory and a trigger

*Written 2026-08-26, when the toy-seismometer plan turned into a survey instrument. The
two are one board with two jobs: the **toy** ([toy-seismometer.md](toy-seismometer.md))
shows the ground on a screen; the **field rig** writes it to a card. Same geophone, same
ADS1220, same ESP32-S3. This document is only the delta.*

## What it is for

1. **Hammer refraction** on the lot and the street: soil velocity, depth to rock, and
   whether the refractor dips with the hill. See STATUS.md 2026-08-26 for the plan.
2. **Amplitude-vs-distance** of a known impulse, to calibrate the station's
   cultural-noise classifier and its coupling.
3. Later, with a second geophone: surface-wave dispersion (MASW-lite) → Vs30.

Everything above needs **relative** time only — the hammer switch and the geophone on
the same ADC clock — so the rig needs no Wi-Fi, no NTP and no RTC in the field.

## Delta from the toy

| addition | choice | why |
|---|---|---|
| **microSD logger** | Adafruit MicroSD breakout+ (#254) on SPI, or the T-Display-S3's own SD pads if the board revision has them | the whole point: press, whack, carry the card home. FAT32, one file per record session |
| **record button** | 16 mm momentary panel-mount pushbutton (Adafruit 1439–1442 family, any colour in stock) — illuminated, so the LED is the "recording" lamp | one button, two states. Press = new file + LED on; press = close file + LED off |
| **second ADC channel: hammer switch** | ADS1220 AIN2/AIN3 (it has four inputs); a **piezo disc** (Adafruit #1740) on the strike plate, through a 1 MΩ bleed and 3.3 V clamp diodes | t = 0 for every blow, on the same clock as the geophone. ~1 ms is the pick precision needed; the piezo edge is ~10 µs |
| **sample rate 1000 sps** | ADS1220 does it; PGA 32 on the geophone channel | a first break 5 m away arrives at ~12 ms. 250 sps cannot pick it; 1000 can |
| **spike** | a machined stud or the LGT-4.5's threaded spike accessory | the geophone must be *planted*, not set down. On a lawn a 75 mm spike is enough |
| **trigger cable** | 100 m of 22 AWG two-conductor bell/alarm wire on a hose reel, 3.5 mm jack at the rig end | the piezo lives at the plate, up to 90 m from the rig. Volts on the wire, so unshielded is fine |
| **battery** | a USB power bank the rig already accepts | a survey is an hour; no design work |

Not needed: display (keep it — it is free and shows the trace while you work), network,
GPS, RTC.

## Firmware delta

- Core 0 acquires **two channels** at 1000 sps: geophone (AIN0/AIN1, PGA 32) and hammer
  switch (AIN2/AIN3, PGA 1). The ADS1220 multiplexes; alternate the MUX each conversion
  and run the ADC at 2000 sps, or read the switch on a GPIO interrupt with the ESP32's
  microsecond timer and log `(sample_index_at_edge)` — the latter is simpler and more
  precise, and leaves the ADC on one channel. **Do the GPIO version.**
- Record file format: raw int32 samples at 1000 sps plus a sidecar of hammer-edge sample
  indices. `field/` tooling on the Mac reads both and does the picking.
- Button: debounce, toggle, LED = recording. Long-press = new line (increments a
  line number in the filename) so a survey's files sort themselves.
- Display: same envelope trace; add the file name and sample count in a corner.

## Analysis (on the Mac, not the rig)

For each blow: window ±0.2 s around the switch edge, stack the five blows at that
offset, pick the first break by eye (or STA/LTA on the stack), tabulate `(offset,
time)`. Plot; fit two lines; crossover and intercept give the depth
`h = t_i · V1·V2 / (2·√(V2² − V1²))`. Forward and reverse lines give dip. Correct each
geophone position to a datum (elevation ÷ V1). A spreadsheet is enough; a 60-line
Python script is nicer.

## Shopping list with links (verified 2026-08-26)

| item | link | ~$ |
|---|---|---|
| MicroSD breakout+ | https://www.adafruit.com/product/254 | 7.50 |
| microSD card, 32 GB | any SanDisk/Samsung class-10 from Amazon | 8 |
| Piezo disc w/ wires (buy a few) | https://www.adafruit.com/product/1740 | 0.95 ea |
| 16 mm illuminated momentary pushbutton | https://www.adafruit.com/product/1439 (red; 1440–1442 are the other colours — pick one in stock) | 1.50 |
| 100 m 22 AWG two-conductor bell wire | Amazon/Home Depot, "22/2 alarm wire 100 m" | 15–20 |
| 3.5 mm mono panel jack + plug | Amazon, any | 5 |
| 8 lb fibreglass sledge | Home Depot / Harbor Freight | 30–40 |
| strike plate | a 10–25 lb cast-iron barbell plate (used is fine) | 10–20 |
| geophone spike | LGT-4.5 threaded spike from the geophone vendor, or an M8/M10 stud ground to a point | 5 |

Already on order (toy BOM): LGT-4.5 geophones, ADS1220, LilyGO T-Display-S3.

## Build order

1. Toy breadboard as planned (geophone → ADS1220 → screen).
2. Add the SD + button; record a minute; read it on the Mac. **This is the milestone.**
3. Add the piezo on a GPIO; verify one edge per whack in the sidecar.
4. Spike, cable, plate, hammer — first survey is #0 from STATUS (amplitude vs distance,
   no picking), then the backyard refraction line.

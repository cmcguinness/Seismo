# BOM — strong-motion node (ADXL355 on an ESP32-S3, location code 10)

One printed case on the garage slab next to the geophone: the ADXL355 eval board screwed
to the case floor, an ESP32-S3 module alongside with its antenna clear of anything metal,
a panel-mount USB-C for power and programming, nothing else. It samples three axes at
250 sps, stamps every FIFO block from an SNTP clock disciplined to the house's stratum-1
GPS host, and sends raw blocks by UDP to pi5, which decimates to the station's exact
100 sps grid and writes `SS.OAKM1.10.HNZ / HNN / HNE`. The Pi 2 is not touched, not
shared with, and not grounded to: that isolation is the entire reason this is a second
box with its own radio and its own wall supply.

**What it buys:** the two horizontals (S wave, an H/V site ratio of our own), headroom
above the geophone's ~4 mm/s saturation (the ADXL355 clips at ±2 g, the same ceiling as
the EpiSensor at NP.1835), and PGA / PGV / instrumental intensity comparable line for
line with 1835's ShakeMap entry. **What it does not buy:** sensitivity. Its floor is
~1 mm/s² RMS in 1–15 Hz, about 16 µm/s at 10 Hz — fifty times the geophone's. M3+ within
20 km is clean; M2.5 at 40 km is at the floor; the weak catches stay the geophone's.

## Bill of materials

| Qty | Part | Notes |
|---|---|---|
| 1 | **EVAL-ADXL355-PMDZ** (Analog Devices) — *the part actually in hand as of 2026-09-09; this line previously read EVAL-ADXL355Z* | Chip on a board with a 12-pin Pmod Type 2A header (1 /CS, 2 MOSI, 3 MISO, 4 SCLK, 5 GND, 6 VDD, 7 INT1, 8 NC, 9 INT2, 10 DRDY, 11 GND, 12 VDD), 3.3 V only (the chip's supply tops out at 3.6 V). **Board is 20 × 20 mm, and the 2×6 header is RIGHT-ANGLE** — both measured on the part in hand, 2026-09-10. ⚠️ **No mounting holes.** (An earlier revision of this cell claimed corner holes and then warned against the `-PMDZ` in the same breath; that was a botched 2026-09-09 edit, since the `-PMDZ` is what we have. The two gold pads at diagonal corners are filled vias / tooling pads, not open holes — they photograph like mounting holes and are not.) It is therefore **held in a printed pocket**, not bolted — see the case row below. Ordered from Mouser 2026-09-03; the "restricted availability" lifecycle flag was boilerplate and the order went through |
| 1 | **ESP32-S3-WROOM-1 N16R8** dev board | 16 MB flash, 8 MB PSRAM (minutes of three-axis ring buffer for free), two cores: acquisition on one, WiFi/SNTP/UDP on the other. The WROOM-1's trace-antenna tab must hang over the board edge with ~15 mm of keep-out from metal; face it toward the house. Not the C3: single core, no PSRAM, and the SuperMini-style boards have a chip antenna that is 10–20 dB down |
| 1 | **Panel-mount USB-C extension**, female flange to male plug, ~15–30 cm (Adafruit 4218 or the generic screw-flange ones) | Power **and** data through the wall: flash and read the console without opening the case. Cutout plus two M2.5 holes; the coupon-first workflow in `parts/` applies. Allow 20–30 mm behind the panel for the plug's overmold |
| 1 | **Clip-on ferrite**, split core for a ~3–4 mm cable, at the USB-C entry | A common-mode choke: stops RF riding along the cord in either direction (a noisy wall supply in, the S3's own transmitter out). Does nothing for ripple on the 5 V rail inside the box — that is the chip's own regulators' job, and the ADXL355 has internal 1.8 V LDOs behind its supply pin. Cheap, harmless, and it makes the cable stop being an antenna |
| 1 | 5 V USB-C wall supply, any decent 2 A one | **Its own.** Not shared with the Pi 2, no ground strap between the boxes. Inverse square only helps with what travels through the air; a shared supply couples at full strength across any distance (2026-07-20) |
| 1 | **BME280** breakout, I²C | Case temperature and pressure. The ADXL355's offset drifts with temperature and the trace will wander when the garage does; this is the column that explains it. Read once a minute |
| 7 | 0.1" female–female leads, 10–15 cm | Sensor to S3: 3V3, GND, SCLK, MOSI, MISO, CS, INT1 (FIFO watermark → GPIO interrupt). Short: it is SPI at a few MHz, not a bus |
| 2 | 0.1" leads for the BME280 (SDA, SCL; share 3V3/GND) | I²C1 |
| 1 | 10 µF ceramic, at the sensor's supply pins | Belt and braces; the eval board has its own decoupling |
| 3 | **M1.7 × 5 pan head**, self-tapping, **U-shaped retainer** over the sensor board | The `-PMDZ` has no holes, so it drops into a pocket milled into the case floor and a printed tab screws down over it. Decided 2026-09-10 over a perfboard carrier: the pocket couples the board to the floor directly instead of inserting an extra plate, it keeps a $50 eval board unmodified, and it enforces the X-axis orientation every time the box is reopened (bring-up step 3 needs that azimuth). **No epoxy, no tape, no putty** — foam/VHB tape in particular is a real spring and is the one mounting scheme that would actually show up in the band. The margin is otherwise huge: a few grams supported at its corners resonates in the high hundreds of Hz, 30×+ above our 15 Hz. What bites is tall standoffs (stiffness falls as the cube of height) and two-point support, not the absence of screws through the board |
| 4 | M2.5 screws + standoffs, S3 board to case | Antenna end toward a plastic wall |
| 1 | Printed case, build123d, `parts/` | Sensor at one end **in a pocket sized to the measured board outline** (⚠️ measure it with calipers — do not infer it; `look-up-standard-part-dims` exists because every connector number we guessed was the one that failed), S3 at the other, USB-C flange on the outside face, lid. The pocket needs clearance for the 12-pin header and a lead-out slot for the jumpers; keep the floor under the board solid and the pocket shallow. **The right-angle header is the lucky case and settles the axes**: the back face (ADI logo, no components) is flat and clean, so it is the seating surface; the board lies flat with the chip side up and the pins exiting horizontally off one edge through a slot in the pocket wall. The ADXL355's Z axis is normal to the package top, hence normal to the PCB, so **flat board = Z vertical = HNZ**, with X and Y in the board plane for the compass azimuth. A straight header would have wanted the board on edge and put Z horizontal. Pocket ≈ 20.4 mm square × 1.6 mm deep (PCB thickness), solid floor beneath; the clamp tab must bear on bare PCB, not on the chip or the header body, so span the edge opposite the header. Indoors on the garage slab; it keeps dust and fingers off, that is all |

## Wiring

    ADXL355   SCLK  -> S3 GPIO (SPI2 SCLK)
              MOSI  -> S3 GPIO (SPI2 MOSI)
              MISO  -> S3 GPIO (SPI2 MISO)
              CS    -> S3 GPIO (SPI2 CS)
              INT1  -> S3 GPIO (input, FIFO watermark)
              VDD/VDDIO -> 3V3          GND -> GND
    BME280    SDA/SCL -> S3 I2C1        3V3 / GND shared

Chip at 250 sps with its internal 62.5 Hz low-pass; FIFO watermark drains blocks of a
few dozen samples; every block is stamped from `esp_timer` at the interrupt. **The
ADXL355's output rate comes from its own oscillator, specified to about a percent, not
ppm**, so pi5 never assumes 250: it fits the true rate from the block stamps over a
minute and resamples onto its exact 100 sps grid — the same job `recorder.py` does for the
ADS1256's 85 ppm crystal, with a bigger correction. The node stays honest about when it
received each block; pi5 does the arithmetic.

## Packet

Binary, one per FIFO block, ~4 a second, ~2.3 kB/s total: magic, version, sequence,
first-sample time (µs since epoch), sample count, nominal rate, die temperature, then
3 × n samples as int32 (20-bit left in the low bits). Sequence numbers let pi5 count
drops. Raw 250 sps goes over the wire and pi5 decimates: firmware stays dumb and the
bandwidth choice stays reversible.

## Bring-up, in order

1. S3 on the bench reading the chip, SNTP locked to the GPS host by hostname, packets
   landing in a `tcpdump` on pi5. Tap the bench, watch the packet change.
2. `udp_collector` grows a second listener and writes the three day-files; ObsPy reads
   them on the Mac; first trace plotted.
3. Into the case, onto the slab, a compass reading for the X axis written into the
   StationXML azimuth **before** anything else, then a night of data with WiFi on and the
   spectrum checked for the 100 ms beacon interval before believing anything about the
   ground. The bet is that a MEMS chip behind its own regulators shows nothing; the
   bet gets checked.
4. StationXML: the three channels with the datasheet response (sensitivity, the eval
   board's analog pole, the digital low-pass) — the first defensible response on the site.
5. Live page gets the three traces; Catches gets a PGA / PGV strip per event.

After the calibration injector build: both want the bench.

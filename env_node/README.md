# env_node — environmental / tilt monitoring node

A small sensor node that logs the *environment around the station* — barometric
**pressure**, **tilt**, **temperature**, **humidity** — at ~1 Hz, timestamped in UTC,
to correlate against the seismic stream. It targets specific open noise questions
(see `../STATUS.md`, `../doc/rev2-data-plane.md §10`):

- **Pressure** couples to the sub-Hz (0.02–0.12 Hz) seismic undulation — sampled ~1 Hz
  so it can be correlated in that band (Nyquist 0.5 Hz).
- **Tilt** (from the accelerometer's gravity vector) *is* the leading suspect for that
  undulation — thermal settling = ground tilt. This measures it directly.
- **Temperature / humidity** — the thermal-settling and moisture-vs-noise correlations.
  (These are *hyperlocal*, so the node lives near the station, not in the office.)

## Architecture — two idle boards, each doing what it's good at

```
Adafruit CLUE  ──USB serial (CSV, 1 Hz)──►  Pi 4 (host)  ──rsync CSV──►  pi5
(sensor pack)                               NTP-UTC clock + logging       (analysis,
BMP280 / SHT31 / LSM6DS3                     + network                     beside seismic mirror)
```

The **CLUE has no RTC/NTP**, so it streams only its monotonic clock; the **Pi 4 host
stamps the authoritative UTC on receipt** — that alignment is the whole point (a pressure
series that isn't UTC-aligned to the seismic stream is useless for correlation).

**Placement:** garage, near — but *not too near* — the geophone (~1 m+, different surface).
**Own power supply**, never the station's 5 V rail (the conducted-noise path that already
bit acquisition). It's a separate electrical island, like the rest of the environmental
sensors in the rev-2 telemetry design.

## `clue/code.py` — the CircuitPython sensor firmware

Runs on the Adafruit CLUE (CircuitPython 8.x; `adafruit_clue` + drivers already in its
`lib/`). Each ~1 s it reads pressure/temp/humidity/3-axis accel and prints one CSV row
over USB serial. The board is mounted **face down** (sensors up), so the TFT backlight is
turned **off** (`board.DISPLAY.brightness = 0`) — it lit nothing visible and sat millimetres
from the temp/humidity sensors as a self-heat source (a sealed-case test plateaued several
°C above ambient). Liveness = the blue NeoPixel heartbeat + the serial stream itself:

```
# seismo-env  mono_s,temp_C,press_hPa,humid_pct,ax_ms2,ay_ms2,az_ms2,n_acc,ax_rms_ms2,ay_rms_ms2,az_rms_ms2,a_pk_ms2,n_press,p_sd_Pa
3584486.863,27.41,1000.8110,41.2,-0.1082,-0.3561,9.9720,244,0.0141,0.0096,0.0167,0.0469,11,1.336
```

Since **2026-09-05** each tick *bursts* the sensors instead of taking one reading: ~250
accelerometer reads and ~12 barometer reads per second, reported as a mean plus a
scatter. Sensor reads are wrapped so one bad read can't kill the loop. Blue NeoPixel
blinks = alive.

### Why it bursts — the node accidentally recorded an earthquake

On **2026-09-03** the M3.3 under Larkfield-Wikiup (13.3 km) appeared in this node as five
consecutive large sample-to-sample changes on `ay`: the alternating-sign signature of
3–10 Hz ground motion aliased onto a 1 sps sampler. It was **the largest `ay` excursion
in the whole 43-day archive** outside of days somebody was handling the rig (0.069 m/s²;
every undisturbed day otherwise caps at 0.040–0.062), and it landed **5.9 s after origin**,
in the S window, on a horizontal axis. Landing there by chance is ~1.4×10⁻⁴.

That was luck — one sample happened to fall during the shaking. Bursting makes it
deliberate: averaging N reads pulls the *amplitude estimate's* noise down by √N, so the
tick reports a genuine envelope instead of one aliased sample.

**This is not a seismometer and must not be read as one.** The LSM6DS33's measured
per-sample noise is 0.0070 m/s² on `ay` — within 10% of its 90 µg/√Hz datasheet figure,
so there is nothing to recover by tuning — against roughly 8×10⁻⁶ m/s² equivalent for
the geophone. It is ~1000× less sensitive; it detects what you can feel. Across 54
catalogue events the geophone saw, only 2 exceeded the null's p95 — exactly the 5% you
get from chance. Only the M3.3 cleared the threshold. **The ADXL355 strong-motion node
is the real accelerometer;** this is a weather station that got lucky once.

### Three things the first flash got wrong, all visible in the data

Kept here because each was invisible to inspection and obvious in the numbers:

1. **A partial config that looked like a working one.** All five BMP280 settings were
   applied in one `try` block; the fourth used a constant name that doesn't exist
   (`STANDBY_TC_1` — it's `STANDBY_TC_0_5`), so the chip kept `MODE_FORCE`, where every
   read *blocks* for a full ~40 ms conversion. That ate half the tick: `n_acc` ~40
   instead of ~250, and intervals wandering to 1.43 s. Each setting now reports itself.
2. **float32 catastrophic cancellation.** CircuitPython's floats here are 32-bit (~7
   digits). Accumulating Σp² on raw pressure (p² ≈ 1.0×10⁶) and then taking
   `Σp²/n − mean²` subtracts two numbers agreeing to seven digits — the variance is
   annihilated. The board printed a "scatter" of 0.5 hPa on a signal moving 0.002 hPa,
   quantised to multiples of the float32 ulp. Both accumulators now run on deviations
   from the previous tick's mean, where the squares are ~10⁻⁴ and nothing cancels.
3. **`time.monotonic()` had run out of resolution.** Same 32-bit floats: at 40 days
   uptime the ulp is **0.25 s**, so `clue_mono_s` was quantised to whole seconds and the
   self-correcting sleep was computing its delta from a dead clock. Cost: mean interval
   1.040 s, **3,334 samples lost per day (3.9%)**, host dt ranging 0.46–1.53 s. Now paced
   on `time.monotonic_ns()` against an absolute schedule, and printed from integer
   arithmetic. Ticks land within 1.000–1.004 s.

### The ODR sweep — where the obvious move was the wrong one

The instinct was to raise the accelerometer's output data rate so all ~250 reads/s are
fresh samples. Backwards: the noise is flat in density, so per-sample σ grows as √ODR
while the usable sample count is capped by the read loop. What matters is how far a
small added signal moves the reported RMS out of its own tick-to-tick scatter,
∝ 1/(2·level·scatter). Swept live, 91 ticks each, on `ay`:

| ODR | level (m/s²) | tick scatter | relative detectability |
|---|---|---|---|
| 52 Hz | 0.00863 | 0.00109 | 53k |
| **104 Hz** | 0.00926 | 0.00077 | **70k** |
| 208 Hz | 0.01283 | 0.00084 | 46k |
| 416 Hz | 0.01792 | 0.00110 | 25k |

52 Hz wins on `az` and ties on `ax`, so the axes disagree at the 1.3× level; **104 Hz**
breaks the tie because Nyquist 52 Hz keeps the 35–50 Hz energy `analysis/audible.py`
found in this same M3.3 rather than folding it back into the band. Both extremes are
clearly worse — 416 Hz costs a factor of ~3.

**Net result: the ODR is unchanged.** 104 Hz is what the driver defaulted to all along.
It is now set explicitly, so it is a measured choice rather than an inherited one.

### Pressure oversampling

The barometer now runs **×16 pressure / ×2 temperature oversampling, free-running**, and
the tick averages ~12 reads. The on-chip IIR filter is deliberately **off**: coefficient
16 would put a ~0.08 Hz corner right inside the 0.02–0.12 Hz undulation band this node
exists to measure. Averaging in software is a boxcar — it anti-aliases the HVAC lines
without eating the signal.

Two things were being thrown away before. The log wrote `press_hPa` with two decimals,
quantising at **exactly 1 Pa**, while the sensor floor measured ~2.3 Pa/√Hz — the format
string was discarding real resolution. And the oversampling sat at the driver default.
Measured now: per-read scatter (`p_sd_Pa`) ~1.2–1.6 Pa, so the mean of 12 has a standard
error of ~0.35 Pa, against ~2.3 Pa/√Hz before. **Predicted** ~4.7× reduction in the
0.02–0.12 Hz band RMS (0.943 Pa → ~0.20 Pa) — *predicted, not yet confirmed*; it needs a
day of the new data to measure, and if the band doesn't drop that far, what's left is
real atmosphere rather than sensor floor. Which would be the more interesting outcome.

**Deploy:** copy `clue/code.py` to the CLUE's `CLUEPY/code.py` (CircuitPython auto-runs it).
On Linux the CLUE's serial is `/dev/ttyACM0`; on macOS `/dev/cu.usbmodem*`.

### Temperature is self-heated — use DELTAS, not the absolute value

The `temp_C` channel (BMP280, **on the CLUE PCB**) reads the board's own self-heat,
conducted from the nRF52840 + regulators through the copper — **not** ambient air.
Measured 2026-07-25 on the desk: it holds a steady **~31.7 °C** equilibrium (was
~32.4 °C sealed; backlight-off + face-down bought ~1 °C; a case redesign putting the
Pi 4 inside and the CLUE on top *in moving air* changed it essentially not at all,
~31.7 °C). Conduction across the PCB dominates; airflow over the top can't beat it,
so no enclosure geometry fixes the absolute reading — the board simply feels warm to
the touch.

The offset is roughly **constant**, so it subtracts out: **for the thermal-settling
correlation (does temperature swing track the 0.02–0.12 Hz undulation) only the
deltas matter, and those are valid.** The absolute number is *not* garage temperature
and should not be used as such. Pinning the offset to a real °C would need a reference
thermometer beside the board (not done — we don't need it). True ambient would require
a temp probe on a short lead, *off* the board in the airstream (DS18B20 / remote SHT31).

## `host/env_logger.py` — the Pi 4 host logger (DONE, running on pi4env)

Reads the CLUE's stable by-id serial, drops `#` lines, prepends **NTP-UTC** (millisecond),
appends to a daily CSV `~/env-data/env-YYYY-MM-DD.csv` (schema above, raw values). A
reconnect loop survives unplug/reset; malformed lines are dropped.

It accepts **both** the original 7-field row and the wide 14-field one, writing either
under the wide header and padding short rows with empty trailing fields — the two
firmwares can alternate across a CLUE reset or a rollback, and a superset schema keeps
every row in one file readable by one parser. A day-file carries exactly one header, so
if the schema changes part-way through a UTC day the old file is renamed
`env-YYYY-MM-DD.v1.csv` (still matched by the `env-*.csv` glob, still self-describing)
and a fresh one started. That happened once, on 2026-09-05. Runs as the
**`env-logger`** systemd service (`enabled`, `Restart=always`).

Deploy on pi4env: venv at `~/env_node/.venv` (`pip install pyserial`), copy `env_logger.py`
+ `env-logger.service` (install commands in the service file's header).

## In the feed: `SS.OAKM1.20.LDO`

Since **2026-09-05** the pressure channel is published as real miniSEED beside the
geophone, so pressure and ground motion open in one ObsPy `Stream` with one set of time
handling. `server/env_mseed.py` builds it, `seismo-env-mseed.timer` runs every 10 min,
and the whole 43-day history is backfilled (28 s for the lot).

- **Location `20`** — location codes distinguish co-located acquisition *packages*, not
  sensors: `00` geophone + ADS1256, `10` reserved for the ADXL355, `20` this node. That
  is NSMP's own convention at NP.1835 1.6 km away, where a second digitizer package sits
  under location `2C` carrying its accelerometers **plus system temperature, voltage,
  current and clock quality, all at 1 sps**. Environmental and SOH channels in the feed
  is professional practice.
- **Channel `LDO`** — band `L` = 1 sps, instrument `D` = pressure, orientation `O` =
  outside. The standard microbarograph code; nothing invented.
- **Counts are centi-Pascals** (100 counts/Pa). Whole Pa would have thrown away the
  resolution the ×16 oversampling was turned on to get.
- **The response is not provisional.** The BMP280 is factory-calibrated in absolute Pa,
  so `LDO` is the first channel at this station with a *known* sensitivity — while
  `EHZ`'s f0 and ζ are still guesses waiting on the injector.

### The clock fit is piecewise, and the reason is measurable

miniSEED wants a regular grid; these samples are stamped by the host when USB bytes
arrive. So host-UTC is fitted against the CLUE's own monotonic clock, with the offset
taken from a **low percentile** of the residuals rather than the mean — USB delay is
one-sided, a row can only arrive *after* it was measured, and least squares would chase
that tail and put every sample systematically late.

A single straight line over one 7.2-hour run appeared to have **112 ms of jitter**.
Almost all of it was curvature: the crystal wandered **+6 to +59 ppm within the run**
(temperature-driven, on a board that measurably self-heats) and the residuals traced a
smooth +105/−7 ms arc rather than scattering. Refitted in 10-minute windows, the same
data gives **p95 jitter of 5 ms**. Every record is stamped from the resulting chain of
local anchors, so within one 100-second record the crystal cannot drift more than ~6 ms.

Verified against the raw CSV: **270 spot checks, zero unmatched** — every value appears
in the stream, and the host stamp slides cleanly from 0 to −1 samples across 7 hours as
the +35 ppm crystal is absorbed. The per-window ppm spread is logged rather than hidden;
it is a thermometer for the node.

This only became possible on 2026-09-05. Before the firmware fix, `time.monotonic()` had
decayed to 0.25 s resolution and 3.9 % of samples were being dropped — there was no clock
to fit. Those days convert too, and it shows: a pre-fix day lands in **~3,300 fragments**
with 866 ms of jitter, against **one unbroken 26,000-sample block** after. The backfill is
kept anyway; the fragmentation is the honest shape of that data.

## TODO — the rest of the channels

- Temperature and humidity as their own channels under `20`, following NSMP's lead —
  they belong in the feed, they just weren't the one with a question attached.
- The accelerometer: mean (tilt) and the new RMS envelope. Needs a decision about how to
  express a derived envelope as a SEED channel, which pressure didn't force.
- Then the actual question: **does pressure or tilt explain the 0.02–0.12 Hz undulation?**
  (and the slow DC-bias drift vs temperature). This is why the node exists — and now the
  pressure half of it is a `Stream` away.

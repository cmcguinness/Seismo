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

### MEASURED 2026-09-07, replacing the prediction — and the prediction was wrong

I predicted ~4.7× in the 0.02–0.12 Hz band (0.943 → ~0.20 Pa). Measured on a full
post-fix day against 41 pre-fix days:

| | pre-fix (41 days) | post-fix | gain |
|---|---|---|---|
| white floor near Nyquist | median 2.10 Pa/√Hz (1.58–2.24) | **1.22** | 1.76× |
| 0.02–0.12 Hz band RMS | median 0.938 Pa (0.891–1.065) | **0.746** | 1.31× |

The improvement is real — the post-fix day is below **all 41** pre-fix days on both
measures — but it is a third of what I claimed. The control matters here: pre-fix band
RMS varied only ±8 % across six weeks of different weather, and a quantity that barely
moves while the weather does was dominated by a constant, i.e. the floor.

**Why it stopped at 1.76×, measured rather than guessed.** Querying the chip over the
CircuitPython REPL: `ctrl_meas` = 0x54 (osrs_t ×2, osrs_p ×16, both as set) and `config`
= 0x00 (0.5 ms standby, IIR off, both as set). So the oversampling is real. Per-sample
noise is now 1.22 × √0.5 = **0.86 Pa**, but ~12 reads of ~1.3 Pa scatter should give
1.3/√12 = **0.38 Pa**. The missing part is not sensor noise:

    sqrt(0.86^2 - 0.38^2) = 0.77 Pa of REAL pressure fluctuation

correlated across the reads inside one tick, because it is genuine physics below 0.5 Hz,
so averaging cannot touch it. **The channel is now atmosphere-limited, not
sensor-limited** — the BMP280 contributes about 20 % of the remaining variance, and more
oversampling would buy almost nothing. Going lower means attacking the fluctuation
itself, which is exactly what real microbarographs do with a sealed reference volume and
a slow leak.

**Caveat on that split:** one barometer cannot prove which part is real. The definitive
test is two sensors side by side — coherent between them is atmosphere, incoherent is
sensor noise. Until that is run, the 0.38/0.77 division is an inference from the reported
within-tick scatter, not a measurement.

**An open bug found in the same query:** the driver reports `mode` = 1 (MODE_FORCE), not
the MODE_NORMAL the firmware sets, and the boot log said the assignment succeeded. In
FORCED mode every read triggers its own conversion and blocks ~43 ms, which is why
`n_press` sits at ~12/s and `n_acc` at ~250 rather than higher. It does NOT invalidate
the noise result — forced reads are independent conversions, which is what the
arithmetic above assumes — but the cause is not yet understood.

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

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
# seismo-env  mono_s,temp_C,press_hPa,humid_pct,ax_ms2,ay_ms2,az_ms2
741.06,29.33,1002.19,39.3,-0.863,5.250,-7.959
```

Self-correcting loop → even 1 Hz. Sensor reads are wrapped so one bad read can't kill the
loop. Blue NeoPixel blinks = alive.

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
reconnect loop survives unplug/reset; malformed lines are dropped. Runs as the
**`env-logger`** systemd service (`enabled`, `Restart=always`).

Deploy on pi4env: venv at `~/env_node/.venv` (`pip install pyserial`), copy `env_logger.py`
+ `env-logger.service` (install commands in the service file's header).

## TODO — pull to the pi5 + analyze

- A pi5-side rsync (like the seismic mirror) pulls `pi4env:~/env-data/` next to the seismic
  data, so the pressure/tilt series sits UTC-aligned beside the stream.
- Then the actual question: **does pressure or tilt explain the 0.02–0.12 Hz undulation?**
  (and the slow DC-bias drift vs temperature). This is why the node exists.

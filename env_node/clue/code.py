# SPDX-License-Identifier: MIT
"""code.py -- Seismo environmental node (Adafruit CLUE, CircuitPython).

Reads pressure / temperature / humidity / 3-axis acceleration ~once a second and
streams one CSV row per sample over USB serial. The row carries only the CLUE's
*monotonic* clock -- the USB host stamps the authoritative UTC on receipt (the CLUE
has no NTP/RTC), so the pressure/tilt series can be aligned against the seismic
stream.

The board is mounted FACE DOWN (sensors on the top side), so the TFT backlight is
turned OFF -- it lights nothing anyone can see and is a heat source millimetres from
the temp/humidity sensors (a sealed-case test plateaued several degrees above ambient,
dominated by on-board self-heat). Liveness is the blue NeoPixel heartbeat + the serial
stream the host logs.

Why these channels (all near the station, electrically isolated from acquisition):
  - PRESSURE (BMP280): couples to the sub-Hz seismic undulation; sampled ~1 Hz so
    it can be correlated against the 0.02-0.12 Hz band (Nyquist 0.25 Hz).
  - TILT, from the accelerometer's gravity vector (LSM6DS3): the leading suspect for
    that undulation is thermal SETTLING = ground tilt; this measures it directly.
  - TEMPERATURE / HUMIDITY (BMP280 / SHT31): the thermal-settling and moisture
    correlations.

Deploy: copy this file to CLUEPY/code.py (CircuitPython auto-runs it).
Serial CSV columns:  mono_s, temp_C, press_hPa, humid_pct, ax, ay, az   (SI units)
"""
import time

import board
from adafruit_clue import clue

SAMPLE_S = 1.0   # ~1 Hz -- fast enough for the 0.02-0.12 Hz undulation

# Board is face down: kill the backlight (no visible readout, less self-heat next to
# the sensors). Guarded so a firmware without a brightness-controllable display can't
# stop the node from logging.
try:
    board.DISPLAY.brightness = 0
except Exception as exc:
    print("# backlight off failed:", exc)

print("# seismo-env  mono_s,temp_C,press_hPa,humid_pct,ax_ms2,ay_ms2,az_ms2")

n = 0
while True:
    t0 = time.monotonic()
    n += 1
    try:
        temp = clue.temperature           # C     (BMP280)
        press = clue.pressure             # hPa   (BMP280)
        humid = clue.humidity             # %     (SHT31)
        ax, ay, az = clue.acceleration    # m/s^2 (LSM6DS3, 3-axis)
    except Exception as exc:              # never let one bad read kill the loop
        print("# read error:", exc)
        time.sleep(SAMPLE_S)
        continue

    # --- USB serial: one CSV row; the host prepends UTC on receipt ---
    # Raw ax/ay/az are logged so true tilt is computed in the mounted frame later.
    print("{:.2f},{:.2f},{:.2f},{:.1f},{:.3f},{:.3f},{:.3f}".format(
        t0, temp, press, humid, ax, ay, az))

    clue.pixel.fill((0, 0, 6) if n % 2 else (0, 0, 0))   # blue heartbeat = alive
    dt = SAMPLE_S - (time.monotonic() - t0)              # self-correct to an even ~1 Hz
    time.sleep(dt if dt > 0 else 0)

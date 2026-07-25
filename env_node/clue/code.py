# SPDX-License-Identifier: MIT
"""code.py -- Seismo environmental node (Adafruit CLUE, CircuitPython).

Reads pressure / temperature / humidity / 3-axis acceleration ~once a second,
shows them on the CLUE screen (so you can eyeball that it's alive), and streams one
CSV row per sample over USB serial. The row carries only the CLUE's *monotonic*
clock -- the USB host stamps the authoritative UTC on receipt (the CLUE has no
NTP/RTC), so the pressure/tilt series can be aligned against the seismic stream.

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
import math
import time

from adafruit_clue import clue

SAMPLE_S = 1.0   # ~1 Hz -- fast enough for the 0.02-0.12 Hz undulation

# On-screen readout. text_scale=2 is safe/readable on the 240x240; bump to 3 for bigger.
disp = clue.simple_text_display(
    title="Seismo Env Node", title_scale=2, text_scale=2,
    colors=(clue.CYAN, clue.WHITE, clue.WHITE, clue.YELLOW, clue.GREEN),
)

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

    # Tilt from horizontal: how far the board has tipped from flat (0 deg = flat,
    # 90 = on edge). |az| so it reads ~0 flat regardless of which way z points.
    # Display-only -- raw ax/ay/az are logged so true tilt is computed in the
    # mounted frame later.
    amag = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
    tilt = math.degrees(math.acos(min(1.0, abs(az) / amag)))

    # --- USB serial: one CSV row; the host prepends UTC on receipt ---
    print("{:.2f},{:.2f},{:.2f},{:.1f},{:.3f},{:.3f},{:.3f}".format(
        t0, temp, press, humid, ax, ay, az))

    # --- on-screen readout ---
    disp[0].text = "P {:.2f} hPa".format(press)
    disp[1].text = "T {:.1f} C".format(temp)
    disp[2].text = "H {:.1f} %".format(humid)
    disp[3].text = "tilt {:.2f} deg".format(tilt)
    disp[4].text = "sample #{}".format(n)
    disp.show()

    clue.pixel.fill((0, 0, 6) if n % 2 else (0, 0, 0))   # blue heartbeat = alive
    dt = SAMPLE_S - (time.monotonic() - t0)              # self-correct to an even ~1 Hz
    time.sleep(dt if dt > 0 else 0)

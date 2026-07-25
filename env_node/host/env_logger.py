#!/usr/bin/env python3
"""env_logger.py -- read the CLUE environmental node over USB serial, stamp UTC on
receipt, and append to daily CSV. Runs on the host (pi4env) under systemd.

The CLUE has no clock -- THIS host owns the authoritative UTC (NTP-kept), which is
what makes the pressure/tilt series alignable to the seismic stream. We log raw
ax/ay/az (not a derived tilt) so tilt is computed later in the mounted frame, with
both horizontal components kept.

Robust to unplug/reset: a reconnect loop reopens the port. Malformed/partial lines
are dropped. Daily files with a header; gaps + CLUE resets are derivable from the
utc + clue_mono_s columns.

Schema:  utc,clue_mono_s,temp_C,press_hPa,humid_pct,ax_ms2,ay_ms2,az_ms2
"""
import os
import time
from datetime import datetime, timezone

import serial

# Stable by-id path -> the CLUE specifically, survives re-enumeration (preferred
# over /dev/ttyACM0 which can renumber). Override with ENV_DEV.
DEV = os.environ.get(
    "ENV_DEV",
    "/dev/serial/by-id/usb-Adafruit_Industries_LLC_CLUE_nRF52840_Express_"
    "EAB0D1E5A045ECAA-if00")
DATADIR = os.environ.get("ENV_DATADIR", os.path.expanduser("~/env-data"))
HEADER = "utc,clue_mono_s,temp_C,press_hPa,humid_pct,ax_ms2,ay_ms2,az_ms2"
NFIELDS = 7                                    # fields the CLUE sends per row

os.makedirs(DATADIR, exist_ok=True)


def write_row(utc, fields):
    """Append one row to the current UTC day-file (creating it with a header)."""
    path = os.path.join(DATADIR, f"env-{utc:%Y-%m-%d}.csv")
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            f.write(HEADER + "\n")
        f.write(f"{utc.isoformat(timespec='milliseconds')},{','.join(fields)}\n")


def main():
    print(f"env_logger: {DEV} -> {DATADIR}", flush=True)
    while True:                                # reconnect loop (survives unplug/reset)
        try:
            ser = serial.Serial(DEV, 115200, timeout=2)
        except Exception as exc:
            print(f"open failed: {exc} -- retry in 3 s", flush=True)
            time.sleep(3)
            continue
        print("connected", flush=True)
        try:
            while True:
                line = ser.readline().decode("ascii", "replace").strip()
                if not line or line.startswith("#"):
                    continue
                fields = line.split(",")
                if len(fields) != NFIELDS:
                    continue                   # partial/garbled line
                try:                           # all fields must be numeric --
                    [float(x) for x in fields]  # drops CLUE reboot-banner text
                except ValueError:              # (banner has no commas, so it
                    continue                    # can pass the count check alone)
                write_row(datetime.now(timezone.utc), fields)
        except Exception as exc:
            print(f"serial lost: {exc} -- reopening", flush=True)
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(2)


if __name__ == "__main__":
    main()

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

Schema:  utc,clue_mono_s,temp_C,press_hPa,humid_pct,ax_ms2,ay_ms2,az_ms2,
         n_acc,ax_rms_ms2,ay_rms_ms2,az_rms_ms2,a_pk_ms2,n_press,p_sd_Pa

The CLUE sends either the ORIGINAL 7 fields or the WIDE 14 (burst-averaged, with the
accelerometer envelope and the pressure scatter -- see clue/code.py). Both are accepted
and both are written under the wide header, short rows padded with empty trailing
fields. That matters because the two firmwares can alternate across a CLUE reset or a
rollback, and a day-file gets exactly one header line: a superset schema keeps every
row in the same file readable by the same parser instead of splitting the series.
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
HEADER = ("utc,clue_mono_s,temp_C,press_hPa,humid_pct,ax_ms2,ay_ms2,az_ms2,"
          "n_acc,ax_rms_ms2,ay_rms_ms2,az_rms_ms2,a_pk_ms2,n_press,p_sd_Pa")
NFIELDS = 14                                   # wide row: burst mean + envelope
NFIELDS_LEGACY = 7                             # pre-2026-09-05 row: single samples

os.makedirs(DATADIR, exist_ok=True)


_checked = set()


def _retire_stale_header(path):
    """If a day-file was started under a different schema, set it aside.

    A day-file carries exactly one header line, so a schema change part-way through a
    UTC day would leave wide rows sitting under a narrow header -- silently misparsed
    by anything using DictReader. Rename the old file to `.v<n>.csv` (still matched by
    the env-*.csv glob, still self-describing via its own header) and start fresh.
    """
    try:
        with open(path) as f:
            if f.readline().strip() == HEADER:
                return
    except OSError:
        return
    stem = path[:-4] if path.endswith(".csv") else path
    for i in range(1, 100):
        alt = f"{stem}.v{i}.csv"
        if not os.path.exists(alt):
            os.rename(path, alt)
            print(f"schema change: {path} -> {alt}", flush=True)
            return


def write_row(utc, fields):
    """Append one row to the current UTC day-file (creating it with a header)."""
    path = os.path.join(DATADIR, f"env-{utc:%Y-%m-%d}.csv")
    if path not in _checked:                   # probe each day-file once, not per row
        _checked.add(path)
        if os.path.exists(path):
            _retire_stale_header(path)
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
                if len(fields) not in (NFIELDS, NFIELDS_LEGACY):
                    continue                   # partial/garbled line
                try:                           # all fields must be numeric --
                    [float(x) for x in fields]  # drops CLUE reboot-banner text
                except ValueError:              # (banner has no commas, so it
                    continue                    # can pass the count check alone)
                fields += [""] * (NFIELDS - len(fields))   # legacy row -> wide schema
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

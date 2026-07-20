#!/usr/bin/env python3
"""adc_diag.py — front-end bring-up check for the geophone differential read.

Run on the Pi (needs the ADS1256 + pigpiod). Three checks, in order:

  1. BIAS  — AIN0 and AIN1 vs AINCOM, single-ended. Expect ~1.6 V each (the
     100k/100k divider pulling the floating coil to mid-supply). A leg at 0 V
     or ~3.3 V means a bias resistor is open / swapped.
  2. RATE  — samples/sec actually sustained for the differential AIN0-AIN1
     read, both per-sample (read_oneshot, full re-sync each sample) and cyclic
     (read_continue, DRDY-paced). Tells us which read path the real sampler
     should use and whether a Pi 2B can hold 100 sps.
  3. LIVE  — rolling peak-to-peak of the differential channel in microvolts,
     with a bar, so you can watch the geophone respond to taps.

Usage:  python adc_diag.py            # gain from waveshare_config (GAIN_1)
"""
import signal
import time
import waveshare_config
from pipyadc import ADS1256
from pipyadc.ADS1256_definitions import *

# Translate SIGTERM into KeyboardInterrupt so the finally: below always runs and
# releases the ADC -- a killed run must never leave the chip locked.
def _on_sigterm(signum, frame):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, _on_sigterm)

DIFF = POS_AIN0 | NEG_AIN1       # geophone across AIN0 (+) / AIN1 (-)
SE0 = POS_AIN0 | NEG_AINCOM      # AIN0 vs analog ground (bias check)
SE1 = POS_AIN1 | NEG_AINCOM      # AIN1 vs analog ground (bias check)

N_BENCH = 500
WLEN = 50                        # live window (~0.5 s at 100 sps)


def main() -> None:
    ads = ADS1256(waveshare_config)
    try:
        ads.drate = DRATE_100
        ads.cal_self()
        vpd = ads.v_per_digit

        # --- 1. bias check ---
        v0 = ads.read_oneshot(SE0) * vpd
        v1 = ads.read_oneshot(SE1) * vpd
        d = ads.read_oneshot(DIFF) * vpd
        print(f"BIAS  AIN0={v0:+.3f} V   AIN1={v1:+.3f} V   (want ~1.6 V each)")
        print(f"DIFF  AIN0-AIN1 = {d * 1e3:+.3f} mV  (small DC offset ok)")

        # --- 2. rate benchmark ---
        t0 = time.time()
        for _ in range(N_BENCH):
            ads.read_oneshot(DIFF)
        r_one = N_BENCH / (time.time() - t0)

        buf = [0]
        ads.read_oneshot(DIFF)                       # prime prior-conversion data
        t0 = time.time()
        for _ in range(N_BENCH):
            ads.read_continue([DIFF], buf)
        r_cont = N_BENCH / (time.time() - t0)
        print(f"RATE  oneshot={r_one:6.1f} sps   continue={r_cont:6.1f} sps  "
              f"(DRATE_100 nominal)")

        # --- 3. live peak-to-peak monitor ---
        print("\nLIVE  tap the geophone.  Ctrl-C to stop.")
        win = []
        while True:
            win.append(ads.read_continue([DIFF], buf)[0] * vpd)
            if len(win) >= WLEN:
                pp = (max(win) - min(win)) * 1e6      # microvolts
                bar = "#" * min(60, int(pp / 20))
                print(f"pp = {pp:9.1f} uV  {bar:<60}", end="\r", flush=True)
                win = []
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        ads.stop_close_all()


if __name__ == "__main__":
    main()

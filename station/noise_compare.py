#!/usr/bin/env python3
"""noise_compare.py — measure the differential noise floor at several ADS1256
data rates, to see whether 60 Hz mains is folding into our floor.

Diagnostic logic:
  - Lower data rates give the sinc filter a narrower bandwidth => lower noise
    regardless of source (more averaging).
  - BUT the ADS1256's filter also puts a NOTCH at the data rate and its
    multiples. DRATE_60 notches 60 Hz (US mains); DRATE_50 notches 50 Hz
    (does NOT reject 60 Hz).
  => If 60 drops much more than 50, mains is a real contributor and DRATE_60
     is a free win. If 60 ~= 50, the gain is just bandwidth, not mains.

Reads the AIN0-AIN1 differential channel at gain 64 (our operating point).
Run with the shunt-socket jumper IN (shorted) for the pure electronics floor,
or out for the operating floor -- just keep it the same for the whole run.
"""
import os
import signal
import statistics

import waveshare_config
from pipyadc import ADS1256
from pipyadc.ADS1256_definitions import *

DIFF = POS_AIN0 | NEG_AIN1
GAIN = int(os.environ.get("SEISMO_GAIN", "64"))

# (label, DRATE const, samples). Fewer samples at low rates so it doesn't crawl.
RATES = [
    ("100 sps", DRATE_100, 400),
    (" 60 sps (60Hz notch)", DRATE_60, 300),
    (" 50 sps (50Hz notch)", DRATE_50, 300),
    (" 30 sps", DRATE_30, 200),
    (" 10 sps", DRATE_10, 120),
]


def measure(ads, drate, n, vpd):
    ads.drate = drate
    ads.cal_self()
    buf = [0]
    ads.read_oneshot(DIFF)                 # prime the cyclic read
    samples = [ads.read_continue([DIFF], buf)[0] * vpd * 1e6 for _ in range(n)]
    rms = statistics.pstdev(samples)       # ~input-referred noise, uV RMS
    pp = max(samples) - min(samples)
    return rms, pp


def main():
    def _term(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _term)

    waveshare_config.adcon = CLKOUT_OFF | SDCS_OFF | (GAIN.bit_length() - 1)
    ads = ADS1256(waveshare_config)
    try:
        vpd = ads.v_per_digit
        print(f"noise floor vs data rate  (gain {GAIN}, differential AIN0-AIN1)\n")
        print(f"{'rate':<22} {'RMS uV':>8} {'pp uV':>8}")
        print("-" * 40)
        for label, drate, n in RATES:
            rms, pp = measure(ads, drate, n, vpd)
            print(f"{label:<22} {rms:8.2f} {pp:8.1f}")
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        ads.stop_close_all()


if __name__ == "__main__":
    main()

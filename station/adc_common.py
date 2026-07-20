"""adc_common.py — shared ADS1256 setup for the station tools.

One place for the two things every tool needs: opening the ADC at a chosen PGA
gain + data rate, and the differential channel constant. Keeps the gain
workaround (below) and rate table from being copy-pasted into every script.
"""
import time

import waveshare_config
from pipyadc import ADS1256
from pipyadc.ADS1256_definitions import *

DIFF = POS_AIN0 | NEG_AIN1        # geophone across AIN0 (+) / AIN1 (-)

# Data-rate name -> ADS1256 DRATE register code, for the rates we care about.
_DRATE = {
    500: DRATE_500, 100: DRATE_100, 60: DRATE_60,
    50: DRATE_50, 30: DRATE_30, 25: DRATE_25, 10: DRATE_10,
}
_GAINS = (1, 2, 4, 8, 16, 32, 64)


def open_ads(gain: int = 64, drate_sps: int = 60) -> ADS1256:
    """Return a self-calibrated ADS1256 at the given PGA gain and data rate.

    Gain is applied via the config's ADCON register, NOT the ads.pga_gain
    setter: the installed PiPyADC's pga_gain/adcon setters are broken (they read
    an uninitialized self._status). __init__ writes conf.adcon straight to the
    register, sidestepping that. Caller must ads.stop_close_all() when done.
    """
    if gain not in _GAINS:
        raise ValueError(f"gain must be one of {_GAINS} (got {gain})")
    if drate_sps not in _DRATE:
        raise ValueError(f"drate_sps must be one of {sorted(_DRATE)} (got {drate_sps})")
    waveshare_config.adcon = CLKOUT_OFF | SDCS_OFF | (gain.bit_length() - 1)
    ads = ADS1256(waveshare_config)
    ads.drate = _DRATE[drate_sps]
    ads.cal_self()
    return ads


def measure_rate(ads, n: int = 200) -> float:
    """Measure the actually-sustained differential sample rate (sps).

    The read path re-syncs every sample, so the real rate sits a few percent
    below the DRATE nominal and is mildly load-dependent -- so we measure it
    rather than trust the nominal. Also primes the cyclic read as a side effect.
    """
    buf = [0]
    ads.read_oneshot(DIFF)
    t0 = time.time()
    for _ in range(n):
        ads.read_continue([DIFF], buf)
    return n / (time.time() - t0)

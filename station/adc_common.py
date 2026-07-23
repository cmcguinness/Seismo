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


def _pin_reset(reset_pin: int = None) -> None:
    """Pulse the ADS1256 RESET pin before we try to talk to it.

    The driver's own CHIP_HARD_RESET_ON_START happens AFTER it verifies the chip ID,
    so a chip left mid-stream (e.g. an RDATAC session that died without sending
    SDATAC) fails construction with "Received wrong chip ID" and can never
    self-recover. Pulsing RESET first makes every tool startup-robust regardless of
    how the previous process exited. Best-effort: if pigpio isn't reachable, let the
    driver report the real problem."""
    import pigpio

    pin = reset_pin if reset_pin is not None else getattr(waveshare_config, "RESET_PIN", None)
    if pin is None:
        return
    try:
        pi = pigpio.pi()
        if not pi.connected:
            return
        pi.set_mode(pin, pigpio.OUTPUT)
        pi.write(pin, 1)
        time.sleep(0.01)
        pi.write(pin, 0)
        time.sleep(0.01)
        pi.write(pin, 1)
        time.sleep(0.30)          # t_16 + oscillator/PLL settling
        pi.stop()
    except Exception:
        pass


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
    _pin_reset()                      # recover a chip left mid-stream by a dead run
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

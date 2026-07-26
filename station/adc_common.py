"""adc_common.py — shared ADS1256 setup for the station tools.

One place for the two things every tool needs: opening the ADC at a chosen PGA
gain + data rate, and the differential channel constant. Keeps the gain
workaround (below) and rate table from being copy-pasted into every script.
"""
import os
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


# Why any of this exists: the driver's own reset (hard or soft) runs AFTER
# check_chip_id(), so a chip left mid-stream -- an RDATAC session that died without
# sending SDATAC -- answers the ID read with conversion data and construction fails
# with "Received wrong chip ID", forever. Something has to put the chip in a known
# state BEFORE the driver opens it.
#
# That used to be a RESET-pin pulse. It is now an SPI command sequence, because the
# pin is not universal: bare ADS1256 breakouts (e.g. the LC Tech ADS1256_V1.1) bring
# out only SCLK/DIN/DOUT/CS/DRDY/PDWN and leave RESET on the die. SDATAC + RESET over
# SPI works on any board and drops a GPIO dependency. Set SEISMO_RESET_PIN=1 to also
# pulse the pin (belt and braces on hardware that has one).
RESET_SETTLE_S = 0.30             # t_16 + oscillator/PLL settling after a reset

# pigpio SPI flags, copied from PiPyADC's _configure_spi: mode 1 (CPOL=0, CPHA=1)
# plus the uuu bits that stop pigpio driving CE0/1/2 -- chip select is software, on
# CS_PIN. Must match the driver or the pre-open reset talks to the chip differently
# than the driver will.
_SPI_FLAGS = 0b0000000000000011100001


def _soft_reset() -> bool:
    """Put the ADS1256 in a known state over SPI, before the driver opens it.

    SDATAC first (twice, with CS cycled): it is the documented exit from RDATAC, and
    a single one CAN be swallowed if it lands mid-frame -- which is exactly the state
    we are recovering from. Then RESET (0xFE) to return the registers to defaults.

    Returns True if the sequence was sent. Best-effort: on any failure return False
    and let the driver report the real problem.
    """
    import pigpio

    cfg = waveshare_config
    pi = spi = None
    try:
        pi = pigpio.pi()
        if not pi.connected:
            return False
        cs = getattr(cfg, "CS_PIN", None)
        if cs is not None:
            pi.set_mode(cs, pigpio.OUTPUT)
            pi.write(cs, 1)
        flags = _SPI_FLAGS | (0b100000000 if getattr(cfg, "SPI_BUS", 0) == 1 else 0)
        spi = pi.spi_open(cfg.SPI_CHANNEL, cfg.SPI_FREQUENCY, flags)

        def cmd(byte):
            if cs is not None:
                pi.write(cs, 0)
            pi.spi_write(spi, bytes([byte]))
            time.sleep(0.002)
            if cs is not None:
                pi.write(cs, 1)
            time.sleep(0.001)

        cmd(0x0F)                 # SDATAC -- stop read-data-continuous
        cmd(0x0F)                 # again: the first can be eaten mid-frame
        cmd(0xFE)                 # RESET -- registers back to power-up defaults
        time.sleep(RESET_SETTLE_S)
        return True
    except Exception:
        return False
    finally:
        try:
            if spi is not None:
                pi.spi_close(spi)
        except Exception:
            pass
        try:
            if pi is not None:
                pi.stop()
        except Exception:
            pass


def _pin_reset(reset_pin: int = None) -> None:
    """Pulse the ADS1256 RESET pin. Only used when SEISMO_RESET_PIN=1 -- kept because
    a board that HAS the pin can still use it, and it is the one recovery that works
    when the chip has stopped answering SPI entirely."""
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
        time.sleep(RESET_SETTLE_S)
        pi.stop()
    except Exception:
        pass


def reset_adc() -> None:
    """Bring the ADS1256 to a known state before the driver opens it."""
    _soft_reset()
    if os.environ.get("SEISMO_RESET_PIN", "0") == "1":
        _pin_reset()


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
    reset_adc()                       # recover a chip left mid-stream by a dead run
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

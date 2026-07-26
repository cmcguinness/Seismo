"""waveshare_config.py — our copy of the PiPyADC hardware config for the
Waveshare High-Precision AD/DA board (ADS1256) on the Pi 2B.

Owned by the project (not the pip package) so gain / data-rate / reference are
version-controlled with the station code. Values below are the validated
bring-up config (Chip ID 3, VCC+VREF jumpers on 3V3 -> effective v_ref 2.5 V,
confirmed by a AA cell reading 1.29 V at gain 1).

Change `gain_flags` here to raise sensitivity (GAIN_1 for taps/first-light;
GAIN_64 for weak ambient motion). `drate` is set explicitly by the samplers,
so the value here is only the power-on default.
"""
import logging
from typing import Literal
from pipyadc.ADS1256_definitions import *

LOGLEVEL = logging.WARNING

# --- SPI / GPIO wiring of the Waveshare board (do not change) ---
SPI_BUS: int = 0
SPI_CHANNEL: Literal[0, 1, 2] = 0
SPI_FREQUENCY: Literal[976563, 1953125] = 976563
CHIP_HARD_RESET_ON_START: bool = False  # the driver's own post-ID reset is now the
                                       # SOFTWARE one (CMD_RESET over SPI). We no
                                       # longer depend on the RESET pin at all:
                                       # adc_common.reset_adc() has already put the
                                       # chip in a known state BEFORE construction,
                                       # and bare ADS1256 breakouts don't break the
                                       # pin out. Set SEISMO_RESET_PIN=1 to also
                                       # pulse it on hardware that has one.
CHIP_ID: int = 3
CHIP_SELECT_GPIOS_INITIALIZE: tuple[int, ...] = (22, 23)
CS_PIN: int = 22
DRDY_PIN: int = 17
RESET_PIN: int = 18
PDWN_PIN: int = 27
DRDY_TIMEOUT: float = 2.0
DRDY_DELAY: float = 0.000001
CLKIN_FREQUENCY: int = 7680000

# --- ADC reference / analog config ---
v_ref: float = 2.5                     # effective VREF (validated); sets volt scaling
gain_flags: int = GAIN_1               # GAIN_1 first-light; GAIN_64 for weak motion
status: int = 0x00                     # input buffer OFF. With AVDD=3.3V the buffered
                                       # common-mode range is only 0..~1.3V, but our
                                       # mid-supply bias is ~1.65V -> buffer would clip.
                                       # Buffer off gives full 0..AVDD range; our source
                                       # impedance is ~385R (coil) so the buffer's high
                                       # Zin buys us nothing here anyway.
mux: int = POS_AIN0 | NEG_AINCOM       # power-on mux (samplers override)
adcon: int = CLKOUT_OFF | SDCS_OFF | gain_flags
drate: int = DRATE_100                 # power-on data rate (samplers override).
                                       # 100 sps epoch (2026-07-25): a back-to-back
                                       # RDATAC measurement on this hardware REVERSED the
                                       # old bring-up call -- 100 sps is LOWER noise in
                                       # the quake band than 60 (1-15 Hz 2.74 vs 3.99 µV,
                                       # 3-15 Hz 2.62 vs 3.86) and RDATAC sustains it
                                       # (99.91 sps, 5 glitches/90 s; the old ~92 sps
                                       # ceiling was the legacy SYNC path, not RDATAC).
                                       # Tradeoff: 60 Hz mains no longer lands on a sinc
                                       # notch (aliases to 40 Hz, above band -> notch in
                                       # post). Old note: 60 sps measured 1.17 µV vs 2.0
                                       # @100 at bring-up -- superseded by the above.
gpio: int = 0x00

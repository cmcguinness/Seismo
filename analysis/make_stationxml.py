#!/usr/bin/env python3
"""make_stationxml.py — emit a PROVISIONAL StationXML response for SS.OAKM1.00.EHZ.

⚠️ PROVISIONAL. Two of the three parameters are guesses, and they are labelled as such
in the file itself. Do not publish amplitudes from this without saying so.

  f0    4.5 Hz   NAMEPLATE (LGT-4.5, spec 4.5 +-0.5). response_fit.py could not
                 distinguish 2.5-4.5 Hz from the data -- it excludes a corner above
                 ~5 Hz and nothing more -- so nameplate is the honest choice.
  zeta  0.6      VENDOR SPEC (specification.md: "damping ~0.6"). response_fit.py put it
                 somewhere in 0.39-0.70 per anchor, which straddles this. No shunt is
                 fitted, so this is the element's own damping.
  S     9.0      MEASURED, and the one parameter that is not a guess: refstation.py
        V/(m/s)  against NP.1835, four anchors, median 3.20x below the 28.8 nameplate.

The chain is short enough to model exactly otherwise. There is no analog gain and no
analog filtering on the interface board -- the PGA and input buffer are inside the
ADS1256 -- and no shunt is fitted, so the whole response is:

  stage 1  ground velocity -> volts   two zeros at the origin, one conjugate pole pair
  stage 2  volts -> counts            2*2.5/(64*(2^23-1)) V/count, exact from the datasheet

NOT MODELLED: the ADS1256's decimation filter, which shapes the last octave below
Nyquist. Fine for the 1-15 Hz work this station actually does; it matters if anyone ever
looks near 50 Hz.

Replace f0/zeta with the bench ring-down when it exists (BACKLOG: coil reciprocity).

    python analysis/make_stationxml.py            # writes station/SS.OAKM1.xml
"""
import datetime

import numpy as np
from obspy import UTCDateTime
from obspy.core.inventory import (Channel, Equipment, Inventory, Network, Response,
                                  Site, Station)
from obspy.core.inventory.response import (CoefficientsTypeResponseStage,
                                           InstrumentSensitivity,
                                           PolesZerosResponseStage)

# --- the three parameters -----------------------------------------------------------
F0 = 4.5            # Hz   nameplate; see the header
ZETA = 0.6          # -    vendor spec; see the header
SENS_V_PER_MS = 9.0 # V/(m/s)  MEASURED (refstation.py, 4 anchors)

# --- exact, from the datasheet ------------------------------------------------------
VREF, PGA, BITS = 2.5, 64, 23
# The ADS1256's full-scale range is +-2.VREF/PGA, not +-VREF/PGA -- the factor of two is
# easy to drop and puts every amplitude out by 2x. This matches UV_PER_COUNT in
# server/detector.py and station/recorder.py, which is the definition the data was
# recorded under: 2*2.5/(64*(2**23-1)) volts per count.
COUNTS_PER_VOLT = (2 ** BITS - 1) / (2 * VREF / PGA)
FS = 100.0
NORM_F = 15.0       # normalisation frequency: flat band, well above the corner

LAT, LON, ELEV_M = 38.451817, -122.621049, 128.3     # as registered with the ISC
START = UTCDateTime("2026-08-30T15:37:00")            # the EHZ identity epoch


def paz():
    """Moving-coil geophone: velocity in, volts out. Two zeros at the origin and a
    conjugate pole pair at -zeta.w0 +- i.w0.sqrt(1-zeta^2)."""
    w0 = 2 * np.pi * F0
    wd = w0 * np.sqrt(1 - ZETA ** 2)
    return ([0j, 0j], [complex(-ZETA * w0, wd), complex(-ZETA * w0, -wd)])


def main():
    zeros, poles = paz()
    total = SENS_V_PER_MS * COUNTS_PER_VOLT
    # TWO stages. Only modelling the sensor leaves the response in V/(m/s) while the
    # advertised sensitivity is counts/(m/s), which is what evalresp complains about.
    sensor = PolesZerosResponseStage(
        stage_sequence_number=1, stage_gain=SENS_V_PER_MS,
        stage_gain_frequency=NORM_F, input_units="M/S", output_units="V",
        pz_transfer_function_type="LAPLACE (RADIANS/SECOND)",
        normalization_frequency=NORM_F, zeros=zeros, poles=poles,
        normalization_factor=1.0, name="LGT-4.5 geophone")
    # renormalise A0 so the PZ block is unity at NORM_F
    w = 2j * np.pi * NORM_F
    h = np.prod([w - z for z in zeros]) / np.prod([w - p for p in poles])
    sensor.normalization_factor = float(1.0 / np.abs(h))
    digitizer = CoefficientsTypeResponseStage(
        stage_sequence_number=2, stage_gain=COUNTS_PER_VOLT,
        stage_gain_frequency=NORM_F, input_units="V", output_units="COUNTS",
        cf_transfer_function_type="DIGITAL", numerator=[1.0], denominator=[],
        decimation_input_sample_rate=FS, decimation_factor=1, decimation_offset=0,
        decimation_delay=0.0, decimation_correction=0.0, name="ADS1256")
    resp = Response(
        instrument_sensitivity=InstrumentSensitivity(
            value=total, frequency=NORM_F, input_units="M/S", output_units="COUNTS"),
        response_stages=[sensor, digitizer])

    cha = Channel(
        code="EHZ", location_code="00", latitude=LAT, longitude=LON,
        elevation=ELEV_M, depth=0.0, azimuth=0.0, dip=-90.0,
        sample_rate=FS, start_date=START, response=resp,
        sensor=Equipment(type="Geophone", description=(
            f"LGT-4.5/EG-4.5-II class, 4.5 Hz vertical, 375 ohm coil, no shunt. "
            f"PROVISIONAL response: f0={F0} Hz nameplate, zeta={ZETA} vendor spec, "
            f"sensitivity {SENS_V_PER_MS} V/(m/s) measured vs NP.1835")),
        data_logger=Equipment(type="Digitizer", description=(
            f"TI ADS1256, 24-bit, PGA x{PGA}, Vref {VREF} V, {FS:g} sps "
            f"({COUNTS_PER_VOLT:.6g} counts/V, exact)")))

    sta = Station(code="OAKM1", latitude=LAT, longitude=LON, elevation=ELEV_M,
                  channels=[cha], start_date=UTCDateTime("2026-07-20"),
                  site=Site(name="Oakmont, Santa Rosa, CA, USA"))
    inv = Inventory(networks=[Network(code="SS", stations=[sta],
                                      description="FDSN single-station code")],
                    source="Seismo (C. McGuinness) -- PROVISIONAL response")
    out = "station/SS.OAKM1.xml"
    inv.write(out, format="STATIONXML")

    print(f"wrote {out}\n")
    print(f"  f0 {F0} Hz (nameplate)   zeta {ZETA} (vendor spec)   "
          f"sensitivity {SENS_V_PER_MS} V/(m/s) (measured)")
    print(f"  digitiser {COUNTS_PER_VOLT:.6g} counts/V (exact)")
    print(f"  total {total:.4g} counts/(m/s) at {NORM_F:g} Hz\n")
    print("  amplitude response, counts per (m/s):")
    for f in (0.5, 1, 2, 3, 4.5, 6, 10, 15, 30):
        a = float(np.abs(resp.get_evalresp_response_for_frequencies(
            np.array([f], dtype=np.float64))[0]))
        print(f"    {f:5.1f} Hz  {a:12.4g}   {a/total:6.3f} of flat-band"
              + ("   <- corner" if abs(f - F0) < 0.01 else ""))


if __name__ == "__main__":
    main()

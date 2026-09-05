# SPDX-License-Identifier: MIT
"""code.py -- Seismo environmental node (Adafruit CLUE, CircuitPython).

Streams one CSV row per second over USB serial; the USB host stamps the authoritative
UTC on receipt (the CLUE has no NTP/RTC), so the series aligns to the seismic stream.

Within each 1 s tick this now BURSTS the sensors instead of taking one reading:

  - the accelerometer is read as fast as CircuitPython manages (~100/s), and the tick
    reports the MEAN (tilt, as before) plus the per-axis RMS and the peak deviation --
    an envelope detector rather than a single aliased sample;
  - the barometer is read at its own conversion limit (~20/s at x16 oversampling) and
    the tick reports the MEAN plus the scatter, in Pa.

WHY THE ENVELOPE. On 2026-09-03 the M3.3 under Larkfield-Wikiup (13.3 km) showed up in
this node as five consecutive large sample-to-sample changes on ay -- the alternating-sign
signature of 3-10 Hz ground motion aliased onto a 1 sps sampler. It was the largest ay
excursion of the whole 43-day archive outside of days when somebody was handling the
rig, and it landed 5.9 s after origin, in the S window. That was luck: one sample
happened to fall during the shaking. Averaging N reads pulls the AMPLITUDE ESTIMATE's
noise down by sqrt(N), so a ~100-read tick moves the floor from ~0.007 m/s^2 to
~7e-4 m/s^2 and the same event sits ~13x above it instead of ~1.5x.

This is NOT a seismometer and must not be read as one -- the LSM6DS33's measured
per-sample noise (0.0070 m/s^2 on ay, straight out of the archive, and within 10% of
its 90 ug/sqrt(Hz) datasheet figure) is ~1000x above the geophone's equivalent floor.
It detects what you can feel. The ADXL355 strong-motion node is the real accelerometer.

WHY THE RUNNING SUMS ARE OFFSET. CircuitPython's floats here are 32-bit (~7 decimal
digits). Accumulating sum-of-squares of raw pressure (~1000 hPa, so p^2 ~ 1.0e6) and
then taking sumsq/n - mean^2 subtracts two numbers that agree to seven digits: the
variance is destroyed by cancellation. The first flash of this firmware printed a
"scatter" of 0.5 hPa on a signal that moved 0.002 hPa between ticks, quantised to
multiples of the float32 ulp -- a textbook symptom. Both accumulators therefore run on
deviations from a reference (the previous tick's mean), where the squares are ~1e-4
instead of ~1e6 and there is nothing to cancel. The same trap applies to the
accelerometer: az ~ 9.81, az^2 ~ 96, and the RMS being measured is ~0.01.

WHY monotonic_ns. CircuitPython on the nRF52840 uses 32-bit floats, so time.monotonic()
loses resolution as uptime grows: at 40 days the ulp is 0.25 s and the old
self-correcting sleep was computing its delta from a quantised clock. Measured cost:
mean interval 1.040 s and 3,334 samples lost per day (3.9%), host dt ranging
0.46-1.53 s. time.monotonic_ns() is an exact integer and fixes both the pacing and the
reported timestamp (printed from integer arithmetic, never through a float).

The board is mounted FACE DOWN (sensors on the top side), so the TFT backlight is off --
it lights nothing anyone can see and is a heat source millimetres from the temp/humidity
sensors. Liveness is the blue NeoPixel heartbeat + the serial stream itself.

Channels (all near the station, electrically isolated from acquisition):
  - PRESSURE (BMP280): couples to the sub-Hz seismic undulation; the 0.02-0.12 Hz band.
  - TILT, from the accelerometer's gravity vector (LSM6DS33): thermal SETTLING = ground
    tilt is the leading suspect for that undulation; this measures it directly.
  - TEMPERATURE / HUMIDITY (BMP280 / SHT31): thermal-settling and moisture correlations.
    BMP280 temp is the board's own self-heat, roughly constant -- use DELTAS ONLY.

Deploy: copy this file to CLUEPY/code.py (CircuitPython auto-runs it). Remotely, from
the USB host: sudo mount /dev/sda1 /mnt/clue && cp code.py /mnt/clue/ && sudo umount.

Serial CSV columns (the host prepends utc):
  mono_s, temp_C, press_hPa, humid_pct, ax_ms2, ay_ms2, az_ms2,
  n_acc, ax_rms_ms2, ay_rms_ms2, az_rms_ms2, a_pk_ms2, n_press, p_sd_Pa
"""
import math
import time

import board
from adafruit_clue import clue

TICK_NS = 1_000_000_000        # one row per second, as before
PRESS_EVERY_NS = 50_000_000    # BMP280 at x16 converts in ~43 ms; don't outrun it
RESERVE_NS = 80_000_000        # leave the tail of the tick for humidity + the print
ACC_ODR = "RATE_104_HZ"        # measured optimum -- see the ODR note below

# Board is face down: kill the backlight (no visible readout, less self-heat next to
# the sensors). Guarded so a firmware without a brightness-controllable display can't
# stop the node from logging.
try:
    board.DISPLAY.brightness = 0
except Exception as exc:
    print("# backlight off failed:", exc)


def _find(module, base_name, *names):
    """Return clue's own driver instance for a chip, or None.

    We reconfigure and read the objects adafruit_clue already built rather than making
    our own: a second driver instance on the same I2C address would fight over the
    config registers (the BMP280 driver rewrites ctrl_meas on every forced read).
    Attribute names differ between library versions, so try the known ones, then fall
    back to scanning by type.
    """
    base = getattr(module, base_name, None)
    for n in names:
        o = getattr(clue, n, None)
        if o is not None and (base is None or isinstance(o, base)):
            return o
    if base is not None:
        try:
            for o in clue.__dict__.values():
                if isinstance(o, base):
                    return o
        except Exception:
            pass
    return None


# --- barometer: raise the oversampling (this is the whole point of the burst) --------
# Logged pressure was quantised at exactly 1 Pa while the sensor floor measured
# ~2.3 Pa/sqrt(Hz) -- real headroom thrown away in the format string. x16 oversampling
# plus a ~20-read average per tick goes after the rest of it.
#
# NOTE the on-chip IIR filter is deliberately DISABLED. Coefficient 16 would put a
# ~0.08 Hz corner right inside the 0.02-0.12 Hz undulation band this node exists to
# measure. Averaging in software is a boxcar: it anti-aliases the HVAC lines without
# eating the signal.
_bmp = None


def _const(mod, *names):
    """First constant that exists, by name. Library versions rename these."""
    for n in names:
        v = getattr(mod, n, None)
        if v is not None:
            return v
    raise AttributeError("none of {}".format(names))


try:
    import adafruit_bmp280
    _bmp = _find(adafruit_bmp280, "Adafruit_BMP280", "_bmp280", "_pressure", "_baro")
    if _bmp is None:
        print("# bmp280 not found -- default oversampling")
    else:
        # Applied one at a time and reported: the first flash of this firmware set all
        # five in a single try block, hit a constant that didn't exist on the fourth
        # (STANDBY_TC_1), and silently left the chip in FORCED mode -- where every read
        # BLOCKS for a full ~40 ms conversion. That alone cost more than half the tick
        # and dragged n_acc down to ~40. A partial config that looks like a working one
        # is worse than a loud failure, so each setting speaks for itself. `mode` is
        # last on purpose: config takes effect cleanly while the chip is still asleep.
        for _attr, _names in (
                ("overscan_pressure", ("OVERSCAN_X16",)),
                ("overscan_temperature", ("OVERSCAN_X2",)),
                ("iir_filter", ("IIR_FILTER_DISABLE",)),
                ("standby_period", ("STANDBY_TC_0_5", "STANDBY_TC_1", "STANDBY_TC_0P5")),
                ("mode", ("MODE_NORMAL",))):
            try:
                setattr(_bmp, _attr, _const(adafruit_bmp280, *_names))
                print("# bmp280", _attr, "ok")
            except Exception as exc:
                print("# bmp280", _attr, "FAILED:", exc)
except Exception as exc:                # a missing library must not stop the node
    print("# bmp280 config failed:", exc)
    _bmp = None


# --- accelerometer: bypass the adafruit_clue property so the burst can run fast ------
_lsm = None
try:
    import adafruit_lsm6ds
    _lsm = _find(adafruit_lsm6ds, "LSM6DS", "_lsm6ds33", "_lsm6ds", "_accelerometer")
    print("# lsm6ds fast path" if _lsm else "# lsm6ds not found -- via clue.acceleration")
    if _lsm is not None:
        # ODR. Pinned explicitly at the value the driver happens to default to, because
        # it was MEASURED to be the best one -- not inherited by accident.
        #
        # The instinct is to raise it so that every one of the ~250 reads/s is a fresh
        # sample. That is backwards: the chip's noise is flat in density, so per-sample
        # sigma grows as sqrt(ODR), while the reads that turn into independent samples
        # are capped by the loop at ~250/s. What matters is how well a small added
        # signal moves the reported RMS out of its own tick-to-tick scatter, i.e.
        # 1 / (2 * level * scatter). Swept live, 91 ticks each, ay (the axis that caught
        # the M3.3):
        #
        #     ODR      level     scatter    relative detectability
        #      52 Hz   0.00863   0.00109      53k
        #     104 Hz   0.00926   0.00077      70k     <-- best
        #     208 Hz   0.01283   0.00084      46k
        #     416 Hz   0.01792   0.00110      25k     (from the 19-tick first pass)
        #
        # 52 Hz wins on az and ties on ax, so the axes disagree at the 1.3x level; 104 Hz
        # breaks the tie because Nyquist 52 Hz keeps the 35-50 Hz energy that analysis/
        # audible.py found in this same M3.3 instead of folding it back into the band.
        # Both extremes are clearly worse: 416 Hz costs a factor of ~3.
        try:
            _rate = getattr(adafruit_lsm6ds, "Rate", None)
            print("# lsm6ds ODR was", _lsm.accelerometer_data_rate)
            if _rate is not None:
                _lsm.accelerometer_data_rate = _const(_rate, ACC_ODR)
                print("# lsm6ds ODR now", _lsm.accelerometer_data_rate, ACC_ODR)
        except Exception as exc:
            print("# lsm6ds ODR unchanged:", exc)
except Exception as exc:
    print("# lsm6ds lookup failed:", exc)
    _lsm = None


def read_accel():
    return _lsm.acceleration if _lsm is not None else clue.acceleration


def read_press():
    return _bmp.pressure if _bmp is not None else clue.pressure


def _rms(sumsq, mean, k):
    """RMS about the mean from running sums -- no per-tick sample buffer."""
    v = sumsq / k - mean * mean           # can go slightly negative on rounding
    return math.sqrt(v) if v > 0 else 0.0


print("# seismo-env  mono_s,temp_C,press_hPa,humid_pct,ax_ms2,ay_ms2,az_ms2,"
      "n_acc,ax_rms_ms2,ay_rms_ms2,az_rms_ms2,a_pk_ms2,n_press,p_sd_Pa")

# Both accumulators run on deviations from the PREVIOUS tick's mean, not on raw values:
# in 32-bit floats, sumsq/n - mean^2 on raw pressure cancels away the entire variance
# (see the module docstring). The reference doubles as the peak-deviation baseline --
# the true mean of a burst isn't known until the burst is over, and the gravity vector
# and the barometer both drift on the scale of hours, not seconds.
ref = (0.0, 0.0, 9.81)
pref = None
n = 0
next_tick = time.monotonic_ns() + TICK_NS

while True:
    deadline = next_tick - RESERVE_NS
    n += 1

    rx0, ry0, rz0 = ref
    sx = sy = sz = 0.0
    qx = qy = qz = 0.0
    pk = 0.0
    n_acc = 0
    sp = qp = 0.0
    n_press = 0
    t_press = 0

    try:
        if pref is None:
            pref = read_press()
        while time.monotonic_ns() < deadline:
            ax, ay, az = read_accel()
            dx = ax - rx0; dy = ay - ry0; dz = az - rz0
            sx += dx; sy += dy; sz += dz
            qx += dx * dx; qy += dy * dy; qz += dz * dz
            d = dx * dx + dy * dy + dz * dz
            if d > pk:
                pk = d
            n_acc += 1

            now = time.monotonic_ns()
            if now - t_press >= PRESS_EVERY_NS:
                dp = read_press() - pref
                sp += dp; qp += dp * dp
                n_press += 1
                t_press = now

        temp = clue.temperature           # C   (BMP280, self-heated -- deltas only)
        humid = clue.humidity             # %   (SHT31), slow: once per tick
    except Exception as exc:              # never let one bad read kill the loop
        print("# read error:", exc)
        time.sleep(1.0)
        next_tick = time.monotonic_ns() + TICK_NS
        continue

    if n_acc == 0 or n_press == 0:        # a stalled bus would divide by zero
        print("# empty tick: n_acc={} n_press={}".format(n_acc, n_press))
        time.sleep(1.0)
        next_tick = time.monotonic_ns() + TICK_NS
        continue

    ux = sx / n_acc; uy = sy / n_acc; uz = sz / n_acc      # mean OFFSET from the ref
    mx = rx0 + ux; my = ry0 + uy; mz = rz0 + uz            # absolute mean = tilt vector
    up = sp / n_press
    mp = pref + up
    ref = (mx, my, mz)

    rx = _rms(qx, ux, n_acc)
    ry = _rms(qy, uy, n_acc)
    rz = _rms(qz, uz, n_acc)
    p_sd_pa = _rms(qp, up, n_press) * 100.0 if n_press > 1 else 0.0
    pref = mp

    # Timestamp printed from integer arithmetic: a float32 seconds value has 0.25 s
    # resolution at this board's uptime and would throw the sub-second part away.
    secs, ms = divmod(time.monotonic_ns() // 1_000_000, 1000)
    print("{}.{:03d},{:.2f},{:.4f},{:.1f},{:.4f},{:.4f},{:.4f},"
          "{},{:.4f},{:.4f},{:.4f},{:.4f},{},{:.3f}".format(
              secs, ms, temp, mp, humid, mx, my, mz,
              n_acc, rx, ry, rz, math.sqrt(pk), n_press, p_sd_pa))

    clue.pixel.fill((0, 0, 6) if n % 2 else (0, 0, 0))   # blue heartbeat = alive

    # Absolute schedule, so one slow tick doesn't shift the grid for every tick after
    # it (the first flash recomputed the deadline from the loop top and drifted to
    # 1.43 s intervals). If we somehow fall a whole tick behind, resync rather than
    # sprint to catch up -- this is a 1 Hz environmental log, not a real-time bus.
    now = time.monotonic_ns()
    if now < next_tick:
        time.sleep((next_tick - now) / 1_000_000_000)
    next_tick += TICK_NS
    if next_tick <= time.monotonic_ns():
        next_tick = time.monotonic_ns() + TICK_NS

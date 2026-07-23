#!/usr/bin/env python3
"""rdatac_test.py — prototype ADS1256 RDATAC (read-data-continuous) acquisition.

STEP 1 of the continuous-sampling change. Touches NOTHING in recorder.py: this
just proves whether the Pi 2B can hold true RDATAC reliably, which is the only
real unknown. Requires the recorder stopped (it owns the ADC):

    sudo systemctl stop seismo-recorder
    python rdatac_test.py --seconds 600
    sudo systemctl start seismo-recorder

WHY: the recorder's read path issues a SYNC/WAKEUP per sample (PiPyADC's
read_continue), so the achieved rate sits a few percent under nominal, wanders
with load, and every ~10 s block is re-anchored to the wall clock -- leaving a
~68 ms gap at each block boundary. In RDATAC the converter free-runs off its own
crystal and each DRDY falling edge presents a fresh 24-bit sample: exactly
DRATE sps, forever, no per-sample command traffic.

PiPyADC defines CMD_RDATAC (0x03) but never uses it, so the loop is here. It uses
the driver's pigpio handle and pin config directly -- deliberately reaching past
the public API, which is fine for a prototype but should become a driver method
(or a vendored read path) if this graduates.

WHAT IT MEASURES
  - achieved rate vs nominal (samples / wall-clock elapsed)
  - DRDY interval jitter, from pigpio's microsecond tick stamps
  - MISSED samples: DRDY edges the reader failed to service (the failure mode
    that would make RDATAC worse than what we have -- a silent data loss)
  - the raw samples, saved to npz for noise analysis on the Mac

It does NOT write miniSEED and does not touch the archive.
"""
import argparse
import time

import numpy as np
import pigpio

from adc_common import DIFF, open_ads
from pipyadc.ADS1256_definitions import CMD_RDATAC, CMD_SDATAC

INT24 = 3


def run(seconds: float, gain: int, drate: int, out: str | None):
    ads = open_ads(gain, drate)
    pi = ads.pi
    drdy = ads._DRDY_PIN
    cs = ads._CS_PIN
    if drdy is None:
        raise SystemExit("no DRDY pin configured -- RDATAC needs it for sample timing")

    print(f"chip id {ads.chip_ID}, gain {gain}, DRATE nominal {drate} sps")

    # Park the mux on the geophone pair and start a conversion cycle. In RDATAC the
    # channel must not change -- one differential channel only, which is all we use.
    ads.mux = DIFF
    ads.sync()
    ads.wakeup()

    # --- DRDY edge accounting -------------------------------------------------
    # A pigpio callback counts falling edges with microsecond ticks. The reader
    # compares its own sample count against this: any shortfall is a sample the
    # ADC produced and we failed to collect.
    edges = {"n": 0, "ticks": []}

    def on_edge(gpio, level, tick):
        edges["n"] += 1
        edges["ticks"].append(tick)

    cb = pi.callback(drdy, pigpio.FALLING_EDGE, on_edge)

    samples = np.empty(int(seconds * drate * 1.2) + 1000, dtype=np.int32)
    n = 0
    missed = 0
    if cs is not None:
        pi.write(cs, pigpio.LOW)          # hold CS asserted for the whole run
    try:
        pi.spi_write(ads.spi_handle, CMD_RDATAC.to_bytes())
        time.sleep(0.001)
        t0 = time.time()
        seen = edges["n"]
        deadline = t0 + seconds
        while time.time() < deadline:
            # wait for a NEW edge (level polling can re-read the same sample)
            spin = 0
            while edges["n"] == seen:
                time.sleep(0.0005)
                spin += 1
                if spin > 20000:          # ~10 s: DRDY stopped -> bail out
                    raise SystemExit("DRDY stopped -- RDATAC not running?")
            gained = edges["n"] - seen
            if gained > 1:
                missed += gained - 1      # edges that came while we were busy
            seen = edges["n"]
            cnt, raw = pi.spi_read(ads.spi_handle, INT24)
            if cnt == INT24 and isinstance(raw, bytearray):
                if n < samples.size:
                    samples[n] = int.from_bytes(raw, byteorder="big", signed=True)
                    n += 1
        elapsed = time.time() - t0
    finally:
        pi.spi_write(ads.spi_handle, CMD_SDATAC.to_bytes())
        if cs is not None:
            pi.write(cs, pigpio.HIGH)
        cb.cancel()
        ads.stop_close_all()

    x = samples[:n].astype(np.float64)
    ticks = np.array(edges["ticks"], dtype=np.int64)
    d = np.diff(ticks) / 1e6                       # DRDY intervals, seconds
    d = d[(d > 0) & (d < 1.0)]                     # drop tick wraps
    uv = 2.5 * 2 / (gain * (2 ** 23 - 1)) * 1e6

    print(f"\n--- {elapsed:.1f} s run ---")
    print(f"samples read      {n}")
    print(f"DRDY edges seen   {edges['n']}")
    print(f"MISSED samples    {missed}   ({100*missed/max(edges['n'],1):.3f}% of edges)")
    print(f"achieved rate     {n/elapsed:.4f} sps   (nominal {drate})")
    if d.size:
        print(f"DRDY interval     mean {d.mean()*1000:.3f} ms  "
              f"sd {d.std()*1000:.3f} ms  min {d.min()*1000:.3f}  max {d.max()*1000:.3f}")
        print(f"implied rate      {1/d.mean():.4f} sps (from DRDY ticks)")
        print(f"jitter            {d.std()/d.mean()*100:.4f}% of interval")
    if n > 10:
        print(f"signal            {np.ptp(x)*uv:.1f} uV pp, "
              f"{x.std()*uv:.3f} uV rms (raw, unfiltered)")
    if out:
        np.savez(out, counts=samples[:n], drate=np.int32(drate), gain=np.int32(gain),
                 elapsed=np.float64(elapsed), achieved=np.float64(n / elapsed),
                 drdy_intervals=d, missed=np.int32(missed))
        print(f"\nsaved {out} (analyse on the Mac)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=float, default=600)
    p.add_argument("--gain", type=int, default=64)
    p.add_argument("--drate", type=int, default=60)
    p.add_argument("--out", default="/tmp/rdatac_test.npz")
    a = p.parse_args()
    run(a.seconds, a.gain, a.drate, a.out)

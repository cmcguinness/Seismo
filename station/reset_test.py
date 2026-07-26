#!/usr/bin/env python3
"""reset_test.py — prove the ADS1256 can be recovered WITHOUT the RESET pin.

The station has always leaned on a RESET-pin pulse to rescue a chip left in
read-data-continuous by a process that died without sending SDATAC. Bare ADS1256
breakouts (LC Tech ADS1256_V1.1 and friends) don't bring RESET out, so the recovery
has to be an SPI command sequence instead. This proves it on hardware we already own.

Each phase runs as its own PROCESS. That is not fussiness: PiPyADC tracks claimed
GPIOs in a class attribute, so a second open in the same interpreter fails with
"CS pin already used" -- an in-process bookkeeping error that looks exactly like a
wedged chip and will happily fake a passing test. Only a fresh process actually asks
the hardware anything.

  wedge   -- open, enter RDATAC, then _exit without SDATAC or reset (a SIGKILLed
             recorder). Chip is left streaming.
  bare    -- construct with NO prior reset. Expect FAILURE. If this succeeds the
             chip was not wedged and the round proves nothing -> INCONCLUSIVE.
  recover -- adc_common.reset_adc() (SDATAC x2 + RESET over SPI), then construct and
             read. Expect SUCCESS.

Run with the recorder STOPPED. Usage: python reset_test.py [rounds]
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _phase_wedge():
    import adc_common
    from rdatac import RdatacReader
    adc_common.reset_adc()
    ads = adc_common.open_ads(gain=64, drate_sps=100)
    reader = RdatacReader(ads, adc_common.DIFF)
    reader.start()
    for _ in range(20):
        reader.read()
    print("wedged: left in RDATAC, no SDATAC, no reset")
    sys.stdout.flush()
    os._exit(0)                     # hard exit: no atexit, no cleanup, like SIGKILL


def _phase_open(do_reset):
    import adc_common
    import waveshare_config
    from pipyadc import ADS1256
    if do_reset:
        adc_common.reset_adc()
    try:
        ads = ADS1256(waveshare_config)
        v = ads.read_oneshot(adc_common.DIFF)
        ads.stop_close_all()
        print(f"OK read {v}")
        return 0
    except Exception as e:
        print(f"FAIL {type(e).__name__}: {e}")
        return 1


def _run(phase):
    """Run one phase in a fresh interpreter; return (rc, output)."""
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--phase", phase],
                       cwd=HERE, capture_output=True, text=True, timeout=120)
    out = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode, (out[-1] if out else "<no output>")


def main():
    if "--phase" in sys.argv:
        phase = sys.argv[sys.argv.index("--phase") + 1]
        if phase == "wedge":
            return _phase_wedge()
        return _phase_open(do_reset=(phase == "recover"))

    import waveshare_config
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    pin = os.environ.get("SEISMO_RESET_PIN", "0")
    print(f"RESET-pin assist: {'ON' if pin == '1' else 'OFF (software only)'}")
    print(f"CHIP_HARD_RESET_ON_START = {waveshare_config.CHIP_HARD_RESET_ON_START}")
    print("each phase runs in its own process\n")

    recovered = wedged = 0
    for i in range(1, rounds + 1):
        print(f"--- round {i} ---")
        rc, msg = _run("wedge")
        print(f"  WEDGE   : {msg}")
        time.sleep(0.2)
        rc, msg = _run("bare")
        if rc == 0:
            print(f"  CONFIRM : chip NOT wedged ({msg}) -> INCONCLUSIVE round")
        else:
            wedged += 1
            print(f"  CONFIRM : wedged as intended -- {msg}")
        rc, msg = _run("recover")
        print(f"  RECOVER : {'PASS' if rc == 0 else 'FAIL'} -- {msg}")
        recovered += (rc == 0)

    print(f"\n{recovered}/{rounds} recovered by software reset alone; "
          f"{wedged}/{rounds} rounds were genuinely wedged first")
    if wedged == 0:
        print("VERDICT: inconclusive -- never managed to wedge the chip")
        return 2
    return 0 if recovered == rounds else 1


if __name__ == "__main__":
    sys.exit(main())

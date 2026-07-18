# STATUS — Seismo

_Last updated: 2026-07-17 (evening)_

## Where we are

**Hardware bring-up COMPLETE** and the **geophone holder is printed and fits.**
The full signal chain is validated on real hardware: geophone → ADS1256 → SPI →
pigpio → PiPyADC → Python, reading on the Pi (geophone twitches on taps; a AA
cell read 1.29 V). The 3D-printed coupling pocket prints clean and the geophone
**seats solid on the floor** (glove fit — museum putty now optional, not
structural).

The gate to a working *instrument* is now the **fast sampler** — software that
renders the 4.5 Hz waveform (the demo tool samples too slowly). Next hardware
step is wiring the geophone into the ADC (differential + bias + shunt).

## Milestone map (bring-up order — specification.md §6)

- [x] **Phase 0** — Pi prepped (OS, SPI, pigpio, PiPyADC)
- [x] **Phase 1** — ADC reads a known source (AA cell → 1.29 V on AIN0)
- [x] **Phase 2a** — geophone connected, twitches on taps (life-check)
- [x] **Enclosure v1** — geophone coupling pocket (`parts/geophone_base.py`) prints, seats solid
- [ ] **ADC-end wiring** — solder XLR to geophone (done? see below), land differential + bias + shunt at the board
- [ ] **Phase 2b** — fast sampler (100–200 sps) + differential/biased front-end + log/plot
- [ ] **Phase 3** — shunt damping resistor (empirical tune to ~0.7 critical)
- [ ] **Phase 4** — station software (miniSEED / helicorder)
- [ ] **Phase 5** — record a real event; cross-check vs USGS / nearby Raspberry Shake

## Hardware as-built

- **Sensor:** LGT-4.5 bare 1" element. Coil **385 Ω** measured. **25.4 mm ⌀ × 36 mm, 74 g.** Bottom = flat rim + central recess. Top = offset green board, two solder pins (one `+`, one marked; **red wire = +, white = −** on our cable).
- **ADC:** Waveshare High-Precision AD/DA (ADS1256).
- **Pi:** Raspberry Pi **2B** (32-bit), Bookworm Lite 32-bit, `seismo.local`, USB Wi-Fi dongle. PSU 5 V / 2.5 A.
- **Cable:** salvaged **XLR** (shielded twisted pair), ~1 m, coiled slack. red=+/white=−, braid=shield.

## Software as-built (on the Pi, `~/seismo`)

- venv `~/seismo/venv` (`--system-site-packages` → sees apt `python3-pigpio`).
- PiPyADC cloned + `pip install ./PiPyADC`. pigpio backend (fine on Pi 2B; the Pi-5 lgpio issue does NOT apply).
- `pigpiod` enabled at boot. Run demo: `cd ~/seismo/PiPyADC/examples/waveshare_board && source ~/seismo/venv/bin/activate && python waveshare_example.py`
- **Shim:** installed PiPyADC lacks context-manager support; patched the example `with ADS1256(...) as ads:` → `for ads in [ADS1256(...)]:`. Temporary — replace with our own sampler.

## Analog front-end plan (decided, not yet wired)

- **Differential**, not single-ended: source is floating + bipolar so it needs a common-mode bias either way, and differential also gives common-mode hum rejection (pairs with the shielded twisted pair).
- Geophone across **AD0 (AINP) / AD1 (AINN)**; common-mode **biased to AVDD/2** via two high-value resistors (≫ coil & shunt, ~100 kΩ+) to a mid-supply reference off VCC.
- **Shunt (damping) resistor across AD0/AD1**, landed in the **screw terminals** so it's swappable — damping is tuned empirically (~3–13 kΩ range; pick the value that gives a clean single overshoot on the sampler).
- **Shield → AGND at the board end only** (floating at the geophone) to avoid a ground loop.
- Coil is ~pure **375 Ω** in-band; inductance (X_L ≈ 5 Ω @ 4.5 Hz) is negligible — treat the network as resistive.

## Enclosure

- `parts/geophone_base.py`: 25.8 mm bore (25.4 + 0.4), 36 mm deep, flat coupling floor, centering boss into the bottom recess, wire-exit notch. **31.8 mm ⌀ × 40 mm.** Prints flat-base-down, no supports. **Fit confirmed: seats solid, boss does not lift it.**
- **Mount = museum putty** on the flanks (NOT under the element — a compliant layer under a vertical geophone would low-pass the signal). No printed clamp.
- Still to model: **Pi/ADC tray** on the same shell, then a **lid**. Single combined case, flat base, no leveling feet.

## Board jumper cheat-sheet (this board shipped with jumpers OFF)

- **Left yellow block** = SPI/GPIO routing. Fully jumpered — leave it.
- **`JMP_AGND`** (AINCOM ↔ AGND): jumpered — required for single-ended reads.
- **Right block top:** VCC selector (`5V/VCC/3V3`) = analog AVDD; VREF selector (`5V/VREF/3V3`). **Both on 3V3** (works). ADS1256 wants AVDD=5 V for best noise floor, but jumpering "to 5 V" **hard-locked the Pi even on a 2.5 A supply** → almost certainly a 3-pin cap shorting 5 V↔3V3. Revisit carefully, Pi OFF, pins verified.
- **Right block bottom:** `AD0–ADJ` (pot) / `AD1–LDR` (photoresistor) = demo sensors, not jumpered. We use the **screw terminals** (`AD7…AD0 AGND VCC GND DAC1 DAC0`) instead.

## Open threads (pick next session)

1. **Wire the ADC end** — differential + bias network + shunt in the screw terminals.
2. **Fast sampler** — read AD0/AD1 differentially at 100–200 sps, log + plot. ← software gate
3. **Tune the damping shunt** against the observed ring.
4. **Model the Pi/ADC tray + lid** (mechanical, non-blocking).
5. Resolve the **5 V AVDD** jumper safely (noise floor).
6. Station software (miniSEED/helicorder) — `will127534/RaspberryPi-seismograph` is thin/stale; reassess.

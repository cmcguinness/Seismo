# STATUS — Seismo

_Last updated: 2026-07-19_

## Where we are

**Hardware bring-up + the mechanical base are DONE.** The signal chain is
validated on real hardware (geophone → ADS1256 → SPI → pigpio → PiPyADC → Python;
geophone twitches on taps; a AA cell read 1.29 V). The combined 3D-printed base
(geophone pocket + Pi 2B mount + cotter-pin retention) is printed and fits, and
the geophone is **soldered to its XLR cable and validated** (coil ohms + movement
response good).

Remaining gates to a working *instrument*: (1) land the geophone at the ADC with
the differential + bias + shunt front-end, and (2) write the **fast sampler** —
the software that actually renders the 4.5 Hz waveform (the demo tool at ~2 sps
can't). Crimp-ferrule kit inbound to re-terminate the tinned cable ends for the
permanent build.

## Milestone map (bring-up order — specification.md §6)

- [x] **Phase 0** — Pi prepped (OS, SPI, pigpio, PiPyADC)
- [x] **Phase 1** — ADC reads a known source (AA cell → 1.29 V on AIN0)
- [x] **Phase 2a** — geophone connected, twitches on taps (life-check)
- [x] **Enclosure v1** — geophone pocket (`geophone_base.py`, seats solid) + combined Pi/geophone base (`chassis.py`, Pi 2B mount + cotter-pin retention), both printed and fitting
- [~] **ADC-end wiring** — XLR soldered to geophone + validated ✓; still to land differential + bias + shunt at the board (ferrule the ends first)
- [ ] **Phase 2b** — fast sampler (100–200 sps) + differential/biased front-end + log/plot
- [ ] **Phase 3** — shunt damping resistor (empirical tune to ~0.7 critical)
- [ ] **Phase 4** — station software (miniSEED / helicorder)
- [ ] **Phase 5** — record a real event; cross-check vs USGS / nearby Raspberry Shake

## Hardware as-built

- **Sensor:** LGT-4.5 bare 1" element. Coil **385 Ω** measured. **25.4 mm ⌀ × 36 mm, 74 g.** Bottom = flat rim + central recess. Top = offset green board, two solder pins (one `+`, one marked; **red wire = +, white = −** on our cable).
- **ADC:** Waveshare High-Precision AD/DA (ADS1256).
- **Pi:** Raspberry Pi **2B** (32-bit), Bookworm Lite 32-bit, `seismo.local`, USB Wi-Fi dongle. PSU 5 V / 2.5 A.
- **Cable:** salvaged **XLR** (shielded twisted pair), ~1 m, coiled slack. red=+/white=−, braid=shield. **Soldered to the geophone + validated** (ohms + movement). Ends tinned for test insertion; **re-terminate with crimp ferrules** for the permanent build — tinned strands cold-flow/loosen under screw terminals. Shield → AGND at the board end only.

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

- `parts/geophone_base.py`: 25.8 mm bore (25.4 + 0.4), 36 mm deep, flat coupling floor, wire-exit notch. **31.8 mm ⌀ × 40 mm.** Prints flat-base-down, no supports.
- **Boss removed (ink test, 2026-07-17):** a 2 mm centering boss bottomed out in the geophone's shallow ~1 mm bottom recess and lifted it — ink transferred only at the center. Removed; flat floor now, glove-fit bore centers it. **Reprinted + re-inked: full rim contact, seats solid. ✓**
- **Mount = museum putty** on the flanks (NOT under the element — a compliant layer under a vertical geophone would low-pass the signal). No printed clamp.
- `parts/chassis.py`: combined base — geophone pocket (+X, port-free DSI end) + Raspberry Pi 2B mount. **~148 × 68 mm** (fits A1 Mini). Pi held by 2 locating pins in the free GPIO-side holes + 1 flat support post between the USB-side standoff nuts; pins stand proud with a transverse **cotter-pin hole** (1.5 mm, axis ⊥ the GPIO header for wire access; solid wire / improvised cotter) that retains the board. (Pi mount hole lightly filed to accept the 2.6 mm pin — future reprints could shave `pin_dia` ~0.1 mm to avoid that.) **Layout confirmed against the real Pi 2B:** GPIO/pins on −Y long edge; power/HDMI/nuts/HAT-terminals on +Y; USB/Ethernet/dongle on −X short edge; geophone on +X. **Printed and fits — Pi, geophone, and cotter all good.**
- Still to model: **walls** (power-connector cutout on +Y, Wi-Fi **dongle slot** on −X) + a **lid**. Single combined case, flat base, no leveling feet. Consider a plate slot between Pi and pocket to break the vibration path.

## Board jumper cheat-sheet (this board shipped with jumpers OFF)

- **Left yellow block** = SPI/GPIO routing. Fully jumpered — leave it.
- **`JMP_AGND`** (AINCOM ↔ AGND): jumpered — required for single-ended reads.
- **Right block top:** VCC selector (`5V/VCC/3V3`) = analog AVDD; VREF selector (`5V/VREF/3V3`). **Both on 3V3** (works). ADS1256 wants AVDD=5 V for best noise floor, but jumpering "to 5 V" **hard-locked the Pi even on a 2.5 A supply** → almost certainly a 3-pin cap shorting 5 V↔3V3. Revisit carefully, Pi OFF, pins verified.
- **Right block bottom:** `AD0–ADJ` (pot) / `AD1–LDR` (photoresistor) = demo sensors, not jumpered. We use the **screw terminals** (`AD7…AD0 AGND VCC GND DAC1 DAC0`) instead.

## Decisions & deferred

- **Accelerometer: not for v1.** The geophone is the sensitive weak-motion sensor; a MEMS accel is strong-motion class and adds nothing to detection sensitivity. If ever added (horizontal components / big-local-quake capture), use the **ADXL355** (~25 µg/√Hz, 20-bit — what OpenEEW / the Raspberry Shake strong-motion units use), **not** the ADXL345 (~300 µg/√Hz, consumer-grade, useless here). 6 free ADS1256 channels available. Add-on, not a gap.
- **Ferrules, not tinned ends, in screw terminals** — see the cable note above.
- **5 V AVDD jumper deferred** — currently on 3V3 (works); see jumper cheat-sheet for the lock-up caution before revisiting.

## Open threads (pick next session)

1. **Wire the ADC end** — differential + bias network + shunt in the screw terminals.
2. **Fast sampler** — read AD0/AD1 differentially at 100–200 sps, log + plot. ← software gate
3. **Tune the damping shunt** against the observed ring.
4. **Model the case walls + lid** (power cutout on +Y, dongle slot on −X; the Pi/geophone base is done) — mechanical, non-blocking.
5. Resolve the **5 V AVDD** jumper safely (noise floor).
6. Station software (miniSEED/helicorder) — `will127534/RaspberryPi-seismograph` is thin/stale; reassess.

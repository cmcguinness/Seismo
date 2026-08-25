# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A DIY Raspberry Pi seismometer — a *sensitivity-first* (not precision-first) instrument to detect local earthquakes, sited in Oakmont / Santa Rosa, Sonoma County, atop the Rodgers Creek / Maacama fault system.

**Current state (important):** Hardware **bring-up is complete** (2026-07-17) — geophone → ADS1256 → Pi chain validated end to end on real hardware. **Read `STATUS.md` first** for exactly where things stand, the board jumper cheat-sheet, config gotchas, and the next step. The code so far lives **on the Pi** (`seismo.local:~/seismo`), not in this repo — this repo still holds only `specification.md`, `pyproject.toml`, and this doc. Also read `specification.md` end-to-end before writing code; it is the source of truth for every decision made so far and the alternatives already rejected (so they aren't re-tread).

## Hardware the software will target

- **Sensor:** LGT-4.5 / EG-4.5-II class geophone — 4.5 Hz vertical, 28.8 V/m/s, 375 Ω coil. Standard (not the 100 V/m/s) element. (The AliExpress listing mislabels it "LGT-20D 4.5 Hz" — "20D"/"LGT-20D" is a family name, **not** a frequency; always confirm actual Hz.)
- **ADC:** Waveshare High-Precision AD/DA Board — **ADS1256**, 8-channel 24-bit ADC, 40-pin header, SPI. This board sets the noise floor; it's the component sensitivity depends on. A bare "ADS1256 breakout" is a *different* board with a different pinout — do not assume compatibility.
- **Compute:** Raspberry Pi **2B** (32-bit ARMv7), Bookworm Lite 32-bit, `seismo.local`, USB Wi-Fi dongle. 40-pin GPIO, SPI.

## Software plan (not yet started — from `specification.md` §4)

- **Seismograph stack:** `will127534/RaspberryPi-seismograph` (and the Seisberry / Erellaz fork) — drives this exact Waveshare board, outputs local web view and/or miniSEED. *Repo currency not yet verified.*
- **ADS1256 driver:** `ul-gh/PiPyADC` (Python).
- **GPIO backend:** PiPyADC uses the **pigpio** backend, which works fine on the **Pi 2B**. (The spec's "Pi 5 → only `lgpio`" warning was Pi-5-specific and does **not** apply here.)
- **Since 2026-08-25 the running station reads the ADC through `station/adsreader/` (C, spidev + GPIO uAPI interrupts) with `SEISMO_READER=c`;** pigpio/PiPyADC remain for the diagnostic tools and the fallback path. Only one process may own the ADS1256 — stop `seismo-recorder` before running any ADC tool.
- **Sampling rate:** seismology runs at **100–250 sps** (Raspberry Shake = 100 sps). The ADS1256's 30 ksps spec and its known SPI-timing noise above ~2 kHz are irrelevant — this station operates two orders of magnitude below where trouble starts.
- **Prefer the existing seismograph stack / PiPyADC over rolling a custom ADC read loop.**

## Bring-up order (isolates ADC faults from geophone faults — §6)

1. ADC arrives first → mount on Pi, enable SPI.
2. Run Waveshare demo or PiPyADC; confirm clean voltage reads off a known source (a battery).
3. Only then introduce the geophone (debug one new variable, not two).
4. Add the shunt damping resistor; verify the 4.5 Hz resonance is tamed. (Value depends on 375 Ω coil + board input impedance — **size it once the board is measurable**, not before.)
5. Stand up seismograph software; log + view.

## Enclosure & CAD (build123d)

The 3D-printed enclosure is modeled with **build123d** (not CadQuery/OpenSCAD). Env set up by the `cad:setup` skill; live preview via `cad:watch`.

- **Parts** live one-per-file in `parts/`; **shared dims** in `dimensions.py` (`from dimensions import *`). STLs export to `stl/` (gitignored).
- Every part ends with `show(part)` (ocp_vscode) + `export_stl(part.part, "stl/<name>.stl")`.
- The venv is **uv-managed and has no pip** — install with `uv pip install --python .venv/bin/python <pkg>`. CAD packages are dev tooling, not in `pyproject.toml`.
- Parts import `dimensions`, so run with the root on the path: `PYTHONPATH=. .venv/bin/python parts/<name>.py`, or use `.venv/bin/python watch.py parts/<name>.py` (auto-re-renders).
- **Viewer:** `python -m ocp_vscode` → http://localhost:3939/**viewer**. Must run *before* `show()`, and open the browser tab *before* the push — it won't replay to a late-joining client, so re-run the part after opening.
- Fasteners + their holes come from `bd_warehouse.fastener` — never hand-size a screw hole.
- **Current parts** (as of 2026-08-08):
  - **Geophone case — COMPLETE, printed and assembled:** `geophone_case.py` (body, XLR
    mount), `geophone_case_lid.py` (lid + carry handle), `geophone_base.py` (the original
    coupling pocket — seats solid, held by museum putty, no clamp), `geophone_stand.py`.
  - **Pi + front-end case — modelled, not yet printed:** `case_base.py` (flat shelf with
    the Pi and interface-board mounts), `case_cover.py` (domed shell, all three jacks),
    `case_handle.py` (screws to the cover roof from inside). Three parts on purpose: the
    piece you iterate on is the cheap flat one.
  - **Fit coupons, both validated:** `xlr_coupon.py` (D-series cutout), `panel_coupon.py`
    (barrel bore = 12 mm; RJ45 feedthrough is D-series too).
  - **Superseded:** `chassis.py` (open tray, replaced by `case_base` + `geophone_case`).
- **Shared case envelope lives in `dimensions.py`**, not in the parts: the three case
  parts derive their footprint, bay centres and connector positions from it, with z=0
  defined as the base's TOP face (= the cover's rim). ⚠️ Names there must NOT start with
  `_` — `from dimensions import *` silently skips them.

## Environment

- Python **3.13+** (see `pyproject.toml`). A project `.venv` exists (uv-managed) and is auto-activated by direnv.
- **direnv is configured** (`.envrc`). Run environment-sensitive commands through `direnv exec .` — it sets the `cmcguinness` gh account (`GH_TOKEN`), the commit identity (`charles@mcguinness.us`), `CLAUDE_CONFIG_DIR`, and the venv `PATH`. The Bash tool does not fire the direnv hook on its own.
- **Git:** repo initialized; pushes to the `cmcguinness` GitHub account (private repo `Seismo`). Run git/gh through `direnv exec .` so the right account (`GH_TOKEN`) and commit identity (`charles@mcguinness.us`) apply — the Bash tool doesn't fire the direnv hook.
- Much of the Pi software only runs on the target Pi (SPI, pigpio, the ADS1256) and can't be exercised on this macOS dev machine. The **enclosure CAD**, by contrast, is developed here (build123d).

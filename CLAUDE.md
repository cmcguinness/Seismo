# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A DIY Raspberry Pi seismometer — a *sensitivity-first* (not precision-first) instrument to detect local earthquakes, sited in Oakmont / Santa Rosa, Sonoma County, atop the Rodgers Creek / Maacama fault system.

**Current state (as of 2026-09-02):** the station has been **recording 24/7 since
2026-07-20**, with 34 catalog-confirmed earthquakes inside a validated range of 88.8 km,
plus an M4.8 recorded at 319 km that is verified by arrival time but deliberately left
out of the range fit (enforced by `EXCLUDE_FROM_FIT` in `analysis/detection_map.py` —
a magnitude revision made it *qualify* on 2026-09-02 and the re-harvest gate had to stop
the publish), and two dashboards. **f0 and zeta in `station/SS.OAKM1.xml` are still
guesses**; the inline calibration injector (`calibrator/`, `doc/BOM-calibrator.md`) is
being built to replace them, parts due ~2026-09-09. **Read `STATUS.md` first** — its *Current system* section is the resume point, then
recent entries newest-first; everything before 2026-08-20 is verbatim in
`STATUS-ARCHIVE.md` (indexed at the bottom of STATUS.md). `BACKLOG.md` holds deferred work; `specification.md` is the
original design with the alternatives already rejected.

## Where the code runs (three hosts, one repo)

| host | what | code |
|---|---|---|
| `seismo.local` (Pi 2B, garage) | acquisition only: `station/adsreader/` (C) owns the ADS1256 — DRDY as a kernel interrupt, hardware timestamps — and `station/recorder.py` writes miniSEED day-files on an exact 100 sps grid, despikes, runs the inline STA/LTA, streams records by UDP to pi5 | `station/` — deployed by hand (`scp`), units in `station/*.service` |
| `pi5` (Pi 5, house, LAN only) | the owned data plane: `server/udp_collector.py` builds the archive, `server/detector.py` re-detects over it and **scores each trigger with the classifier** (`p_quake`, ntfy push at ≥ 0.7), `server/seismo_server.py` serves `/v1/*`; the **LAN dashboard** (Dokku app `seismo`, `dashboard/`) | `server/`, `dashboard/` — **auto-deployed**: pi5 pulls `main` every 2 min (`pi5/autodeploy.sh`); `./deploy.sh` is the manual path |
| `apps02.mcguinness.ai` (public VPS) | the **public dashboard**, https://seismo.mcguinness.ai — same image, fed **outbound-only** by pi5 (rsync every minute + the live ring every 3 s). Nothing at the house is reachable from the internet. Also the **visitor digest** (`apps02/visitors.py`: nginx log → Dokku Postgres `seismo-visitors` → ntfy `seismo-visitors` daily; own report at `/visitors/` behind basic auth) | `./deploy.sh public`; `apps02/install-visitors.sh` by hand |

The Mac is for analysis (`analysis/`, obspy venv), CAD (`parts/`), **training the
trigger classifier** (`analysis/trigger_train.py` → `analysis/models/`, shipped to pi5
by deploy), and the **calibration injector firmware** (`calibrator/`, avr-gcc + avrdude
via Homebrew — `osx-cross/avr` needs `brew trust`). Nothing trains on the Pis.

The **calibration injector** is a fourth piece of hardware, not a host: an ATtiny85 box
inline on the geophone cable that fires a known current burst four times a day, so f0 and
zeta can be measured instead of guessed. `doc/BOM-calibrator.md` is the build,
`calibrator/` the firmware, `analysis/calfinder.py` finds the bursts in the archive (and
masks them out of the classifier's training set), `analysis/ringdown.py` fits them.
**Its protocol constants are shared:** `N_PULSES`/`PULSE_MS`/`SPACING_MS` must match
between `calibrator/calibrator.c` and `calfinder.py`, and calfinder's self-test parses the
C file and fails if they drift apart.

**Rules of the road:**
- Only one process may own the ADS1256. Stop `seismo-recorder` before any ADC tool.
- `deploy.sh` refuses a dirty tree; commit first. Dashboard changes need BOTH
  `./deploy.sh dashboard` and `./deploy.sh public` (autodeploy covers pi5 only).
- Every hardware/siting/timing change gets a row in `analysis/epochs.py` the same day.
- The 41 / 40.6 / 37.65 / 19.3 / 20 Hz spectral lines are the house's heat-pump AC, not
  the electronics; 40.0 Hz is the 60 Hz mains alias. Only 1.05 Hz is unexplained.

## Hardware the software will target

- **Sensor:** LGT-4.5 / EG-4.5-II class geophone — 4.5 Hz vertical, 28.8 V/m/s, 375 Ω coil. Standard (not the 100 V/m/s) element. (The AliExpress listing mislabels it "LGT-20D 4.5 Hz" — "20D"/"LGT-20D" is a family name, **not** a frequency; always confirm actual Hz.)
- **ADC:** Waveshare High-Precision AD/DA Board — **ADS1256**, 8-channel 24-bit ADC, 40-pin header, SPI. This board sets the noise floor; it's the component sensitivity depends on. A bare "ADS1256 breakout" is a *different* board with a different pinout — do not assume compatibility.
- **Compute:** Raspberry Pi **2B** (32-bit ARMv7), Bookworm Lite 32-bit, `seismo.local`, USB Wi-Fi dongle. 40-pin GPIO, SPI.

## Software notes

- **Sampling:** 100 sps, PGA 64, one vertical channel — **`SS.OAKM1.00.EHZ`** since the
  identity cutover of 2026-08-30 (was `XX.OAKMT.00.SHZ`; `E` because the band code follows
  the sample rate, and `SS` is self-assigned pending a real FDSN network code from ISC).
  The ADS1256's crystal runs ~80–90 ppm fast; the recorder tosses one sample every ~2 min
  to hold an exact 100 sps grid (±7.5 ms).
- **ADC access:** `station/adsreader/adsreader.c` via spidev + GPIO uAPI (no pigpio in
  the hot path). `pigpio`/`PiPyADC` remain for the diagnostic tools and the fallback
  reader (`SEISMO_READER=pigpio`).
- **Calibration:** ~3.2× quieter than the 28.8 V/(m/s) nameplate (`refstation.py`
  against USGS NP.1835, 1.6 km away); Vp 5.19 km/s measured from local events.
- **Detection:** STA/LTA on the station AND on pi5 (the pi5 log is canonical); the
  gradient-boosting trigger classifier (`server/trigger_features.py` defines the
  features; retrain with `harvest_events.py` → `trigger_dataset.py` → `augment.py` →
  `trigger_train.py --aug`). `augment.py` buries the real events in real archive noise to
  make the weak positives the catalogue is too slow to supply; those rows are
  **train-only** and every reported metric is computed on real rows.

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
- `station/` only runs on the target Pi (SPI, the ADS1256); `server/` and `dashboard/` run on pi5/apps02 but import cleanly here; `analysis/` and the CAD run on the Mac. Day-files for analysis are pulled into `analysis/data/` (gitignored) by `eventcheck.py`/`scp`.

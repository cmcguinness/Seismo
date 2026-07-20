# STATUS — Seismo

_Last updated: 2026-07-19_

## Where we are

**The full analog + digital signal chain is now VALIDATED end to end** (2026-07-19).
Geophone → perfboard front-end (differential + mid-supply bias) → ADS1256 →
SPI → pigpio → PiPyADC → Python → **live browser waveform**. Measured: both
inputs biased at 1.503 V, ~10 µV pp idle noise floor, and a tap kicks the
differential channel to ~235 µV (25× over floor) — clean, responsive motion on
screen. The mechanical base (geophone pocket + Pi 2B mount + cotter retention)
is printed and fits; the geophone is soldered to its XLR cable and validated.

**Station code now lives in the repo** under `station/` (was Pi-only before):
`waveshare_config.py` (our owned board config), `adc_diag.py` (bias/rate/tap
check), `live_view.py` (real-time browser strip-chart on :8347). Deployed to
`seismo.local:~/seismo/station/`; passwordless SSH from the Mac is set up.

**The continuous recorder is DONE and validated** (2026-07-19): `recorder.py`
writes gapless miniSEED day-files (`XX.OAKMT.00.SHZ`, int32, ~57 sps, absolute
UTC) that read back clean, with real ambient motion in them (~1.7 µV RMS /
~57 nm/s, above the 41 nm/s electronics floor). So the station **records**.

**DEPLOYED as a systemd service** (`seismo-recorder.service`, 2026-07-19):
enabled (auto-starts on boot), `Restart=always`, clean SIGTERM shutdown. The
station now records 24/7 to `~/seismo/data/*.mseed` unattended.

**Public dashboard — DEPLOYED** (2026-07-20): heavy work runs OFF the 1 GB Pi 2B on
LAN hardware. **Pi 2B = acquire** (recorder + STA/LTA, owns the ADC), **Pi 5 (16 GB,
Dokku) = render/serve**, **Jetson = future ML** (backlog). Live at **https://seismo.mcguinness.ai** (PUBLIC, via Cloudflare Tunnel) — also
`http://seismo.pi5.mcguinness.ai` on the LAN.
- **Public exposure = Cloudflare Tunnel** (`cloudflared` on pi5, systemd service).
  mcguinness.ai is on Cloudflare, so: `cloudflared tunnel login` (interactive, done)
  → `cloudflared tunnel create seismo` → `cloudflared tunnel route dns --overwrite-dns
  seismo seismo.mcguinness.ai` → `/etc/cloudflared/config.yml` (ingress
  `seismo.mcguinness.ai → http://localhost:80`, tunnel id + creds) → `cloudflared
  service install`. Also `dokku domains:add seismo seismo.mcguinness.ai` so nginx
  serves that Host. Outbound-only (no port-forward, home IP hidden), TLS by
  Cloudflare. NO Let's Encrypt (the tunnel handles TLS; Dokku host is LAN-only).
- **Pipeline:** host-level `seismo-rsync.timer` on pi5 mirrors
  `seismo.local:~/seismo/{data,events.log}` → `~/seismo-data/` every minute. Dokku
  app `seismo` (`dashboard/`: FastHTML + ObsPy, Dockerfile) renders helicorder/
  spectrum from the mirror and **proxies** the Pi's live feed (`192.168.4.47:8347`)
  so the acquisition box stays private. pi5→Pi2B SSH set up (pi5 key on seismo).
- **Deploy recipe** (pi5, all `dokku` as user charles; `docker` needs sudo):
  `sudo docker build -t seismo-dash ~/seismo-dashboard` →
  `dokku apps:create seismo` · `dokku storage:mount seismo /home/charles/seismo-data:/data`
  · `dokku config:set --no-restart seismo SEISMO_LIVE_URL=http://192.168.4.47:8347/data SEISMO_PLACE=...`
  · `dokku git:from-image seismo seismo-dash:latest` · `dokku ports:set seismo http:80:5000`.
  (Rebuild + `git:from-image` again to update.) Note: obspy compiles from source
  (no aarch64 py3.12 wheel) → the Dockerfile needs `build-essential`.
- **Note:** images render on-demand per request (~2 s, fresher than the "every 15 min"
  ask); add a render cache if traffic warrants. Makes the "does the 2B need a RAM
  upgrade" question moot — it just acquires.

**Event detection** (2026-07-20): the recorder runs a streaming **STA/LTA** trigger
(`stalta.py`) inline — 1-pole high-pass (rejects microseism) → energy CF → STA/LTA
with the LTA frozen during events. Detections → journal (`EVENT …`), `~/seismo/
events.log` (permanent JSONL), and `/dev/shm/seismo_events.json` (recent, for the
viewer). Tunable via `SEISMO_TRIG`/`STA`/`LTA`/`HP` (default trig 4.0). Feeds the
planned APRS alerts + helicorder event annotation. Wrapped so it can never break
acquisition.

**Real-time viewer** (2026-07-20): the recorder mirrors a rolling 30 s window to
shared memory (`/dev/shm/seismo_live.npz`) from a dedicated publisher thread (no
ADC contention, isolated from the sampling loop). `live_server.py` (its own
`seismo-live.service`, always-on, ADC-free) serves a scrolling waveform at
**http://seismo.local:8347** — real-time viewing that coexists with recording.
(This is why `live_view.py` alone can't run now: the recorder owns the ADC.)

**Helicorder DONE** (2026-07-19): `analysis/helicorder.py` on the Mac pulls the
Pi's miniSEED (rsync) and renders a classic ObsPy dayplot drum — full loop
closed (geophone → 24/7 recorder → miniSEED → drum). ObsPy lives in a Mac-only
`analysis/.venv`, never on the Pi.

Remaining / refinements: (1) **tune the shunt damping** resistor against a
recorded impulse; (2) **data-continuity** — steady-state recording showed some
small gaps (jitter in the wall-clock-per-block timing, worsened by SSH load
during setup); watch it, and the RDATAC continuous-mode upgrade would remove it;
(3) minor: simplemseed writes a slightly inconsistent word-order flag (ObsPy
warns but reads fine) and int32 (STEIM2 compression later). Case walls/lid
deferred by choice. Crimp ferrules still inbound for permanent termination.

**Deferred work → see `BACKLOG.md`** — notably the **Rev-2 geophone→ADC front-end**
(revisit the input buffer for the noise floor, add an input anti-alias RC /
switched-cap reservoir, cleaner analog supply), plus STEIM2, RDATAC timing, and
the enclosure walls/lid.

### Operating the service (the recorder OWNS the ADC while running)
- Status / live log: `systemctl status seismo-recorder` · `journalctl -u seismo-recorder -f`
- **Before any manual ADC tool** (`live_view.py`, `adc_diag.py`, `noise_compare.py`, `recorder.py`): `sudo systemctl stop seismo-recorder` first, else the ADC is busy (chip-ID error). `sudo systemctl start seismo-recorder` when done.
- Unit lives at `/etc/systemd/system/seismo-recorder.service` (source of truth: `station/seismo-recorder.service`). Config via `Environment=` lines (station/gain/drate).

## Milestone map (bring-up order — specification.md §6)

- [x] **Phase 0** — Pi prepped (OS, SPI, pigpio, PiPyADC)
- [x] **Phase 1** — ADC reads a known source (AA cell → 1.29 V on AIN0)
- [x] **Phase 2a** — geophone connected, twitches on taps (life-check)
- [x] **Enclosure v1** — geophone pocket (`geophone_base.py`, seats solid) + combined Pi/geophone base (`chassis.py`, Pi 2B mount + cotter-pin retention), both printed and fitting
- [x] **ADC-end wiring** — perfboard front-end built + **validated** (bias 1.503 V, 10 µV floor, tap → 235 µV). 2× 100 kΩ bias to VCC/AGND, geophone on a detachable connector, empty shunt socket across AIN0/AIN1.
- [x] **Phase 2b** — differential/biased front-end ✓, live view ✓ (`live_view.py`), gain 64 + **DRATE_60** chosen from a noise sweep (`noise_compare.py`): electronics floor ~1.17 µV RMS / ~41 nm/s, mains-notched, sustainable timing
- [x] **Phase 4a** — **continuous recorder** (`recorder.py`): geophone → gapless miniSEED day-files via simplemseed, validated read-back
- [ ] **Phase 3** — shunt damping resistor (empirical tune to ~0.7 critical) — socket is wired, just needs a value (tune against a recorded impulse)
- [x] **Phase 4b** — recorder deployed as a **systemd service** (`seismo-recorder.service`, enabled/auto-start, 24/7)
- [x] **Phase 4c** — helicorder drum view (`analysis/helicorder.py`, Mac-side ObsPy dayplot vs the Pi's miniSEED)
- [ ] **Phase 5** — record a real event; cross-check vs USGS / nearby Raspberry Shake

## Hardware as-built

- **Sensor:** LGT-4.5 bare 1" element. Coil **385 Ω** measured. **25.4 mm ⌀ × 36 mm, 74 g.** Bottom = flat rim + central recess. Top = offset green board, two solder pins (one `+`, one marked; **red wire = +, white = −** on our cable).
- **ADC:** Waveshare High-Precision AD/DA (ADS1256).
- **Pi:** Raspberry Pi **2B** (32-bit), Bookworm Lite 32-bit, `seismo.local`, USB Wi-Fi dongle. PSU 5 V / 2.5 A.
- **Station:** `XX.OAKMT.00.SHZ` — vertical, 4.5 Hz. Location **38.451817°N, −122.621049°W** (Oakmont, Santa Rosa; measured at the sensor). Used by `analysis/eventcheck.py` for distance/travel-times.
- **Cable:** salvaged **XLR** (shielded twisted pair), ~1 m, coiled slack. red=+/white=−, braid=shield. **Soldered to the geophone + validated** (ohms + movement). Ends tinned for test insertion; **re-terminate with crimp ferrules** for the permanent build — tinned strands cold-flow/loosen under screw terminals. Shield → AGND at the board end only.

## Software as-built (on the Pi, `~/seismo`)

- venv `~/seismo/venv` (`--system-site-packages` → sees apt `python3-pigpio`).
- PiPyADC cloned + `pip install ./PiPyADC`. pigpio backend (fine on Pi 2B; the Pi-5 lgpio issue does NOT apply).
- `pigpiod` enabled at boot. Run demo: `cd ~/seismo/PiPyADC/examples/waveshare_board && source ~/seismo/venv/bin/activate && python waveshare_example.py`
- **Shim:** installed PiPyADC lacks context-manager support; patched the example `with ADS1256(...) as ads:` → `for ads in [ADS1256(...)]:`. Temporary — replace with our own sampler.

## Analog front-end (AS-BUILT + validated 2026-07-19)

Built on a **perfboard** (the ADS1256 screw strip was too cramped for 2 resistors
+ 3 wires + a bare shield without shorts). Three connectors on the board:
geophone-in (detachable), ADC-out (AIN0/AIN1/VCC/AGND), shunt socket.

- **Differential** read: geophone across **AIN0 (+) / AIN1 (−)**. Floating bipolar
  source, so it needs a common-mode bias regardless; differential also rejects hum
  (pairs with the shielded twisted pair).
- **Bias:** two **100 kΩ** resistors — R1 AIN0→VCC, R2 AIN1→AGND — pull the coil to
  mid-supply. Measured 1.503 V on both legs (≈AVDD/2; a hair low from unbuffered
  input bias current through the 100 k legs — harmless, symmetric). 100 k keeps the
  bias network invisible to the geophone (~200 kΩ across a 385 Ω coil), so damping
  stays independent of bias.
- **Input buffer OFF** (`status=0x00`). With AVDD on the 3V3 jumper the *buffered*
  common-mode range is only 0–1.3 V, but our bias sits at ~1.5 V — buffer on
  mangled the reads (chased this as a phantom wiring fault first). Buffer off gives
  the full 0–AVDD range; we don't need its high Zin (source is ~385 Ω).
- **Shunt (damping) resistor across AIN0/AIN1** goes in a **2-pin socket on the
  perfboard** (moved off the ADC screw terminals) — swappable by hand. Empty for
  now; tune empirically (~3–13 kΩ; clean single overshoot on the sampler).
- **Shield → AGND at the board end only** (floating at the geophone) — no ground loop.
- Coil is ~pure **385 Ω** in-band (measured; X_L ≈ 5 Ω @ 4.5 Hz negligible) — resistive network.
- **Sample rate:** DRDY-paced read sustains **~92 sps** at DRATE_100 on the Pi 2B
  (per-sample SYNC overhead nips just under the 100 nominal). Fine for viewing;
  the recorder will need a decide-the-rate strategy (accept ~92, or run DRATE_500
  and decimate to a clean 100).

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
- **miniSEED via `simplemseed`, NOT ObsPy, on the Pi.** ObsPy (scipy + matplotlib) OOM-wedged the 1 GB Pi 2B for an hour during install and is overkill for an acquisition daemon. `simplemseed` is pure-Python (numpy-only), installs in seconds, stays lean. ObsPy-based analysis (helicorder, response) belongs on the Mac, reading the Pi's files. If ObsPy is ever needed on the Pi, add a swapfile first (`CONF_SWAPSIZE=2048`) or it OOMs.
- **miniSEED specifics (v1):** int32 uncompressed (STEIM2 later), 512-byte records chunked at 100 samples, integer sample rate declared via explicit `sampRateFactor`/`sampRateMult` (simplemseed's auto rate-calc is broken). Rate is measured at startup (~56–57 sps, SYNC-limited) and each block is wall-clock anchored → accurate absolute time, ≤3 ms/block cosmetic overlap. Exact 60.000 sps would need ADS1256 RDATAC mode — deferred.
- **Passwordless SSH** from the Mac to `seismo.local` is set up (Claude can drive the Pi directly).

## Open threads (pick next session)

1. **Wire the ADC end** — differential + bias network + shunt in the screw terminals.
2. **Fast sampler** — read AD0/AD1 differentially at 100–200 sps, log + plot. ← software gate
3. **Tune the damping shunt** against the observed ring.
4. **Model the case walls + lid** (power cutout on +Y, dongle slot on −X; the Pi/geophone base is done) — mechanical, non-blocking.
5. Resolve the **5 V AVDD** jumper safely (noise floor).
6. Station software (miniSEED/helicorder) — `will127534/RaspberryPi-seismograph` is thin/stale; reassess.

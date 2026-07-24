# STATUS — Seismo

_Last updated: 2026-07-23 (UTC)_

## ✅ Galvanic Ethernet isolator INSTALLED and it LOWERED the noise floor (2026-07-23)

Measured, undisturbed, all late-night (comparable cultural noise):

| config | 1–15 Hz RMS | 3–15 Hz | 0.02–0.12 Hz | count range |
|---|---|---|---|---|
| baseline, no isolator (06:00–06:14) | 1.15 µV | 0.88 | 0.96 | 2,857 |
| isolator in, original orientation | 0.74 | 0.61 | 1.16 | 3,392 |
| isolator in, **reversed** (07:13–07:16) | **0.68** | **0.48** | **0.59** | **1,236** |

**~1.6× better in the signal band, ~1.8× in 3–15 Hz, and the DC bias is *more*
stable than without it.** Both orientations agree (it's a symmetric passive part,
so no one-sided shield bond). Keep it installed.

### The trap: this rig needs ~35 min to settle after being HANDLED
The install looked catastrophic for the first 35 minutes — 1–15 Hz hit 14–68 µV
with the DC bias wandering ±10,000 counts — and I (Claude) misread that transient
as a steady state and told Charles to remove the thing that was helping. **Don't
judge this front end for at least 40 minutes after touching it.** Evidence it's
handling, not the device: the initial install took ~35 min to settle, but the
reinstall took ~3 min and the reversal ~2 min. Mechanism is charge injected into a
high-impedance node — the common-mode path is the 2× 100 kΩ bias legs (the
*differential* path is already 375 Ω through the coil, so a shunt won't speed it up).

Diagnostics that separate "electrical fault" from "ground motion" in one number:
- **DC bias stability** (mean counts/minute). No earthquake moves the ADC's
  operating point; a wandering bias is always electrical.
- **Settling time.** A 4.5 Hz geophone rings out in *seconds* even undamped, so a
  minutes-long decay is an electrical node, not mechanics.
- Undervoltage was checked and ruled out: `throttled=0x0`, `in0_lcrit_alarm=0`,
  stable 57.0 sps, no stuck ADC codes. (Note: power is still **micro-USB** — the
  GPIO-header feed is still only a BACKLOG plan.)

**`events.log` is polluted for 06:15–07:13 UTC 2026-07-23** — the STA/LTA fired
every 10–20 s (peaks ~380 µV) through the unsettled period. Annotate/exclude that
window; those detections are not real.

## ⚠️ NEW EPOCH 2026-07-24 ~02:15 UTC — demo jumpers removed from AD0/AD1

**The entire archive before this timestamp was recorded with the Waveshare demo-sensor
jumpers fitted on the differential pair** (the block STATUS.md wrongly recorded as
"not jumpered"). Removing them moved the DC operating point from **0.27 % of FS to
3.96 %** — ~310,000 counts — and that shift **persisted** after VCC was reverted from
5V to 3V3, so it tracks the jumpers, not the supply fault. The input network was
electrically different for every measurement taken before this point.

The split is **analog vs digital**, NOT absolute vs relative. An earlier draft of this
note claimed relative A/B results survived because the network was constant across them.
**That is wrong** and has been retracted: if the parasitic network dominated the noise
budget, every ratio measured through it is compressed toward 1 by an unknown factor — a
real 5× isolator improvement would read as 1.6×. "Constant" is not "transparent", and we
cannot bound the distortion.

- **DEAD — anything measured through the analog front end.** Every noise figure, absolute
  *and* relative: the "electronics floor ~1.17 µV / 41 nm/s"; the **gain-64 / DRATE-60
  selection** from the noise sweep (the optimum may differ now); the **isolator's 1.6×**;
  **RDATAC's "+2.2 % in band"** cost; all **PPSD**; the **~1.002 Hz line** attribution.
  All of it needs re-measuring post-epoch.
- **INTACT — nothing to do with the input network.** The clock work (60.0054 sps,
  ClockAnchor, ±1–3 ms residual); continuity (RDATAC 0 gaps vs 41.2 s/hour legacy); the
  all-zero-frame glitch filter; all software, dashboard and infrastructure.
- **Unaffected qualitatively:** it recorded real ground motion — waveforms, the diurnal
  cultural pattern, the Berkeley M2.1 non-detection.
- **RE-TEST the ~1.002 Hz instrumental line.** It was never attributed, and a trimpot +
  photoresistor on the differential pair were never on the suspect list because this doc
  said the block was unpopulated. If the line is gone post-epoch, that was the cause.
- **First job once settled:** re-measure the noise floor and compare against the historical
  ~1.5 µV ambient / 1.17 µV floor. That quantifies what the old network was doing.

## 🐛 SOLVED 2026-07-24 — the "faux detection" population was a `peak_uv` bug

The long-standing mystery where detections clustered implausibly tightly (204–219 µV,
hour after hour) was **not a physical phenomenon**. `stalta.py` computed
`amp = abs(x) * uv_per_count` from the **raw** count, which carries the front end's DC
operating point — so whenever real signal was smaller than the offset, the reported peak
*was* the offset. Proof: DC sat at 0.27 % of FS = **211 µV** and the cluster was 204–219;
after the epoch change moved DC to 3.96 % = **3094 µV**, the cluster moved with it to
3106–3130. Fixed to use the high-passed `hp`. **Triggering was always correct** (the CF
already used `hp`); only the reported amplitude was wrong — so every `peak_uv` in
`events.log` before 2026-07-24 is garbage, but the detection times are fine.

Charles spotted the thread that led here by eye: pre-epoch noise was **one-sided**
(positive spikes, no negative). Measured: beyond 8σ, **+50 / −0** pre-epoch vs +25/−28
post-epoch; beyond 5σ, 20.6× asymmetric vs 1.02×. Ground motion is symmetric, so that was
a **rectifying nonlinearity** in the signal path — most likely ADS1256 input ESD-diode
conduction (datasheet: keep inputs within −100 mV of AGND and +100 mV of AVDD). It vanished
with the demo jumpers. This is further evidence the pre-epoch archive is not trustworthy.

## 🚗 Site ambient is TRAFFIC-limited, not electronics-limited (2026-07-24)

Charles correlated Highway 12 traffic (~300 ft / ~90 m from the station) with the live
waveform, consistent over dozens of cars: quiet gaps bottom out at **< ~1.5 µV RMS**, and
each passing vehicle drives it well above that. Vehicle-induced Rayleigh waves at 90 m are
a textbook dominant cultural source, broadband ~few Hz–tens of Hz, overlapping the
local-quake band.

**Consequences (do not re-litigate the noise floor without these):**
- The ~1.5 µV quiet floor is **site ambient, not the electronics floor**. Every raw-RMS
  figure taken here (1.17 µV historical, 2.4 µV tonight) is contaminated with real ground
  motion, so it is an *upper bound* on electronics noise, never a measurement of it.
- The **shorted-input floor test** (rev2-frontend.md) is the only clean separator of
  site-ambient vs electronics, and traffic proves the site term is large. Prioritise it.
- Daytime at this site is **cultural-noise-limited**. Pushing the electronics below
  ~1.5 µV only helps in the deep-night quiet window and the microseism band — it is not a
  bug to chase. The RS1D Sleeman self-noise benchmarks are vault instrument noise; our
  working floor is the site.
- Traffic is a **free, repeatable, on-demand test source**: after any front-end change,
  confirm the chain still responds by watching a car, without waiting for a quake.

## Plan (agreed 2026-07-23)

**Hands off the hardware until the weekend.** Let the current configuration run a
couple of days to get a feel for it, THEN tackle the 5 V AVDD fault (which unblocks
buffer-on, the biggest remaining noise lever -- see `doc/rev2-frontend.md`).

Current configuration = the first clean epoch: RDATAC 60 sps gapless, galvanic
isolator in (reversed), gain 64, garage slab, **no shunt damping fitted**. What two
undisturbed days buys, all passive:
- The **spike-rate test** that settles whether the 1-3 min spikes were electrical
  (BACKLOG "Suppress faux (cultural) detections") -- watch the 20:00-23:00 local
  window that ran 130-180/h.
- A meaningful **PPSD** (`analysis/ppsd.py`, epoch `rdatac-60sps`) -- it was
  pointless before because the archive mixed configurations.
- A baseline for the **QC counters** (`health.json`: dropped/glitches/spikes/stalls).
- A chance at a real local event.

Every touch of the rig costs ~35 min of settling and may start a new epoch, so if
something does get changed, write down the time.

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

**RDATAC CONTINUOUS SAMPLING — DEPLOYED (2026-07-23 08:56 UTC).** The recorder now
free-runs the ADS1256 in read-data-continuous mode (`station/rdatac.py`,
`SEISMO_RDATAC=1` in the unit). Measured: **0 gaps** vs **41.2 s lost per hour** on
the legacy per-sample-SYNC path, exactly **60 sps** declared and achieved (was a
load-dependent 54-57), and DRDY jitter of **1 us** instead of a ~68 ms discontinuity
at every 10 s block boundary.
- The crystal is not a clock: DRDY measures **60.0054 sps** against NTP time, i.e.
  ~90 ppm fast, so timestamping from sample count alone would drift 7.8 s/day.
  `ClockAnchor` predicts from a running anchor and slews a fraction of the error per
  block (cumulative rate estimate + 0.2 gain), holding residual clock error to
  **+/-1-3 ms**. Two independent methods agree on 60.0054.
- **NEW EPOCH.** Declared rate changed 57 -> 60, so files are not mergeable with the
  old archive. The 57 sps day-file was set aside as `*.mseed.57sps-epoch`; PPSD/
  template work starts from this epoch (`analysis/ppsd.py` epoch `rdatac-60sps`).
- A stuck chip (an RDATAC session that died without SDATAC) used to fail every later
  startup with "Received wrong chip ID" -- `adc_common._pin_reset()` now pulses the
  RESET pin before construction, so any tool recovers regardless of how the previous
  process exited.
- **NOISE COST: ~2% in band, ~20% at 15-28 Hz** -- measured BACK-TO-BACK in one
  session (`station/rdatac_noise_test.py`, 150 s per case, median of per-10 s band RMS):

  | case | 1-15 Hz | 3-15 Hz | 15-28 Hz |
  |---|---|---|---|
  | legacy | 0.7425 | 0.4859 | 0.2769 |
  | RDATAC 976 kHz | 0.7590 (+2.2%) | 0.5071 | 0.3334 (+20%) |
  | RDATAC 1.95 MHz | 0.7974 (+7.4%) | 0.5202 | 0.3491 |

  An earlier "+10% in band" figure was WRONG -- it compared windows 40 min apart with
  different ambient noise. Always A/B in the same session.
  The excess is injected HF (digital) noise, and it sits ABOVE the 1-15 Hz working
  band that every analysis path already low-passes -- so it is close to free.
  **Faster SPI is worse** (+7.4%), refuting "shorter burst = less coupling": faster
  edges couple more than the shorter duration saves. Keep 976 kHz.
  **CS cannot be toggled per read** in RDATAC -- releasing it aborts the stream
  (3737/3737 samples came back all-zero), so "CS held low" is not an adjustable
  suspect. Oversampling doesn't help either: per-sample noise scales with DRATE
  bandwidth (that IS what DRATE does), and RDATAC needs one SPI read per conversion,
  so a higher rate injects proportionally more bursts into shorter windows.
- **Glitch filter (needed):** roughly once per 100 s a read lands in the chip's
  register-update window and clocks out `0x000000`. Unfiltered that wrote a 200 uV
  single-sample needle -- enough to trip the STA/LTA and to make the drum look hairy
  (Charles spotted it as "hairy-er"). `rdatac.read()` now returns None for an all-zero
  frame or a late read (DRDY already high), the recorder holds the previous value, and
  the contaminated block's clock update is SKIPPED (the stall makes that boundary's
  wall-clock reading ~one sample period late, which would otherwise slew a fake error
  into the next boundary). Verified: 0 zero-samples, 0 needles, 0 gaps over 379 s.

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
  (To UPDATE: `sudo docker build` then `dokku ps:rebuild seismo` — `git:from-image`
  with the same tag reports "no changes" and skips.) Note: obspy compiles from source
  (no aarch64 py3.12 wheel) → the Dockerfile needs `build-essential`.
- **Helicorder v2 — DEPLOYED (2026-07-21):** precomputed-envelope drum, off the
  request path. `heli_build.py` reduces each 15-min interval to a fixed-width
  (min,max) envelope npz (`/data/heli`); `heli_render.py` stacks them into a
  1920×1080 drum with NO obspy; `heli_service.py` (daemon thread in the app)
  rebuilds+re-renders only on data change. Request cost is now O(1) served bytes,
  independent of viewers. High-pass 1 Hz kills tilt/drift. Design: `dashboard/
  HELICORDER.md`. Verified live on real 8 h data — scaling defaults look good.
- **Spectrum — still on-demand (SLOW): ~24–37 s per render on the pi5** (re-parses
  the whole day-file + Welch every hit — the same flaw the helicorder used to have).
  Moved OFF the home page onto a dedicated `/spectrum` info page (2026-07-21) so it
  no longer blocks the home load. TODO: give it the same background pre-render
  treatment as the helicorder (see BACKLOG "Helicorder v2").
- **Note:** the "does the 2B need a RAM upgrade" question is moot — it just acquires.

**Detection character badge** (2026-07-22): the detections table now labels each
trigger's waveform *shape* — `impulsive` / `sustained` / `near-threshold` — from
envelope kurtosis + duration-above-25%-of-peak + peak/median SNR, scored on the same
±30 s slice the sparkline already loads (14 ms/event, no extra I/O). Soft label only:
never filters, and NOT an earthquake classifier (a very local quake is impulsive too,
and there's no confirmed event yet to calibrate against). Thresholds measured from 127
real triggers; the backlog's HF/spectral-flatness idea was tested and **refuted** —
see `dashboard/CHARACTER.md`. The sparkline/character fill also moved **off the request
path** into a background thread (it was a ~90 s cold-start hang on the public page).

**Detections moved to `/detections`** (2026-07-23): the table is off the home page and
onto its own nav entry. Every trigger so far is a false positive, so it wasn't worth the
front-page real estate — and the home request no longer kicks off any sparkline/character
work at all (that background fill now only runs when someone opens `/detections`).

**Event detection** (2026-07-20): the recorder runs a streaming **STA/LTA** trigger
(`stalta.py`) inline — 1-pole high-pass (**3 Hz corner since 2026-07-22**, was 1 Hz:
rejects microseism *and* the sub-Hz tilt/settling that was mistriggering faux
high-ratio events — the old gentle 1 Hz pole passed 0.3–0.5 Hz nearly intact) →
energy CF → STA/LTA with the LTA frozen during events. Detections → journal (`EVENT …`), `~/seismo/
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
The ring carries `t_end` (UTC epoch of its newest sample, stamped by the station —
the pi5 mirror's mtime is only its own copy time), so the dashboard's strip-chart
draws a **scrolling UTC time axis**: 1 s minor ticks, labels + gridlines every 10 s
(2026-07-22). Falls back to no axis if a ring predates `t_end`.

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

- **Left yellow block** = the **AD input sensor-interface pinheader** (item 3 in the Waveshare manual: `VCC AGND AD7…AD0 D0–D3 P22–P25`), NOT jumpers and NOT SPI routing. It carries the SAME nets as the screw terminals. **Zero shunts fitted is correct** — it's a header for plugging in Waveshare sensor modules. (An earlier note here wrongly called it "SPI/GPIO routing, fully jumpered".)
- **Reference is an on-board `LM285-2.5`**, not the VREF jumper. The jumper only selects the LM285's bias source, so **v_ref = 2.5 V in every jumper position** — the hardcoded `2.5` in `recorder.py` / `live_server.py` / `render.py` is valid regardless of VCC/VREF selector position.
- **Waveshare's documented default is VCC→5V and VREF→5V** (manual §2.1). That makes our 5V failures a real fault on this board's 5V path, not a misconfiguration: it hard-locked the Pi once, and on 2026-07-23 (VCC→5V, all demo shunts removed) it produced a DC offset of −32% of full scale and ~1500× the normal RMS. Reverted to VCC→3V3.
- **`JMP_AGND`** (AINCOM ↔ AGND): jumpered — required for single-ended reads.
- **Right block top:** VCC selector (`5V/VCC/3V3`) = analog AVDD; VREF selector (`5V/VREF/3V3`). **Both on 3V3** (works). ADS1256 wants AVDD=5 V for best noise floor, but jumpering "to 5 V" **hard-locked the Pi even on a 2.5 A supply** → almost certainly a 3-pin cap shorting 5 V↔3V3. Revisit carefully, Pi OFF, pins verified.
- **Right block bottom:** the demo-sensor block (pot `ADJ`, photoresistor `LDR`). **It IS jumpered** (verified on the board 2026-07-23 — an earlier note here wrongly said "not jumpered"). Observed: the top four shunts sit **vertically** (`VCC→3V3`, `VREF→3V3`, `DAC1→LEDB`, `DAC0→LEDA`); the bottom two sit **horizontally** (`AD1—AD0`, `LDR—ADJ`). We use the **screw terminals** (`AD7…AD0 AGND VCC GND DAC1 DAC0`) for signal.
  - The above is **observed fact, verified visually on the board by Charles** (2026-07-23). Treat it as ground truth; do not re-derive it from the silkscreen legend or from photos.
  - Open question (does **not** cast doubt on the observation): the silkscreen legend would read `AD1—AD0` as bridging the differential pair, yet the front end demonstrably works (235 µV taps, real ground motion recorded). So the header's physical pin-to-net mapping is not what the printed legend implies. Resolve by buzzing out nets with a meter when convenient — it is a mapping question, not a fault.
  - Light sensitivity was tested and is **negative**: lights on vs off gave RMS 1.59 µV in both cases with near-identical spectra (`analysis/lights.png`), so the LDR is not coupling into the signal.

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

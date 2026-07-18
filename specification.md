# DIY Raspberry Pi Seismometer — Project Notes

**Goal:** A cheap, *sensitivity-first* (not precision-first) Raspberry Pi seismometer to detect local earthquakes, sited in Oakmont / Santa Rosa, Sonoma County — on top of the Rodgers Creek / Maacama fault system.

**Approach:** Incrementalism. Buy a known-good geophone + ADC, get a basic station running, then decide whether to graduate to a much more capable build later. (This project is competing with a CA Route 12 traffic counter for the "next project" slot.)

**Status (paused):** Parts selected. Geophone to be ordered from AliExpress; ADC to be ordered from a US reseller. Everything downstream (software, shunt-resistor sizing, bring-up) deferred until the geophone arrives.

---

## 1. The core decision

Sense ground motion with a **geophone** (a moving-coil velocity transducer) feeding a **24-bit ADC**. The geophone is the precision-mechanical part; the electronics are easy. The 24 bits of the ADC are what buy sensitivity — they pull the geophone's microvolt-range signal out of the noise.

Rejected alternatives and why (see Appendix A for the full tour):

- **MEMS accelerometer** — easy to wire, but it's a *strong-motion* sensor. Wrong regime for "I want to feel small/distant quakes." Even the good one (ADXL355) is strong-motion-class.
- **Building our own geophone** — technically possible, economically pointless (~$35 to buy), and the failure modes are sneaky (a bad homemade sensor lies to you silently).
- **Exotic schemes** (pendulum/lamp, carbon-granule, maglev) — instructive, but each has a fatal or hard flaw for a v1 instrument.

---

## 2. Frequency / sensitivity rationale (why 4.5 Hz, vertical)

Local-quake energy lives roughly in the **1–10 Hz** band, centered ~**2–5 Hz**. A geophone is flat in velocity *above* its corner (natural) frequency and rolls off hard *below* it. Design rule: **put the corner frequency at or below the bottom of the target band.**

- **10 Hz element** (SM-24, LGT-20D base) — corner sits *inside* the band; rolls off through the 2–10 Hz region we care most about. **Wrong tool.** (Note: "20D" / "LGT-20D" is a *family name*, not a frequency — always confirm the actual Hz, not the model name.)
- **4.5 Hz element** — flat from 4.5 Hz up; captures the upper two-thirds of the local band. The hobby sweet spot; what Raspberry Shake uses. **← chosen.**
- **2 Hz element** — captures nearly the whole local band, reaches toward regional events; pricier and more microseism noise. Diminishing returns for *local* Sonoma quakes.

**Vertical, not horizontal.** Vertical is the better-behaved axis. Horizontal geophones pick up wind and tilt noise (trees, building sway) even when buried.

---

## 3. Bill of Materials (v1)

| Component | Choice | Key specs | Source | Price | Status |
|---|---|---|---|---|---|
| Geophone | LGT-4.5 / EG-4.5-II class (SM-6 equiv) | 4.5 Hz vertical, 28.8 V/m/s, 375 Ω coil, damping ~0.6 | AliExpress (KRYOND Electronic) | ~$30.96 + $1.61 ship ≈ **$36 landed** | **To order** |
| ADC | Waveshare High-Precision AD/DA Board | ADS1256, 8-ch 24-bit ADC; DAC8532 (unused) | **PiShop.us** (US, authorized reseller) | **$43.95**, in stock | **To order** |
| Compute | Raspberry Pi (already owned) | Pi 5 / Pi 2B / etc., 40-pin GPIO | on hand | — | Have |
| Damping | Shunt resistor across coil | value TBD (see §5) | TBD | ~$0 | Compute later |
| Enclosure | 3D-printed | — | Bambu A1 Mini (on hand) | filament | Later |

**Geophone listing note:** the AliExpress title says "LGT-20D 4.5 Hz," but the actual unit is an **LGT-4.5** and the spec confirms 4.5 Hz (±0.5) and 0.288 V/cm/s = **28.8 V/m/s**. This is the *standard* element, not the 100 V/m/s high-sensitivity variant (that one was $200+ and overkill for v1). 90-day returns cover a DOA element; max 1 per buyer (no spare in the box).

**ADC sourcing decision:** buy from the USA, not AliExpress. The ~$15 saving isn't worth the clone risk on the one component that sets the **noise floor** — and a US in-stock board arrives in days, so software can be developed against real hardware while the geophone is still in transit. (If buying the board from AliExpress later, only do so from the **Waveshare Official Store**, and confirm the photos show the Waveshare silkscreen, 40-pin header, ADS1256 + DAC8532, and the on-board demo cluster — pot, photoresistor, LEDs, screw terminals. A bare "ADS1256 breakout" is a *different* board with a different pinout.)

---

## 4. Software plan

- **Seismograph stack:** `will127534/RaspberryPi-seismograph` (and the **Seisberry** / Erellaz fork). Open source; drives this exact Waveshare board; outputs to a local web view and/or miniSEED. *(Repo currency not yet verified — we paused before checking.)*
- **ADS1256 Python library:** `ul-gh/PiPyADC` (good, well-documented).
- **Pi OS note:** on **Pi 5 / Bookworm**, only the `lgpio` library works — the older `bcm2835` / `wiringPi` drivers do **not**. One-line config difference; the seismograph stack should handle it.
- **Sampling rate reality:** seismology samples at **100–250 sps** (Raspberry Shake = 100 sps). The ADS1256's 30 ksps spec is irrelevant, and the board's known Pi SPI-timing limit (gets noisy above ~2 kHz) **does not affect us** — we operate two orders of magnitude below where trouble starts.

---

## 5. Open technical items (compute when wired)

- **Shunt damping resistor.** The element's open-circuit damping is ~0.6; for a flat response we want ~0.7 of critical. A shunt resistor across the coil sets this. Value depends on coil resistance (375 Ω) and the ADC board's input impedance — **size it once the board is in hand and measurable.** Without it, the raw output rings at 4.5 Hz (same pathology as an undamped pendulum).
- **Siting.** Solid concrete slab, lowest floor, good ground coupling, away from HVAC / appliances / foot traffic.

---

## 6. Bring-up order of operations

Order matters — it isolates "is my ADC chain working?" from "is my geophone working?":

1. **ADC arrives first** (US shipping). Mount on the Pi, enable SPI.
2. Run Waveshare's demo or PiPyADC; confirm **clean voltage reads off a known source** (a battery works).
3. **Only then** introduce the geophone, so you're debugging one new variable, not two.
4. Add the shunt resistor; verify the resonance is tamed.
5. Stand up the seismograph software; log + view.

---

## Appendix A — Alternatives considered (and verdicts)

Kept so we don't re-tread these:

- **Hall lamp pendulum (~0.5 Hz).** Right physics — a pendulum *is* a seismometer, and its low corner beats a 4.5 Hz geophone on paper. But: undamped high-Q → rings at its own 0.5 Hz instead of tracing the quake; horizontal only; noisy hall (drafts/HVAC/footsteps); chain+wire pivot is nonlinear; and it can't be physically modified (cosmetic constraint). Camera/OpenCV tracking solves the *pickup* non-invasively but **not** the ringing. Verdict: a *detector*, not a seismometer. Good intuition pump. (Aside: 10 ft drop, CoG ~9 ft, observed 0.5 Hz is *faster* than a 9 ft simple pendulum predicts → compound-pendulum mass distribution + wire bending stiffness raise the frequency.)
- **Carbon-granule (telephone-mic) inertial sensor.** Right transduction instinct (resistance ∝ force), but carbon beds have heavy **1/f noise** — worst exactly in the low-frequency seismic band — and **pack** under a sustained static mass, so it drifts and self-destructs. Verdict: at best an AC-coupled tremor detector. The clean version of this idea is a **strain-gauge / load cell**; the dirty modern version is an FSR (same pathology).
- **Two-magnet maglev + coil.** Least crazy — it's a rediscovery of the real **magnetic-suspension geophone** (published: ~0.59 Hz, 412 V/m/s). The magnetic spring gives low corner frequency from geometry, no spring sag. Catch: **Earnshaw's theorem** — you can't passively, stably levitate a permanent magnet. Escapes: (a) tube constraint → works, but wall **friction** is the noise floor; (b) diamagnetic stabilization → contactless but weak/tiny mass; (c) **active feedback** → which *becomes* force-balance (see Appendix B). Verdict: passive tube version buildable but friction-limited; the idea points straight at the real upgrade.
- **DIY moving-coil geophone (2 / 4.5 Hz).** Hard, no cost advantage, sneaky failure modes. Skip.
- **MEMS accelerometer.** Easy, wrong regime (strong motion). ADXL355 (~22.5 µg/√Hz, used by OpenEEW) is the only usable one and still strong-motion-class; MPU6050 / ADXL335 are useless for weak motion.
- **Lehman horizontal pendulum.** The proven DIY long-period path (low frequency from geometry, not springs). But horizontal → wind/tilt-noisy. A real option if going broadband, but vertical force-balance is preferred.

---

## Appendix B — Future upgrade path ("much better than a geophone")

If the eventual goal becomes a *science-grade broadband instrument* (record teleseisms from across the planet, faithful waveforms), the dividing line is **force-balance feedback** — servo the proof mass to stay still and measure the restoring force. That's what crosses from short-period (geophone) into broadband.

- **Reference build:** the **Inyo Force-Balance Vertical (FBV)** by Dave Nelson & Brett Nordgren, via the **Public Seismic Network (PSN)**. Free CAD, schematics, and feedback-loop modeling tools. Achieves commercial-grade performance (one of their units: flat ~50 s → 30 Hz, ~27,700 V/m/s high-gain output).
- **Build vertical, not horizontal** (horizontal is wind/tilt-noisy even in a vault).
- **Scope:** a serious multi-month project — precision mechanics + low-noise analog + a control loop + a stable pier. The ADS1256 is fine as the digitizer; the hard part is upstream.
- This is also where the maglev idea converges if pushed to its stable conclusion.

---

## Reference links

- Waveshare board wiki: https://www.waveshare.com/wiki/High-Precision_AD/DA_Board
- ADC board (US): https://www.pishop.us/product/raspberry-pi-high-precision-ad-da-expansion-board/
- PiPyADC (Python ADS1256): https://github.com/ul-gh/PiPyADC
- Seismograph stack: github.com/will127534/RaspberryPi-seismograph *(verify current)*
- Public Seismic Network (force-balance, future): http://psn.quake.net/
- Nordgren force-balance designs: https://bnordgren.org/seismo/

*(Marketplace URLs intentionally omitted — AliExpress/eBay listings rotate and expire. Search the part numbers above.)*

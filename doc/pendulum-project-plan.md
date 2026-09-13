# Project plan — a calibrated, printable 1 Hz horizontal pendulum

**Status:** planning, 2026-09-12. Nothing built. Sits behind the calibration injector and
the CLUE-sensor replacement in priority, but **phase 0 and phase 1 need neither** and can
run in parallel.

**Background and physics:** `BACKLOG.md`, addendum 2026-09-12 under the Lehman entry. That
block holds the derivations (alpha = 90 deg tilt insensitivity, why 1 Hz rescues printed
mechanics, the coil equations and the two damping/SNR theorems). This file is the plan
only; do not duplicate the physics here.

## The thesis, stated so it can be falsified

> A printed, sub-$100, single-axis 1 Hz horizontal seismometer whose builder ends up with
> **their own measured G, f0 and zeta and a StationXML file**, produced with tools they
> also printed.

The contribution is the **calibration procedure**, not the sensor. The amateur corpus is
almost entirely uncalibrated — it publishes counts, not m/s, so the data cannot be stacked,
deconvolved or joined to a network. Filling that cell is the point.

Validation reference: **NP.1835**, 3-component strong motion, 1.6 km away.

## Ground rules

1. **End-to-end before polish.** No tooling, no docs, no second unit until one instrument
   round-trips from ground motion to m/s.
2. **Every sustained load goes through metal.** Printed parts in compression or
   non-load-bearing. Creep is the one polymer failure mode we cannot filter out.
3. **Nothing structural over 180 mm** (A1 mini). The 248 mm span is bought stock; the
   enclosure is drain pipe with printed caps.
4. **Measure, do not predict.** Bbar is uncertain to 2x and it does not matter, because
   every G is measured per unit.
5. Each phase has a **gate** below. If the gate fails, stop and re-plan rather than
   pressing on — the failure is the result.

## Phase 0 — the bench DAQ ("excite and record")

The dependency of every measurement in the project. One weekend if scoped hard.

- ESP32-S3, **ADS1220** differential in (NOT the ADS1115 — 16 bits at 7.8 uV/LSB is fine
  for ringdowns and useless for anything else; the ADS1220 is already in the field-rig
  plan, so it is one fewer part family to learn).
- **A programmable current output driving the coil.** This is the feature that matters —
  with excitation AND acquisition it is a network analyzer for mechanical systems, and it
  serves the injector bench work, the ADXL355 node and the field rig as well.
- USB-C, CSV over serial. **No wifi, no SD, no display.** Feature creep here eats a month.
- Host side: Python capture + ringdown fit. Reuse `analysis/ringdown.py`.
- Self-test: shorted-input noise floor, and a known signal from a divider.

**Gate:** shorted-input noise floor measured and written down. If it is not well below the
expected ringdown amplitudes, the rest of the plan is measuring the DAQ.

## Phase 1 — the crude throwaway

Charles's framing: *"as quickly, cheaply, and crudely as possible... who cares if I screw
it up? Only then do we fully scope the project because we've done it once before and our
scoping has priors."* ~2 weekends.

A throwaway is only worth building if it names in advance the unknowns it retires:

| unknown | how phase 1 retires it |
|---|---|
| **G** | two ringdowns (coil open, then shorted): `G = sqrt(dzeta * 2*m*w0*R)` |
| does shunt damping alone reach zeta ~0.7 | falls out of the same pair |
| **is the suspension clean** | envelope SHAPE: exponential = viscous; LINEAR = Coulomb friction, hinge rubs, that design is dead |
| f0 vs the 248 mm prediction | how much stiffness the flexure adds |
| the air term | lid-on vs lid-off zeta_mech |
| light bob vs heavy bob | the open fork: shunt damping wants light, draught immunity wants dense — see BACKLOG |

Build: 20-30 g magnet stack in a **located printed pocket** (gap repeatability dominates
magnet-grade tolerance); 248 mm pivot-to-bob on metal stock; **both suspensions tried**
(bifilar fine wire in one plane, and feeler-gauge strip) since the suspension is the only
part worth iterating; scrounged transformer primary as the coil — no coil design needed,
because G is measured; cardboard box; phase-0 DAQ as readout.

Cross-check G by **step-tilt integration** (below). Two independent routes to G on the
crudest possible hardware is the whole point.

**Do not wire it into the station.** Every question here is a bench question, and touching
`recorder.py` to add a channel is production risk for zero prototype value.

**Gate:** a numbers table, and an answer to the suspension question. If every suspension
variant shows Coulomb decay, stop — the topology needs rethinking (capacitive sensing, a
different hinge) and the plan below does not apply.

## Phase 1.5 — scope the real project

An explicit stop. Re-estimate everything below with priors from phase 1, and re-decide
whether the contribution is worth 3-6 months. This is the checkpoint the whole
crude-first approach exists to create; skipping it wastes phase 1.

## Phase 2 — unit 1, designed and calibrated

~1 month. The first thing that is an instrument.

- Designed coil, hand-wound on a printed bobbin (see BACKLOG for G = N*Bbar*l_turn and the
  gauge/damping theorems — gauge is chosen to match the preamp, not for SNR).
- Designed magnetic circuit; Bbar pinned with the Hall jig or FEMM.
- Drain-pipe enclosure, printed caps, printed **kinematic mount** (3-groove Maxwell) so the
  unit can be removed and replaced identically.
- Preamp — the coil's Johnson noise is below the ADC floor, so the ADC is the limit.
- Reciprocity calibration via the phase-0 DAQ; `ringdown.py` fits it.
- Response file, StationXML, onto the station as a real channel.

**Gate:** the channel reports **m/s** and agrees with NP.1835 on a real local event. If it
does not, the calibration methodology is wrong — and the methodology IS the contribution,
so nothing downstream is worth building until it agrees.

## Phase 3 — tooling for replication

~1 month. **Third, not first.** The winder is a tool for making MANY coils and until phase
2 we do not know which coil.

- Coil winder: stepper traverse + spindle + turns counter, printed.
- Hall-probe jig for incoming magnet QC.
- Isolation bench (paving slab on sorbothane, printed cups).
- BOM and build guide, written as someone else would follow them.

## Phase 4 — units 2 and 3, the repeatability study

~1 month. **This is the scientific content.** One unit cannot support a repeatability
claim; the deliverable is the table of unit-to-unit spread in G, f0 and zeta, built to the
phase-3 written procedure by following it rather than remembering it.

**Gate / fallback:** if spread in G exceeds ~30% and cannot be reduced, the "repeatable"
claim fails — but the fallback is still valuable: *individually calibratable* rather than
*identical*. Say which one the data supports; do not quietly ship the stronger claim.

## Phase 5 — release

Repo (probably its own, split out of Seismo), docs, a response-file generator, writeup.
Venues: the amateur networks first (PSN, Raspberry Shake community), then an SSA/SRL
abstract if phase 4 holds up.

## Calibration methods, ranked

| method | cost | gives | notes |
|---|---|---|---|
| two-ringdown | free | G, f0, zeta | phase 1; no injector, no reference needed |
| step-force release | free | stiffness, f0 | known small mass on a thread, cut it |
| **step-tilt integration** | ~$0 | **G, absolute** | see below |
| comparison vs ADXL355 | free later | G, absolute | needs a LARGE deliberate transient |
| shake table | high | linearity only | **not a calibrator** without motion metrology |

**Step-tilt integration.** Tilt the instrument by a known small angle theta; the bob hangs
along gravity so it moves to a new equilibrium `dx = L*theta` relative to the frame. Since
`V = G*dx/dt`, integrating the coil output through the transient gives

    integral(V dt) = G * L * theta

theta comes from a shim of measured thickness over a measured baseline. **Traceable to
gravity and a caliper, with no reference instrument in the chain.** This is the independent
check on reciprocity.

**Why not a shake table:** a shaker with no independent motion reference is a stimulus, not
a calibration. Knowing the platform's actual motion needs an interferometer, LVDT or
optical encoder, and that metrology costs more than everything else here combined. Build
one later for linearity and cross-axis tests, where only relative motion matters.

**ADXL355 caveat:** factory-calibrated, so a genuine transfer standard, but its self-noise
at 1 Hz is ~25 ug/rtHz ~ 245 um/s^2/rtHz — tens of times above typical ambient. Comparison
works against a hammer blow, not against background.

## Known open questions

- **The bob-mass fork.** Shunt damping wants ~20 g (zeta ~0.9, trimmed by one resistor);
  draught immunity wants dense and heavy. Phase 1 settles it. Do not decide it on paper.
- **Bbar** — uncertain to 2x until the Hall jig or FEMM says otherwise. Affects the coil
  design in phase 2, nothing in phase 1.
- **Magnet temperature coefficient.** NdFeB Br runs -0.11 %/degC, so a 10 degC swing moves
  G by 1.2% and zeta_e by 2.4%. Not a design problem — an argument for the injector's
  4x/day cadence, which turns it into a logged, fitted series. Log temperature alongside.
- **Whether this becomes its own repo.** Deferred to phase 5.

## Budget

    bench DAQ (ESP32-S3, ADS1220, driver, box)        ~$40
    per unit (magnets, wire, stock, pipe, filament)   <$100
    coil winder (stepper, driver, printed)            ~$40
    3 units + tooling, all in                         ~$400

## Parts to order (long lead — do this first)

Ordering is the one thing with lead time that carries **no freeze risk**, unlike a PCB.
Get it out before any bench work starts.

| qty | part | why |
|---|---|---|
| 2 | **ESP32-S3-DevKitC-1 (N16R8)** | the DAQ, and the ADXL355 bring-up (STATUS: may not have a bare one) |
| 2 | **ADS1220 breakout** — ProtoCentral is the best-documented | the DAQ; the second goes to the field rig |
| 4 | **DPDT latching signal relay, 5 V** (Panasonic TQ2-L2-5V class) + ULN2003 | the resistor bank. **Latching**, so no coil field sits next to the magnet during acquisition |
| — | **0.1% metal film: 100R, 470R, 2k2, 10k, + 100R sense** | the zeta-vs-1/R bank; this tolerance lands directly in G |
| — | **N42 discs, assorted** (10x5 mm, 12x3 mm packs) | bob stacks — buy variety, phase 1 is an experiment |
| 1 ea | **Magnet wire AWG 38 and 40**, 250 g | phase 2, but long lead and cheap |
| 1 | **Feeler gauge set** | flexure strip stock, and a measuring tool regardless |
| — | **Plain steel guitar strings .009-.012** | bifilar suspension wire |
| 1 | **1 mm aluminium sheet** | eddy-damping plate |
| 5 | **SS49E Hall sensors** | magnet QC jig |
| 1 | **Fuzion 500 g x 0.01 g scale** — ORDERED 2026-09-12 | NOT optional: **G ~ sqrt(m)**, so bob mass is a calibration input. Chosen because it PUBLISHES a permissible error (+/-0.02 g); nearly nothing in the category does, and "0.01 g accuracy" elsewhere is readability wearing accuracy's clothes. 500 g not 200 g, so the heavy-bob branch of the mass fork still fits |
| 1 | **Fuzion 9-pc M1 weight set, 1-100 g** — ORDERED 2026-09-12 | Substitution weighing (`m = m_ref * reading/reading_ref`) cancels the scale's span error, so the scale never needs calibrating — but the reference must be CLOSE to the unknown, since cheap load cells are least linear low in range. An independent A&D FX-120i test (Amazon review) put the two 20 g pieces at +3 and -3 mg, i.e. ~7x better than needed; the two 2 g pieces fail M1 at +5/+6 mg and we do not care. 200 g for the scale's own CAL routine is reachable by stacking 100+50+20+20+10 |

**Hardware store, no lead time:** 4" PVC drain pipe, metal stock for the 248 mm span,
sorbothane pucks or tennis balls, a paving slab.

**Probably in hand:** Neutrik XLR panel jack, perfboard, headers, power bank.

### Weighing gotcha specific to this project

**Neodymium stacks on a stainless pan read heavy.** The magnet attracts to any ferrous mass
below it — pan, load-cell frame, steel bench — and that force adds to the reading in GRAMS,
not milligrams. It can also snatch the stack off the pan and chip it.

  - weigh magnets in one of the scale's plastic trays, never on the bare platform;
  - stand the scale on wood or plastic, never a steel bench;
  - **self-test: weigh the stack on the pan, then on a 30 mm plastic riser. If the readings
    differ, magnetic coupling is present and the lower one is closer to true.** Raise it
    until the reading stops changing.
  - keep the weight set well away from the magnet bench — cheap "stainless" is often
    ferromagnetic 400-series.

Handling degrades weights faster than manufacturing does: tweezers every time, back in the
box, and not stored in the garage where they will pit.

## PCB — the existing rule applies, and it says not yet

`BACKLOG.md` "Custom PCB — do it, but only once Rev-2 is frozen" (2026-07-23) already
settles this: *prototype on perfboard -> shorted-input floor test -> lock values -> then
lay out.* A PCB freezes a design and this one is not frozen.

The justification does not transfer anyway. What earns the Rev-2 front end a board is that
it is a **microvolt** path (ground pour, symmetric pair, star ground, microphonics). **The
DAQ handles millivolts** — a ringdown starts near 160 mV — so perfboard with modules is
adequate, not a compromise, and the same shorted-input floor test proves it.

Where a board does earn its place is **phase 3, for replication**: nobody reproduces a
perfboard, and gerbers are the deliverable. Middle path if wanted sooner: a dumb two-layer
**carrier** for the modules (headers, ground plane, through-hole passives, no SMT), ~$25
for five, bodgeable. Residual risk is footprints of modules not yet held — the shape of the
ADXL355 failure — but a wrong carrier is a $25 lesson.

Vendors: **JLCPCB** cheaper, LCSC/EasyEDA integrated, better for own builds. **PCBWay**
pricier but has one-click project sharing, which matters at phase 5 for an open-hardware
release. Same gerbers; use both.

**Layout tooling is still an open question** — `doc/rev2-frontend.md:297` records KiCad
created and deleted (Charles dislikes schematic capture). Untried alternatives: SKiDL,
atopile, EasyEDA. The carrier board would be a cheap place to settle it, at phase 3.

## Rough total

**3-6 months of hobby weekends** to a publishable release, assuming the gates pass.
Documentation will dominate; every open-hardware project underestimates it by 3x.

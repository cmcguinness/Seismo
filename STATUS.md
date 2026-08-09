# STATUS — Seismo

_Last updated: 2026-08-07 (UTC)_

## ✅ REBUILT FRONT END CHECKS OUT ON THE BENCH (2026-08-07)

Interface board rewired (same circuit), geophone in its printed case, XLR panel connector
and cable in the chain for the first time. Read from the ADC side, on the bench, ~3 min
after power-up (i.e. **not settled** — see [[settling-time-after-handling]]):

| check | known-good 2026-08-03 | now | Δ |
|---|---|---|---|
| AIN0 / AIN1 single-ended, **gain 1** | 1.528 / 1.524 V | 1.516 / 1.513 V | −0.8 % |
| DC counts @ gain 64 | 336,304 | 330,110 | −1.8 % |
| DIFF @ gain 64 | 3.026 mV | 3.074 mV | +1.6 % |

The standing differential offset is bias current through the coil, so its presence proves
the DC path is continuous **through both new connector pairs** with no added series
resistance worth measuring. Landing within 2 % of the pre-rebuild operating point is the
confirmation.

**Noise** (gain 64, median of per-10 s band RMS — comparable to every other table here).
Three captures: two unsettled 120 s runs bracketing a `JMP_AGND` remove/replace, then a
300 s run after **35 min undisturbed**.

| band (µV) | on, unsettled | off, unsettled | **ON, SETTLED** | garage ambient | V1 elec floor |
|---|---|---|---|---|---|
| DC counts @ g64 | 330,110 | 330,741 | **330,808** | — | — |
| 0.02–0.12 Hz | 0.88 | 4.30 | **0.54** | 0.80–0.90 | — |
| 1–5 Hz | 2.02 | 2.21 | **1.64** | — | — |
| 1–15 Hz | 15.97 | 18.02 | **11.07** | 2.74 | 1.18 |
| 10–15 Hz | 17.33 | 18.67 | **11.07** | — | — |
| 15–28 Hz | 35.31 | 39.26 | **10.12** | 5.69 | 1.08 |
| 19–21 Hz | 7.99 | 9.09 | **3.08** | — | — |

- **Settling is worth 3.5× at 15–28 Hz and 8× sub-Hz.** Reconfirms
  [[settling-time-after-handling]] — do not read a noise number within 35 min of a touch.
- **The residual 1–15 Hz excess is still all the 10–15 Hz hump**; 1–5 Hz is 1.64 µV, *below*
  the garage number. Benchtop mechanical noise, not electronics. Re-measure on the slab.
- Figure: `analysis/bench_rebuild_2026-08-07.png` (settled trace + both spectra).

### `JMP_AGND` on vs off: no effect on the signal path (2026-08-07)

Pulled and replaced while measuring. **DC operating point identical across all three runs
(0.2 % spread)** — expected, since AINCOM is only a mux input node and the common mode is
set by the 100 k pull-up / 100 k pull-down against the board rails. The ~10 % apparent rise
with the jumper out was settling, not grounding: it lifted *every* band uniformly including
the 19–21 and 40–42 Hz mechanical lines, and the settled run came in far below both.

**Keep the jumper fitted.** It buys nothing measurable to remove, and without it the
single-ended BIAS check — the one 10-second reading that localizes a lost DC path — reads
both legs at an arbitrary −0.38 V and is useless. Refitted, they read 1.515 / 1.514 V.

**The 19.95 / 41 Hz line pair is still present on the bench** (7.99 µV at 19–21, 9.71 µV at
40–42) — different room, rebuilt board, new cable. Combined with the negative coupling test,
that points at the **instrument**, not any structure.

### ⚠️ adc_diag's BIAS check RAILS at any gain above 1 — and reads as a real voltage

At gain 64 the single-ended FSR is ±78.125 mV, so the ~1.5 V bias legs peg and print as
"+0.078 V" — which looks exactly like the floating-pair signature this project has already
chased once. **Always run the BIAS check with `SEISMO_GAIN=1`.** `adc_diag.py` now prints
the correct FSR (it previously mislabelled it ±VREF/gain) and appends `<-- RAILED` when a
leg is within 1 % of full scale.

**Open, pre-existing:** gain 1 and gain 64 disagree by ~2× on the differential offset
(7.78 vs 3.07 mV today; 6.31 vs 3.03 mV on 08-03). Predates the rebuild — a scaling bug in
the gain-1 path, not a hardware change. Trust gain 64; it is what the recorder runs.

## ✅ FAULT FIXED 2026-08-03 — it was a STRAY SHIELD STRAND, not a bias resistor

**Root cause: a single whisker of the cable's shield braid making intermittent contact
with a coil wire.** Charles found and cleared it on the bench. Everything below in the
"faulted" section is retained for the diagnostic trail, but **its hypothesis was wrong** —
it blamed a bias-resistor leg or a cold-flowed ferrule, and the real failure was a loose
braid strand. Different failure, different prevention: **terminate the shield properly**
(comb the braid, twist to one pigtail, sleeve/heat-shrink right up to its landing) rather
than trusting ferrules to fix it. The shield lands at the board end only, right next to
the input terminals — that is the one place in this build where a stray strand can reach
a signal leg. Carry this into the rev-2 layout and the case wiring.

**Confirmed restored** (bench, geophone attached, `adc_diag.py` + `capture_raw.py`):

| | faulted | after fix |
|---|---|---|
| AIN0 / AIN1 (single-ended) | −1.224 / −1.225 V | **+1.528 / +1.524 V** |
| DIFF @ gain 64 | −78.125 mV (railed) | **+3.026 mV** |
| DC, raw counts @ gain 64 | −2,174,268 | **+336,304** (baseline ~334,000 — **0.7 %**) |

Landing within 0.7 % of the pre-fault operating point is the strong confirmation: nothing
else drifted.

### Diagnostic lessons from this session (worth more than the fix)

- **`adc_diag.py`'s BIAS check is single-ended vs AINCOM**, so it is only meaningful with
  `JMP_AGND` fitted. With the geophone connected, healthy is ~1.5 V on both legs; **both
  legs equal but at an arbitrary/negative potential means the pair is FLOATING**, because
  the coil ties them together. That one reading localises the fault to the DC path.
- **The rev-1 topology is a series divider** — `V+ –100k– AIN0 – coil – AIN1 –100k– GND`,
  shield to GND, no damping shunt fitted. It is NOT a common-node bias. Consequence:
  **a single open 100 k floats BOTH legs**, because there is only one DC path. (I argued
  the opposite from the rev-2 schematic during this session and was wrong — `doc/rev2-frontend.md`
  describes the *replacement* board, not what is built.)
- **The design's own arithmetic checks out:** 3.3 V / 200 kΩ = 16.5 µA through the coil,
  × 375 Ω = **6.2 mV** standing differential offset. Measured at gain 1: **+6.308 mV**.
- **`adc_diag.py` prints full-scale as ±VREF/gain; the ADS1256's FSR is ±2·VREF/gain.**
  Its gain-64 "±39.1 mV" is half the true ±78.125 mV. Convert via raw counts, not its mV.
- **Do not diagnose off "seems better" after reseating a connection.** A reseat that
  changed nothing measurable read as an improvement; the ADC said otherwise.

## ✅ V1 ELECTRONICS NOISE FLOOR MEASURED (2026-08-03) — and it bounds rev-2

The **shorted-input floor test** that `BACKLOG.md` puts in the rev-2 critical path is
**done**, on the bench, geophone disconnected, cable terminated at its far end. Settled,
RDATAC, 100 sps, gain 64 — same statistic as everything else in this file (median of
per-10 s band RMS, µV), so the columns are directly comparable.

| band | 0 Ω short | 330 Ω source | garage ambient (100 sps epoch) |
|---|---|---|---|
| 1–15 Hz | 1.176 | **1.179** | 2.74 |
| 3–15 Hz | 0.968 | 1.023 | 2.62 |
| 15–28 Hz | 1.077 | 1.240 | 5.69 |

- **The old "~1.17 µV electronics floor" was right after all.** It sits in the DEAD column
  because it was measured through the demo-jumper network; the clean re-measurement lands
  on **1.176 µV**. The figure is now re-established on valid hardware.
- **Source impedance costs nothing in the quake band.** 1.179 vs 1.176 µV is noise. The
  penalty is HF-weighted (+15 % at 15–28 Hz), consistent with switched-cap sampling noise,
  and above the band of interest. **BACKLOG item 2 (input RC + charge reservoir) is worth
  ~0 % in 1–15 Hz** — an earlier +4.6 % reading was an unsettled measurement, not physics.
- **Electronics are ~10 % of the in-band noise.** Noise adds in quadrature: at 2.74 µV
  ambient, site alone is √(2.74² − 1.18²) = 2.47 µV. Removing the front end *entirely*
  buys 2.74 → 2.47. **Buffer-on and 5 V AVDD cannot beat that ceiling.**
- Caveat: measured in the bench's EM environment, not the garage's. Re-run once in place.

### 🔀 DECISION (2026-08-03): rebuild V1 ruggedly; do NOT chase rev-2's noise features

The failure was **mechanical**, and the measurements say the circuit is not the problem.
So: **same topology, same values, better mechanics** — rigid mounting instead of a rat's
nest, shield combed/twisted/sleeved to its landing, strain relief both ends, XLR panel
connector for a real service disconnect. This also keeps the archive comparable, because
the epoch change becomes mechanical only rather than mechanical *and* electrical.

- **Still carry over: the input anti-alias RC.** That one is *correctness*, not noise — at
  100 sps, 60 Hz mains aliases to 40 Hz, and no digital filtering afterwards can undo it.
- **DEFER the LC Tech ADS1256_V1.1 swap.** Its whole draw was enabling buffer-on at 5 V
  AVDD, and that payoff is now measured as small. It is also the riskiest item on the list
  (unmetered P1→ADC R/C network, new epoch, unfamiliar board).
- **Shunt damping is the last step, and it is a real tradeoff, not a default.** No shunt is
  fitted today. Size it by *measurement* (tap the element, take the log decrement of the
  ring-down, solve for the difference to target), not from the datasheet. And note a shunt
  damps by loading the coil, i.e. **it costs sensitivity** — with absolute calibration
  already ~7.5× low and the project explicitly sensitivity-first, deliberate under-damping
  is defensible. Do it last, in the garage, against a stable baseline.

## 🧰 Pi + front-end CASE — modelled, coupon validated (2026-08-08)

**`parts/pi_case.py` — 168 × 164 × 93 mm, ~454 g PLA.** Minimal tier (Charles's call):
base + lid + handle, three panel jacks, boards on standoffs. No gasket, vents, inserts or
labels. Plan + elevation: `parts/pi_case.png`.

### ✅ Coupon results (2026-08-08) — both open connector questions closed

`parts/panel_coupon.py`, 80 × 106 × 3 mm, ~27 g, printed and fitted against the real parts:

- **Barrel jack → the rung labelled `12`.** `barrel_bore_dia = 12.0`, no longer provisional.
- **RJ45 coupler mounts fine in the D-series cutout**, so **Ethernet and XLR are the same
  cutout** — the pattern already validated by `xlr_coupon.py` covers both.

The ladder-of-candidate-bores approach is worth reusing: it answers "what size is this
thread" for ~27 g *including* print shrinkage, which a caliper reading does not.

### Design rules this case is built on

- **SIZE IS DERIVED from a bay table**, not chosen, so a corrected component dimension
  rescales the case instead of forcing a redesign.
- **Generous margins are deliberate** (Charles, forcefully, 2026-08-07): do not design a
  box so tight that everything must be perfect or it is scrap. 12 mm wall clearance,
  20 mm between rows, and a NAMED `iso_allow = 10 mm` on the isolator bay.
- **The unvalidated dimension never goes in the expensive part** — *while it is still
  unvalidated*. The barrel bore briefly lived on a removable 48 × 48 × 3 plate for exactly
  that reason. The coupon then validated it at 12 mm on this printer and filament, so the
  risk was gone and **the plate was deleted rather than carried as dead weight** (it cost a
  part, four screws and a 34 mm opening). The case takes a plain bore. The lesson is the
  pattern, not the plate: isolate a guess until it is settled, then remove the scaffolding.
- **Connectors ride ABOVE the boards**, so no floor is reserved behind them. The XLR's
  32 mm body intrudes at its own height, costing Z (180 mm available) instead of Y (which
  was fighting the bed). The tall upper cavity is where the coiled patch cable lives.
  This also made the old `panel_band` parameter dead — removed.
- **Interface board stands ON EDGE** (Charles's suggestion) in two slotted uprights, slot =
  board + 1.4 mm so it takes ~1.4–2.6 mm stock. Honest accounting: this did NOT shrink the
  box (the row's depth is set by the isolator), but it puts the screw terminals sideways
  and reachable, shortens the runs to the XLR, and drops the board's footprint 50 × 35 →
  50 × 22. It cost 10 mm of height.
- **The bed check includes a 5 mm brim allowance.** "Fits the bed" and "prints on the bed"
  are different claims; at 176 mm the case had 4 mm to spare and nowhere to put a skirt.

### Asserts that caught real defects while modelling

Worth keeping because each was invisible to a manifold/volume check:

- Asserting connector positions against the **corner radius** rather than the cavity
  half-width caught the barrel flange AND then the XLR pad sitting where a flange cannot
  seat and a nut has nothing square to pull against.
- The barrel plate's own assert caught its M3 circle at ±17.5 falling **inside** the 34 mm
  opening — four screws into thin air. Plate resized 44 → 48 mm.
- An assert written `... or True` could never fail; replaced with the check that matters.
- Every bore is **point-in-solid scanned** with a control point in solid material, per the
  `geophone_case` lesson that watertight + plausible volume hides a plug.

### Layouts tried and rejected (do not retry)

- Interface board packed against the −X wall beside the Pi: collides unless the Pi is
  offset, and offsetting the Pi drives its end into the +X wall where the 5 V jack wants
  to be.
- 5 V plate on the −Y wall: must clear the 36 mm Pi stack vertically, breaks through the
  ceiling, implies a ~107 mm box.

### 🔌 Isolator moved OUT of the case (2026-08-08) — the 08-04 decision was self-contradictory

STATUS 2026-08-04 said "isolator INSIDE, on the Pi side, with the panel jack on the network
side — **isolation barrier at the enclosure boundary**". Those cannot both hold: an isolator
inside puts the *barrier* inside, so the **unisolated** segment (panel jack → isolator, and
6 in is the shortest patch cable Charles has) runs through the case past the front end,
carrying exactly the common-mode currents the isolator exists to block into the enclosure
volume. Charles caught this.

**It now lives at the NETWORK TAP**, with isolated cable running the whole way down to the
box — better than merely "outside the case", because the long run cannot pick up
common-mode along its length either. Isolate at the source, not the destination.

**The case got much smaller as a result: 168 × 164 → 130 × 143 mm, ~454 → ~348 g**, with
50 mm and 36 mm now spare on the bed. Knock-on changes:

- The 5 V plate moved from the +Y wall to the **+X side wall**. Three pads side by side
  needed 166 mm of flat wall, which would have forced a 196 mm case on a 180 mm bed; +Y now
  carries XLR + Ethernet only, and +X has room that only exists because the isolator left.
- **The Pi is deliberately OFF-CENTRE in X** (`pi_cx` derived, not 0). The 5 V jack pokes
  `barrel_body_depth` into the cavity from +X, and centring the Pi would pay that clearance
  on both sides — worth ~30 mm of case width for nothing.
- `cav_x` is now **derived from the connector wall** as well as the component packing, so
  "the jacks do not fit side by side" is caught by arithmetic instead of by an assert
  firing late.

### Still open

- **Lid + handle** — not modelled yet. Reuses the geophone case's handle.
- Connector intrusion depths were going to set `panel_band`; that parameter no longer
  exists, so this is now only a sanity check that no body is deeper than the 158 mm cavity.

## 📦 Pi + front-end ENCLOSURE — decisions and parts ordered (2026-08-04)

Design pass for the case holding the Pi 2B + Waveshare + front-end board. Gen-1 geophone
case is **printed and assembled-tested** (body + lid; handle prints clean, the 24 mm bridge
at the top of the trapezoidal opening came out with no sag). Everything fits: geophone into
cup, XLR into case, M3 screws through both.

- **Front end shares the Pi's case — do NOT give it its own.** `BACKLOG.md`'s
  digitize-at-the-sensor analysis: the geophone run is *differential* across a low 375 Ω
  source and is fine over a cable; the vulnerable nodes are the **high-impedance,
  single-ended** bias network and ADC input. A separate front-end case puts exactly those
  nodes on a connector and cable. Get serviceability from a **removable sub-plate** inside
  the shared case instead, so rev-1 → rev-2 swaps never touch the enclosure.
- **⚠️ NEVER panel-mount micro-USB for Pi power.** The 5 V USB side already browns out when
  extended ([[power-5v-usb-extension-gotcha]]) — dropped sample rate, square-wave plateaus.
  A feedthrough adds two more contact pairs to the rail that is already marginal. Instead:
  **panel-mount barrel jack → short heavy run → Pi GPIO 5 V/GND pins.** Tradeoff: the GPIO
  feed bypasses the Pi's input protection.
- **Keep the PSU external and extend the AC side, never the 5 V side.** A switcher inside
  the box is also an EMI source next to a µV front end.
- **Ethernet: D-type panel coupler**, because it reuses the D-series bore + ±(10, 11.5) mm
  hole pattern already validated by `parts/xlr_coupon.py`. Unshielded is *preferable* here —
  the case is PLA with nothing to bond to, and a shielded coupler would risk a second ground
  path against the single-point-ground doctrine.
- **Galvanic Ethernet isolator goes INSIDE, on the Pi side**, with the panel jack on the
  network side — isolation barrier at the enclosure boundary. It measured a real **1.6×**
  improvement in the signal band; preserve it deliberately.
- **Print a fit coupon for every new panel connector before committing to a case print.**
  That is why the XLR fit first try.

### Parts ordered 2026-08-04

| item | part | notes |
|---|---|---|
| PSU | **Mean Well GST25A05-P1J** | 5 V 4 A, 20 W, IEC C14 in, 5.5 × 2.1 barrel out, **80 mV published ripple**, ~$13–25 |
| AC cords | C13→NEMA 5-15, **25 ft** (under-house) + **6 ft** (bench) | AC side is the side you extend |
| DC jack | **RuiLing 5.5 × 2.1 panel mount, 3-pin, hex nut** | flange Ø14.0, thread length 11.8 mm, receptacle Ø6.3. **Pin 5 = +, pin 2 = −, pin 3 = switch contact, leave unconnected.** Thread OD still to be measured — that is the panel hole |
| Ethernet | D-type Cat6 female/female feedthrough, 2-pk | verify flange + hole spacing against the validated D pattern |
| screws | #6 × ½″ 18-8 stainless **pan head** sheet-metal (variety pack) | pan/button head deliberately: the 3 feet ARE the ground contact, so a rounded head gives near-point 3-point contact. `pilot_6 = 2.7` |

**Rejected:** a $135 linear supply. At ~10 % of in-band noise from the whole front end, the
payoff is bounded; buy ripple performance later only if the floor test says to. Thread-forming
plastic screws (Plastite / Delta PT) are genuinely better in PLA but not worth re-specifying
gen-1 pilots for — revisit with heat-set inserts at gen 2.

**Cosmetic:** the engraved `GEOPHONE` will be wax-filled (Stockmar beeswax **sticks** — a
0.9–1.3 mm marker nib cannot enter the letter strokes, so pack wax in and scrape flush
rather than trying to paint into the groove). Gen 2 should instead raise the text and do a
filament change, now that an AMS lite is on order.

## 🛰️ FDSN network identity: `SS` is available WITHOUT asking (2026-08-03)

`BACKLOG.md` said the only routes were "register an FDSN network code" or "be a Raspberry
Shake". There is a third and it is the easy one: **`SS` ("Single Station") may be used by
any operator running a single station, with no application to FDSN** — "a generic network
code for any operator that wishes to produce data in FDSN formats, but is not otherwise
associated with a network."

- ✅ **ISC replied 2026-08-07 (James) and the registration is proceeding under IR** —
  Charles confirmed "yes, register under IR" the same day. The ISC explicitly stated it is
  **happy to use stations with FDSN network codes in its operations, and there is no reason
  not to have it in both**. So IR and `SS` are *complementary*, exactly as assumed: IR is the
  ISC's own registry (it reserves the station code against collision), `SS` is the FDSN
  network code used in miniSEED headers. Registering under IR is what makes `SS.<code>` safe
  to publish.
- Submission was filed ~2026-07-27 and auto-acknowledged; the human reply took 11 days.
- 🔤 **The registered code is `OAKM1`, NOT `OAKMT`** (Charles, 2026-08-07) — chosen so a
  future second station can be `OAKM2`. The cutover is therefore **two fields, not one**:
  `XX.OAKMT` → `SS.OAKM1`. The station code is embedded in every **day-file name**, so this
  is a bigger change than the network flip alone.
- **Still outstanding:** James's confirmation that `OAKM1` is actually registered. The
  cutover waits on that email, not on the 08-07 reply.
- **Station codes are not globally unique in FDSN** — the unique key is
  network·station·location·channel. Under `SS` specifically, uniqueness *within* `SS` is
  the requirement, which is exactly what registering buys.
- Cutover: flip `SEISMO_NETWORK` `XX` → `SS` once the registry confirms `OAKMT`. It rewrites
  miniSEED headers, so it is a **metadata** discontinuity (not an instrument epoch), and
  anything globbing the archive by station code needs to know about both. Do it once.
- ⏳ **Do the flip while the rig is still off the slab.** The rebuilt front end already makes
  2026-08-07 an instrument epoch break, and the archive is currently taking throwaway bench
  data. Flipping `XX` → `SS` now folds the metadata discontinuity into a break that exists
  anyway, so the production slab epoch starts clean as `SS.OAKM1` with one boundary instead
  of two. Blocked only on the registration-confirmed email.

#### Cutover checklist — audited 2026-08-07

**Already parameterized** (just set the env): `station/recorder.py`, `server/store.py`,
`dashboard/seismo_dashboard.py`, `dashboard/heli_render.py` — all read `SEISMO_STATION`
(default `OAKMT`).

**Hardcoded, will break:**
- `server/detector.py:41` — `NET, STA, LOC, CHAN = "XX", "OAKMT", "00", "SHZ"`; the pi5
  detector will not see the renamed files at all.
- `station/seismo-recorder.service:16` — `Environment=SEISMO_STATION=OAKMT` (+ network).
- `station/motd-50-seismo.sh` — cosmetic.

**⚠️ Silent failures — FIXED 2026-08-07.** `analysis/ppsd.py` globbed `XX.OAKMT*.mseed`
and `analysis/coupling_test.py` / `analysis/break_1641.py` built
`XX.OAKMT.00.SHZ.D.{julian}.mseed` by hand. These would not have errored after the flip —
they would quietly stop matching new files, so a mixed-epoch analysis would run on
pre-cutover data only and look healthy. Same class as the `max(st, key=npts)` trap.

### ✅ CUTOVER PREP DONE (2026-08-07) — the flip is now config-only

All code is SEED-id agnostic. **No source change is required at cutover**; it is env vars
plus a restart.

- **`analysis/helicorder.py` gained `day_path(julian)`** — resolves a day-file by globbing
  `*.D.{julian}.mseed`, i.e. on the date (stable) rather than the SEED prefix (changes).
  Refuses to guess when a day has two SEED ids, which is the cutover day itself.
  `coupling_test.py` and `break_1641.py` now use it.
- **`analysis/ppsd.py`** globs `*.D.*.mseed`; its state/PNG names follow `SEISMO_STATION`.
- **`server/detector.py`** no longer hardcodes `NET, STA, LOC, CHAN` — reads the same four
  env vars as `recorder.py` / `store.py`. **Deployed to pi5 and restarted**; behavior is
  identical today because the defaults are still `XX`/`OAKMT`.
- **`analysis/detection_map.py`** figure labels follow `SEISMO_STATION` so the map stops
  saying OAKMT after the flip.
- **No change needed in `server/udp_collector.py`** — it derives day-file names from the
  *record headers* (`_dayfile()`), so it follows the station automatically.

#### 🔎 Found while testing: a shadowed `AM.OAKMT` day-file — and it is REAL DATA

`day_path("2026.201")` immediately errored on **two** files for that day. Characterised
2026-08-07: they are **complementary halves of 2026-07-20, not duplicates.**

| file | covers (UTC) | span | samples | sps |
|---|---|---|---|---|
| `AM.OAKMT...201` | 05:31:18 → 16:24:43 | 10.9 h | 2,197,176 | 55 + 57 |
| `XX.OAKMT...201` | 16:24:48 → 24:00:00 | 7.6 h | 1,510,763 | 57 |

The 5.4 s seam is the recorder restart at the `AM` → `XX` rename (AM is Raspberry Shake's
registered code — see the warning in `recorder.py`). So the AM file is the **first 10.9 h
of day 201, 59 % of that day's samples**, and every prefix-hardcoding analysis has silently
dropped it. The exact failure mode this cutover prep guards against, already realised once.

**Impact is bounded:** day 201 is the 55/57 sps epoch (100 sps did not start until day
206), so current-epoch work was never affected. What was short-changed is early-archive
noise/PPSD work, which lost more than half of that day.

**Also found: 2 KB of corruption in the XX day-201 file** — 16 consecutive 128-byte
non-SEED records at bytes 2,902,016–2,904,063. obspy skips them with a warning, so ~16
records are lost from that day; not a correctness threat, but it only shows up on a real
read.

#### 🐍 obspy import failure — cause found, and the manifest was the real bug

`import obspy` failed while `obspy/` sat on `sys.path`: the install was **half-present**
(dist-info there, package directory gone). `uv pip install --reinstall obspy` fixed it.
Root cause is that **`pyproject.toml` declared no dependencies at all**, so the whole
analysis stack was an undeclared local install free to drift. `numpy` / `scipy` / `obspy` /
`matplotlib` are now declared.

⚠️ **Do NOT run `uv sync` in this repo.** The build123d / ocp-vscode CAD stack shares this
`.venv` and is deliberately undeclared (dev tooling, per `CLAUDE.md`); `uv sync` prunes
anything undeclared and would delete it. `[tool.uv] package = false` is set so nothing
tries to build the repo as a package. Install with
`uv pip install --python .venv/bin/python <pkg>`.

#### Cutover runbook — run when James confirms `OAKM1` is registered

1. **Station** (`seismo.local`), `/etc/systemd/system/seismo-recorder.service`:
   `SEISMO_NETWORK=XX` → `SS`, `SEISMO_STATION=OAKMT` → `OAKM1`.
   `sudo systemctl daemon-reload && sudo systemctl restart seismo-recorder`
2. **pi5** — add `Environment=SEISMO_NETWORK=SS` + `SEISMO_STATION=OAKM1` to *both*
   `seismo-detector.service` and `seismo-server.service`; `daemon-reload` + restart each.
   The collector needs nothing.
3. **Dashboard** (dokku on pi5): `dokku config:set seismo SEISMO_NETWORK=SS SEISMO_STATION=OAKM1`
   (it currently sets neither, so both fall through to the `OAKMT` defaults).
4. **Verify:** a new `SS.OAKM1.00.SHZ.D.2026.<jjj>.mseed` appears in `~/seismo-archive/`,
   `/v1/health` still fresh, detector still writing events.
5. **Do NOT rename historical files.** The archive legitimately spans `AM` → `XX` → `SS`;
   `day_path()` handles that, and rewriting history would falsify the record.
- Refs: <https://docs.fdsn.org/projects/source-identifiers/en/v1.0/network-codes.html>,
  <https://www.fdsn.org/networks/detail/SS/>

## 🔴 (HISTORICAL — RESOLVED, see above) STATION FAULTED 2026-07-31 16:41 PDT

**Recorder stopped AND `systemctl disable`d at 22:35 PDT** so it does not come back on a
power cycle during the repair. The Pi itself is still up and reachable (`seismo.local`);
run `sudo shutdown -h now` on it before touching the wiring. To bring the station back
after the fix:

```
sudo systemctl enable --now seismo-recorder     # re-enable + start
journalctl -u seismo-recorder -f                # expect DC near mid-scale, 5-min std ~700
```

Data through 2026-08-01T05:35Z is synced to `analysis/data/`. **Everything from 16:41 PDT
onward is instrument noise, not ground** — exclude it from any archive analysis, and
ignore the ~200 false `EVENT` entries it wrote to `events.log` in that window.

At **23:41 UTC / 16:41 PDT** the trace slammed to negative full scale for a few seconds
and then parked at **≈ −2.2M counts (≈ −20 mV input-referred)**, where it still sits.
Broadband noise went up **20–200×** (5-min std ~700 → 15k–140k counts) and the STA/LTA
detector has been firing continuously ever since — the `EVENT` lines in the journal from
16:41 onward are **all false**. The recorder itself is healthy (no restart, 8 d uptime,
clock error ±0–14 ms, rate 99.84 sps).

- **It is not the tile→slab move.** The move was at 13:40 PDT; it produced a 2-min
  handling transient and then the DC returned to its normal ~+334k with std ~700, and
  stayed clean for three hours. The break is a separate, later event with nobody at the
  rig.
- **Signature:** big negative DC offset + broadband, non-sinusoidal, 1/f-ish noise 100×
  the floor from 0.01 Hz to ~20 Hz, **no mains lines** (see `analysis/break_1641.png`).
  That is what a **lost DC path on one input leg** looks like — a bias resistor leg or a
  screw-terminal/ferrule that let go, leaving the input high-impedance and drifting.
  A move-loosened connection that finally opened three hours later fits the timing.
- **Ruled out — it is not the ADC's state.** A recorder restart does a hard pin reset plus
  `cal_self()` (`adc_common.py:143-146`): every register rewritten, offset recalibrated.
  Done at 22:33 PDT and the offset came back **identical** (−2,174,268 counts, std 22,614).
  A **reboot is therefore pointless** — it adds only kernel/pigpiod state, and nothing in
  software can hold a −20 mV offset on an analog input.
- **⚠️ WRONG WHEN WRITTEN — there was no XLR to unplug.** This said "unplug the XLR at the
  case", but the gen-1 case was never assembled and no connector existed in the chain: the
  geophone was hardwired, salvaged XLR *cable* soldered at the element end and tinned into
  the ADC screw terminals at the other. There was no disconnect point at all, which is why
  the XLR panel connector is worth fitting — it turns this diagnosis into a 10-second
  unplug-and-meter. (Kept as a caution: check what is physically built before writing a
  repair step against it.)
- **Then, Pi off:** reseat/verify the two 100 kΩ bias resistors and both signal legs in the
  ADC screw terminals and at the perfboard, then confirm DC returns to ~mid-scale before
  trusting anything.

## ✅ COUPLING TEST DONE (2026-07-31 13:40 PDT) — tile→slab changed nothing measurable

Geophone taken off the garage's plastic interlocking tile and set directly on the
concrete slab. Valid post-move data is the **2.8 h window 13:45–16:40 PDT** (settling +
the fault above), compared against matched clock windows on the tile.
`analysis/coupling_test.py` → `analysis/coupling_test.png`.

| band (median 5-min RMS) | Jul 30 14:20–16:35 tile | Jul 31 11:00–13:15 tile | **Jul 31 14:20–16:35 SLAB** |
|---|---|---|---|
| 0.02–0.12 Hz | 0.83 µV | 0.80 µV | **0.90 µV** |
| 1–15 Hz | 4.47 µV | 4.32 µV | **4.03 µV** |
| 18–22 Hz | 5.80 µV | 1.22 µV | **1.96 µV** |
| 38–44 Hz | 2.68 µV | 1.07 µV | **2.56 µV** |

- **The 19.95 / 41 Hz line pair survived the move at the same frequencies** (19.93–20.00
  and 40.9–41.2 Hz on both sides). The hollow-tile-resonance hypothesis in `BACKLOG.md`
  is therefore **not supported** — those lines are something else (instrument or another
  structure). Their *amplitude* swings 5× with time of day on the tile alone, so
  amplitude comparisons across windows prove nothing; frequency is the robust part.
- **No sensitivity was recovered.** The 1–15 Hz ambient floor is unchanged (4.0 vs 4.3–4.5
  µV), so the 7.5×-low absolute calibration is **not** coupling loss through the tile.
  That candidate is closed; shunt loading / element sensitivity / site response remain.
- **Two analysis traps found and fixed while doing this** (both now documented in the
  script): day-files are fragmented into ~10 s blocks with 2–3 sample gaps, so
  "longest gapless segment" silently analysed **1 minute** of a 2 h window — bridge the
  gaps by interpolation instead. And a single 82 µV transient at 14:44 made the post-move
  1–15 Hz band look **3.8× worse** under mean-averaged Welch; median-averaged Welch plus a
  median-of-5-min-RMS statistic show the floor was flat. **`spectrum.py` and anything else
  using `max(st, key=npts)` inherits the first bug.**

## 🌟 M4.2 CLOVERDALE — biggest event yet, plus 4 more the same day (2026-07-29)

**USGS: M4.2, 2026-07-29 02:40:06 UTC, 38.777°N 122.936°W, depth 5.9 km — 45.3 km
epicentral / 45.7 km hypocentral, azimuth NW.** Recorded cleanly and unmistakably.
Figures: `reports/2026-07-29-m4.2-cloverdale.png` (shareable),
`reports/2026-07-29-m4.2-cloverdale-look.png` (coda + onset zoom).

| metric | this event | previous best |
|---|---|---|
| detector `peak_ratio` | **8535** | 645 (M2.5 St Helena) |
| harvester SNR | **186** | 35.4 |
| peak (1–15 Hz) | **1406 µV** | 126 µV |
| coda duration (1–15 Hz back to ambient) | **~80 s** | ~25 s |

- **Not remotely clipped.** Raw counts spanned 196,219–491,394 against ±8,388,607 FS —
  the whole event used **~3.5 % of full scale**. Headroom is ~600× the observed peak, so
  gain 64 is in no danger for events of this class; a same-distance M6 would be the first
  to threaten it.
- **Sub-Hz band carried real signal for the first time:** band excess over the 120 s
  pre-event window was **0.5–1 Hz ×50 · 1–5 Hz ×306 · 5–15 Hz ×46 · 15–45 Hz ×5.5** —
  low-band-dominated, the earthquake signature, and by a wider margin than any prior event.
- **Four MORE confirmed events on the same day** (harvester, all three legs):
  M2.2 03:48:38 (aftershock), M1.9 10:48:54 (aftershock), M1.5 13 km NNW of Angwin at
  **28.8 km**, M2.3 20:11:44 (aftershock). That takes the archive from 4 confirmed events
  to **9**, and **M1.9 at 45.9 km is the new smallest-confirmed** (was M2.4 at 43 km).

### 📐 Vp is now MEASURED, not assumed: 5.19 km/s (this was a real error)

The M4.2's first arrival came in at **+9.06 s**, ~1.4 s later than the Vp = 6.0 km/s
prediction of +7.6 s. Ruled out a clock error using our own data — a clock offset is
*constant* with distance, a velocity error *scales* with it:

| event | dist | onset | delay vs Vp 6.0 |
|---|---|---|---|
| M2.5 St Helena | 18.4 km | 3.86 s | +0.79 s |
| M2.5 Geysers | 41.1 km | 8.15 s | +1.30 s |
| **M4.2 Cloverdale** | 45.7 km | 9.06 s | +1.44 s |
| M2.2 aftershock | 45.6 km | 8.90 s | +1.29 s |
| M2.3 aftershock | 45.6 km | 9.38 s | +1.77 s |

The delay scales with distance. Least-squares over the five: **onset = dist / 5.19 km/s
+ 0.30 s**, residuals ≤ 0.3 s over 18–46 km. The +0.30 s intercept is the envelope
detector's own lag (5× threshold on a 0.3 s smoother), not a clock offset — a
pure-clock fit needs +1.32 s with 0.32 s of unexplained spread. **The station clock is
fine; Vp = 6.0 was too fast for these shallow NW paths.** `VP` is now **5.19** (and
`VS` 3.00, keeping Vp/Vs ≈ 1.73) in `eventcheck.py` and `harvest_events.py`; window
placement shifts by ~1.4 s at 45 km, so residuals from earlier harvester runs are not
byte-comparable with new ones. Onset picks: `analysis/` ad-hoc run, method above.

### ⚠️ Peak amplitude under-reads at large magnitude — do not use it as a magnitude proxy

The M4.2's residual is **−0.633**, clearly outside the **−0.16 … −0.31** band the five
M1.5–M2.5 events sit in (and the earlier four M2.4–2.8 events' −0.318 … −0.412). Same
day, same azimuth, same distance for three of them, so this is **not** site or path — it
is **magnitude-dependent**: at M4.2 the source corner frequency drops toward ~1–2 Hz,
where the 4.5 Hz geophone response is falling steeply, so a growing share of the energy
lands below the 1–15 Hz metric. The residual leg still *accepts* it (−1.2 < −0.633 <
0.4), which is the filter working. But the ML-anchored `predict_uv` is only calibrated
in the M1.5–M2.8 range; inverting our peak to a magnitude would read **~1.7× low at
M4.2** and worse above it.

## 🚗 Traffic direction — a road patch gives the symmetry-breaker (2026-07-27)

Charles found the physical source of the "pop" on northbound transits: **broken/patched
pavement on Highway 12, in the NORTHBOUND LANE ONLY** (southbound is smooth). Photo +
measured geometry from satellite:

- **closest approach 336.96 ft** (102.7 m) — and it is essentially the perpendicular foot
- **patch 481.82 ft** (146.9 m), which puts it **344 ft (105 m) along the road** to the NW
  of the closest-approach point

**Why this matters.** A single vertical channel cannot give bearing — that is geometry,
not a sensitivity problem. But a *fixed impulsive source at a known location* breaks the
transit symmetry. Northbound vehicles pass closest approach, THEN hit the patch;
southbound never touch it.

**Falsifiable prediction (UNTESTED):**
- northbound → discrete pop **+4.3 to +6.7 s AFTER** the transit envelope peak (344 ft at
  35–55 mph)
- southbound → **no pop at all**

**⚠️ My first test of this was invalid — do not trust it.** I scored 75 "isolated passes"
overnight and got 7/7 impulses *before* the peak, none after. Three reasons that result
means nothing:
1. It assumes the 5–15 Hz envelope peak is closest approach, and I never verified that.
   Earlier analysis found night events here are **sharp ~1 s features**, not the 8–10 s
   swells a car at 102 m must produce — so the detector may be locking onto impulses, not
   transits, in which case "offset from the peak" measures nothing.
2. Only 7 of 75 candidates carried an impulse (9 %). If every northbound vehicle hits the
   patch and traffic splits evenly, that should be nearer 50 %.
3. The impulses found were 3–7 µV — small for a car striking broken pavement.

**What settles it, cheaply:** watch ONE northbound vehicle pass at a quiet hour and note
the second. That single labelled pass validates the whole chain at once — whether a
transit swell is visible at all, its shape, whether a pop follows, and at what delay.
Everything downstream rests on that unverified assumption.

**Superseded:** the earlier ask for ~20 labelled passes. With a known mechanism, a known
lane and a predicted delay, a handful suffices — and one is enough to validate the
detector.

## 🎯 FOUR confirmed earthquakes — and a detector that finds them (2026-07-27)

The catalogue-driven harvester (`analysis/harvest_events.py`) now identifies every real
event in the archive and rejects the noise, using three independent legs:

| origin (UTC) | M | dist | az | SNR | residual | lo/hi |
|---|---|---|---|---|---|---|
| 2026-07-25 11:31:41 | 2.5 | 18.4 km | ENE | 35.4 | −0.380 | 1.63 |
| 2026-07-27 06:29:25 | 2.5 | 41.1 km | NNW | 12.9 | −0.391 | 6.05 |
| **2026-07-27 15:29:01** | **2.8** | 38.1 km | NNW | 8.8 | −0.412 | 6.88 |
| **2026-07-27 21:35:39** | **2.4** | 43.4 km | NNW | 3.2 | −0.318 | 3.34 |

The last two were **found by the harvester**, not by the STA/LTA or by anyone watching.

**Why three legs and not a threshold.** Over 350 catalogued windows:
- **SNR ≥ 5 alone gives 7** — three of them physically impossible (M0.6 at 249 km,
  M0.7 at 500 km). With 350 windows some simply contain a passing truck.
- **Residual alone** (log₁₀ observed/predicted, scaled from the ML attenuation) is
  remarkable — all four real events fall in **−0.318 … −0.412**, a 0.09 spread across
  18–43 km and 2.5× in magnitude, while false positives sit at **+1.36 … +3.64**. But it
  cannot confirm marginal events: at SNR ~1 the "observed" is noise, and if the
  prediction happens to be a few times that, the residual looks fine by accident.
- **Shape** (1–5 Hz excess ÷ 15–45 Hz excess) is the independent third leg: earthquakes
  are low-band dominated (1.6–6.9), cultural sources are not (0.28–0.45).

Together: **`snr ≥ 3 AND −1.2 < resid < 0.4 AND lo/hi ≥ 1`** → exactly the four real
events, no false positives.

**The constant −0.4 offset is an anchor artefact**, not physics: `REF_PEAK_UV = 126` is a
raw peak from the original STATUS note, while the harvester measures a 1 s smoothed
envelope peak. Setting the anchor near 50 µV centres the residuals on zero.

**Detection threshold, measured rather than scaled:** smallest confirmed is **M2.4 at
43 km**, found at SNR 3.2 on a busy weekday afternoon. All four detections are 18–43 km
and NNW/ENE — nothing yet from the SE, where the Vallejo M2.2 at 54 km was *not* seen
(ray path crosses the Napa–Sonoma marshes; hypothesis recorded, needs months of data).

## 🎉 SECOND CONFIRMED EARTHQUAKE — M2.5, The Geysers (2026-07-27)

**USGS: M2.5, 2026-07-27 06:29:25.4 UTC, 38.798°N 122.781°W, depth 3.5 km — 41.1 km
hypocentral**, more than twice the distance of the first. Detected automatically:
`events.log` 06:29:33, ratio 61.2, peak 55.7 µV, 22.9 s.

**This one was a PREDICTION, which makes it a better validation than the first.**
Scaling the M2.5 at 18.8 km (126 µV) by the California ML attenuation gives 48 µV at
41.1 km; observed 55.7 µV — **16%**. Predicted P at +6.9 s, detector fired at +7.6 s.

**Band signature is unambiguous** (S window vs 120 s pre-event):
`1–5 Hz ×9.4 · 5–15 Hz ×5.6 · 15–45 Hz ×1.4` — all bands up, **low bands most**.
Contrast the 07:20:55 vehicle the same night: 5–15 Hz ×9 with 1–5 Hz *flat*. The two
classes separate cleanly on this alone. Figure: `analysis/geysers_m2.5.png`.

### 🔭 The Geysers is a permanent calibration source — use it as the benchmark

**235 catalogued events in 8 days (~29/day)**, median M0.9, at a fixed 40–50 km. Only
~2/week exceed ~15 µV, but the catalogue supplies origin times, so events far below the
STA/LTA threshold can still be **examined at known times** rather than detected blind:

| class | predicted peak |
|---|---|
| M2.5 @ 41 km | 51 µV (observed 55.7) |
| M2.2 @ 49 km | 19 µV |
| M1.8 @ 45 km | ~9 µV — SNR ~2 on a quiet night, invisible to STA/LTA, findable by cut-and-look |

**This is the instrument metric the project has lacked.** "Noise floor in µV" is
site-contaminated and hard to interpret; **"how many Geysers events can we see"** is
objective, mission-relevant, and directly comparable across hardware changes. Count
before lifting the tile, count after — that is the experiment.

## 🎉 FIRST CONFIRMED EARTHQUAKE — M2.5, 3 km E of St. Helena (2026-07-25)

The station caught its first confirmed local earthquake — the reason it exists.
USGS: **M2.5, 2026-07-25 11:31:41.760 UTC, 38.507°N 122.435°W, depth 6.2 km**
(~19 km hypocentral from Oakmont, on the Maacama/Rodgers Creek system).

- **STA/LTA triggered 11:31:45 UTC** — 4 s after origin. **peak_ratio 645**
  (threshold 4.0; every prior trigger was a false positive under 60), **peak
  ~110–125 µV** vs ~1 µV ambient (**SNR ~100×**), 24 s duration.
- **Waveform (1–15 Hz):** flat noise → sharp **first arrival (P) at 11:31:45.7**
  (jump to ~117 µV, matching the catalog-predicted P) → peak ~126 µV → coda to noise
  by ~11:32:12. Textbook local event.
- **Single-station limit (honesty note):** the **S is buried** — for a close event
  P and S are only ~2.4 s apart and merge into one burst, so S sits in the coda, not
  separately pickable. There is **no independent single-station S–P or distance**;
  the ~19 km is the catalog's. An earlier graphic drew an emergent "P" near the noise
  floor (a +2 s candidate implies an impossible ~10 km/s P velocity) plus an "S–P →
  distance confirms the catalog" annotation — that was **circular** and has been
  removed. What confirms it's a quake is the *network* (BK.CMB, CE.68327 saw it), not
  our single station.
- **This is the calibration reference** the detector/character work was missing
  (`dashboard/CHARACTER.md`: "no confirmed event yet to calibrate against"). Now
  there is ground truth: known M, known distance, clean recording.
- Recorder healthy throughout; the concurrent 24 h UDP probe did **not** perturb
  acquisition. Day-file: `data/XX.OAKMT.00.SHZ.D.2026.206.mseed` (event ~11:31:41 UTC).
- **Shareable image tool:** `analysis/quake_share.py` — parameterized per event (pass
  the catalog facts; measures peak/SNR, marks only phases you can actually pick, and
  renders a labeled hero PNG; it does NOT predict arrivals from the catalog distance —
  predict-then-confirm is circular). This event: `--origin 2026-07-25T11:31:41.760
  --mag 2.5 --event-lat 38.507 --event-lon -122.435 --depth-km 6.2 --p 3.97` (P = the
  measured first arrival; S not pickable). Output: `reports/2026-07-25-m2.5-st-helena.png`.

## ✅ Environmental node LIVE in the garage (2026-07-25)

The CLUE→Pi 4 environmental node (pressure / tilt / temp / humidity, 1 Hz, UTC-stamped
on receipt) is **installed in the garage near the station and logging**. Code in
`env_node/`; `env-logger` systemd service on **pi4env.local**, daily CSVs at
`pi4env:~/env-data/env-YYYY-MM-DD.csv` (schema `utc,clue_mono_s,temp_C,press_hPa,
humid_pct,ax_ms2,ay_ms2,az_ms2`).

- **Hardening from bring-up:** the host log filter now requires all fields numeric
  (drops CircuitPython reboot-banner lines on replug — was writing junk rows); CLUE
  backlight off (board mounted **face down**, sensors up in air).
- **`temp_C` is board self-heat, not ambient — use DELTAS only.** BMP280 is on the CLUE
  PCB and reads conducted self-heat (~constant offset); no case geometry fixes the
  absolute value (backlight-off/face-down/air-exposed all landed ~30–32 °C). Fine for
  the thermal-settling correlation, which wants swings, not absolutes. See
  `env_node/README.md`.
- **Mirror + dashboard DONE (2026-07-25):** the host `seismo-rsync.service` on pi5 now
  also pulls `pi4env.local:~/env-data/` → `~/seismo-data/env/` (= `/data/env` in the
  container) every minute (pi5→pi4env SSH key authorized, host key trusted). The
  dashboard has an **`/env` page** (nav "Environment") — current pressure / temp /
  humidity / tilt tiles + accel + freshness, self-refresh every 15 s off `/env-data`
  (JSON). `temp_C` tile is captioned "read changes, not the absolute". Deployed +
  verified live.
- **Open thread:** the actual question — **does pressure or tilt explain the
  0.02–0.12 Hz undulation?** (needs a day+ of undisturbed garage data first).

## ✅ 24 h UDP loss probe COMPLETE — sets rev-2 redundancy at N=2 (2026-07-25)

Sized the **rev-2 UDP streaming** redundancy (see `doc/rev2-data-plane.md §5`). 24 h,
**864,000 pkts** (10 pps × 512 B) over the real Ethernet-bridge→WiFi path, station→pi5.

- **Result: 0.0073 % loss** (63 of 864k), **0 reorder, 0 dup**. 16 loss events,
  **sporadic across the whole day** (midday, afternoon, evening, *and* 3 am) — random
  interference, **no time-of-day pattern** (the early-7 h "evening peak" guess did not hold).
- **Worst fade 1.4 s** (14 pkts @ 10 pps). Burst histogram (pkts): 1×7, 2×2, 3, 4, 7×2, 8, 9, 14.
- **Decision: fixed N = 2.** At the natural record cadence (~1.75 s/datagram, 100 samples
  @ 57 sps) a 1.4 s fade drops ≤1 datagram, so "send current + previous record" recovers
  **100 % of the observed loss inline** — MTU-safe (~1 KB). Rarer/longer fades → file-backfill
  (would have fired ~16×/day). **No adaptive-N machinery needed.** (Faster batching, e.g.
  0.5 s/datagram, would want N≈4.)
- **Spot test (pre-flight):** 3600 pkts at 512 B & 1400 B, 50 & 5 pps → 0 loss, jitter
  p99 ≤ 41 ms; packet size didn't matter.
- Probe processes finished; `/tmp` scratch (scripts, jsonl, pids) cleaned off both hosts.

## 📏 Instrument characterization from the M2.5 (2026-07-25)

**Absolute amplitude cal reads ~7.5× LOW.** Cross-checked our recorded peak against
**CE.68327** (Kinemetrics EpiSensor, *calibrated*, 19.6 km ≈ our 18.8 km, same vertical
component, same 1–15 Hz band, response-removed from NCEDC metadata):
- CE peak ground velocity **30.6 µm/s** vs ours (nominal 28.8 V/m/s) **4.06 µm/s** →
  **~7.5× deficit**. We're if anything slightly *closer*, so that's a floor on the error.
- **We under-report → over-stated sensitivity.** Likely: the **shunt damping resistor loads
  the 375 Ω coil** (28.8 V/m/s is the *open-circuit* figure; loaded effective sensitivity is
  lower, up to ~3×) and/or the **element sensitivity ≠ datasheet** (mislabeled-listing risk).
  Some fraction is **site response** (CE's site vs our garage slab) — the unquantified
  confound, so 7.5× is the *net* under-scaling, an upper bound on pure instrument error.
- **Effective sensitivity ≈ 28.8 / 7.5 ≈ 3.8 V/(m/s)** as a first empirical anchor.
- **Relative** measurements (our own records over time) UNAFFECTED — internal scale is
  consistent. Only **absolute** ground-motion numbers are ~7.5× low.
- Firm up: also compare CE horizontals + other neighbors, repeat on future quakes, and
  bench-measure the damping-loaded sensitivity to split instrument-vs-site.

## ✅ SWITCHED TO 100 sps — new epoch (2026-07-25)

The station now records **100 sps** (RDATAC, `SEISMO_DRATE=100`/`SEISMO_RATE=100`).
The earlier "switch-or-not maybe" was settled by a back-to-back noise measurement on
the current garage hardware (`rdatac_noise_test.py`, 90 s/case, baseline), which
**reversed the old bring-up call** that 100 sps was noisier:

| median per-10 s band RMS (µV) | 60 sps | 100 sps |
| --- | --- | --- |
| **1–15 Hz** (quake band) | 3.99 | **2.74** (~31 % lower) |
| **3–15 Hz** (detector band) | 3.86 | **2.62** (~32 % lower) |
| 15–28 Hz | 2.57 | 5.69 (60 sps was attenuating near its 30 Hz Nyquist) |
| achieved fs | 60.006 | 99.910 |
| glitches / 90 s | 0 | 5 |

- **Why lower in-band:** higher Nyquist spreads the converter's noise over a wider
  band (lower in-band density) and less HF energy aliases down into the quake band.
- **Read ceiling was a myth** for RDATAC: it sustains 99.91 sps with 5 glitches/90 s.
  The old "~92 sps ceiling" was the legacy per-sample-SYNC path, not RDATAC.
- **Only cost:** 60 Hz mains no longer falls on a sinc notch — it aliases to 40 Hz,
  above the quake band; digital notch in post if a spectrum needs it.
- **Cutover:** live recorder healthy at `rate_est 100.0, dropped 0`; today's 60 sps
  day-file preserved as `*.206.mseed.60sps-epoch`, fresh clean 100 sps `206.mseed`
  started. Dashboard verified live — spectrum Nyquist now reaches 50 Hz. Config
  reasoning updated in `station/waveshare_config.py` + `seismo-recorder.service`.
- **Old 5-min feasibility probe** (for the record): 99.9 sps, ~0.025 % drops,
  ~0.07 % held-sample glitches — corroborated by the above.

## ✅ UDP streaming — Phase-1 step 1 LIVE (2026-07-26)

The station now **streams each miniSEED record to the pi5 over UDP** and the pi5 builds
an **owned archive** from it — the first piece of the rev-2 data plane
(`doc/rev2-data-plane.md`, design pass resolved 2026-07-25). Runs **alongside** the
existing rsync mirror; nothing retired.

- **Station:** `station/udp_publisher.py` — a fail-open publisher thread. The writer
  hands each packed record to it; a paced daemon (record-period paced so the N=2 copies
  are spaced in time) sends `MAGIC|ver|n_records|seq + N×512B` datagrams. `publish()`
  is `put_nowait` drop-on-full → **never blocks or touches the ADC loop.** Enabled by
  `SEISMO_UDP_HOST` in the unit (→ 192.168.5.30:48317, N=2). `health.json` now carries
  `udp_sent`/`udp_dropped`.
- **pi5:** `server/udp_collector.py` + `seismo-collector` systemd service (own venv,
  simplemseed) → `~/seismo-archive/`. Dedups by record start-time (N=2 sends each twice),
  restart-safe (rebuilds the seen-set by scanning the day-file). No firewall on pi5.
- **Verified byte-faithful:** over the streaming window **90/90 in-window records
  arrived, all byte-identical** to the recorder's local day-file — 0 mismatched, 0
  fabricated, `udp_dropped=0`. Records are int32 for now (STEIM2 fill-model is the
  follow-on that lets N=2 also cover the worst 1.4 s fade inline, §14.0).
### ✅ UDP heartbeat + backfill — Phase-1 step 2 LIVE (2026-07-26)

The stream now has its reliability layer.

- **Heartbeat (sec 6):** `station/udp_publisher.py` `Heartbeat` sends a 1 s station→pi5
  JSON pulse on port 48318 — health counters + `hi_seq` (highest data seq, bounds tail
  loss). The collector writes it atomically to `~/seismo-archive/station_health.json`
  (the eventual replacement for the health.json rsync; feeds `/v1/health` in Phase 2).
  Fires regardless of data flow, so its *absence* is the liveness signal.
- **Backfill (sec 14.4):** the collector, on startup and hourly, `ssh`+`rsync`s the
  station's recent local day-files and merges any records missing from the archive
  (dedup by start-time; thread-safe under a lock shared with live ingest). Lazy,
  pi5-initiated, rare-catastrophe recovery — not per-packet plumbing.
- **Verified:** startup backfill healed **+2033** then **+31** records (exactly the
  gaps from the deploy restarts); live stream **`seq_gaps=0`**, `udp_dropped=0`; the
  only ever-residual is the current restart window, which the next cycle converges.
### ⛔ STEIM2 fill-model — tried, worked, then REVERTED (2026-07-26)

**Superseded — see "STEIM2 reverted on the station" below.** The recorder briefly wrote
STEIM2 (encoding 11, `encodeSteim2FrameBlock`, ~210–250 samples/record, ~20 MB/day,
lossless, byte-faithful, dashboard rendered it) — but the pure-Python encoder cost
~211 ms/block on the Pi 2B and starved the read loop (drops ~7×). **Rolled back to int32;
STEIM2 dropped for good in the acquisition/archive path** (int32 miniSEED is valid
FDSN/SeedLink anyway — compression, if ever wanted, is a pi5 *serving-layer* job). The
brief STEIM2 records that landed in the day-files before the revert stay readable (mixed
int32/STEIM2, per-record, lossless).

**Phase 1 is complete** (100 sps · UDP stream · N=2 redundancy · heartbeat · backfill ·
STEIM2).

### ✅ Phase 2 step 1: detector → pi5 (2026-07-26)

STA/LTA detection now also runs on the **pi5**, over the owned archive (`server/detector.py`
+ `stalta.py`, `seismo-detector` service → `<archive>/events.log`). It reuses the exact
`StaLta`, so results match, and it adds the thing the station couldn't do: **retroactive
re-detection** — `detector.py --day 2026.207 --trig 6 ...` re-runs over the whole archive
with tuned thresholds (the surface for killing the false positives).

- **Additive:** the station's inline detector is **still running** (removal is the next
  sub-step, and per house rule needs an explicit go-ahead — it's a working feature).
- **Parity verified:** 10/11 of the station's day-207 events reproduced with identical
  duration/ratio/peak. The 2 diffs are the station re-priming its LTA at today's recorder
  restarts — it actually *missed* a ratio-9 event the continuous pi5 detector caught.
- **Key fix:** feed one StaLta continuously across the frequent small drop-gaps (reset
  only on a real >60 s outage) — matching the station's stream-based behavior. Per-segment
  re-priming had suppressed all but one event.

### ✅ Phase 2 step 2a: /v1 server over the owned archive (2026-07-26)

`seismo-server` (pi5, port 8351) now serves the OWNED data plane via `store.py` — env
swapped to `SEISMO_DATA=~/seismo-archive`, events = the pi5 detector's `events.log`,
health = the heartbeat's `station_health.json`. Verified: `/`, `/v1/health` (rate 100,
`udp_dropped=0`, archive age <1 s), `/v1/events` (pi5 detections), `/v1/live` (fresh ring,
age ~5 s). `/v1/waveform` returns the documented 503 until obspy is added (apt
`python3-obspy` at the dashboard cutover). **Additive** — the dashboard still reads the
mirror; nothing retired.

### ⛔ STEIM2 reverted on the station — Pi 2B too weak to encode (2026-07-26)

STEIM2 fill-encoding worked and was byte-faithful, **but its pure-Python encoder cost
~211 ms/10 s block on the Pi 2B**, and that GIL-holding burst starved the RDATAC read loop:
**drops jumped ~0.05/s (int32) → ~0.35/s (~30k/day).** That trades the *one job* for
archive elegance — wrong on a sensitivity-first box. **Station is back on int32** (drops
confirmed back to ~0.05/s, ~7× lower).

**DECISION (2026-07-26): int32 stays; STEIM2 is not pursued** — not a C encoder, not a
pi5 re-encode. The working config is kept: 44 MB/day is trivial on the disk, and backfill
already heals the rare fade N=2 misses. Thread closed. (`doc/rev2-data-plane.md §14.0`.)

### ⚠️ The ~20 Hz line is a MOUNT RESONANCE — the station is on plastic tile (2026-07-26)

Charles mentioned the garage floor is **inherited plastic interlocking tile**, not bare
slab. Re-measured at 0.012 Hz resolution, the ~20 Hz peak sits at **19.885–20.007 Hz**
across washer spin, dryer, dead quiet, midday and afternoon — a 0.6 % spread — and the
41 Hz peak is **2.03–2.07× it in every case**. Fixed frequency + a 2:1 mode pair is a
**structural resonance the appliances excite**, not a shaft rate they generate. The
"~1195 RPM" reading is **retracted** (`analysis/SOURCES.md`, `dashboard/signatures.json`).

- It dissolves the coincidence that two different machines produced identical lines.
- **New candidate for the 7.5× amplitude deficit:** coupling loss through a compliant
  layer, which is not among the causes STATUS currently lists. Free to test.
- **Fix + test are in `BACKLOG.md` (first item).** Hardware touch → new epoch.
- The live badge's recall is only **59 %** against "an appliance is running" (80/136
  30 s windows over the confirmed 21:16–22:24 laundry period), with regularly
  alternating misses. Charles caught this: the badge was empty while his dryer ran, and
  I had "confirmed" that empty state by reading the detector's own feature to conclude
  nothing was running — circular. The signature detects *excitation*, not the appliance.

### ✅ Live source badge (2026-07-26)

The live page now labels what it can recognise. `dashboard/sources.py` scores the
live ring against `dashboard/signatures.json` (signatures as versioned DATA); a badge
appears in the "Live · last 30 s" header with the detail underneath.

- **Free to run:** `render._live_welch()` memoizes the raw Welch on `t_end`, so the
  display spectrum and the matcher share one FFT per ring update (~3 s) instead of one
  each per 300 ms poll.
- **Soft label**, same doctrine as the character badge: informational, never filters.
  Provisional signatures render light/bordered with a `?`; only `status: active` (seen
  on ≥2 separate days) would render solid.
- **Two guards in the matcher:** epoch (a signature is skipped unless `derived_at_sps`
  matches and `valid_from` has passed — both verified to reject) and an absolute
  `min_asd` floor alongside the peak/shoulder shape term, because the standing 41 Hz
  and 20 Hz lines score ×10 over their own continuum with nothing running.
- **Scored offline against real windows before deploy:** 8/8 true positives (5 washer +
  3 dryer), 7/8 controls correctly negative. The one hit is 2026-07-26T02:00Z, already
  flagged as plausibly an unlabelled real run.
- **Verified in-browser** by intercepting `/live-data` so the real render path runs.
  Nothing was running at deploy time, so the empty state is also confirmed correct
  (19.82 Hz sat at 0.85 µV/√Hz — standing-line level).

### ✅ ADS1256 reset no longer needs the RESET pin (2026-07-26)

The chip is now recovered over SPI — `SDATAC, SDATAC, RESET(0xFE)` with CS cycled
between each (`adc_common._soft_reset`), replacing the RESET-pin pulse.
`CHIP_HARD_RESET_ON_START = False`; the pin is opt-in via `SEISMO_RESET_PIN=1`.
`rdatac.stop()` uses the same sequence.

- **Why:** a bare ADS1256 breakout (LC Tech ADS1256_V1.1, under evaluation) brings out
  only SCLK/DIN/DOUT/CS/DRDY/PDWN — RESET stays on the die. The old recovery would
  simply not exist there, and "chip wedged in RDATAC" bricks every later startup.
- **Proven on the Waveshare** (`station/reset_test.py`, run with the recorder stopped):
  **4/4 rounds genuinely wedged** — reproducing the real *"Received wrong chip ID"* —
  and **4/4 recovered by software alone**, RESET pin untouched.
- **Test-design trap worth remembering:** the first version wedged and re-opened in ONE
  interpreter and "passed" 3/3 on `CS pin already used. Must be exclusive!` — that is
  PiPyADC's class-level GPIO bookkeeping, not a wedged chip. Every phase now runs in
  its own process, which is the only way the hardware is actually asked anything.
- Recorder restarted clean: `rate_est 100.0, clock_err 0.0 ms, dropped 0, udp_dropped 0`.

### 🔎 Alternative ADC board under evaluation — LC Tech ADS1256_V1.1

Bare breakout, considered because the Waveshare's demo-sensor block cost us the whole
pre-2026-07-24 archive and its 5 V AVDD path is faulty. From the board photos:
**ADS1256IDB + 7.680 MHz crystal** (so `CLKIN_FREQUENCY` is unchanged), **ADR03B** 2.5 V
XFET reference (better than the Waveshare's LM285-2.5), **AMS1117-3.3** → 5 V in / 3.3 V
digital, an inductor + 22 µF tantalums on the supplies, and no demo circuitry.

- **The draw:** it is 5 V-only, so AVDD = 5 V and the *buffered* common-mode range is
  0–3 V. A mid-supply bias is 2.5 V, which fits — that is exactly the ✓ row of
  `doc/rev2-frontend.md` §"Open decision", i.e. **buffer-on**, the biggest remaining
  noise lever, currently blocked on the Waveshare's 5 V fault.
- **Must meter before use:** there is an R/C network between header P1 and the ADC
  (~16 resistors, many marked `1000` = 100 Ω, plus C12–C20). Series-R + cap to AGND is
  helpful; a divider to ground would attenuate the signal and load the 385 Ω coil.
  This is the demo-jumper lesson — do not trust the silkscreen, ring it out.
- No RESET on the header (hence the work above). Four unpopulated pads sit next to U3 —
  check whether one is ADS1256 pin 6.
- Swapping the live station starts a **new epoch**. Bench it first.

### ✅ `/history` — browse any past 4 h window (2026-07-26)

The dashboard has a **History** page: `/history?datetime=YYYYmmDDHHMM` renders a drum
for that 4 h window, off the **same interval envelopes the live drum uses** — one npz
load per row, no miniSEED parse, no obspy on the request path.

- **Retention flipped.** `heli_build` used to prune envelopes older than the 4 h live
  window; it now prunes only what predates `SEISMO_EPOCH_START` (default
  `2026-07-25T23:45Z`, the first 100 sps interval). ~20 KB/interval → **~2 MB/day**
  against 87 GB free. `heli_build.py --backfill` is the one-shot that fills the range
  (ran it: 65 intervals; the dir now holds the whole epoch, 1.6 MB).
- **Picker is constrained by what's on disk**, not by epoch-start..now: `_available()`
  reads only the npz *filenames* and offers an hour when its opening hour holds data,
  so 2026-07-25 offers only hour 23 and a not-yet-backfilled range simply can't be
  selected. Changing the date repopulates the hour list client-side and rewrites the
  canonical URL live (shown on the page for copying).
- **Blank rows are real.** A historical window always draws all 16 rows, missing
  intervals included, so the row→time mapping can't silently shift.
- **Scope = current epoch only, on purpose.** Pre-2026-07-25 is 57/60 sps through a
  different front end; offering it behind the same picker would invite exactly the
  like-for-like comparison that isn't valid. The page says so.
- **Operational note:** the live builder only ever builds the last 4 h, so if the
  dashboard is down >4 h a hole appears in the envelope set. `--backfill` heals it.

---

## 🌙 Overnight soak (started 2026-07-26 ~03:30 UTC)

Everything runs; the old rsync path is untouched. **Morning review checklist:**
- **Station acquisition:** `dropped`/`glitches` over a clean restart-free night (int32
  baseline; expect low). `cat seismo.local:~/seismo/health.json`.
- **Link loss:** collector `seq_gaps` + station `udp_dropped` — real WiFi-bridge loss over
  a full day (the honest N=2 stress number). `journalctl -u seismo-collector` on pi5.
- **Backfill:** archive completeness vs the station local file (should self-heal to ~0 gap).
- **Detector:** review `/v1/events` — note the strong 03:14 events (ratio 13.7, **182 µV**;
  ratio 10.8, 157 µV). Real, or cultural? This is the retune surface (`detector.py --day`).
- **Then Phase 2 step 2b — dashboard → `/v1/*`:** add apt `python3-obspy` on pi5 (for
  `/v1/waveform`), point the dashboard at `/v1`, then retire the station's inline detector
  + rsync mirror + live-pull. At that cutover also update the About page (2 edits, both
  currently still accurate): the "rsync-mirrored miniSEED" footer (`seismo_dashboard.py`
  line ~100) → served from `/v1`, and optionally the "Pi 5 renders/serves" line to note it
  now also stores+serves the archive. **STEIM2 is decided/closed — do NOT reopen it.**

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

## 🚗 Traffic training pipeline started (2026-07-24)

Goal: a car-counter trained on observed counts. Charles logs discrete intervals with
`analysis/collect_traffic.py` — a stopwatch CLI: START beep → type `z` (north) / `/`
(south) per vehicle → STOP beep at `--interval` (30s default) → RETURN → appends
`start_utc,end_utc,total,north,south` (creates the CSV with a header). Then
`analysis/traffic_features.py`
joins each interval to the archive and reduces it to features (`rms_uv`, `peak_uv`,
sub-band RMS 1-5/5-15/15-28 Hz, `n_bumps`, coverage) → `<labels>.features.csv`. All
features high-passed (DC/epoch-robust). Offline, no API, no Pi changes — decided over a
live endpoint because labels are interval-based, so windowed archive reduction is the
right tool. `labels.example.csv` is a template.

- **The 5-15 Hz band is the standout discriminator** on real data: ~0.5 µV quiet night
  vs 5-8 µV during the commute (~10-16×), matching the by-eye traffic correlation.
- **`n_bumps` is provisional/weak** — it thresholds against each interval's own median, so
  it misfires on quiet windows and undercounts sustained traffic. Needs a fixed threshold
  from a quiet-epoch baseline (unavailable while traffic-limited). Let real labels decide
  if it survives.
- **Collect each label run within ONE epoch** (no hardware changes mid-session) or the
  transfer function shifts under the features.
- Next: Charles collects real counts → train (start simple: does band RMS regress on
  cars/interval?). A live 1 Hz `/traffic` display is a possible later slice, not needed
  for training.
- **One-off event annotations:** `analysis/log_event.py "label" [--at HH:MM] [--dur s]`
  appends to `analysis/annotations.csv` (`t_start_utc,t_end_utc,label,note`) — known
  discrete events (street sweeper, garbage truck, helicopter) as high-confidence labels.
- **First individually-resolved vehicle (2026-07-24):** a street sweeper at 18:40 UTC and
  its return pass ~18:42 both show clearly — 1–15 Hz RMS 5.6/4.5 µV vs 2.8 quiet (2.0×/
  1.6×), pass 1 a smooth transit swell, pass 2 sharper. Confirms the reframe: heavy/slow
  vehicles resolve cleanly where aggregate car counts washed out. This is the shape of the
  real target (heavy-vehicle detection), and a local microquake would look similar.

## Plan (agreed 2026-07-23)

**Hands off the hardware until the weekend.** Let the current configuration run a
couple of days to get a feel for it, THEN tackle the 5 V AVDD fault (which unblocks
buffer-on, the biggest remaining noise lever -- see `doc/rev2-frontend.md`).

Current configuration = RDATAC **100 sps** epoch (2026-07-25; was 60 sps, see the
switch note above) gapless, galvanic isolator in (reversed), gain 64, garage slab,
**no shunt damping fitted**. (PPSD/template work that started on the `rdatac-60sps`
epoch now has a `rdatac-100sps` successor epoch.) What two
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
−8/+22 s slice the sparkline already loads (14 ms/event, no extra I/O). Soft label only:
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
- [~] **Phase 5** — record a real event; cross-check vs USGS / nearby Raspberry Shake.
  **Capability demonstrated 2026-07-24:** first correlation of readings to an external
  physical event — Hwy 12 traffic (~90 m), repeatable over dozens of cars. This closes the
  forward link world→ground→sensor→screen and proves the station resolves a weak, near,
  impulsive source — the same geometry as a local microquake. Still need an actual
  catalogued earthquake to tick the box, but the chain is now validated end to end against
  a known source, not just self-consistent.

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
- Still to model (Pi/ADC side): **walls** (power-connector cutout on +Y, Wi-Fi **dongle slot** on −X) + a **lid**. Single combined case, flat base, no leveling feet. Consider a plate slot between Pi and pocket to break the vibration path.
- **Gen-1 geophone case (2026-07-28) — DESIGN DONE AND VALIDATED, printing scheduled 2026-07-29.**
  **Resume here:** slice `stl/geophone_case.stl` floor-down and `stl/geophone_case_lid.stl` flat — 0.28 mm layers, 4 walls, 6 top/bottom, 40% gyroid, **no supports**, brim if adhesion is marginal (~200 g, 7–9 h body, <1 h lid). Assemble in this order: (1) XLR into its seat, 2 × M3 × 10 countersunk + nuts, **before the geophone** or there is no hand room; (2) twisted 26 AWG to pins 2/3, pin 1 to nothing, ~60 mm service loop hot-glued to the wall; (3) geophone into the pocket on putty, standing 2 mm proud of the rim; (4) lid on 4 sheet-metal screws, 3 more as feet. Nothing is unresolved — both the geometry and the print orientation are validated on coupons.
  **Still the bigger lever, and independent of the case:** cut the plastic floor tile out from under the station and re-measure on bare concrete (`BACKLOG.md`, "⚠️ COUPLING"). New epoch, ~35 min to settle. `parts/geophone_case.py` + `parts/geophone_case_lid.py`. A deliberately crude POC whose only jobs are *pick it up and set it down* and *put the XLR on the case so the cable unplugs*. **116 × 116 × 79 mm** (74 body + 5 lid, plus ~4 mm of foot screw) rounded square, PLA, no seals, no ballast, no inserts. 30 mm of headroom over the element for terminals, wire and slack. Lid engraved "GEOPHONE". Element stands **2 mm proud of the cup rim** (cup 34 vs element 36) — flush meant any real variation put the rim high, and a hold-down pad cannot drop into the bore alongside the element (0.2 mm radial), so the element has to come up. Two **tall clamp bosses** (top 6 mm above the element) flank the cup as anchors; **no clamp fitted in gen 1** — the element is vertical under 1 g so the rim contact is never in tension at seismic amplitudes and gravity is already the preload. Any future hold-down must be COMPLIANT (silicone O-ring or extension spring over the bosses, with a printed saddle clear of the terminal pins); not paracord, which creeps and silently loses preload, and not rigid PLA, which at ~560 N/mm swings ±80 N on print tolerance alone. Three screw heads as feet (three-point contact; also lets the floor print flat on the bed instead of bridging over printed feet; ~1.4° of tilt per turn, which is the only leveling it has and enough). **No vents** — no heat source inside and the cavity's lowest acoustic mode is ~1.5 kHz, 30× above Nyquist, so they bought nothing and cost a convection path over the element. **XLR mount — VALIDATED on the printed coupon, 2026-07-28, twice.** Flat first (geometry: connector passes the bore, flange seats, panel and nut landing good), then **reprinted standing on edge in the case's wall orientation** — the flat print had put the bore axis vertical, so it never tested the overhang the real wall has. Vertical print at case layer height: bore, screw holes and pad underside all print clean, connector still passes. **No supports needed anywhere.** Connector passes the bore, flange seats in the recess, panel thickness and nut landing all good; the case carries the same geometry, so it is ready to print.
- **XLR mount detail.** Connector: 22 mm shell but the shank carries four slots/ribs (three centring + one release-lever) → **24 mm bore**, the published cutout, which is oversized precisely so those clear rather than engage; 23 mm fouls them and the connector will not pass; flange **30 × 25 × ~2 mm**; two countersunk holes 30 mm centre-to-centre on a diagonal. Offsets are the published D-series pattern — **±(10, 11.5) mm** from the bore centre, larger offset on the flange's 30 mm axis — spanning 30.5 mm, which reproduces the measurement. Panel screw holes **3.4 mm (M3)**: the measured 5 mm is the countersink's outer diameter — the standard flange takes countersunk M3 — and at a 24 mm bore a 5 mm hole leaves only 0.74 mm of web to the bore, vs 1.54 mm at 3.4. **The flange seats in a recess in a raised pad on the OUTSIDE wall**: pad 38 × 38 standing 1.5 mm proud, flange footprint recessed 2.0 mm into it → flange flush, **2.5 mm of panel** under it (inside the connector's 1–3 mm range). The recess is structural, not cosmetic — it carries the latch's lateral and torsional load in shear through plastic so the two screws only clamp. Nothing on the inside face: the case is a rounded square so that wall is already flat, and an inside pocket cannot restrain a flange bearing on the outside. Flange runs **30 mm axis vertical** (`xlr_flange_axis = "V"`) — a free choice of how to mount it, not a property of the connector, picked because it puts the screws 23 mm apart vertically instead of 20 against a hanging cable. `parts/xlr_coupon.py` is a 56 × 56 × 4.5 mm fit test (~10 min) reproducing the wall cross-section exactly; it carries all four sign combinations of the hole pattern so handedness never has to be established (two holes take screws, two hide under the flange). **Fasteners: 7 × #6 × ½″ sheet-metal (4 lid, 3 feet) + 2 × M3 × 10 countersunk + nuts for the XLR** (grip is just 4.5 mm; flat head seats in the flange countersink, no washer needed). Fit the connector before the geophone goes in.
- **Internal wiring (gen-1 case).** 26 AWG fine-stranded, silicone jacket, **twisted ~5 turns/inch** — the loop area between the two conductors is the magnetic-pickup antenna and any EMF induced there is in series with the 375 Ω coil, i.e. indistinguishable from signal. Not solid core (fatigues, and stiff enough to preload the element in its pocket). `+` → XLR **pin 2**, other → **pin 3**, **pin 1 unconnected** so the cable shield stays grounded at the Pi end only. **~60 mm service loop**, coiled along the wall and tacked with hot glue so nothing bears on the element — the pocket is 36 mm deep, so the lead must be long enough to lift the element fully clear and rest it on the rim rather than soldering down a hole. **No in-line JST/connector** — a tin crimp is a thermoelectric junction worth ~µV/°C against a ~1.6 µV noise floor, with two per conductor, drifting straight into the sub-Hz band where the thermal problem already lives; and it buys nothing, since the XLR *is* the service disconnect and swapping the element is two solder joints. If a disconnect is ever genuinely needed, gold contacts, not JST.
- **Servicing: the XLR belongs to the CASE, not the sensor, and never comes out.** It cannot be withdrawn with wires attached anyway — 22 mm shell in a 24 mm bore is 1.0 mm of annular gap and a twisted 26 AWG pair is ~2.4 mm across. Both service operations are therefore the same two joints at the ELEMENT end: swapping the geophone leaves the connector in place, and swapping the case (gen 2) also leaves it, because gen 2 takes the outdoor TOP-series connector, not this one. So the XLR solder cups are soldered exactly once — make them neat and heat-shrink them; keep the element-end joints tidy and accessible. Views: `doc/geophone_case*.svg`.
- The sealed/outdoor version is **gen-2**, specced separately in `doc/BOM-geophone-case.md`.

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

# BOM — inline calibration injector

A small printed box that sits **in the XLR run near the Pi**, injects a known current
into the geophone coil a few times a day, and lets go. The mass rings down; the same coil
reports it; `analysis/ringdown.py measure --at <UTC>` fits f0 and zeta out of the archive.
Nothing has to be touched, so the usual ~35 min settling never applies.

    Pi case (female chassis) --short cable-- [ CALIBRATOR ] --long cable-- geophone case

**Why this exists:** the response in `station/SS.OAKM1.xml` currently carries f0 = 4.5 Hz
(nameplate) and zeta = 0.6 (vendor spec) because `analysis/response_fit.py` proved the
spectral-ratio route cannot constrain them — 1.64 km of site response between here and
NP.1835 swamps the corner. Only a bench measurement isolates the instrument. And once it
is automated it stops being a one-off: `epochs.py` records changes *you made*, while a
calibration series records changes that *happened* — a spring aging, a thermal excursion,
a knock nobody witnessed.

Observatory instruments have had exactly this since forever, driven from a **separate**
calibration coil. We have one coil, so injection and measurement share it — the "signal
coil calibration" method. The practical consequence is only that it should fire in quiet
hours, which the automation gives for free.

## Connectors — standard D-series, NOT the TOP series

The sensor case uses `NC3MDX-TOP` (IP65) and that part does **not** use the standard
cutout. This box lives indoors beside the Pi, so it takes plain D-series, which is what
`dimensions.py` (measured off the part, 2026-07-28) and the validated `parts/xlr_coupon.py`
already describe: 24 mm bore, 30 x 25 flange, 2 x M3 on the 30 mm diagonal, 32 mm body
depth behind the panel — that last one sets the box's minimum internal width.

| Qty | Part | Notes |
|-----|------|-------|
| 1 | Neutrik **NC3FD-L-B** — female chassis | Geophone side. Accepts the long cable's male end |
| 1 | Neutrik **NC3MD-L-B** — male chassis | Pi side. Accepts the short cable's female end |
| 1 | XLR mic cable, **0.5–1 m**, female→male | Box to Pi. Buy it, do not build it — same reasoning as the sensor cable |
| 4 | M3 x 10 countersunk machine screws + nuts | Two per flange. Flat head seats in the flange countersink |

## The injector

**Every part below is through-hole.** This is a perfboard build; nothing here needs an
adapter or a hot-air station. (The ATtiny412 was briefly in this list and is not any more
— the whole tinyAVR 0/1/2-series is SMD-only.)

| Qty | Part | Notes |
|-----|------|-------|
| 5 | **Panasonic AQY212EH** PhotoMOS, 4-DIP through-hole | SPST-NO, 0.85 Ω on, nanoamp off-leakage, 5 kV isolation. **Not** the `EHA`/`EHAX` suffixes — those are surface-mount |
| 1 | **ATTINY85-20PU** — PDIP-8 | Through-hole, so it drops straight into perfboard; ISP programming with a USBasp or Arduino-as-ISP. Sleeps at ~5 µA in power-down with the watchdog, wakes on its own timer, fires the burst. **Not the ATtiny412** — there is no DIP version of it (the whole tinyAVR 0/1/2-series is SMD-only; `-SSF`/`-SSN` are both SOIC-8, the suffix being temperature grade only), so it would need a SOIC-8→DIP adapter for no useful gain: its ~1 µA would give 25 years on paper, but CR2032 self-discharge caps real life near 8–10 years either way, and the ATtiny85's ~5 years is already far beyond any revisit interval. A micro rather than a 555/CD4060 because the *three pulses at 2.00 s* signature is what makes the bursts self-identifying in the archive — trivial in firmware, clumsy in logic. A CMOS 555's ~150 µA quiescent would flatten a coin cell in months |
| 1 | **LM4040DIZ-2.5/NOPB** shunt voltage reference, TO-92 | The part that makes this a calibration rather than a battery-discharge curve — see below. **Buy whichever grade DigiKey actually stocks** — the A is usually a marketplace listing with a ~2 week lead time, and the difference does not matter: the D grade's ±1 % initial tolerance is irrelevant (**measure the actual voltage once with a DMM at build time and write it on the box** — that is the number that counts, and it turns 1 % into your meter's accuracy), and even the worst grade's 150 ppm/°C over a 20 °C garage swing is 0.3 %, several times smaller than the percent-level sensitivity changes this exists to detect — and temperature is logged separately, so even that is separable. Any of 2.048 / 2.5 / 3.0 / 4.096 V also works against the 6 V cell B; just size the injection resistor for V_ref / 10 µA and the bias for ~150 µA |
| 3 | CR2032 cells + **3 × single holders with flying leads** (`DKS-CR2032H`, DigiKey Standard, 6" leads; or MPD `BC-2032-E2`) | Cell A (one holder, 3 V) runs the ATtiny and the LED. Cell B (**two holders in series, 6 V**) runs the injection leg — a 3 V cell leaves an LM4040-2.5 no headroom. **Wire-lead, not PC-pin**, and **screwed or taped to the box wall, not the board**: changing cells then never involves the perfboard, and the holders can sit where a hand can reach them instead of wherever the layout put them. Three identical singles rather than a single + a dual, because series-wiring two is one solder joint and it halves the number of parts to source. Through-hole PC-pin holders *do* exist if you would rather board-mount (Keystone `103`, MPD `BVSD-2032-PC`, `BA2032`, `BK-913`) — DigiKey's category is mostly SMD reels by volume, so set **Mounting Type → Through Hole** or the first several pages are all SMT |
| 1 | ~249 kΩ **0.1 %** metal film, axial | Injection resistor. 2.5 V / 249 kΩ ≈ 10 µA. 249 k is an **E96** value — the grid 0.1 % and 1 % parts use — so it is stocked, but it is invisible if you are filtering at 5 %, where E24 gives you 240 k and 270 k instead. **Any nearby value is fine.** What the calibration needs is a current that is *known and stable*, not one that is round: measure the resistor once with a DMM and write it on the box, exactly as with the reference. The 0.1 % part is specified for its **tempco and long-term stability** (~25 ppm/°C), which you cannot measure away — not for its initial tolerance, which you can. **A 1 % metal film is perfectly adequate** and worth using if one is already in the drawer: 50–100 ppm/°C over a ~20 °C garage swing is 0.1–0.2 %, against percent-level changes we are trying to see, and temperature is logged separately so even that is separable. Long-term drift is moot at 2.5 V / 220 kΩ ≈ 25 µW — there is no self-heating to age it. **Metal film is the requirement, not the tolerance grade**; carbon film at 200–500 ppm/°C would be the one to refuse. 220 kΩ gives 11.4 µA, which is 14 % more injection than the nominal 10 µA and slightly more margin against `SNR_SPEC` — and the 22 kΩ bias still leaves ~148 µA through the LM4040, well above the ~65 µA it needs to regulate. **And check the resulting burst amplitude against `SNR_SPEC` before committing to any value** — see below |
| 1 | 22 kΩ axial | LM4040 bias: (6 − 2.5)/22 k ≈ 160 µA |
| 1 | 330 Ω axial | PhotoMOS LED from a 3 V pin: (3.0 − 1.25)/5 mA |
| 1 | 1 kΩ axial + 3 mm LED | Status blink. A bring-up aid, not an operational feature — the box sits ignored for months |
| 1 | Panel-mount momentary pushbutton, SPST-NO | **Short press: restart the soak. Long press: fire a burst now.** Plain panel mount, no recess — the box lives on a shelf and is ignored for months at a time, and anything disturbing it enough to press a button has already caused worse problems than a restarted soak. Wakes the ATtiny on pin-change with the internal pull-up, so zero standby current with the button open. (Not a reed switch — that belongs on the *sealed* geophone case. This box is indoors and already has two 24 mm holes in it, so there is no penetration to avoid and a magnet is just something to lose) |
| 2 | 0.1 µF ceramic + 1 x 22 µF | ATtiny decoupling; the 22 µF holds the rail through the 5 mA LED pulse |
| 1 | 6-pin ISP header, 2x3 0.1" | For the ATtiny85 |
| 1 | **8-pin DIP socket** | Program the chip on a breadboard and drop it in; pull it to change the interval. Also makes a bricked chip a 50¢ problem rather than a desoldering job |
| 1 | ISP programmer — **USBasp** (~$8–12, Amazon/eBay; open design, many clones) or **any Arduino running `ArduinoISP`** (free — Uno/Nano/Pro Mini, six wires, 10 µF across the Uno's RESET to GND). Adafruit's USBtinyISP is **discontinued**, do not go looking for it. Buying a USBasp: check the listing includes a **10-pin→6-pin adapter** (the board is 10-pin IDC, our header is 2×3) and has the **slow-SCK jumper** (usually JP3) | Board package: **ATTinyCore** (Spence Konde) |
| 1 | Small perfboard | It is a dozen parts. No PCB needed |
| 1 pk | Insulated crimp ferrules, 22–20 AWG | `STATUS.md`: tinned strands cold-flow under screw terminals. Ferrules, not solder |

## How hard to inject — a number the software fixes, not a preference

`analysis/calfinder.py` is what finds these bursts in the archive, and it only works
above a floor it measures on itself (`python analysis/calfinder.py selftest`). The
sweep there gives, for a burst of three pulses in a realistic background:

| damping | reliably found above |
|---|---|
| ζ = 0.3 | SNR ≥ 14 |
| ζ = 0.6 | SNR ≥ 20 |
| ζ = 0.85 | SNR ≥ 40 |

where SNR is the burst's peak amplitude over the background RMS in the 0.5–20 Hz band.
Heavier damping is harder for the obvious reason: a well-damped element barely rings,
so there is less waveform to recognise. Since **ζ is precisely the unknown the injector
exists to measure**, the level has to be sized for the worst case, not the expected
one. Hence `SNR_SPEC = 50` in `calfinder.py`, which carries margin over the ζ = 0.85
row.

This is a requirement on the hardware, and it does not negotiate. The detector's
selectivity comes from `RHO_MIN = 0.90` — the same gate that rejects a truck over
expansion joints, and machinery ticking at exactly 2.00 s. Lowering it to rescue a
burst that was injected too faintly would trade the property the whole design rests
on. **If bursts come out weak, change the resistor, not the threshold.**

So: 10 µA is the starting point, not the answer. Once the box is inline, fire a burst,
run `calfinder.py scan` over that day, and read the reported `amp_counts` against the
day's background. If the margin is thin, drop the injection resistor (68 kΩ ≈ 37 µA is
still a small perturbation) and re-check. Headroom is the limit at the other end — the
ADS1256 at PGA 64 saturates at ±2·VREF/64 ≈ ±78 mV — so there is a wide range to work
in, and no reason to sit near the bottom of it.

## The status LED is gone, and the shunt drive takes MISO

**Decided 2026-09-04 (Charles): drop the status LED.** "I'm not in the room when it's
deployed." The LED existed so the box visibly does something during the acceptance test,
but the acceptance test that matters is `calfinder.py` finding the burst in the archive —
which is the only evidence that survives the walk back from the garage.

That frees **PB1**, and PB1 is the pin this design wants. The ATtiny85 was out of I/O:
PB3 injector, PB4 button, PB5 RESET (untouchable), and PB0/PB2 are MOSI/SCK — *driven by
the programmer* during ISP. A PhotoMOS LED there would hang ~5 mA on the programmer's
output, which is the load this document already argues against putting on MOSI: "the one
end of the link we cannot specify — USBasp clones vary." **MISO is driven by the ATtiny
itself**, so the shunt drive on PB1 loads a driver we control, exactly as the old LED did.

**And the shunt socket stays empty during programming.** During ISP the ATtiny toggles
MISO as it answers the programmer, so the shunt PhotoMOS will flicker closed. With no
resistor in the socket that does nothing whatsoever. Removing the resistor is a
one-second step in the flashing procedure and it removes the only functional consequence.

Note what each half fixes, because they are different problems: dropping the LED removes
the *electrical* risk (nothing loads the programmer's outputs), and the empty socket
removes the *functional* one (nothing is switched across the coil while MISO chatters).
Neither alone is sufficient.

## Changing the shunt — a jack on the wall, and resistors as plug-in modules

**Decided 2026-09-04 (Charles): a connector on the outside of the box.** "I don't have to
open and fiddle with a circuit (which I'd stress to breaking)." That is also the existing
rule — `doc/rev2-frontend.md` makes *"the source must be swappable without a soldering
iron"* a **requirement**, because a test you have to open the box for is a test that does
not get run. And opening this box means disturbing the injector and the coin cell
immediately before a campaign whose whole premise is that nothing else changed.

**Do not put a resistor socket on the wall. Put a jack, and make each value a module.**
A bare resistor in an external screw terminal is fiddly with cold fingers, easy to fit
crookedly, and gives no record of what is in there. Instead solder each resistor inside
a **3.5 mm mono (TS) plug**, label the barrel with its value, and keep the set in a bag.
Swapping is then: unplug, plug, write the value in `analysis/epochs.py`. No tools, no
bare leads, no ambiguity about what is fitted.

| Qty | Part | Notes |
|-----|------|-------|
| 1 | 3.5 mm mono **panel** jack, non-switched | 6 mm cutout — far smaller than the XLR's 24 mm, which matters on a box whose width is already set by the XLR body depth |
| n | 3.5 mm mono plugs, plastic barrel | One per shunt value. Solder the resistor tip-to-sleeve inside |
| n | metal-film resistors, 5 % E24 | See below on why 5 % is already finer than the measurement |

**Why 3.5 mm and not something bigger.** It cannot be confused with the XLRs — the box
carries an `NC3FD-L-B` and an `NC3MD-L-B`, and plugging a shunt module into the signal
path would be a bad afternoon. It is mechanically distinct, physically far too small to
fit, and nothing else in this system uses 3.5 mm. Its contacts also *wipe* on insertion,
which self-cleans a connection that will sit in a garage between uses.

**Empty is the correct default.** No plug fitted = no shunt = open circuit, which is both
the unshunted baseline and the state wanted while flashing (MISO chatters during ISP and
will toggle the shunt PhotoMOS; with nothing plugged in that does nothing).

**Wiring: PhotoMOS on the coil side of the jack.** Then when the shunt is open, the jack
and its module are disconnected from the coil rather than hanging across it. A single
SPST can only isolate one leg, so the other remains a short stub — keep the internal run
from PhotoMOS to jack as short as the layout allows, because it sits across a source
producing microvolts.

**5 % E24 parts are already finer than the instrument that judges them.** `ζ_e =
k/(Rc+Rs)`, so `dζ/ζ = −dRs/(Rc+Rs)`: a 5 % part moves ζ by about 4 %, while the
ring-down fit carries a **−0.066 systematic residual at ζ = 0.85** (STATUS open thread 2)
and `calfinder`'s self-test says ζ = 0.85 needs SNR ≥ 40 to be reliable at all. Buying
1 % parts would be measuring the resistor with a ruler and the damping with a thumb.

**The low end is bounded by signal, not by the part.** The shunt keeps `Rs/(Rc+Rs)` of
the output, so at `Rs = Rc = 375 Ω` half the signal is gone and at 100 Ω only 21 %
remains — and the shunted burst still has to carry enough amplitude for `ringdown.py` to
fit a decay. A short is useless: maximum damping, zero signal, nothing to measure. Treat
a few hundred ohms as the practical floor.

**A multiturn trimmer is fine for the campaign and wrong for the finish.** It walks the
value continuously while ζ is watched, but a cermet trimmer has real excess (1/f) noise
and a wiper that can go intermittent, sitting across a microvolt coil. Find the value
with it, measure it, then fit a metal-film part of that value.

## The switched shunt — a second PhotoMOS that measures the generator constant

**Decided 2026-09-04 (Charles).** A second AQY212EH, identical to the injection one,
switches a **socketed** shunt resistor across the coil. Each calibration then fires
**two bursts**: three pulses with the shunt open, a 15 s gap, three pulses with it
closed. You change the resistor by hand every so often and record it in
`analysis/epochs.py`; the schedule needs no command channel, no relay ladder and no
telemetry to say which value is fitted.

**Why it is worth one extra part.** `doc/shunt-damping.md` calls measuring the generator
constant "the real prize", and G is the biggest disputed number in the instrument — the
datasheet says 28.8 V/(m/s), the effective measurement says nearer 3.8, and the whole
question of whether a shunt does anything at all hinges on which. `ringdown.py solve`
gets G from exactly two ζ measurements, one unshunted and one with a known resistor.
This produces that pair **four times a day, fifteen seconds apart**.

Fifteen seconds apart is the point, not a detail. ζ estimates drift with ground
conditions, temperature and background noise, so a Tuesday measurement against a Friday
one buries the shunt's effect under everything that changed in between. Inside one burst
pair, all of that is common and cancels — the same reason a paired test beat a pooled one
when the coda features were evaluated on 2026-09-04.

**And it separates measuring from committing.** The shunt is connected only during the
second half of each burst, so the station keeps its full open-circuit sensitivity for
actual recording while the damping curve is characterised. You learn what a value *would*
do before deciding to live with it — which is the bind shunt-damping.md is stuck in.

**Two bursts, not one six-pulse burst.** `calfinder.py`'s `AMP_TOL` is 1.30: pulses
within one burst must match in amplitude to 30%. A shunt costs `Rc/(Rc+Rs)` of the
signal, so a combined burst passes down to about 2.2 kΩ and is **rejected at 1 kΩ** —
precisely the low end where the damping is. Two bursts of three matched pulses are
internally consistent at any value, and the finder's 749-hour zero-false-positive result
carries over untouched. The gap must clear `amp_out`, which probes 2 s before onset and
6 s after; 15 s also lets the first ring-down die completely so the second is not fitted
on a contaminated decay.

**Open on power-up, and open on reset.** The shunt loads the coil, so a stuck-closed
PhotoMOS costs sensitivity 24/7 and silently changes the instrument. Drive it from a pin
that idles low, and leave the socket empty until the first sweep says a value is wanted.

| qty | part | why |
|---|---|---|
| 1 | **Panasonic AQY212EH** PhotoMOS (a second one) | switches the shunt across the coil |
| 1 | 330 Ω axial | its LED drive, same as the injector's |
| 1 | 2-way screw terminal or turned-pin socket | the shunt itself, changed by hand |

**Still to settle before the build:** `doc/rev2-frontend.md` says keep the shunt at the
**board** end, not the sensor, and the interface board already has an empty socket across
AIN0/AIN1. If the injector sits mid-cable, its switched shunt is not at the board end —
either move the injector, or accept the cable in parallel for the few seconds of the
measurement. Probably negligible for a ζ fit, but it should be a decision.

**`calfinder.py` needs to learn about pairs.** It currently finds independent bursts;
something must recognise that two bursts 15 s apart are a matched pair and hand them to
`ringdown.py solve` in the right order. Its self-test should grow a synthetic paired
burst before any of this is trusted.

## Why the LM4040 goes in from day one

Injection current is I = V/R. A bare coin cell starts near 3.0 V, sags toward 2.7 V over
its life, and moves with temperature — so I drifts. That is harmless for f0 and zeta,
which come from the *shape* of the decay. But the whole point of the automated loop is to
notice when the **sensor** changes, and a drifting battery produces exactly the same
signature as a drifting sensitivity. Without the reference you have built a monitor that
cannot distinguish itself from its subject. Retrofitting it means opening the box.

**Gate it with the PhotoMOS, upstream of the bias resistor**, or its ~160 µA standby
would flatten the cell in about three months:

    cell B (+) -- PhotoMOS -- R_bias --+-- 249 kΩ -- XLR pin 2 ... coil ... pin 3 -- cell B (−)
                                       +-- LM4040 --------------------------------------+

Off, nothing draws anywhere. On, the reference settles in microseconds — irrelevant
against a 2 s pulse, and `ringdown.py` skips the first 60 ms regardless.

## Pin assignment — constrained by in-circuit ISP

The 2x3 header is fitted so the chip can be reprogrammed without pulling it. That makes
the ISP lines application pins too: PB0 = MOSI, PB1 = MISO, PB2 = SCK, PB5 = RESET. Only
**PB3 and PB4** are untouched by ISP, and there are three I/O to place — so the
assignment is not free:

| pin | signal | why |
|---|---|---|
| PB3 | **PhotoMOS LED drive** | The actual function. Must never share a line with ISP |
| PB4 | **Button** | Input, internal pull-up, pin-change wake |
| PB1 (MISO) | **Shunt PhotoMOS LED drive** | Was the status LED, dropped 2026-09-04 to free this pin. **MISO, not MOSI:** MISO is driven by the *ATtiny* and only read by the programmer, so the few mA come out of a driver we control. Hung on MOSI the same load sits on the *programmer's* output instead, which is the one end of the link we cannot specify — USBasp clones vary. Flickers while programming; keep the shunt socket **empty** when flashing and that is harmless |

- **No low-impedance load on MOSI/MISO/SCK.** The programmer must drive those lines; the
  status LED at 1 kΩ (~3 mA) is fine, the PhotoMOS drive at 330 Ω would fight it. That is
  the reason the drive goes on PB3 rather than wherever is convenient on the perfboard.
- **No capacitor on RESET.** A tempting noise-immunity addition that breaks ISP outright.
  The internal pull-up is enough in a battery-powered box; a 10 kΩ to VCC is optional,
  a cap is not.

## Fuses — two settings that matter more than the code

**Read them before writing anything: the factory defaults are already correct.** A new ATtiny85 ships `lfuse 0x62 / hfuse 0xDF / efuse 0xFF`, which is internal 8 MHz RC with `CKDIV8` (so, 1 MHz), BOD *already disabled*, `SPIEN` enabled and `RSTDISBL` clear — exactly what is wanted below. `make fuses` reads them back; `make writefuses` exists but should normally be unnecessary. Every fuse write is a chance to brick the part, so the best outcome here is confirming there is nothing to do.

- **Disable the brown-out detector.** BOD enabled draws ~20 µA continuously on an
  ATtiny85 — four times the sleep current the whole power budget assumes, turning ~5 years
  of cell life into about one. There is nothing to protect: a coin cell decays slowly and
  the firmware holds no state worth corrupting.
- **Never set RSTDISBL.** It reclaims the reset pin as I/O and permanently disables ISP;
  recovery needs a high-voltage programmer. There is no pin pressure here — LED out and
  button in uses two of five I/O lines.
- Internal RC oscillator, no crystal. Its ±10 % drift is *wanted*: it walks the bursts
  through the day so calibrations sample the whole diurnal temperature range, which a
  disciplined clock would never do.
- **Program with the cells out**, powered from the programmer — most ISP dongles drive
  5 V and that must not reach an installed CR2032.

**The gotcha that stops most first ATtiny85 attempts:** a fresh chip ships with `CKDIV8`
set, so it runs at **1 MHz**, and ISP needs its clock below ¼ of the target — under
250 kHz — while most USBasp clones default to 375 kHz. It fails with
`avrdude: error: program enable: target doesn't answer`, which reads exactly like a dead
chip or miswiring and costs an evening. Set the slow-SCK jumper, or pass `-B 8` to
avrdude. Confirm this works before suspecting anything else.

## Wiring rules

- **Pin 1 straight through**, connector to connector, and **nothing in the box touches
  it.** Cell A, cell B, the ATtiny and both PhotoMOS sides all float. This preserves
  "shield grounded solely at the Pi" from `BOM-geophone-case.md`. (In a PLA box the two
  connector shells are insulated from each other, so shell-bonded pin 1 is harmless.)
- Cell B's flying leads are the one place the wire-lead holders cost you something: that
  loop wants to stay small. Trim them to reach and twist the pair. Cell A's can be as
  long and untidy as the box demands — it feeds nothing that the geophone sees.
- Keep cell B, the 249 kΩ and the PhotoMOS **output** pins as one tight loop near the
  output connector. Keep the ATtiny, cell A and the LED leads on the other side. The
  PhotoMOS gives 5 kV of isolation — do not undo it by running the two together.
- Injector at the **Pi end** of the run, not the sensor end.

## Before it is powered for the first time

Three stages, each ending in a quiet-night noise floor compared against the documented
**~0.8 µV RMS in 1–15 Hz**, and each costing a ~35 min settle. Do not merge them: they
fail for different reasons and a merged test cannot tell you which.

1. **Populated, batteries OUT.** Not a straight-through wire — the whole board, fully
   assembled, in the run. This is not a preliminary check, it is *the steady-state
   condition*: the box spends 86,376 s a day doing exactly this, and the pulses are the
   exception. It exercises the PhotoMOS off-state leakage and output capacitance in
   series with the 249 kΩ, the board's stray capacitance to the signal pair, the layout,
   and every joint and ferrule. If the floor moves here, the fault is passive and
   physical.
2. **Batteries IN, firmware in its startup soak.** A running microcontroller with its
   oscillator going, centimetres from a µV differential pair, is its own noise source —
   and this project's worst-ever event was a *powered* device coupling into this exact
   analog path. A clean stage 1 says nothing about stage 2.

   **The firmware enforces this stage itself: on every power-up it sleeps for
   `SOAK_H = 48` before the first burst.** A spot check is nearly worthless here, because
   the floor swings from ~0.8 µV RMS at night to ~3.5 µV in the afternoon — only an
   hour-for-hour comparison against the preceding days can reveal a small addition. Two
   diurnal cycles rather than one, so day-to-day weather does not masquerade as a result.

   Because it re-soaks on *every* power cycle, a battery change automatically produces a
   fresh baseline, and over the years those accumulate into a record of whether the box's
   own contribution has drifted as its connectors age.

The button's short press **restarts the soak** rather than toggling anything off: the
   gesture means "I just disturbed something", which is what it is wanted for almost every
   time, and re-baselining and silencing become one action. Note this does not stop the
   oscillator — the micro keeps running, so whatever stage 2 measures is present whether
   soaking or armed. That is the honest reading and the reason stage 2 exists.

   The status LED should distinguish soaking from armed, so the state is readable at a
   glance without a meter.
3. **Firing.** Long-press to fire a burst on demand rather than waiting out 48 h of soak
   plus 6 h to the first scheduled one. Confirm the burst looks as designed, that
   `ringdown.py measure --at` fits it, and that the signature finder catches it before it
   reaches `events.log`.
3. Add an `analysis/epochs.py` row the day it goes in — a signal-path hardware change.
4. **Write the signature finder first.** A 27 mV release against a ~1 µV floor is roughly
   27,000x: every pulse will trigger the detector. Four bursts a day, unrecognised, is
   ~1,460 fake high-amplitude "cultural" triggers a year going straight into `events.log`
   and the classifier's training set. Recognise them by the 2.00 s spacing and matched
   amplitudes, exclude them from training, and hand them to `ringdown.py --at`.

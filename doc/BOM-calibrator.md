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

| Qty | Part | Notes |
|-----|------|-------|
| 5 | **Panasonic AQY212EH** PhotoMOS, 4-DIP through-hole | SPST-NO, 0.85 Ω on, nanoamp off-leakage, 5 kV isolation. **Not** the `EHA`/`EHAX` suffixes — those are surface-mount |
| 1 | **ATtiny412** (or ATtiny85) | Sleeps at ~1 µA, wakes on its periodic interrupt, fires the burst. A micro rather than a 555/CD4060 because the *three pulses at 2.00 s* signature is what makes the bursts self-identifying in the archive — trivial in firmware, clumsy in logic. A CMOS 555's ~150 µA quiescent would flatten a coin cell in months |
| 1 | **LM4040DIZ-2.5** shunt voltage reference | The part that makes this a calibration rather than a battery-discharge curve — see below |
| 3 | CR2032 cells + holders (1 single, 1 dual) | Cell A (single, 3 V) runs the ATtiny and the LED. Cell B (**two in series, 6 V**) runs the injection leg — a 3 V cell leaves an LM4040-2.5 no headroom |
| 1 | 249 kΩ **0.1 %** metal film | Injection resistor. 2.5 V / 249 kΩ ≈ 10 µA |
| 1 | 22 kΩ | LM4040 bias: (6 − 2.5)/22 k ≈ 160 µA |
| 1 | 330 Ω | PhotoMOS LED from a 3 V pin: (3.0 − 1.25)/5 mA |
| 1 | 1 kΩ + small LED | Status blink, visible through the lid |
| 1 | Reed switch, SPST | Magnet-swipe disable. Rarely needed — design as though it is always on |
| 2 | 0.1 µF ceramic + 1 x 22 µF | ATtiny decoupling; the 22 µF holds the rail through the 5 mA LED pulse |
| 1 | 3-pin header | UPDI (or 6-pin ISP for the ATtiny85) |
| 1 | Small perfboard | It is a dozen parts. No PCB needed |
| 1 pk | Insulated crimp ferrules, 22–20 AWG | `STATUS.md`: tinned strands cold-flow under screw terminals. Ferrules, not solder |

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

## Wiring rules

- **Pin 1 straight through**, connector to connector, and **nothing in the box touches
  it.** Cell A, cell B, the ATtiny and both PhotoMOS sides all float. This preserves
  "shield grounded solely at the Pi" from `BOM-geophone-case.md`. (In a PLA box the two
  connector shells are insulated from each other, so shell-bonded pin 1 is harmless.)
- Keep cell B, the 249 kΩ and the PhotoMOS **output** pins as one tight loop near the
  output connector. Keep the ATtiny, cell A and the LED leads on the other side. The
  PhotoMOS gives 5 kV of isolation — do not undo it by running the two together.
- Injector at the **Pi end** of the run, not the sensor end.

## Before it is powered for the first time

1. Print, fit the connectors, wire pin 2/3 through with the injector **unpopulated**.
   Confirm the station still records normally.
2. Wait out the ~35 min settling, then compare the quiet-night floor with the documented
   **~0.8 µV RMS in 1–15 Hz**. If it has not moved, the box is transparent. If it has,
   find out now, before a calibration signal confuses the picture.
3. Add an `analysis/epochs.py` row the day it goes in — a signal-path hardware change.
4. **Write the signature finder first.** A 27 mV release against a ~1 µV floor is roughly
   27,000x: every pulse will trigger the detector. Four bursts a day, unrecognised, is
   ~1,460 fake high-amplitude "cultural" triggers a year going straight into `events.log`
   and the classifier's training set. Recognise them by the 2.00 s spacing and matched
   amplitudes, exclude them from training, and hand them to `ringdown.py --at`.

# Power wiring — panel barrel jack → Pi 2B

Mean Well **GST25A05-P1J** (5 V, 4 A, IEC C14 in, 5.5 × 2.1 barrel out) → panel-mount
barrel jack on the case → **Pi GPIO 5 V / GND**.

The GPIO feed is a deliberate choice, recorded in STATUS 2026-08-04: micro-USB is
**never** panel-mounted for this build, because the 5 V side already browns out when
extended (dropped sample rate, square-wave plateaus) and a feedthrough adds two more
contact pairs to the rail that is already marginal. Keep the **AC** side long (the 25 ft
cord) and the **DC** side short and fat.

---

## ⚠️ Resolve this first: the HAT occupies the 40-pin header

Pi 5 V is on **header pins 2 and 4**, GND on **pin 6** — but the Waveshare board is
stacked on that header, so those pins are not exposed. Pick an injection point before
cutting wire:

1. **Waveshare terminal block, if it carries 5 V and GND.** Waveshare describe the board's
   terminal blocks as encapsulating the input/output interface, and the 5 V there is the
   same rail as the Pi's. If a 5 V and a GND position exist, this is the tidiest injection
   point — no soldering to the Pi at all. **Check the silkscreen and confirm continuity to
   Pi pin 2 with a meter before trusting it.**
2. **Solder to the underside of the Pi's header pins 2/4 and 6.** Permanent, reliable,
   and it does not depend on what the HAT exposes.
3. **A stacking (tall) header** between Pi and Waveshare, leaving the pin tops accessible.
   Cleanest electrically, but it raises the stack — re-measure `stack_h` (currently 30 mm)
   if you do this, because the case cavity is derived from it.

Do **not** solve this by powering through micro-USB as well — see the interlock below.

---

## What this bypasses, and what to add back

Feeding 5 V into the GPIO header goes **around the Pi's input polyfuse and its
reverse-polarity protection**. Two consequences, both worth spending five minutes on:

- **Fit an inline fuse in the + line: 2 A slow-blow.** The supply can deliver 4 A into a
  fault; the Pi 2B with no Wi-Fi dongle draws roughly 0.6–0.8 A. Nothing else limits it.
- **Verify polarity with a meter before the plug ever goes near the Pi.** Reverse 5 V on
  the GPIO rail kills the Pi instantly, with no fuse or diode in the way. The GST series
  is centre-positive, but *measure it anyway* — this is a two-second check against an
  unrecoverable mistake.

## Interlock (state this on a label inside the lid)

**Never power via micro-USB and the GPIO jack at the same time.** Two supplies fighting
across the polyfuse is a good way to lose the board.

---

## Wiring

Panel jack (RuiLing 5.5 × 2.1, 3-pin, hex nut) — pin numbering per STATUS 2026-08-04:

| jack pin | function | connect to |
|---|---|---|
| **5** | **+ (centre)** | fuse → Pi 5 V (pin 2 or 4, or the injection point chosen above) |
| **2** | **− (sleeve)** | Pi GND (pin 6) |
| 3 | switch contact | **leave unconnected** |

- **Wire: 20 AWG stranded silicone**, both legs. Fat for the current (trivial), *flexible*
  because this is the one internal run that gets disturbed during service, and silicone
  insulation survives being pushed around. Keep it as short as the layout allows.
- **Twist the + and − together** along the run. It is a DC feed next to a µV front end;
  twisting cancels the loop area so it radiates as little as possible.
- **Route it away from the interface board and the XLR run.** The case has the Pi at −Y
  and the front end at +Y — keep the power leg on the Pi side of the box.
- Strain-relieve at the jack: the hex nut holds the jack, not the wires.

## Bring-up order

1. Wire the jack, fuse fitted, **nothing connected to the Pi**.
2. Plug in the PSU. Meter the jack's output leads: expect **+5 V ±2 %**, correct polarity.
3. Unplug the PSU. Connect to the Pi.
4. Power up and check the voltage **at the Pi under load** — it must stay above **4.75 V**.
   Below that the Pi 2B misbehaves in ways that look like software faults.
5. Confirm the recorder comes up clean: `rate_est` ~100, `dropped` low, no plateaus.

The last step matters more than it looks: the failure mode this whole arrangement exists
to avoid (brownout → dropped samples → square-wave plateaus) is *silent* in the sense that
the Pi keeps running. The data shows it before anything else does.

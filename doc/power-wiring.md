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

### ❌ NOT the Waveshare terminal block — this would destroy hardware

Ruled out 2026-08-07. The terminal block's positions are `AD7…AD0 AGND VCC GND DAC1 DAC0`,
and that **`VCC` is the ANALOG supply selected by the right-block-top jumper, which on this
board is on `3V3`** (STATUS "Board jumper cheat-sheet"). Two independent confirmations it is
really 3.3 V: the shunt is physically observed in the `VCC→3V3` position, and the front
end's own arithmetic depends on it — 3.3 V / 200 kΩ = 16.5 µA through the coil, which is
the ~6 mV standing offset measured repeatedly.

**Putting 5 V there back-feeds 5 V onto the Pi's 3.3 V rail** and takes out the ADS1256,
the Pi's 3.3 V regulator, and anything else on that rail.

Moving the jumper to `5V` does not rescue it: STATUS records this board's **5 V path as a
real fault** — it hard-locked the Pi even on a 2.5 A supply, and on 2026-07-23 produced a
−32 %-of-full-scale DC offset with ~1500× normal RMS, suspected to be a cap shorting
5 V↔3V3. That is precisely the fault that would make this injection lethal.

That terminal is a low-current **output** for powering sensor modules. It is not a power
inlet, and even at the right voltage its trace is not sized to carry the Pi's ~0.8 A.

### ✅ Use the header

1. **Solder to the underside of the Pi's header pins 2 or 4 (5 V) and 6 (GND).** Permanent,
   reliable, and independent of what the HAT exposes. This is the default.
2. **A stacking (tall) header** between Pi and Waveshare, leaving the pin tops accessible.
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

### Terminating at the pass-through header

The pass-through pins take Dupont sockets, but a stock jumper is **28 AWG** (213 mΩ/m).
A 200 mm jumper is 43 mΩ, out-and-back ~85 mΩ, so at the Pi 2B's ~0.7 A that is **~60 mV**
of drop, plus 20–40 mV across the four Dupont contacts. ~0.1 V total: survivable from a
5.0 V supply, but thin margin on the one rail whose brownouts this whole arrangement
exists to prevent. Heating is a non-issue; **drop and contact-resistance drift** are the
problem — Dupont sockets are stamped tin springs that relax and oxidize, and this is a
sealed, permanent install.

- **Double the rails.** 5 V on header pins **2 and 4**, GND on **6 and 14** — two jumpers
  per leg. Halves wire *and* contact resistance (~30 mV total) and gives redundancy if one
  socket backs off. This is the default.
- **Or crimp 22 AWG** female Dupont contacts onto a short pigtail off the 20 AWG run.
  22 AWG is the fattest wire that crimps reliably into a Dupont barrel; 20 AWG will not go.
- **Hot-glue the housings** once tested. A socket walking off a pin during final assembly
  is the realistic mechanical failure, and the lid goes on over it.

Bring-up step 4 is the arbiter, not this arithmetic: if it holds above 4.75 V at the Pi
*under load*, the termination is fine.

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

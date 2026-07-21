# Rev-2 geophone → ADS1256 interface board

**Status: DRAFT / not frozen.** This is the working design for the permanent
front-end board that replaces the current perfboard (2× 100 kΩ bias + shunt
socket + XLR in). It is a *passive* differential network — bias, damping,
anti-alias/charge-reservoir — feeding the ADS1256's differential input. All
active gain (PGA ×64) and the input buffer live **inside** the ADS1256, not on
this board.

Two decisions are still open (see [Open decision](#open-decision--vcm-voltage)),
so the values here are the prototype starting point. Freeze them on the perfboard
via the shorted-input floor test **before** laying out the PCB — see
`../BACKLOG.md` (“Custom PCB — do it, but only once Rev-2 is frozen”).

## Topology (signal flow)

Mermaid sketch of the network — **topology only**, not a literal schematic
(dotted links = components *across* two nodes; solid links = series components).
The authoritative netlist is the ASCII schematic below.

```mermaid
graph LR
    COIL["Geophone<br/>4.5 Hz · 375 Ω"]
    N0(("N0"))
    N1(("N1"))
    VCM(("VCM"))
    AGND(("AGND"))
    AVDD(("AVDD"))
    AD0(("AD0"))
    AD1(("AD1"))
    OUT["J2 → Waveshare<br/>AD0 · AD1 · AGND · AVDD"]

    COIL ---|coil+| N0
    COIL ---|coil-| N1
    N0 -. "Rd damping (socket)" .- N1
    N0 ---|"Rb1 100k"| VCM
    N1 ---|"Rb2 100k"| VCM
    N0 -->|"Rs1 1k"| AD0
    N1 -->|"Rs2 1k"| AD1
    AD0 -. "Cd 10nF" .- AD1
    AD0 ---|"Ccm1 1nF"| AGND
    AD1 ---|"Ccm2 1nF"| AGND
    AVDD ---|"R1"| VCM
    VCM ---|"R2"| AGND
    VCM -. "C3 10µF" .- AGND
    AVDD -. "C1 ∥ C2" .- AGND
    AD0 --> OUT
    AD1 --> OUT
```

The **XLR J1** shield (pin 1) is not in the graph: it goes to the **single star
ground** point (bonded to AGND once, at the Pi end), *not* to the signal return.

## Schematic (authoritative netlist)

```
   Waveshare rail (via 4-pin JST J2)
   AVDD ●──┬────────────┬─────────────────────────●
           │            │
          R1           C1 10µF ∥ C2 100nF   (supply bypass at board)
           │            │
   VCM ●───┼───┬────────┼──────────────────────┐
           │   │        │                       │
          R2  C3 10µF   │                    (VCM = AC ground /
           │   │        │                     common-mode ref)
   AGND ●──┴───┴────────┴───────────────────┬───┴──●
                                            │
   ── signal path ──────────────────────────────────────────────
                                            │
   XLR J1 pin2 (coil+) ● N0 ──[Rs1 1k]──● AD0 ─────► J2 AD0
                        │                 │
                       Rb1 100k          Ccm1 1nF
                        │                 │
                       VCM               AGND

        Rd (socketed) ══ across N0──N1 ══     ← damping, tuned
        Cd 10nF ═══════ across AD0──AD1 ═══   ← diff reservoir / AA

   XLR J1 pin3 (coil−) ● N1 ──[Rs2 1k]──● AD1 ─────► J2 AD1
                        │                 │
                       Rb2 100k          Ccm2 1nF
                        │                 │
                       VCM               AGND

   XLR J1 pin1 (shield) ●──────────────────────────► star ground
                                            (single point, Pi end)
```

## Net-by-net

- **Geophone coil** sits directly across **N0–N1** (XLR pins 2/3). All
  AC-relevant sensor behavior happens at this node.
- **VCM (common-mode bias)** — divider R1/R2 off AVDD, heavily filtered by
  **C3 (10 µF)** into a dead-quiet AC ground. **Rb1/Rb2 (100 k)** pull each coil
  terminal to VCM to set the DC operating point without shorting the differential
  AC. The 375 Ω coil dominates the differential source impedance, so the bias-R
  Johnson noise is largely shunted.
- **Rd** — shunt **damping** resistor across the coil, **socketed**, tuned
  empirically against a recorded impulse (~0.7 critical). Placed at N0–N1,
  *before* the series R, so Rs doesn't perturb the damping.
- **Rs1/Rs2 (1 k) + Cd (10 nF) + Ccm1/2 (1 nF)** — anti-alias / charge-reservoir
  RC. Cd right at the ADC pins feeds the switched-cap sampler's charge spikes;
  the CM caps knock down RF. Corner ≈ **8 kHz** differential (see
  [Anti-alias note](#anti-alias--charge-reservoir-note)).
- **Shield (pin 1)** → the single star-ground point, not the signal return.

## BOM (prototype starting values)

| Ref | Value | Role |
|-----|-------|------|
| R1, R2 | 100 k (see decision) | VCM divider |
| Rb1, Rb2 | 100 k | input bias to VCM |
| Rd | socket, ~1–5 k | shunt damping (tune) |
| Rs1, Rs2 | 1 k | series to ADC (keep ≤1 k) |
| Cd | 10 nF C0G | differential reservoir / AA |
| Ccm1, Ccm2 | 1 nF C0G | per-input RF to AGND |
| C1 / C2 | 10 µF / 100 nF | AVDD bypass |
| C3 | 10 µF | VCM filter |
| J1 | XLR (PCB-mount, Neutrik) | geophone in |
| J2 | 4-pin JST-XH | AD0 / AD1 / AGND / AVDD to Waveshare |

## Open decision — VCM voltage

This *is* the buffer / AVDD question. The board is identical across all three
options — only R1/R2 and the AVDD jumper change — which is why it stays on the
perfboard until one is chosen:

| Config | R1 / R2 | VCM | Buffer |
|--------|---------|-----|--------|
| Current: AVDD = 3.3 V, buffer **off** | 100k / 100k | 1.65 V | off (noisier) |
| AVDD = 3.3 V, buffer **on** | 180k / 100k | 1.18 V | on — needs VCM < 1.3 V |
| **Resolve 5 V AVDD**, buffer **on** | 100k / 100k | 2.5 V | on (range 0–3 V) ✓ |

Buffer-on is the real noise-floor win, and it also collapses the switched-cap
input current — so the bias-R offset shrinks and Rb could rise to 1 M (lower
loading, less noise). The 5 V AVDD path is blocked on a hardware fault
(jumpering AVDD to 5 V crashed the Pi — suspected a 3-pin cap shorting 5 V↔3V3;
investigate with the Pi OFF, pins verified). See `../BACKLOG.md` item 1.

## Anti-alias / charge-reservoir note

The earlier backlog phrasing ("1 kΩ + 10–47 nF, corner ~60–80 Hz") was wrong:
1 k×2 + 10–47 nF lands at **~1.7–8 kHz**, not 60–80 Hz — and the kHz corner is
the *correct* behavior. The analog RC's job here is charge-reservoir for the
switched-cap input + RF/modulator-alias rejection; the ADS1256's digital SINC
filter does the decimation anti-aliasing. A true ~30 Hz analog corner would need
~25 k series R, which wrecks gain accuracy and adds noise on the unbuffered
input — **don't**. Keep the corner in the low kHz.

## Alternatives worth knowing

- **VCM from VREF (2.5 V)** instead of an AVDD divider, if CM stability
  independent of the supply is wanted. (For a floating differential source the
  CM point only needs to stay in range, so the filtered AVDD divider is fine.)
- **Rb → 1 M** once the buffer is on (input current collapses → lower loading,
  less noise).

## Connectors (internal wiring)

- **J1 geophone in** — board-mounted XLR jack (Neutrik PCB series); the geophone
  cable's XLR plugs straight in, no solder-to-cable.
- **J2 to Waveshare** — single **4-pin JST-XH** (keyed, latching, crimped)
  carrying AVDD / AGND / AD0 / AD1, so the whole link connects/disconnects at
  once. Pin order `AVDD · AGND · AD0 · AD1` (ground between the rail and the
  signal pair). The Waveshare screw terminals get a ferruled pigtail landed
  **once** and left alone; the quick-disconnect is this JST, not the terminals.
```

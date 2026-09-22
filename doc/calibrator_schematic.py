#!/usr/bin/env python3
"""Inline calibration injector — schematic, drawn with schemdraw.

Source of the image embedded in doc/calibrator-build.md. Render with:
    direnv exec . python doc/calibrator_schematic.py
-> writes doc/calibrator.svg

doc/calibrator.png is the same drawing for the bench -- an SVG is awkward on a phone
or a tablet next to a soldering iron. Regenerate it by swapping the two lines below
(drop the schemdraw.use("svg") and change the filename); it is not worth a flag.

Same conventions as doc/rev2_frontend_schematic.py: real component symbols, and
net labels that tie by name rather than routing every wire across the sheet.
Junctions are DOTTED; two lines crossing without a dot are not connected.

THE ONE THING THIS DRAWING IS FOR: the dashed red line is the isolation barrier.
Left of it is a microcontroller doing microcontroller things, referenced to cell A.
Right of it is the coil, where the signal we are trying to record is a microvolt.
The only parts that cross are the two PhotoMOS packages, and they cross it with
5 kV of isolation and no galvanic path at all. Laying the perfboard out so the two
halves stay on their own sides of this line is the electrical discipline of the
whole build -- see doc/calibrator-build.md.

Pinouts are from the datasheets, not from memory, because this is a drawing
somebody solders from (both checked 2026-09-21):

  AQY212EH  4-DIP   pin 1 = LED anode, pin 2 = LED cathode, pins 3/4 = output.
                    Panasonic GU-E PhotoMOS datasheet, 1 Form A internal diagram.
                    0.85 ohm typ on-resistance, 1 uA max off-state leakage,
                    I_F 5-10 mA recommended, V_F 1.14 V at 5 mA, and 3.0 mA is
                    the MAX current at which turn-on is still guaranteed.
  LM4040-N  TO-92   pin 1 = anode, pin 2 = cathode, pin 3 = NC (leave open, or tie
                    to anode). TI SNOS633K section 5. Viewed from the FLAT face
                    with the leads down, 1-2-3 reads left to right. The datasheet's
                    TO-92 drawing is a BOTTOM view, which is the trap.
  ATtiny85  PDIP-8  1=PB5/RESET 2=PB3 3=PB4 4=GND 5=PB0/MOSI 6=PB1/MISO 7=PB2/SCK
                    8=VCC. Table 21-1: V_OH min 2.5 V at -5 mA and V_CC = 3 V, and
                    power-down with the watchdog running is 10 uA MAX. R1/R2 are
                    180R, not the BOM's 330R -- see calibrator-build.md, "The LED
                    resistor the BOM got wrong".

Pin numbers are printed on every symbol. The ATtiny is drawn by FUNCTION, not in
physical DIP order -- PB3 and PB1 leave to the right because that is where they
go, not because they are on that side of the package.
"""
import schemdraw
schemdraw.use("svg")
import schemdraw.elements as elm

# ---- the two halves ---------------------------------------------------
BARRIER = 13.5           # isolation barrier: control left, coil right
GND_Y = 1.0              # cell A negative rail
VA_Y = 15.4              # cell A positive rail. MUST sit ABOVE U1's VCC anchor:
                         # Ic.at() places by the BOTTOM-LEFT corner, not the centre, so
                         # with h=6.8 and leadlen=1.0 the VCC pin lands at y=14.7. Put the
                         # rail below that and the connecting wire runs back down THROUGH
                         # the package, which is exactly how it looked (Charles, 2026-09-22:
                         # "VCC runs inside the chip not connecting to the line coming out
                         # of it"). If U1 moves or grows, re-check this number.

# ---- the signal pair, straight through, along the top ------------------
RAIL_SHIELD = 18.0       # XLR pin 1 -- carried through, touched by nothing
RAIL_P = 16.5            # XLR pin 2 -- coil+
RAIL_M = 15.0            # XLR pin 3 -- coil-
RAIL_L, RAIL_R = 16.0, 27.5

with schemdraw.Drawing(file="doc/calibrator.svg", show=False) as d:
    drawing = d
    d.config(unit=2.0, fontsize=11)

    # ===================================================================
    # THE SIGNAL PAIR
    # ===================================================================
    # Pin 1 is carried connector to connector and nothing in the box touches it.
    # That is what keeps "shield grounded solely at the Pi" (BOM-geophone-case.md)
    # true with a box spliced into the middle of the run.
    for y, lbl in ((RAIL_SHIELD, "1  shield"), (RAIL_P, "2  coil+"), (RAIL_M, "3  coil-")):
        d += elm.Line().at((RAIL_L, y)).to((RAIL_R, y))
        d += elm.Dot(open=True).at((RAIL_L, y))
        d += elm.Dot(open=True).at((RAIL_R, y))
        d += elm.Label().at((RAIL_L + 1.6, y + 0.32)).label(lbl, fontsize=9)

    d += elm.Label().at((RAIL_L - 0.6, RAIL_SHIELD + 1.0)).label(
        "J1  NC3FD-L-B\nfemale, geophone side", fontsize=9)
    d += elm.Label().at((RAIL_R + 0.6, RAIL_SHIELD + 1.0)).label(
        "J2  NC3MD-L-B\nmale, Pi side", fontsize=9)

    # ===================================================================
    # SHUNT LEG — the second PhotoMOS and a plug-in resistor module
    # ===================================================================
    # Closed for the whole of the SECOND burst of each pair, so ringdown.py solve
    # gets an unshunted and a shunted zeta sixteen seconds apart, with ground
    # conditions, temperature and background common to both and cancelling.
    u3 = elm.Ic(pins=[elm.IcPin(name="A", pin="1", side="left", slot="2/2"),
                      elm.IcPin(name="K", pin="2", side="left", slot="1/2"),
                      elm.IcPin(name="O4", pin="4", side="right", slot="2/2"),
                      elm.IcPin(name="O3", pin="3", side="right", slot="1/2")],
                w=2.8, h=1.8, leadlen=0.6, plblofst=0.1,
                label="U3").at((BARRIER, 9.6)).theta(0)
    d += u3

    # The PhotoMOS is on the COIL side of the jack, so with the shunt open the jack
    # and whatever is plugged into it are DISCONNECTED from the coil rather than
    # hanging across it. A single SPST can only isolate one leg; the sleeve stays a
    # stub, so keep that run short on the board.
    d += elm.Label().at((BARRIER, u3.O4.y + 1.05)).label(
        "U3  AQY212EH — shunt", fontsize=9)
    d += elm.Line().at(u3.O4).to((16.8, u3.O4.y))
    d += elm.Line().at((16.8, u3.O4.y)).to((16.8, RAIL_P))
    d += elm.Dot().at((16.8, RAIL_P))

    d += elm.Line().at(u3.O3).to((18.4, u3.O3.y))
    tip = elm.Dot(open=True).at((18.4, u3.O3.y))
    d += tip
    d += elm.Resistor().at((18.4, u3.O3.y)).to((21.0, u3.O3.y)).label("Rs", fontsize=9)
    sleeve = elm.Dot(open=True).at((21.0, u3.O3.y))
    d += sleeve
    d += elm.Line().at((21.0, u3.O3.y)).to((21.0, RAIL_M))
    d += elm.Dot().at((21.0, RAIL_M))
    d += elm.Label().at((18.4, u3.O3.y - 0.5)).label("tip", fontsize=8)
    d += elm.Label().at((21.0, u3.O3.y - 0.5)).label("sleeve", fontsize=8)

    # Rs is not on the board: it lives inside a screw-off 1/4" plug with its value
    # written on the barrel, and the set lives in a bag. Changing it is unplug,
    # plug, write the value in analysis/epochs.py -- no iron, and no opening the
    # box immediately before a campaign whose premise is that nothing else changed.
    d += elm.EncircleBox([tip, sleeve], padx=0.5, pady=0.6).linestyle("--").color("#888")
    # BELOW the module, and MEASURED rather than eyeballed (Charles found this twice:
    # above the jack it crossed the wire from U3's O4 to coil+ at x=16.8, then at
    # y=7.4 it drifted onto Rb). The clear band runs from the Rb row at y=6.35 to the
    # jack row at y=10.55, so 8.45 is the middle of it. Three short lines rather than
    # two long ones, centred at 18.6: the two-line version was ~11 units wide and ran
    # into Rinj at x=23.0.
    d += elm.Label().at((18.6, 8.45)).label(
        "J3  1/4\" TS panel jack\n"
        "shunt module lives in the plug\n"
        "NO PLUG = no shunt = the default",
        fontsize=8, color="#555")

    # ===================================================================
    # INJECTION ISLAND — floating, and gated so it draws nothing at rest
    # ===================================================================
    u2 = elm.Ic(pins=[elm.IcPin(name="A", pin="1", side="left", slot="2/2"),
                      elm.IcPin(name="K", pin="2", side="left", slot="1/2"),
                      elm.IcPin(name="O4", pin="4", side="right", slot="2/2"),
                      elm.IcPin(name="O3", pin="3", side="right", slot="1/2")],
                w=2.8, h=1.8, leadlen=0.6, plblofst=0.1,
                label="U2").at((BARRIER, 4.8)).theta(0)
    d += u2

    d += elm.Label().at((BARRIER, u2.O4.y + 1.05)).label(
        "U2  AQY212EH — injector", fontsize=9)

    NODE_X = 23.0
    BMINUS_Y = 1.6

    #   cell B (+) - U2 - Rb - N - LM4040 - cell B (-)
    #                          \- Rinj - coil+ ... coil ... coil- -/
    # Gated UPSTREAM of Rb on purpose: the LM4040's ~160 uA of bias is what makes
    # this a calibration rather than a battery-discharge curve, and left on it
    # would flatten a 220 mAh cell in about eight weeks.
    d += elm.Line().at(u2.O4).to((17.2, u2.O4.y))
    d += elm.Resistor().at((17.2, u2.O4.y)).to((20.6, u2.O4.y)).label("Rb 22k", fontsize=9)
    d += elm.Line().at((20.6, u2.O4.y)).to((NODE_X, u2.O4.y))
    d += elm.Dot().at((NODE_X, u2.O4.y))
    d += elm.Label().at((NODE_X + 0.55, u2.O4.y + 0.5)).label("2.5 V", fontsize=9)

    d += elm.Zener().at((NODE_X, BMINUS_Y)).to((NODE_X, u2.O4.y)).label(
        "U4  LM4040-2.5\npin 2 (K) up\npin 1 (A) down\npin 3 NC", loc="left", fontsize=9)

    d += elm.Resistor().at((NODE_X, u2.O4.y)).to((NODE_X, RAIL_P))
    d += elm.Label().at((NODE_X + 1.35, (u2.O4.y + RAIL_P) / 2)).label(
        "Rinj\n249k", fontsize=9)
    d += elm.Dot().at((NODE_X, RAIL_P))

    # cell B negative: the LM4040 anode, the cell, and the coil return all meet.
    d += elm.Line().at((NODE_X, BMINUS_Y)).to((25.6, BMINUS_Y))
    d += elm.Line().at((25.6, BMINUS_Y)).to((25.6, RAIL_M))
    d += elm.Dot().at((25.6, RAIL_M))
    d += elm.Dot().at((NODE_X, BMINUS_Y))
    d += elm.Line().at((NODE_X, BMINUS_Y)).to((17.2, BMINUS_Y))
    d += elm.Battery().at((17.2, BMINUS_Y)).to((17.2, u2.O3.y)).label(
        "cell B\n2 x CR2032\n6 V", loc="left", fontsize=9)
    d += elm.Line().at((17.2, u2.O3.y)).to(u2.O3)

    # ===================================================================
    # THE BARRIER
    # ===================================================================
    barrier = elm.Line().at((BARRIER, 0.2)).to((BARRIER, 19.6)) \
        .linestyle("--").color("#c0392b").linewidth(1.3)
    d += barrier
    d += elm.Label().at((BARRIER, 20.1)).label(
        "5 kV isolation\nnothing galvanic crosses", fontsize=9, color="#c0392b")

    # ===================================================================
    # CONTROL SIDE
    # ===================================================================
    d += elm.Line().at((0.6, GND_Y)).to((11.3, GND_Y))
    d += elm.Line().at((0.6, VA_Y)).to((8.6, VA_Y))   # past u1.VCC.x = 7.65
    d += elm.Label().at((0.0, VA_Y + 0.4)).label("VA", fontsize=10)
    d += elm.Label().at((0.0, GND_Y - 0.55)).label("0A", fontsize=10)

    # Cell A, behind JP1. Drawn as a GAP because open is a real operating state:
    # most ISP dongles drive 5 V and that must never reach an installed CR2032, so
    # JP1 out is the programming configuration -- and a microammeter across the open
    # header is the only convenient way to check the ~5 uA sleep current.
    d += elm.Line().at((0.6, GND_Y)).to((0.6, 3.2))
    d += elm.Battery().at((0.6, 3.2)).to((0.6, 6.8)).label(
        "cell A\nCR2032\n3 V", loc="left", fontsize=9)
    d += elm.Dot(open=True).at((0.6, 6.8))
    d += elm.Dot(open=True).at((0.6, 8.4))
    d += elm.Label().at((-0.55, 7.6)).label("JP1", fontsize=9)
    d += elm.Line().at((0.6, 8.4)).to((0.6, VA_Y))

    d += elm.Capacitor().at((1.7, VA_Y)).to((1.7, GND_Y)).label("C1\n100n", loc="left",
                                                                fontsize=9)
    d += elm.Dot().at((1.7, VA_Y))
    d += elm.Dot().at((1.7, GND_Y))
    d += elm.Capacitor(polar=True).at((2.7, VA_Y)).to((2.7, GND_Y)).label(
        "C2\n22u", loc="left", fontsize=9)
    d += elm.Dot().at((2.7, VA_Y))
    d += elm.Dot().at((2.7, GND_Y))

    u1 = elm.Ic(pins=[elm.IcPin(name="VCC", pin="8", side="top"),
                      elm.IcPin(name="GND", pin="4", side="bottom"),
                      elm.IcPin(name="RST", pin="1", side="left", slot="4/5"),
                      elm.IcPin(name="MOSI", pin="5", side="left", slot="3/5"),
                      elm.IcPin(name="SCK", pin="7", side="left", slot="2/5"),
                      elm.IcPin(name="PB1", pin="6", side="right", slot="4/5"),
                      elm.IcPin(name="PB3", pin="2", side="right", slot="3/5"),
                      elm.IcPin(name="PB4", pin="3", side="right", slot="2/5")],
                w=4.6, h=6.8, leadlen=1.0, pinspacing=1.7, plblofst=0.1,
                label="").at((6.4, 5.9)).theta(0)
    d += u1

    # Above the box top (13.7) and below the rail (15.4), left of the VCC lead (x=7.65).
    d += elm.Label().at((5.2, 14.2)).label("U1  ATtiny85  PDIP-8", fontsize=10)
    d += elm.Line().at(u1.VCC).to((u1.VCC.x, VA_Y))
    d += elm.Dot().at((u1.VCC.x, VA_Y))
    d += elm.Line().at(u1.GND).to((u1.GND.x, GND_Y))
    d += elm.Dot().at((u1.GND.x, GND_Y))

    # ISP net labels. PB1 is BOTH MISO and the shunt drive; drawing that as a wire
    # would cross the sheet twice, so it is named instead. The shunt socket stays
    # EMPTY while flashing: MISO chatters as the ATtiny answers the programmer, so
    # the shunt PhotoMOS flickers closed, and with no plug in J3 that does nothing.
    for anchor, netname in ((u1.RST, "RESET"), (u1.MOSI, "MOSI"), (u1.SCK, "SCK")):
        d += elm.Dot(open=True).at(anchor)
        d += elm.Label().at((anchor.x - 0.15, anchor.y + 0.42)).label(
            netname, fontsize=9, color="#1a6a1a")

    # PB3 -> injector LED. Never shares a line with ISP: that is the whole reason
    # the drive sits on PB3 rather than wherever the perfboard made it convenient.
    d += elm.Resistor().at(u1.PB3).to((10.2, u1.PB3.y)).label("R1 180", fontsize=9)
    d += elm.Line().at((10.2, u1.PB3.y)).to((10.7, u1.PB3.y))
    d += elm.Line().at((10.7, u1.PB3.y)).to((10.7, u2.A.y))
    d += elm.Line().at((10.7, u2.A.y)).to(u2.A)

    # PB1 -> shunt LED. MISO on purpose: it is driven by the ATTINY and only read
    # by the programmer, so the ~5 mA comes out of a driver we specify. Hung on
    # MOSI, the same load would sit on the PROGRAMMER's output -- the one end of
    # the link we cannot specify, since USBasp clones vary.
    d += elm.Resistor().at(u1.PB1).to((10.2, u1.PB1.y)).label("R2 180", fontsize=9)
    d += elm.Line().at((10.2, u1.PB1.y)).to((11.0, u1.PB1.y))
    d += elm.Line().at((11.0, u1.PB1.y)).to((11.0, u3.A.y))
    d += elm.Line().at((11.0, u3.A.y)).to(u3.A)
    d += elm.Label().at((9.2, u1.PB1.y + 0.45)).label("MISO", fontsize=9, color="#1a6a1a")

    # Both LED cathodes return to 0A on one vertical, kept on the control side.
    d += elm.Line().at(u3.K).to((11.3, u3.K.y))
    d += elm.Line().at((11.3, u3.K.y)).to((11.3, GND_Y))
    d += elm.Line().at(u2.K).to((11.3, u2.K.y))
    d += elm.Dot().at((11.3, u2.K.y))
    d += elm.Dot().at((11.3, GND_Y))

    # PB4 -> panel button to 0A, internal pull-up, pin-change wake. No hardware
    # debounce on purpose: held_long()'s fixed 30 ms is the logic under test
    # (STATUS open thread 1), and a cap here would test the cap instead.
    d += elm.Line().at(u1.PB4).to((9.4, u1.PB4.y))
    d += elm.Button().at((9.4, u1.PB4.y)).to((9.4, GND_Y))
    # Directly BELOW SW1 and below the 0A rail. Beside the switch there is only 1.75
    # units between U1's GND lead and the cathode return -- too narrow for the caption --
    # and parking it in the wide gap to the left divorced it from the switch it labels.
    d += elm.Label().at((9.4, -0.15)).label(
        "SW1  panel button\nshort press: restart the soak\nlong press: fire a burst now",
        fontsize=8, color="#555")
    d += elm.Dot().at((9.4, GND_Y))

    # The ISP header itself, drawn with its real pin numbers: getting the 2x3
    # order wrong is the classic first-attempt failure, after CKDIV8.
    j4 = elm.Ic(pins=[elm.IcPin(name="MISO", pin="1", side="left", slot="3/3"),
                      elm.IcPin(name="SCK", pin="3", side="left", slot="2/3"),
                      elm.IcPin(name="RESET", pin="5", side="left", slot="1/3"),
                      elm.IcPin(name="VCC", pin="2", side="right", slot="3/3"),
                      elm.IcPin(name="MOSI", pin="4", side="right", slot="2/3"),
                      elm.IcPin(name="GND", pin="6", side="right", slot="1/3")],
                w=3.2, h=3.2, leadlen=0.7, pinspacing=1.0, plblofst=0.1,
                label="").at((4.4, 17.2)).theta(0)
    d += j4
    d += elm.Label().at((4.4, 20.9)).label("J4  ISP header, 2x3 0.1\"", fontsize=10)
    d += elm.Label().at((5.9, 16.3)).label(
        "VCC and GND go to the VA / 0A rails. The other four have NO WIRE drawn:\n"
        "they connect to the matching green net names on U1's stubs.",
        fontsize=8, color="#555")

    # ===================================================================
    d += elm.Label().at((4.4, 22.3)).label(
        "CONTROL — referenced to cell A", fontsize=12, color="#2c3e50")
    d += elm.Label().at((21.0, 22.3)).label(
        "COIL — microvolts live here", fontsize=12, color="#2c3e50")
    check_labels = True          # see the collision check after the drawing closes
    d += elm.Label().at((14.0, -1.6)).label(
        "Inline calibration injector, SS.OAKM1.   "
        "Junctions are dotted; crossings without a dot are not connections.\n"
        "Rinj and Rs are MEASURED with a DMM at build time and written on the box: "
        "the value that counts is the measured one, not the marked one.",
        fontsize=9, color="#555")


# ---------------------------------------------------------------------------
# COLLISION CHECK -- text over wires
#
# Six separate label-over-wire collisions were found by Charles reading the
# rendered drawing, and none by me looking at it. Eyeballing does not work; a
# bounding-box test does, because every wire here is axis-aligned, so a Line's
# bbox IS the wire rather than a loose rectangle around it.
#
# Only standalone elm.Label() objects are checked. Labels attached to an element
# (.label("Rb 22k")) belong to that element and are not separate objects, so this
# will not catch those -- it catches the free-floating captions, which is where
# every one of the six actually happened.
def _bbox(el):
    try:
        bb = el.get_bbox(transform=True)
        return bb.xmin, bb.ymin, bb.xmax, bb.ymax
    except Exception:
        return None


def _overlap(a, b, pad=0.05):
    return not (a[2] < b[0] + pad or b[2] < a[0] + pad
                or a[3] < b[1] + pad or b[3] < a[1] + pad)


_labels, _wires = [], []
for _el in drawing.elements:
    _bb = _bbox(_el)
    if _bb is None:
        continue
    if isinstance(_el, elm.Label):
        _labels.append((_el, _bb))
    elif _el is barrier:
        continue                 # annotation, not a wire; U2/U3 sit astride it on purpose
    elif isinstance(_el, (elm.Line, elm.Resistor, elm.Capacitor, elm.Battery,
                          elm.Zener, elm.Button)):
        _wires.append((_el, _bb))

# JUNCTION CHECK -- dots that nothing connects to.
# The VA rail once stopped 0.25 units short of U1's VCC riser, leaving the junction dot
# floating off the end of it (Charles, 2026-09-22). The drawing looked connected and was
# not. A solid Dot is a claim that two or more wires meet there; verify the claim.
# An OPEN dot is a terminal or a net-name stub -- one wire is correct there, and JP1's
# two ends are meant to have a gap between them. Only SOLID dots claim a junction.
_dots = [e for e in drawing.elements
         if isinstance(e, elm.Dot)
         and not getattr(e, "_userparams", {}).get("open", False)]
_floating = []
for _d in _dots:
    _bb = _bbox(_d)
    if _bb is None:
        continue
    _cx, _cy = (_bb[0] + _bb[2]) / 2, (_bb[1] + _bb[3]) / 2
    _touch = sum(1 for _, wb in _wires
                 if wb[0] - 0.12 <= _cx <= wb[2] + 0.12
                 and wb[1] - 0.12 <= _cy <= wb[3] + 0.12)
    if _touch < 2:
        _floating.append((_cx, _cy, _touch))
if _floating:
    print(f"\n*** {len(_floating)} junction dot(s) that nothing meets ***")
    for _cx, _cy, _n in _floating:
        print(f"    dot at ({_cx:.2f}, {_cy:.2f}) is reached by {_n} wire(s), expected >= 2")
    raise SystemExit(1)

_hits = [(lb, wb) for _, lb in _labels for _, wb in _wires if _overlap(lb, wb)]
if _hits:
    print(f"\n*** {len(_hits)} label/wire overlap(s) -- the drawing is not clean ***")
    for lb, wb in _hits:
        print(f"    label at ({(lb[0]+lb[2])/2:.1f}, {(lb[1]+lb[3])/2:.1f}) "
              f"overlaps a wire spanning x {wb[0]:.1f}-{wb[2]:.1f}, y {wb[1]:.1f}-{wb[3]:.1f}")
    raise SystemExit(1)
print(f"checks clean: {len(_labels)} captions vs {len(_wires)} wires, "
      f"{len(_dots)} junctions all met")

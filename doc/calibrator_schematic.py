#!/usr/bin/env python3
"""Inline calibration injector — schematic, drawn with schemdraw.

Source of the image embedded in doc/calibrator-build.md. Render with:
    direnv exec . python doc/calibrator_schematic.py
-> writes doc/calibrator.svg

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
VA_Y = 13.0              # cell A positive rail (ATtiny VCC)

# ---- the signal pair, straight through, along the top ------------------
RAIL_SHIELD = 18.0       # XLR pin 1 -- carried through, touched by nothing
RAIL_P = 16.5            # XLR pin 2 -- coil+
RAIL_M = 15.0            # XLR pin 3 -- coil-
RAIL_L, RAIL_R = 16.0, 27.5

with schemdraw.Drawing(file="doc/calibrator.svg", show=False) as d:
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
    d += elm.Label().at((19.7, u3.O3.y + 1.7)).label(
        "J3  1/4\" TS panel jack  +  shunt module in the plug\n"
        "NO PLUG FITTED = no shunt = the default state",
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

    d += elm.Resistor().at((NODE_X, u2.O4.y)).to((NODE_X, RAIL_P)).label(
        "Rinj  249k", loc="right", fontsize=9)
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
    d += elm.Line().at((BARRIER, 0.2)).to((BARRIER, 19.6)) \
        .linestyle("--").color("#c0392b").linewidth(1.3)
    d += elm.Label().at((BARRIER, 20.1)).label(
        "5 kV isolation\nnothing galvanic crosses", fontsize=9, color="#c0392b")

    # ===================================================================
    # CONTROL SIDE
    # ===================================================================
    d += elm.Line().at((0.6, GND_Y)).to((11.3, GND_Y))
    d += elm.Line().at((0.6, VA_Y)).to((6.4, VA_Y))
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

    d += elm.Capacitor().at((2.2, VA_Y)).to((2.2, GND_Y)).label("C1\n100n", loc="left",
                                                                fontsize=9)
    d += elm.Dot().at((2.2, VA_Y))
    d += elm.Dot().at((2.2, GND_Y))
    d += elm.Capacitor(polar=True).at((3.4, VA_Y)).to((3.4, GND_Y)).label(
        "C2\n22u", loc="left", fontsize=9)
    d += elm.Dot().at((3.4, VA_Y))
    d += elm.Dot().at((3.4, GND_Y))

    u1 = elm.Ic(pins=[elm.IcPin(name="VCC", pin="8", side="top"),
                      elm.IcPin(name="GND", pin="4", side="bottom"),
                      elm.IcPin(name="RST", pin="1", side="left", slot="3/3"),
                      elm.IcPin(name="MOSI", pin="5", side="left", slot="2/3"),
                      elm.IcPin(name="SCK", pin="7", side="left", slot="1/3"),
                      elm.IcPin(name="PB1", pin="6", side="right", slot="3/3"),
                      elm.IcPin(name="PB3", pin="2", side="right", slot="2/3"),
                      elm.IcPin(name="PB4", pin="3", side="right", slot="1/3")],
                w=4.6, h=5.6, leadlen=1.0, pinspacing=1.7, plblofst=0.1,
                label="").at((6.4, 7.0)).theta(0)
    d += u1

    d += elm.Label().at((6.4, 12.1)).label("U1  ATtiny85  PDIP-8", fontsize=10)
    d += elm.Line().at(u1.VCC).to((u1.VCC.x, VA_Y))
    d += elm.Dot().at((u1.VCC.x, VA_Y))
    d += elm.Line().at(u1.GND).to((u1.GND.x, GND_Y))
    d += elm.Dot().at((u1.GND.x, GND_Y))

    # ISP net labels. PB1 is BOTH MISO and the shunt drive; drawing that as a wire
    # would cross the sheet twice, so it is named instead. The shunt socket stays
    # EMPTY while flashing: MISO chatters as the ATtiny answers the programmer, so
    # the shunt PhotoMOS flickers closed, and with no plug in J3 that does nothing.
    for anchor in (u1.RST, u1.MOSI, u1.SCK):
        d += elm.Dot(open=True).at(anchor)

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
    d += elm.Label().at((10.2, u1.PB1.y + 0.9)).label("PB1 is also MISO", fontsize=8,
                                                     color="#555")

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
    d += elm.Label().at((9.4, 1.9)).label(
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
    d += elm.Label().at((4.4, 14.9)).label(
        "VCC and GND go to the VA / 0A rails; the other four\n"
        "tie by name to the stubs on U1.", fontsize=8, color="#555")

    # ===================================================================
    d += elm.Label().at((4.4, 22.3)).label(
        "CONTROL — referenced to cell A", fontsize=12, color="#2c3e50")
    d += elm.Label().at((21.0, 22.3)).label(
        "COIL — microvolts live here", fontsize=12, color="#2c3e50")
    d += elm.Label().at((14.0, -1.6)).label(
        "Inline calibration injector, SS.OAKM1.   "
        "Junctions are dotted; crossings without a dot are not connections.\n"
        "Rinj and Rs are MEASURED with a DMM at build time and written on the box: "
        "the value that counts is the measured one, not the marked one.",
        fontsize=9, color="#555")

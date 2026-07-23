#!/usr/bin/env python3
"""Rev-2 front-end schematic, drawn with schemdraw (real component symbols).

Source of the schematic image embedded in doc/rev2-frontend.md. Render with:
    direnv exec . python doc/rev2_frontend_schematic.py
-> writes doc/rev2-frontend.svg

Net labels (VCM, AVDD, AGND) tie together by name, standard EE practice, to
avoid routing spaghetti. Values are the prototype starting point (not frozen).
"""
import schemdraw
schemdraw.use("svg")
import schemdraw.elements as elm

GAP = 3.4    # vertical spacing between the two differential rails
LEAD = 1.4   # short lead segments used to open up spacing

with schemdraw.Drawing(file="doc/rev2-frontend.svg", show=False) as d:
    d.config(unit=2.6, fontsize=13)

    # --- geophone (velocity source) on the far left, vertical ------------
    geo = elm.SourceSin().up().length(GAP).label(
        "Geophone\n4.5 Hz\n375 Ω", loc="left")
    d += geo
    coil_p, coil_m = geo.end, geo.start   # coil+ (top), coil- (bottom)

    # --- top rail: coil+ -> N0 -> Rs1 -> AD0 -----------------------------
    d += elm.Line().at(coil_p).right().length(LEAD)
    n0 = elm.Dot().label("N0", loc="left", ofst=(-0.15, 0.3))
    d += n0
    d += elm.Line().right().length(0.5)
    d += elm.Resistor().right().label("Rs1 1k")
    d += elm.Line().right().length(0.5)
    a0 = elm.Dot().label("AD0", loc="left", ofst=(-0.15, 0.3))
    d += a0
    d += elm.Line().right().length(LEAD)
    d += elm.Dot(open=True).label("J2·AD0", loc="right")

    # --- bottom rail: coil- -> N1 -> Rs2 -> AD1 --------------------------
    d += elm.Line().at(coil_m).right().length(LEAD)
    n1 = elm.Dot().label("N1", loc="left", ofst=(-0.15, -0.3))
    d += n1
    d += elm.Line().right().length(0.5)
    d += elm.Resistor().right().label("Rs2 1k", loc="bottom")
    d += elm.Line().right().length(0.5)
    a1 = elm.Dot().label("AD1", loc="left", ofst=(-0.15, -0.3))
    d += a1
    d += elm.Line().right().length(LEAD)
    d += elm.Dot(open=True).label("J2·AD1", loc="right")

    # --- damping resistor across the coil (N0-N1) ------------------------
    d += elm.Resistor().at(n0.center).to(n1.center).label(
        "Rd (socket)", loc="right")

    # --- differential reservoir / anti-alias cap across AD0-AD1 ----------
    d += elm.Capacitor().at(a0.center).to(a1.center).label("Cd 10n", loc="left")

    # --- bias resistors from each input up/down to VCM -------------------
    d += elm.Resistor().at(n0.center).up().length(2.6).label(
        "Rb1 100k", loc="left")
    d += elm.Vdd().label("VCM")
    d += elm.Resistor().at(n1.center).down().length(2.6).label(
        "Rb2 100k", loc="left")
    d += elm.Vss().label("VCM")

    # --- common-mode caps at the ADC pins (opposite side from bias) ------
    d += elm.Capacitor().at(a0.center).up().length(2.6).label(
        "Ccm1 1n", loc="right")
    d += elm.Ground()
    d += elm.Capacitor().at(a1.center).down().length(2.6).label(
        "Ccm2 1n", loc="right")
    d += elm.Ground()

    # --- common-mode reference network (right side, own column) ----------
    d.move(12, 1.5)
    ref_top = d.here
    d += elm.Vdd().label("AVDD")
    d += elm.Resistor().down().label("R1")
    vcm = elm.Dot().label("VCM", loc="left")
    d += vcm
    d += elm.Resistor().down().label("R2")
    d += elm.Ground()
    d += elm.Capacitor().at(vcm.center).right().length(2.2).label("C3 10µ")
    d += elm.Ground()
    d += elm.Capacitor().at(ref_top).right().length(3.2).label(
        "C1∥C2  10µ∥100n")
    d += elm.Ground()

"""geophone_case_lid.py — GEN-1 lid for geophone_case.py.

Deliberately dumb: a flat rounded-square plate, four clearance holes, no gasket
groove, no register lip (the four screws locate it), no vents (the body wall
vents do that job — a hole directly over the element is an acoustic path down
onto it). "GEOPHONE" engraved in the top face. Prints flat, no supports.

CARRY HANDLE (added 2026-08-03). A 116 mm flat-sided box sitting on a slab has
no purchase — you cannot get fingers under it without dragging it. A raised bail
over the CENTROID fixes that, and centroid placement matters: lifted off-centre
the case tips, and the element is held by nothing but putty and gravity.

Printability drove the opening shape. The lid prints flat, top face up, and the
project tenet is no supports anywhere, so the opening is a TRAPEZOID narrowing
toward the top (48 mm at the base, 24 at the top). Every internal face is then a
55 deg overhang, comfortably self-supporting, and the only flat span is the 24 mm
top of the opening. A rectangular opening would have meant a 48 mm bridge — which
PLA would very likely manage, but "likely" is a poor trade against a shape that
cannot fail. Do NOT "improve" this into a round arch: a circular opening goes
horizontal at its crown, which is the one geometry that does need support.

The handle forced the label off centre. "GEOPHONE" moved to y=-34 at 12 mm (was
centred at 16 mm) — it clears the handle footprint and still clears the corner
screws. Cosmetic; the handle is the functional element.

Load path is worth knowing: lifting by the handle puts the whole case weight
through the four #6 lid screws into their PLA bosses. Fine for ~0.5 kg, but they
are self-tappers in plastic, so if a boss ever strips, that is why.

5 mm thick rather than 3: the engraving eats 0.8 mm and a 3 mm plate with a
recess in it is thin enough to bow when the four corner screws are snugged.

No bubble-level inset (considered and rejected 2026-07-28). Tilt tolerance is
loose — 5 deg costs 0.4% of axial sensitivity — and a phone laid on this flat
lid resolves tenths of a degree where a bullseye vial resolves 1-2. Vials that
size are 7-9 mm tall, so flush-mounting one would double the lid thickness.
The lid is also the wrong datum: the element seats on the case FLOOR and the
lid sits on four bosses, so there is an unknown degree or so between the two
planes. Leveling already exists anyway — the three feet are screws, and #6
coarse pitch over the 57 mm foot-to-pivot distance is ~1.4 deg per turn.
Gen 2 does get a real vial (see doc/BOM-geophone-case.md): once it is bedded on
a paver in the crawl space you cannot iterate and cannot easily read a phone.

Fasteners: 4x #6 x 1/2" sheet-metal screws into the body's corner bosses.
"""
from math import atan2, degrees

from build123d import *
from ocp_vscode import show
from dimensions import *

case_side = 116.0
corner_r = 20.0
lid_th = 5.0
boss_xy = 47.0          # must match geophone_case.py
edge_cham = 0.6
label = "GEOPHONE"
label_size = 12.0       # ~58 mm wide — moved off centre to clear the handle
label_depth = 0.8
label_y = -34.0         # between the handle footprint and the lid edge

# --- carry handle (over the centroid; see the module docstring) ---
handle_span = 70.0      # outer, along X
handle_w = 16.0         # along Y — also the width your fingers bear on
handle_h = 24.0         # above the lid top face
handle_open_w = 48.0    # finger opening, at the base
handle_open_top = 24.0  # finger opening, at the top -> 55 deg sides, self-supporting
handle_open_h = 17.0    # finger clearance under the bar
handle_top_r = 6.0      # round the outer top corners — this is a hand contact surface

# Interior angle at the opening's base. Derived, not typed in, so the overhang
# stays honest if the opening widths above are ever retuned. Must stay >= 45.
handle_side_angle = 90 - degrees(
    atan2((handle_open_w - handle_open_top) / 2, handle_open_h))
assert handle_side_angle >= 45, f"opening sides overhang at {handle_side_angle:.1f} deg"

with BuildPart() as geophone_case_lid:
    with BuildSketch(Plane.XY):
        RectangleRounded(case_side, case_side, corner_r)
    extrude(amount=lid_th)

    with Locations((boss_xy, boss_xy, 0), (-boss_xy, boss_xy, 0),
                   (boss_xy, -boss_xy, 0), (-boss_xy, -boss_xy, 0)):
        Cylinder(clear_6 / 2, lid_th,
                 align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)

    # engrave the label into the top face
    with BuildSketch(Plane.XY.offset(lid_th)):
        with Locations((0, label_y)):
            Text(label, font_size=label_size,
                 align=(Align.CENTER, Align.CENTER))
    extrude(amount=-label_depth, mode=Mode.SUBTRACT)

    chamfer(geophone_case_lid.faces().sort_by(Axis.Z)[0].outer_wire().edges(),
            edge_cham)

# Handle built separately, then fused: its profile lives in XZ (so the trapezoid
# is drawn in the plane that actually prints), which is not the lid's build plane.
with BuildPart() as handle:
    with BuildSketch(Plane.XZ) as handle_prof:
        Rectangle(handle_span, handle_h, align=(Align.CENTER, Align.MIN))
        fillet(handle_prof.vertices().sort_by(Axis.Y)[-2:], handle_top_r)
        Trapezoid(handle_open_w, handle_open_h,
                  left_side_angle=handle_side_angle,
                  right_side_angle=handle_side_angle,
                  align=(Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    extrude(amount=handle_w / 2, both=True)

with BuildPart() as geophone_case_lid_final:
    add(geophone_case_lid.part)
    add(handle.part.moved(Location((0, 0, lid_th))))

geophone_case_lid = geophone_case_lid_final

show(geophone_case_lid)
export_stl(geophone_case_lid.part, "stl/geophone_case_lid.stl")

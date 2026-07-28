"""geophone_case_lid.py — GEN-1 lid for geophone_case.py.

Deliberately dumb: a flat rounded-square plate, four clearance holes, no gasket
groove, no register lip (the four screws locate it), no vents (the body wall
vents do that job — a hole directly over the element is an acoustic path down
onto it). "GEOPHONE" engraved in the top face. Prints flat, no supports.

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
from build123d import *
from ocp_vscode import show
from dimensions import *

case_side = 116.0
corner_r = 20.0
lid_th = 5.0
boss_xy = 47.0          # must match geophone_case.py
edge_cham = 0.6
label = "GEOPHONE"
label_size = 16.0       # ~77 mm wide — clears the corner screws on the y=0 line
label_depth = 0.8

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
        Text(label, font_size=label_size,
             align=(Align.CENTER, Align.CENTER))
    extrude(amount=-label_depth, mode=Mode.SUBTRACT)

    chamfer(geophone_case_lid.faces().sort_by(Axis.Z)[0].outer_wire().edges(),
            edge_cham)

show(geophone_case_lid)
export_stl(geophone_case_lid.part, "stl/geophone_case_lid.stl")

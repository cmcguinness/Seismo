"""geophone_case_lid.py — GEN-1 lid for geophone_case.py.

Deliberately dumb: a flat rounded-square plate, four clearance holes, no gasket
groove, no register lip (the four screws locate it), no vents (the body wall
vents do that job — a hole directly over the element is an acoustic path down
onto it). "GEOPHONE" engraved in the top face. Prints flat, no supports.

5 mm thick rather than 3: the engraving eats 0.8 mm and a 3 mm plate with a
recess in it is thin enough to bow when the four corner screws are snugged.

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

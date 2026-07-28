"""geophone_case_lid.py — GEN-1 lid for geophone_case.py.

Deliberately dumb: a flat rounded-square plate, four clearance holes, no gasket
groove, no register lip (the four screws locate it), no vents (the body wall
vents do that job — a hole directly over the element is an acoustic path down
onto it). Prints flat, no supports.

Fasteners: 4x #6 x 1/2" sheet-metal screws into the body's corner bosses.
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

case_side = 116.0
corner_r = 20.0
lid_th = 3.0
boss_xy = 47.0          # must match geophone_case.py
edge_cham = 0.6

with BuildPart() as geophone_case_lid:
    with BuildSketch(Plane.XY):
        RectangleRounded(case_side, case_side, corner_r)
    extrude(amount=lid_th)

    with Locations((boss_xy, boss_xy, 0), (-boss_xy, boss_xy, 0),
                   (boss_xy, -boss_xy, 0), (-boss_xy, -boss_xy, 0)):
        Cylinder(clear_6 / 2, lid_th,
                 align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)

    chamfer(geophone_case_lid.faces().sort_by(Axis.Z)[0].outer_wire().edges(),
            edge_cham)

show(geophone_case_lid)
export_stl(geophone_case_lid.part, "stl/geophone_case_lid.stl")

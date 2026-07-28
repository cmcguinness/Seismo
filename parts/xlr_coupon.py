"""xlr_coupon.py — test print of just the XLR mount, before committing to the case.

A 60 x 52 offcut of the case's +Y wall, reproducing its exact cross-section: 3 mm
of wall with a 34 x 34 relief on the BACK bringing the panel to 2.4 mm. So it
proves, in ~15 minutes instead of ~4 hours:

  - the 23 mm bore accepts the 22 mm shell,
  - the flange hole pattern lines up,
  - the 2.4 mm panel is inside the connector's 1-3 mm range,
  - an M4 nut seats flat on the relief behind it,
  - the web between each 5 mm hole and the bore, which is only 1.00 mm, actually
    survives printing and tightening. That web is the fragile part of this
    design and is a large part of why the coupon exists.

FOUR holes, both diagonals. The measured pattern (two holes 30 mm apart on the
flange diagonal) is symmetric under 180 deg rotation but NOT under mirroring, so
without the part in hand there is no way to know which handedness is right.
Whichever pair the connector drops onto is the answer — set xlr_screw_diagonal
in dimensions.py to "A" or "B" and the case will carry only that pair.

  A = the pair running lower-left to upper-right, marked with a dimple
  B = the other pair

Print flange-face down (the flat side), no supports.

    PYTHONPATH=. .venv/bin/python parts/xlr_coupon.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

plate_x = 60.0
plate_y = 52.0
wall = 3.0              # matches geophone_case.py
panel_th = 2.4          # matches the case's thinned XLR panel
relief = 34.0           # matches the case's relief patch
corner_r = 4.0

mark_dia = 2.0          # dimple identifying the "A" diagonal
mark_depth = 0.6
label_size = 5.0
label_depth = 0.5

if xlr_screw_dx is None or xlr_screw_dy is None:
    raise SystemExit(
        "xlr_screw_dx / xlr_screw_dy are unmeasured — see dimensions.py.\n"
        "Do NOT derive them from the 30 mm diagonal: assuming the holes follow the\n"
        "flange's corner diagonal leaves 0.40 mm of flange at the long edge, which\n"
        "is not a real part. Measure the horizontal and vertical hole spacings."
    )

dx, dy = xlr_screw_dx, xlr_screw_dy
holes_a = [(dx, dy), (-dx, -dy)]
holes_b = [(dx, -dy), (-dx, dy)]

# a hole that close to the flange edge means the numbers are wrong, not that the
# connector is fragile — catch it before it becomes a print
_edge_long = xlr_flange_h / 2 - dy - xlr_screw_dia / 2
_edge_short = xlr_flange_w / 2 - dx - xlr_screw_dia / 2
assert _edge_long > 1.5 and _edge_short > 1.5, (
    f"only {_edge_long:.2f}/{_edge_short:.2f} mm of flange left at the holes — "
    "re-check the measured offsets")

with BuildPart() as xlr_coupon:
    # wall offcut, flange face on the bed at z=0
    with BuildSketch(Plane.XY):
        RectangleRounded(plate_x, plate_y, corner_r)
    extrude(amount=wall)

    # relief on the back -> 2.4 mm panel, and a flat landing for the nuts
    with BuildSketch(Plane.XY.offset(wall)):
        Rectangle(relief, relief)
    extrude(amount=-(wall - panel_th), mode=Mode.SUBTRACT)

    # bore + both diagonals
    with BuildSketch(Plane.XY):
        Circle(xlr_bore_dia / 2)
        with Locations(*(holes_a + holes_b)):
            Circle(xlr_screw_dia / 2)
    extrude(amount=wall, mode=Mode.SUBTRACT)

    # dimple the "A" pair on the FLANGE face, beyond the 30x25 flange footprint so
    # the marks stay visible with the connector fitted. (They cannot go in the
    # relief pocket — that material is already gone.)
    with BuildSketch(Plane.XY):
        with Locations(*[(x * 1.9, y * 1.9) for x, y in holes_a]):
            Circle(mark_dia / 2)
    extrude(amount=mark_depth, mode=Mode.SUBTRACT)

    # what this coupon is
    with BuildSketch(Plane.XY.offset(wall)):
        with Locations((0, -plate_y / 2 + 5)):
            Text(f"{xlr_bore_dia:g}B {xlr_screw_spacing:g}D",
                 font_size=label_size, align=(Align.CENTER, Align.CENTER))
    extrude(amount=-label_depth, mode=Mode.SUBTRACT)

# the shell must fit and the screw holes must clear the bore
assert xlr_bore_dia > xlr_shell_dia, "bore is smaller than the connector shell"
_gap = (dx ** 2 + dy ** 2) ** 0.5 - xlr_screw_dia / 2 - xlr_bore_dia / 2
assert _gap > 0.5, f"only {_gap:.2f} mm between screw hole and bore"
print(f"screw offsets +-({dx:.2f}, {dy:.2f}) mm; {_gap:.2f} mm of material to the bore")

show(xlr_coupon)
export_stl(xlr_coupon.part, "stl/xlr_coupon.stl")

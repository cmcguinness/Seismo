"""xlr_coupon.py — 10-minute test plate for the XLR panel cutout.

Prints in well under a quarter hour. The connector either bolts to it or it does
not, which is the whole point: we are NOT finding out on a 4-hour case print.

Plate thickness deliberately equals the case's locally-thinned panel (2.4 mm),
so this also proves the connector's 1-3 mm panel range is satisfied and that an
M3 nut seats on the back.

Set `xlr_screw_spacing` and `xlr_screw_axis` in dimensions.py from calipers
first. The measured spacing is engraved on the plate, so if you print two or
three candidates you can tell them apart afterwards.

    PYTHONPATH=. .venv/bin/python parts/xlr_coupon.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

plate_x = 60.0
plate_y = 52.0
plate_th = 2.4          # matches the case's thinned XLR panel
corner_r = 4.0
bore_y = 6.0            # bore centre offset up from plate centre, leaves room to label

label_size = 6.0
label_depth = 0.5

# hole positions, as offsets from the BORE centre at (0, bore_y)
_h = xlr_screw_spacing / 2
_axis = xlr_screw_axis.upper()
if _axis == "X":                      # side by side
    _off = [(-_h, 0), (_h, 0)]
elif _axis == "Z":                    # stacked
    _off = [(0, -_h), (0, _h)]
else:                                 # "D" — diagonal at 45 deg
    _d = _h * 0.70710678
    _off = [(-_d, -_d), (_d, _d)]
holes = [(dx, bore_y + dy) for dx, dy in _off]

with BuildPart() as xlr_coupon:
    with BuildSketch(Plane.XY):
        RectangleRounded(plate_x, plate_y, corner_r)
    extrude(amount=plate_th)

    with BuildSketch(Plane.XY):
        with Locations((0, bore_y)):
            Circle(xlr_bore_dia / 2)
        with Locations(*holes):
            Circle(xlr_screw_dia / 2)
    extrude(amount=plate_th, mode=Mode.SUBTRACT)

    # engrave what this coupon actually is, so candidates stay distinguishable
    with BuildSketch(Plane.XY.offset(plate_th)):
        with Locations((0, -plate_y / 2 + 6)):
            Text(f"{xlr_screw_spacing:g}{xlr_screw_axis.upper()}",
                 font_size=label_size, align=(Align.CENTER, Align.CENTER))
    extrude(amount=-label_depth, mode=Mode.SUBTRACT)

show(xlr_coupon)
export_stl(xlr_coupon.part, "stl/xlr_coupon.stl")

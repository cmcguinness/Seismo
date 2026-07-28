"""xlr_coupon.py — fit test for the XLR mount, before committing to the case print.

An exact offcut of the case's +Y wall: 3 mm wall, a 38 x 38 pad standing 1.5 mm
proud on the OUTSIDE, and the flange footprint recessed 2.0 mm into that pad.
3.0 + 1.5 - 2.0 = 2.5 mm of panel under the flange, inside the connector's
1-3 mm range. ~10 minutes to print instead of ~4 hours for the case.

THE RECESS IS THE POINT. Two M4s through 2.5 mm of PLA are a poor way to carry
the lateral and torsional load a latching XLR puts on a panel every time the
cable is pulled. The recessed seat takes that load in shear through the pocket
walls and leaves the screws doing nothing but clamping.

Depth is set to the ~2 mm flange thickness so it finishes flush, but nothing
depends on that being exact: the screws clamp the flange to the pocket floor
whether it sits proud or sunk.

FOUR holes (all four sign combinations), so handedness is a non-issue: whichever
diagonal the connector uses, two line up and the other two end up hidden under
the 30 x 25 flange.

What this proves:
  - that the recessed seat fits the flange and actually locates it,
  - the 23 mm bore accepts the 22 mm shell (shell 22, bore 23),
  - the 2.5 mm panel is inside the connector's 1-3 mm range,
  - a nut seats flat on the plain inner face behind,
  - the ~1.2 mm web between each 5 mm hole and the bore survives printing and
    tightening. That web is the fragile part of this design.

Print BACK face down (the plain side); the pads and seats face up. No supports.

    PYTHONPATH=. .venv/bin/python parts/xlr_coupon.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

plate_x = 56.0
plate_y = 56.0
wall = 3.0              # matches geophone_case.py
corner_r = 4.0
pad_cham = 0.6          # eases the pad's printed edge

_maj, _min = xlr_screw_off_major, xlr_screw_off_minor
_c = xlr_seat_clearance
_v = xlr_flange_axis.upper() == "V"
hole_dx, hole_dy = (_min, _maj) if _v else (_maj, _min)
seat_w = (xlr_flange_h if _v else xlr_flange_w) + _c
seat_h = (xlr_flange_w if _v else xlr_flange_h) + _c
panel_th = wall + xlr_pad_proud - xlr_seat_depth


with BuildPart() as xlr_coupon:
    with BuildSketch(Plane.XY):
        RectangleRounded(plate_x, plate_y, corner_r)
    extrude(amount=wall)

    # raised pad on the outer face
    with BuildSketch(Plane.XY.offset(wall)):
        RectangleRounded(xlr_pad_w, xlr_pad_h, 3.0)
    extrude(amount=xlr_pad_proud)

    # flange seat recessed into the pad
    with BuildSketch(Plane.XY.offset(wall + xlr_pad_proud)):
        Rectangle(seat_w, seat_h)
    extrude(amount=-xlr_seat_depth, mode=Mode.SUBTRACT)

    # bore and hole pattern, through everything
    with BuildSketch(Plane.XY):
        Circle(xlr_bore_dia / 2)
        with Locations(*[(sx * hole_dx, sy * hole_dy)
                         for sx in (1, -1) for sy in (1, -1)]):
            Circle(xlr_screw_dia / 2)
    extrude(amount=wall + xlr_pad_proud, mode=Mode.SUBTRACT)

# --- checks that must hold before this is worth printing ---
assert xlr_bore_dia > xlr_shell_dia, "bore is smaller than the connector shell"
assert 1.0 <= panel_th <= xlr_panel_th_max, f"panel is {panel_th} mm, outside 1-3"
_r = (_maj ** 2 + _min ** 2) ** 0.5
_web = _r - xlr_screw_dia / 2 - xlr_bore_dia / 2
assert _web > 0.8, f"only {_web:.2f} mm of web between screw hole and bore"
assert abs(2 * _r - xlr_screw_spacing) < 1.0, (
    f"pattern spans {2*_r:.2f} mm, measured {xlr_screw_spacing} mm")
# every screw hole must sit inside the seat, or the flange is not captured at all
assert (hole_dx + xlr_screw_dia / 2 < seat_w / 2
        and hole_dy + xlr_screw_dia / 2 < seat_h / 2), \
    "screw holes fall outside the flange seat"
# and the seat must sit inside the pad
assert max(xlr_flange_w, xlr_flange_h) + _c + 2.0 < min(xlr_pad_w, xlr_pad_h), \
    "flange seat leaves no pad wall around it"
print(f"axis {xlr_flange_axis} | seat {seat_w:.1f} x {seat_h:.1f} x {xlr_seat_depth} deep | "
      f"panel {panel_th:.1f} mm | pattern {2*_r:.2f} mm across (measured "
      f"{xlr_screw_spacing}) | web {_web:.2f} mm")

show(xlr_coupon)
export_stl(xlr_coupon.part, "stl/xlr_coupon.stl")

"""xlr_coupon.py — one test card that settles the XLR mount before the case print.

TWO stations on a single plate, each an exact offcut of the case's +Y wall:
3 mm wall, a 40 x 35 pad standing 1 mm proud on the OUTSIDE, and the flange
footprint recessed 1.5 mm into that pad. 3.0 + 1.0 - 1.5 = 2.5 mm of panel under
the flange, inside the connector's 1-3 mm range. ~20 minutes to print instead of
~4 hours for the case.

  V  — flange's 30 mm axis VERTICAL   -> seat 25.4 x 30.4, holes at (+-10.0, +-11.5)
  H  — flange's 30 mm axis HORIZONTAL -> seat 30.4 x 25.4, holes at (+-11.5, +-10.0)

THE RECESS IS THE POINT. Two M4s through 2.5 mm of PLA are a poor way to carry
the lateral and torsional load a latching XLR puts on a panel every time the
cable is pulled. The recessed seat takes that load in shear through the pocket
walls and leaves the screws doing nothing but clamping.

Its depth deliberately does NOT track the flange thickness — the screws clamp
the flange to the pocket floor whether it sits proud of the pad or below it. So
the flange thickness never needed measuring.

Each station carries FOUR holes (all four sign combinations), so handedness is a
non-issue: whichever diagonal the connector uses, two line up and two end up
hidden under the flange. Only V-vs-H has to come back.

What one print proves:
  - which flange orientation the pattern actually is,
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

station_dx = 26.0       # station centres either side of the plate centre
plate_x = 104.0
plate_y = 56.0
wall = 3.0              # matches geophone_case.py
corner_r = 4.0
pad_cham = 0.6          # eases the pad's printed edge

label_size = 7.0
label_depth = 0.5

_maj, _min = xlr_screw_off_major, xlr_screw_off_minor
_c = xlr_seat_clearance
# per station: (hole dx, hole dy), (seat width, seat height)
STATIONS = {
    "V": ((_min, _maj), (xlr_flange_h + _c, xlr_flange_w + _c)),
    "H": ((_maj, _min), (xlr_flange_w + _c, xlr_flange_h + _c)),
}
panel_th = wall + xlr_pad_proud - xlr_seat_depth


def _cx(name):
    return -station_dx if name == "V" else station_dx


with BuildPart() as xlr_coupon:
    with BuildSketch(Plane.XY):
        RectangleRounded(plate_x, plate_y, corner_r)
    extrude(amount=wall)

    # raised pads on the outer face
    with BuildSketch(Plane.XY.offset(wall)):
        with Locations(*[(_cx(n), 0) for n in STATIONS]):
            RectangleRounded(xlr_pad_w, xlr_pad_h, 3.0)
    extrude(amount=xlr_pad_proud)

    # flange seats recessed into the pads
    with BuildSketch(Plane.XY.offset(wall + xlr_pad_proud)):
        for name, (_, (sw, sh)) in STATIONS.items():
            with Locations((_cx(name), 0)):
                Rectangle(sw, sh)
    extrude(amount=-xlr_seat_depth, mode=Mode.SUBTRACT)

    # bores and hole patterns, through everything
    with BuildSketch(Plane.XY):
        for name, ((dx, dy), _) in STATIONS.items():
            with Locations((_cx(name), 0)):
                Circle(xlr_bore_dia / 2)
            with Locations(*[(_cx(name) + sx * dx, sy * dy)
                             for sx in (1, -1) for sy in (1, -1)]):
                Circle(xlr_screw_dia / 2)
    extrude(amount=wall + xlr_pad_proud, mode=Mode.SUBTRACT)

    # label each station on the plate, clear of the pad
    with BuildSketch(Plane.XY.offset(wall)):
        for name in STATIONS:
            with Locations((_cx(name), -plate_y / 2 + 5)):
                Text(name, font_size=label_size, align=(Align.CENTER, Align.CENTER))
    extrude(amount=-label_depth, mode=Mode.SUBTRACT)

# --- checks that must hold before this is worth printing ---
assert xlr_bore_dia > xlr_shell_dia, "bore is smaller than the connector shell"
assert 1.0 <= panel_th <= xlr_panel_th_max, f"panel is {panel_th} mm, outside 1-3"
_r = (_maj ** 2 + _min ** 2) ** 0.5
_web = _r - xlr_screw_dia / 2 - xlr_bore_dia / 2
assert _web > 0.8, f"only {_web:.2f} mm of web between screw hole and bore"
assert abs(2 * _r - xlr_screw_spacing) < 1.0, (
    f"pattern spans {2*_r:.2f} mm, measured {xlr_screw_spacing} mm")
# every screw hole must sit inside its seat, or it is not being captured at all
for _n, ((_dx, _dy), (_sw, _sh)) in STATIONS.items():
    assert _dx + xlr_screw_dia / 2 < _sw / 2 and _dy + xlr_screw_dia / 2 < _sh / 2, \
        f"station {_n}: screw holes fall outside the flange seat"
# and the seat must sit inside the pad
assert max(xlr_flange_w, xlr_flange_h) + _c + 2.0 < min(xlr_pad_w, xlr_pad_h), \
    "flange seat leaves no pad wall around it"
print(f"panel under flange {panel_th:.1f} mm | seat depth {xlr_seat_depth} mm | "
      f"pattern {2*_r:.2f} mm across (measured {xlr_screw_spacing}) | web {_web:.2f} mm")

show(xlr_coupon)
export_stl(xlr_coupon.part, "stl/xlr_coupon.stl")

"""xlr_coupon.py — one test card that settles the XLR mount before the case print.

TWO stations on a single plate, each an offcut of the case's +Y wall reproducing
its exact cross-section: 3 mm of wall with a 34 x 34 relief on the BACK bringing
the panel to 2.4 mm. ~20 minutes to print instead of ~4 hours for the case.

  V  — flange's 30 mm axis VERTICAL   -> holes at (+-10.0, +-11.5)
  H  — flange's 30 mm axis HORIZONTAL -> holes at (+-11.5, +-10.0)

Each station carries FOUR holes (all four sign combinations), so handedness is a
non-issue — whichever diagonal the connector uses, two of the four line up and
the other two end up hidden under the 30 x 25 flange. Only V-vs-H has to come
back, and the case then carries the same four holes for the winning orientation.

What one print proves:
  - the 23 mm bore accepts the 22 mm shell (Charles's call: shell 22, bore 23),
  - which flange orientation the pattern actually is,
  - the 2.4 mm panel is inside the connector's 1-3 mm range,
  - an M3/M4 nut seats flat on the relief behind,
  - the ~1.2 mm web between each 5 mm hole and the bore survives printing and
    tightening. That web is the fragile part of this design and is much of why
    the card exists.

Holes are 5 mm as measured. A clearance hole cannot be too large: 5 mm passes an
M3 (with a washer) or an M4 regardless of whether the flange's 5 mm is a through
hole or the outer diameter of an M3 countersink.

Print flange-face down, no supports.

    PYTHONPATH=. .venv/bin/python parts/xlr_coupon.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

station_dx = 26.0       # station centres either side of the plate centre
plate_x = 104.0
plate_y = 56.0
wall = 3.0              # matches geophone_case.py
panel_th = 2.4          # matches the case's thinned XLR panel
relief = 34.0           # matches the case's relief patch
corner_r = 4.0

label_size = 7.0
label_depth = 0.5

_maj, _min = xlr_screw_off_major, xlr_screw_off_minor
# all four sign combinations => both diagonals covered
STATIONS = {"V": (_min, _maj), "H": (_maj, _min)}


def _holes(dx, dy):
    return [(sx * dx, sy * dy) for sx in (1, -1) for sy in (1, -1)]


with BuildPart() as xlr_coupon:
    with BuildSketch(Plane.XY):
        RectangleRounded(plate_x, plate_y, corner_r)
    extrude(amount=wall)

    # relief pockets on the back -> 2.4 mm panel + a flat landing for the nuts
    with BuildSketch(Plane.XY.offset(wall)):
        with Locations((-station_dx, 0), (station_dx, 0)):
            Rectangle(relief, relief)
    extrude(amount=-(wall - panel_th), mode=Mode.SUBTRACT)

    # bores and hole patterns
    with BuildSketch(Plane.XY):
        for name, (dx, dy) in STATIONS.items():
            cx = -station_dx if name == "V" else station_dx
            with Locations((cx, 0)):
                Circle(xlr_bore_dia / 2)
            with Locations(*[(cx + hx, hy) for hx, hy in _holes(dx, dy)]):
                Circle(xlr_screw_dia / 2)
    extrude(amount=wall, mode=Mode.SUBTRACT)

    # label each station on the flange face, clear of the 30 x 25 flange footprint
    with BuildSketch(Plane.XY):
        for name in STATIONS:
            cx = -station_dx if name == "V" else station_dx
            with Locations((cx, -plate_y / 2 + 5)):
                Text(name, font_size=label_size, align=(Align.CENTER, Align.CENTER))
    extrude(amount=label_depth, mode=Mode.SUBTRACT)

# --- checks that must hold before this is worth printing ---
assert xlr_bore_dia > xlr_shell_dia, "bore is smaller than the connector shell"
_r = (_maj ** 2 + _min ** 2) ** 0.5
_web = _r - xlr_screw_dia / 2 - xlr_bore_dia / 2
assert _web > 0.8, f"only {_web:.2f} mm of web between screw hole and bore"
# the published pattern must reproduce the measured centre-to-centre distance
assert abs(2 * _r - xlr_screw_spacing) < 1.0, (
    f"pattern spans {2*_r:.2f} mm, measured {xlr_screw_spacing} mm")
# nuts must land on the relief, not off its edge
assert _maj + 4.05 < relief / 2, "nut overhangs the relief pocket"
print(f"hole circle r={_r:.2f} mm -> {2*_r:.2f} mm across (measured "
      f"{xlr_screw_spacing}); web to bore {_web:.2f} mm")

show(xlr_coupon)
export_stl(xlr_coupon.part, "stl/xlr_coupon.stl")

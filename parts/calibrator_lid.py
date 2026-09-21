"""calibrator_lid.py — the flat plate that closes the calibration injector box.

Deliberately featureless. Every cutout in this box lives in `calibrator_case.py`,
so this is the piece that never needs reprinting, and the tray is the piece you
iterate on if a connector does not fit. Four M3 self-tappers into the tray's corner
bosses, and that is the whole part.

No register lip: the corner bosses sit `cal_boss_inset` (6 mm) in from the cavity
edge, which is exactly where a perimeter rim would want to be, and notching a rim
in four places to dodge them buys nothing here. The bosses locate the lid.

Nothing mounts to the underside. The coin-cell holders go on the tray's -Y wall so
that changing a cell never means lifting the lid onto a tethered board -- and the
box spends 86,376 s of every day doing nothing, so the only times this lid comes
off are a cell change and a fault.

Print flat side down, no supports. ~20 minutes.

    PYTHONPATH=. .venv/bin/python parts/calibrator_lid.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

# Same four positions the tray's bosses are built on -- both derive from
# dimensions.py rather than one copying the other.
screw_posts = [(sx * (cal_cav_x / 2 - cal_boss_inset),
                sy * (cal_cav_y / 2 - cal_boss_inset))
               for sx in (1, -1) for sy in (1, -1)]


with BuildPart() as calibrator_lid:
    with BuildSketch(Plane.XY):
        RectangleRounded(cal_case_x, cal_case_y, cal_corner_r)
        with Locations(*screw_posts):
            Circle(clear_m3 / 2, mode=Mode.SUBTRACT)
    extrude(amount=cal_lid_th)


# --- checks ------------------------------------------------------------------
# A screw hole that wanders off the boss is a lid that does not fasten.
for _x, _y in screw_posts:
    _edge_x = cal_case_x / 2 - abs(_x)
    _edge_y = cal_case_y / 2 - abs(_y)
    assert min(_edge_x, _edge_y) > clear_m3 / 2 + 1.5, (
        f"screw hole at ({_x}, {_y}) is {min(_edge_x, _edge_y):.1f} mm from the edge")
assert clear_m3 > pilot_m3, "lid hole must clear the shank the tray taps"
assert cal_lid_th >= 2.0, "a 138 mm plate thinner than 2 mm will bow"

print(f"lid {cal_case_x} x {cal_case_y} x {cal_lid_th} mm, "
      f"4 x M3 clearance ({clear_m3}) at {screw_posts[0]} and mirrors")

show(calibrator_lid)
export_stl(calibrator_lid.part, "stl/calibrator_lid.stl")

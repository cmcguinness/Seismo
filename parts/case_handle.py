"""case_handle.py — carry handle, screwed to the cover roof FROM INSIDE.

One of three parts (Charles, 2026-08-08): BASE + COVER + HANDLE. Separating it is
what lets the cover print rim-down with no support, and lets the handle print legs-
down with its finger opening self-supporting — two parts, two ideal orientations,
instead of one compromise.

Bar geometry is carried over from geophone_case_lid.py, which prints clean: the
finger opening is a trapezoid whose sides sit at ~55 deg, so it bridges itself.

NO FLANGE, and no through-holes. Screws go from INSIDE the cavity, up through
clearance holes in the cover roof, into blind pilots in the undersides of the two
LEGS — heads hidden, nothing extra protruding. An earlier revision grew a 92 mm
flange so the screws could land outboard of the legs; that solved a problem that
does not exist. The leg is 24 mm of solid PLA, which is more thread engagement than
anywhere else on the part.

Load path: lifting hangs the whole case on two #6 screws in tension. The bearing is
on the INSIDE of the roof, which is why case_cover.py thickens it locally there.

Print leg-faces-down, no supports. Use a brim — the part now stands on two small
footprints instead of one flange.

    PYTHONPATH=. .venv/bin/python parts/case_handle.py
"""
from math import atan2, degrees

from build123d import *
from ocp_vscode import show
from dimensions import *

cham = 0.4

# Opening sides must not overhang: shallower than 45 deg from vertical needs support.
side_angle = 90 - degrees(atan2((handle_open_w - handle_open_top) / 2, handle_open_h))

with BuildPart() as case_handle:
    # bar, profile in XZ so the trapezoidal opening lies in the print's vertical plane
    with BuildSketch(Plane.XZ.offset(-handle_w / 2)) as prof:
        Rectangle(handle_span, handle_h, align=(Align.CENTER, Align.MIN))
        fillet(prof.vertices().sort_by(Axis.Y)[-2:], handle_top_r)
        Trapezoid(handle_open_w, handle_open_h,
                  left_side_angle=side_angle, right_side_angle=side_angle,
                  align=(Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    extrude(amount=handle_w)

    # blind pilots UP into each leg, from the underside
    with Locations(*[(sx * handle_screw_off, 0, 0) for sx in (1, -1)]):
        Cylinder(pilot_6 / 2, handle_pilot_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)


# --- checks ---
assert side_angle >= 45, f"opening sides overhang at {side_angle:.1f} deg — needs support"
# each pilot must sit INSIDE a leg, with wall left around it
_leg_inner, _leg_outer = handle_open_w / 2, handle_span / 2
assert handle_screw_off - pilot_6 / 2 > _leg_inner + 1.5, "pilot breaks into the opening"
assert handle_screw_off + pilot_6 / 2 < _leg_outer - 1.5, "pilot breaks out of the leg end"
assert handle_pilot_depth < handle_open_h, \
    "pilot is deeper than the leg is tall before the opening starts"
assert handle_open_h > 15.0, "not enough finger clearance under the bar"

print(f"handle {handle_span:.0f} x {handle_w:.0f} x {handle_h:.0f} mm | opening "
      f"{handle_open_w:.0f} -> {handle_open_top:.0f} at {side_angle:.1f} deg | "
      f"blind pilots +-{handle_screw_off:.1f}, {handle_pilot_depth:.0f} deep into the legs")

show(case_handle)
export_stl(case_handle.part, "stl/case_handle.stl")

"""case_handle.py — carry handle, screwed onto the cover roof from outside.

One of three parts (Charles, 2026-08-08): BASE + COVER + HANDLE. Separating it is
what lets the cover print rim-down with no support, and lets the handle print flange-
down with its finger opening self-supporting — two parts, two ideal orientations,
instead of one compromise.

Bar geometry is carried over from geophone_case_lid.py, which prints clean: the
finger opening is a trapezoid whose sides sit at ~55 deg, so it bridges itself.

THE FLANGE IS LONGER THAN THE BAR ON PURPOSE. The two screws land outside the bar's
legs, at +-40 mm against a 70 mm span. Put them inside and a clearance hole has to
run down through 24 mm of leg to reach the roof — a deep, pointless hole through the
part's only load-bearing section.

Load path: lifting by this hangs the whole case on two #6 screws in PLA, in tension.
That is the reason for the flange rather than two feet: it spreads the pull over
92 x 16 mm of roof instead of two 10 mm pads.

Print flange-down, no supports.

    PYTHONPATH=. .venv/bin/python parts/case_handle.py
"""
from math import atan2, degrees

from build123d import *
from ocp_vscode import show
from dimensions import *

flange_r = 4.0          # rounds the flange corners
cham = 0.4

# Opening sides must not overhang: shallower than 45 deg from vertical needs support.
side_angle = 90 - degrees(atan2((handle_open_w - handle_open_top) / 2, handle_open_h))

with BuildPart() as case_handle:
    # flange
    with BuildSketch(Plane.XY):
        RectangleRounded(handle_flange_len, handle_w, flange_r)
    extrude(amount=handle_flange_th)

    # bar, profile in XZ so the trapezoidal opening lies in the print's vertical plane
    with BuildSketch(Plane.XZ.offset(-handle_w / 2)) as prof:
        with Locations((0, handle_flange_th)):
            Rectangle(handle_span, handle_h, align=(Align.CENTER, Align.MIN))
        fillet(prof.vertices().sort_by(Axis.Y)[-2:], handle_top_r)
        with Locations((0, handle_flange_th)):
            Trapezoid(handle_open_w, handle_open_h,
                      left_side_angle=side_angle, right_side_angle=side_angle,
                      align=(Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    extrude(amount=handle_w)

    # two clearance holes through the flange, outboard of the legs
    with BuildSketch(Plane.XY):
        with Locations(*[(sx * handle_screw_off, 0) for sx in (1, -1)]):
            Circle(clear_6 / 2)
    extrude(amount=handle_flange_th, mode=Mode.SUBTRACT)

    chamfer(case_handle.faces().sort_by(Axis.Z)[0].outer_wire().edges(), cham)


# --- checks ---
assert side_angle >= 45, f"opening sides overhang at {side_angle:.1f} deg — needs support"
# screws must clear the bar's legs, or the hole runs down through the leg
_leg_inner = handle_open_w / 2
_leg_outer = handle_span / 2
assert (handle_screw_off - clear_6 / 2 > _leg_outer
        or handle_screw_off + clear_6 / 2 < _leg_inner), \
    "a screw hole lands under a leg of the bar"
# and stay on the flange
assert handle_screw_off + clear_6 / 2 < handle_flange_len / 2 - 2.0, \
    "screw hole breaks out of the flange edge"
assert handle_flange_len > handle_span, "flange must overhang the bar to carry the screws"
assert handle_open_h > 15.0, "not enough finger clearance under the bar"

print(f"handle {handle_flange_len:.0f} x {handle_w:.0f} x {handle_flange_th + handle_h:.0f} mm"
      f" | bar span {handle_span:.0f} | opening {handle_open_w:.0f} -> {handle_open_top:.0f}"
      f" at {side_angle:.1f} deg | screws +-{handle_screw_off:.0f}")

show(case_handle)
export_stl(case_handle.part, "stl/case_handle.stl")

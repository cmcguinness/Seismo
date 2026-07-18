"""geophone_base.py — open-top coupling pocket for the LGT-4.5 geophone.

MVP part (Phase: enclosure). The geophone drops in bottom-first, seats on its
bottom rim on the floor, and a small centering boss noses into the bottom
recess to stop lateral shift. Prints flat-base-down (the coupling face).

This also doubles as the FIT-TEST coupon: print it, drop the geophone in, and
tune `fit_clearance` in dimensions.py until the slip fit is right. Once the bore
is dialed in we add the clamp ring, the Pi/ADC tray, and a lid.
"""
from build123d import *
from ocp_vscode import show
from dimensions import *   # geophone_dia, geophone_height, fit_clearance

# --- parameters (mm) ---
wall = 3.0                                   # pocket wall thickness
floor = 4.0                                  # coupling floor thickness
bore_dia = geophone_dia + 2 * fit_clearance  # slip-fit bore (tune fit_clearance)
pocket_depth = geophone_height               # element ends ~flush with the rim
wire_slot_w = 6.0                            # top-rim notch for the terminal leads
# NOTE: no centering boss. Ink test (2026-07-17) showed a 2mm boss bottomed out
# in the geophone's shallow ~1mm bottom recess and lifted it off its rim -> only
# the center made contact. Flat floor instead: the full bottom rim seats (broad,
# rigid coupling); the glove-fit bore handles centering.

outer_dia = bore_dia + 2 * wall
total_h = floor + pocket_depth

# --- model ---
with BuildPart() as geophone_base:
    # solid coupling puck, base at z=0
    Cylinder(bore_dia / 2 + wall, total_h,
             align=(Align.CENTER, Align.CENTER, Align.MIN))
    # hollow the pocket from the top (over-cut 1mm through the rim for a clean edge)
    with Locations((0, 0, floor)):
        Cylinder(bore_dia / 2, pocket_depth + 1,
                 align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)
    # (no centering boss — flat floor so the geophone's bottom rim seats fully)
    # wire-exit notch in the top rim
    with Locations((0, outer_dia / 2, total_h)):
        Box(wire_slot_w, 2 * wall + 2, 8,
            align=(Align.CENTER, Align.CENTER, Align.MAX),
            mode=Mode.SUBTRACT)

show(geophone_base)
export_stl(geophone_base.part, "stl/geophone_base.stl")   # refreshed on every run

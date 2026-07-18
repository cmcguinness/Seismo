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
boss_dia = 9.0                               # centering boss -> bottom recess
boss_height = 2.0                            # < recess depth so the rim still seats
wire_slot_w = 6.0                            # top-rim notch for the terminal leads

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
    # centering boss on the floor
    with Locations((0, 0, floor)):
        Cylinder(boss_dia / 2, boss_height,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    # wire-exit notch in the top rim
    with Locations((0, outer_dia / 2, total_h)):
        Box(wire_slot_w, 2 * wall + 2, 8,
            align=(Align.CENTER, Align.CENTER, Align.MAX),
            mode=Mode.SUBTRACT)

show(geophone_base)
export_stl(geophone_base.part, "stl/geophone_base.stl")   # refreshed on every run

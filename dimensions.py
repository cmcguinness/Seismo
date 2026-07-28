# dimensions.py — shared dimensions (mm) live here.
# Import into part scripts with:  from dimensions import *
# Cross-part dims belong here; part-local params stay in their own file.
# (parts/starter.py keeps its own `size = 10` locally so copying the
#  template never collides with names defined here.)

# --- Geophone: LGT-4.5 bare 1" element (measured / confirmed) ---
geophone_dia = 25.4       # body diameter (mm) — 1 inch, confirmed
geophone_height = 36.0    # body height (mm)
geophone_mass_g = 74      # informs base-mass / coupling reasoning
# Bottom : flat outer rim + central recessed hole -> seats on rim; a small
#          centering boss on the pocket floor can nose into the recess.
# Top    : offset green terminal board with two protruding solder pins
#          (one marked +) and a lead wire -> clamp must clear the center
#          and route the wire out the side.

# --- Neutrik D-series XLR chassis connector (NC3MD-L-B / NC3FD-L-B) ---
xlr_bore_dia = 24.0       # standardized "D" panel cutout — this number is reliable
xlr_panel_th_max = 3.0    # D-series accepts a 1-3 mm panel; wall must be thinned to suit
xlr_body_depth = 32.0     # intrusion behind the panel — this sets the case inner width
xlr_screw_dia = 3.4       # M3 clearance — flange is countersunk for M3, nut goes inside
# UNCONFIRMED until measured + proven on parts/xlr_coupon.py. Hand-drilling through the
# connector does NOT work: countersunk flange holes are a cone, not a drill bushing; the
# shell protrudes into the chuck's path; and a 3.2 mm bit snatching through a 2.4 mm PLA
# wall cracks it. Measure with calipers, print the coupon, then commit to the case.
xlr_screw_spacing = 24.0  # centre-to-centre  <-- MEASURE
xlr_screw_axis = "X"      # "X" = holes side-by-side, "Z" = stacked  <-- CONFIRM

# --- Print / fit tuning ---
fit_clearance = 0.2       # radial slip-fit gap added to bores (FDM, PLA/PETG)
pilot_6 = 2.7             # pilot bore for a #6 sheet-metal screw into PLA
clear_6 = 3.6             # clearance bore for a #6 screw shank

# --- Raspberry Pi 2B (mounting) ---
pi_len = 85.0             # board long dimension
pi_wid = 56.0             # board short dimension
pi_hole_dx = 58.0         # mounting-hole rectangle, long axis
pi_hole_dy = 49.0         # mounting-hole rectangle, short axis
pi_hole_offset_x = -10.0  # hole-block center offset from board center along length
                          # (holes sit 3.5mm from one short edge, 23.5mm from the other)
pi_hole_dia = 2.75        # Pi mounting hole (M2.5 clearance)
pi_standoff_h = 6.0       # lift board off base; clears bottom SMD + the nuts
                          # protruding under the Pi<->HAT standoff holes (~2-4mm)
pi_board_th = 1.6         # Pi PCB thickness (~1.4mm) + a hair; sets cotter-hole height
dongle_clearance = 45.0   # -X (USB) side: Wi-Fi dongle reaches ~45mm past the board
                          # edge (USB-A connectors ~15mm). Sizes the future wall's
                          # dongle slot; the plate only underlies the USB connectors.


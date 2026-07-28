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

# --- XLR chassis connector — MEASURED off the part in hand (Charles, 2026-07-28) ---
xlr_shell_dia = 22.0      # circular protrusion behind the flange
xlr_bore_dia = 23.0       # +1 mm on the shell, deliberately loose
xlr_flange_w = 30.0       # flange, long axis
xlr_flange_h = 25.0       # flange, short axis
xlr_screw_spacing = 30.0  # two 5 mm holes, centre-to-centre, ON THE FLANGE DIAGONAL
xlr_screw_dia = 3.4       # our side: M3 clearance. M3 fits whether the flange's 5 mm
                          # holes are plain or a countersink over an M3 through-hole;
                          # use a washer under the head. M4 -> set 4.5 and re-coupon.
xlr_panel_th_max = 3.0    # connector accepts a 1-3 mm panel; wall thinned to suit
xlr_body_depth = 32.0     # intrusion behind the panel — this sets the case inner width

# Hole offsets from the bore centre, along the flange diagonal (39.05 mm long):
#   +-15 mm * (30, 25)/39.05  ->  +-(11.52, 9.60)
_xlr_diag = (xlr_flange_w ** 2 + xlr_flange_h ** 2) ** 0.5
xlr_screw_dx = xlr_screw_spacing / 2 * xlr_flange_w / _xlr_diag
xlr_screw_dy = xlr_screw_spacing / 2 * xlr_flange_h / _xlr_diag

# WHICH diagonal is still open: the pattern is symmetric under 180 deg rotation but NOT
# under mirroring, so the two handednesses are genuinely different parts. The coupon
# carries both (4 holes); set this to "A" (dx,dy)+(-dx,-dy) or "B" (dx,-dy)+(-dx,dy)
# once the connector has actually sat on it, and the case will drill just that pair.
xlr_screw_diagonal = None

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


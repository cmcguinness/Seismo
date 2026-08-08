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
# 24.0, NOT shell+1. The shank carries four slots/ribs — three small centring ones and
# a larger one for the release lever — and the published cutout (23.6-24 mm) is
# oversized precisely so those CLEAR the panel instead of engaging it. A 23 mm bore
# fouls them: the connector will not pass through. Our rectangular flange seat is what
# stops rotation, so the ribs have no job here.
xlr_bore_dia = 24.0
xlr_flange_w = 30.0       # flange, long axis
xlr_flange_h = 25.0       # flange, short axis
xlr_screw_spacing = 30.0  # two 5 mm holes, centre-to-centre, ON THE FLANGE DIAGONAL
xlr_screw_dia = 3.4       # M3 clearance. The measured 5 mm is the COUNTERSINK's outer
                          # diameter — the standard flange takes countersunk M3 — and at
                          # a 24 mm bore a 5 mm hole would leave only 0.74 mm of web to
                          # the bore. 3.4 restores 1.54 mm. Fastener: M3 x 12 + washer
                          # (the flange's 5 mm countersink needs one) + nut inside.
xlr_panel_th_max = 3.0    # connector accepts a 1-3 mm panel
xlr_body_depth = 32.0     # intrusion behind the panel — this sets the case inner width

# --- flange seat: a raised pad on the OUTSIDE with the flange footprint recessed into it
# The recess carries lateral and torsional load into the plastic instead of into two
# screws in a thin wall — that is its job, not cosmetics, and it is why it exists at all.
# Depth is set to the flange thickness so the flange finishes flush, but nothing depends
# on that being exact: the screws clamp the flange to the pocket floor whether it ends up
# proud or sunk. Getting the depth wrong costs appearance, not function.
# (An earlier revision put a 34 x 34 x 0.6 pocket on the INSIDE instead. Useless: the
# case is a rounded square precisely so the walls are flat, so there was nothing to
# flatten, and an inside pocket cannot restrain a flange that bears on the outside. Its
# only real effect was thinning the panel, which the pad now does properly.)
xlr_flange_th = 2.0       # measured ~2 mm
xlr_seat_clearance = 1.4  # added to the flange footprint, total. Was 0.4; the printed
                          # seat came out a smidge tight on the real flange (Charles,
                          # 2026-07-28) so +1 mm on each axis. Costs 0.5 mm of play per
                          # side before the seat wall takes load, which is still a far
                          # better restraint than two screws in 2.5 mm of PLA.
                          # VALIDATED on the printed coupon with the real Neutrik D:
                          # both axes were tight at 0.4, both fit at 1.4. The resulting
                          # play is deliberate and accepted — do NOT tighten this back
                          # up chasing a snugger fit, the ROI does not justify another
                          # fitting round.
xlr_seat_depth = 2.0      # = flange thickness, so the flange finishes flush with the pad
xlr_pad_proud = 1.5       # how far the pad stands out from the wall
xlr_pad_w = 38.0          # pad footprint — square, so V and H both get an even
xlr_pad_h = 38.0          # 3.8 mm of pad wall around the seat that does the capturing
# wall 3.0 + pad 1.5 - recess 2.0 = 2.5 mm of panel under the flange, inside the 1-3 range

# Hole offsets from the bore centre — the PUBLISHED D-series pattern, not a derivation.
# Neutrik give x:10 y:11.5 for M3 screws on the 24 mm cutout (x:9.5 y:12 for 3.2 mm
# drilled holes). That pair is 2*hypot(10, 11.5) = 30.5 mm apart, which is Charles's
# measured 30 mm centre-to-centre. The LARGER offset lies on the flange's 30 mm axis:
# against a 30 x 25 flange that leaves 3.5 and 2.5 mm to the edges, a real part.
#
# My first attempt put the holes on the flange's corner diagonal, giving +-(11.52,
# 9.60) — dx > dy, the wrong way round, leaving 0.40 mm of flange. The flange is not
# square, so "diagonally opposed" and "along the plate diagonal" are different lines.
xlr_screw_off_major = 11.5   # along the flange's 30 mm axis
xlr_screw_off_minor = 10.0   # along the flange's 25 mm axis
# Which way the 30 mm axis runs on the case wall: "V" (vertical) or "H" (horizontal).
# This is a free choice of how to mount it, NOT a property of the connector — it fits
# either way, rotated. Chose V: the screws end up 23 mm apart vertically instead of 20,
# which resists the downward moment of a hanging cable slightly better.
xlr_flange_axis = "V"
xlr_bore_centred = True      # assumed; the coupon confirms it

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
dongle_clearance = 0.0    # WAS 45.0. The Wi-Fi dongle is REMOVED (confirmed 2026-08-07)
                          # -- the station runs on the Ethernet bridge since 2026-07-20
                          # (WiFi TX was corrupting ADC reads). Dropping it takes 45 mm
                          # off the case's longest dimension, which was the single
                          # biggest driver of the envelope. If Wi-Fi ever comes back,
                          # this is the number to restore.


# --- Panel connectors for the Pi / front-end case (gen 1) ---------------------
# Ethernet: D-type (D-series) feedthrough. Deliberately reuses the SAME bore and
# hole pattern as the XLR above -- that pattern is already validated on a printed
# coupon against a real Neutrik D, so the RJ45 coupler is a drop-in IF its flange
# really is D-series. That "if" is what the coupon below checks.
eth_bore_dia = xlr_bore_dia
eth_flange_w = xlr_flange_w
eth_flange_h = xlr_flange_h

# Barrel jack: RuiLing 5.5 x 2.1 panel mount, 3-pin, hex nut.
# Flange OD 14.0 and thread length 11.8 are from the listing; the THREAD OD is the
# panel hole and is NOT published anywhere trustworthy. Rather than caliper it and
# then discover print shrinkage moved it anyway, the coupon prints a LADDER of
# candidate bores and the jack itself picks the winner.
barrel_flange_dia = 14.0   # must not fall through: every ladder bore stays under this
barrel_thread_len = 11.8   # panel + nut must fit inside this
barrel_ladder = [9.5, 10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0]

# --- Waveshare AD/DA stacked on the Pi (measured by Charles, 2026-08-07) ---
stack_h = 30.0            # Pi PCB bottom -> tallest thing on the Waveshare.
stack_overhang = 0.0      # the Waveshare does NOT overhang the Pi in either axis,
                          # so the stack's footprint is just the Pi's 85 x 56.

# --- Interface board (front end), measured by Charles 2026-08-07 ---
iface_len = 50.0          # long axis
iface_wid = 35.0          # short axis
iface_hole_dx = 40.0      # two holes, 5.0 mm in from each END of the 50 mm axis
iface_hole_dy = 0.0       # centred on the 35 mm axis -> both holes on the midline
iface_hole_inset = 5.0    # hole centre to board edge, along the long axis
# Hole diameter was reported as "4 or 5 mm, could not easily measure". Do NOT design
# to that number: use M3 screws, which pass either size, with a washer under the head
# so a 5 mm hole is still properly captured. The case-side boss carries an M3 pilot.
iface_screw = 3.0
iface_washer_od = 9.0     # covers a 5 mm hole with margin

# --- Galvanic Ethernet isolator (inline, RJ45 both ends) ---------------------
# CLAIMED by the Amazon listing (Charles, 2026-08-07): 1.3" L x 2.6" W x 0.9" H
# = 33 x 66 x 23 mm. Listing dimensions are frequently the PACKAGE or rounded, and
# this part is still not in hand, so `iso_allow` below is not decoration -- it is
# what stops a wrong listing from scrapping a 460 g print.
iso_len = 66.0            # 2.6 in
iso_wid = 33.0            # 1.3 in
iso_h = 23.0              # 0.9 in
iso_allow = 10.0          # added to the bay on every side before the retaining ribs
                          # are placed, so a part up to 10 mm over the claim still
                          # drops in. The bay is open, not a pocket, so being wrong
                          # by more than that costs a rib trim, not a reprint.

# Barrel-jack panel bore. PROVISIONAL until panel_coupon.py says which ladder rung
# the real jack passes. Do not print the case on this guess.
barrel_bore_dia = 12.0
barrel_bore_provisional = True

# Ethernet patch cable: shortest Charles has is ~6 in (152 mm) and he does not
# terminate his own. Cat6 minimum bend radius is ~4x OD, so 152 mm is about ONE
# loop -- the case has to swallow slack, not route it tightly.
patch_len = 152.0

# --- Removable barrel-jack plate -------------------------------------------
# The XLR and Ethernet cutouts are D-series and already VALIDATED on a printed
# coupon, so they are cut straight into the case wall. The barrel bore is NOT
# validated, so it does not get to put a 300 g print at risk: it lives on a small
# screw-on plate. Wrong bore -> reprint ~6 g, not the case.
bplate_w = 48.0           # plate footprint. Driven by the screw circle, not chosen:
bplate_h = 48.0           # the holes must clear the opening AND stay inside the edge.
bplate_th = 3.0
bplate_open = 34.0        # square opening in the case wall
bplate_screw_off = 19.5   # M3 clearance holes, all four corners. Must exceed
                          # bplate_open/2 + screw_dia/2 = 18.7, or the screws land in
                          # the middle of the opening with nothing to bite (the plate's
                          # own assert caught exactly that at 17.5).
bplate_screw_dia = 3.4

# --- Interface board mounted ON EDGE (Charles, 2026-08-07) -------------------
# Standing it up frees the whole component row for the isolator -- which is the
# part whose size is still a guess, so that is where the slack belongs.
iface_board_th = 1.6      # perfboard, assumed. The slot is deliberately loose.
iface_slot_extra = 1.4    # slot = board + this. Generous: accepts ~1.4-2.6 mm stock
                          # without a refit, and this is not a precision joint.
iface_edge_depth = 22.0   # X footprint standing up: board + its tallest component

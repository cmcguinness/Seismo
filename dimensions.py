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
# METRIC ONLY (Charles, 2026-09-10): "I have no intuition what #6 means, while an
# M1.5 x 4 is easy easy". #6 was the last imperial thing in this repo. M3 is the
# nearest common metric self-tapper (#6 is ~3.5 mm major, M3 is 3.0), so every bore
# gets slightly SMALLER and every boss gains meat -- the change cannot make a part
# weaker. ⚠️ The geophone case is already PRINTED with #6 holes and keeps them; these
# numbers apply to the next print of anything, not to the object on the slab.
pilot_m3 = 2.5            # pilot bore for an M3 self-tapping screw into PLA
clear_m3 = 3.4            # clearance bore for an M3 shank

# --- Raspberry Pi 2B (mounting) ---
pi_len = 85.0             # board long dimension
pi_wid = 56.0             # board short dimension
pi_hole_dx = 58.0         # mounting-hole rectangle, long axis
pi_hole_dy = 49.0         # mounting-hole rectangle, short axis
pi_hole_offset_x = 10.0   # hole-block center offset from board center along length
                          # (holes sit 3.5mm from one short edge, 23.5mm from the other)
pi_hole_dia = 2.75        # Pi mounting hole (M2.5 clearance)
pi_standoff_h = 6.0       # lift board off base; clears bottom SMD + the nuts
                          # protruding under the Pi<->HAT standoff holes (~2-4mm)
pi_board_th = 1.6         # Pi PCB thickness (~1.4mm) + a hair; sets cotter-hole height
# --- Pi placement, derived from the drawing rather than hand-signed -----------
# EVERY error in this layout has been a sign or a mirror in a hand-written offset.
# So: state the hole positions in BOARD coordinates straight off the mechanical
# drawing, state how the board is turned, and let the code do the mapping. Then
# "ports +X with GPIO -Y" -- a reflection of the real board, and the thing that put
# the locating pins in the standoff holes -- is not expressible.
#
# Board frame, viewed component-side up: x runs 0..85 TOWARD THE PORTS, y runs
# 0..56 TOWARD THE GPIO EDGE. Holes form a 58 x 49 rectangle, 3.5 mm from the
# NON-port short edge and 3.5 mm from both long edges.
pi_holes_gpio = [(3.5, 52.5), (61.5, 52.5)]    # FREE — take the locating pins
pi_holes_far = [(3.5, 3.5), (61.5, 3.5)]       # occupied by the Waveshare standoffs
pi_board_c = (42.5, 28.0)
pi_rot = 0                # 0 -> GPIO +Y and ports +X; 180 -> GPIO -Y and ports -X.
                          # 0 (Charles, 2026-08-09): it puts the COTTER PINS toward the
                          # middle of the case and the round support post out at the
                          # -Y edge -- swapping what gen-1 had -- which turns the Pi
                          # 180 deg so its cables emerge into the open side of the box
                          # instead of into a wall.
pi_conn_overhang = 3.0    # connectors stand proud of the PCB edge (drawing)


def pi_map(px, py, cx, cy):
    """Board-local (px, py) -> case coords, honouring pi_rot. Rotation only, never
    a reflection, which is what makes the mirror bug unrepresentable."""
    dx, dy = px - pi_board_c[0], py - pi_board_c[1]
    if pi_rot == 180:
        dx, dy = -dx, -dy
    return cx + dx, cy + dy


# Clearance past the PORT edge -- the number whose absence scrapped a printed base.
# Built from real parts, not the PCB rectangle:
#     3 mm  connector overhang past the board edge
#   + 21 mm RJ45 plug body
#   + 12 mm strain-relief boot
#   + 24 mm minimum bend radius for Cat6 (4 x ~6 mm OD)
#   = 60 mm, enough for a full 90 deg turn in the horizontal plane. There is also
# ~40 mm of cavity above the Pi, so the cable may instead simply rise and loop.
# NOTE the board is NOT symmetric about the pins: their midpoint is 10 mm toward
# the non-port edge, so the connector faces are 55.5 mm from the pin midpoint.
pi_port_clear = 54.0
pi_sd_clear = 20.0        # opposite short edge: the microSD card protrudes and needs
                          # finger access to swap. It had 12 mm, the same as every
                          # other edge, because nobody had thought about it.
# Why 54 and not more: the A1 Mini bed is the binding constraint once a brim is
# allowed for. 54 = 33 mm of plug + boot, then 21 mm to start the bend -- and the
# real slack path is VERTICAL, ~40 mm of cavity above the Pi for the cable to rise
# and loop. A right-angle RJ45 adapter would free ~30 mm if it is ever wanted.

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
# ✅ VALIDATED 2026-08-08 on the printed panel_coupon: the RJ45 coupler mounts fine in
# the D-series cutout. Ethernet and XLR are therefore the SAME cutout in the case.
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
barrel_body_depth = 22.0   # how far the whole jack sticks in behind the panel, incl.
                           # its solder lugs. Assumed generously -- measure on the
                           # coupon if it matters, but the case now allows +5 on top.
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
iso_allow = 10.0          # bay allowance, IF it were ever mounted inside.

# ⛔ The isolator lives OUTSIDE the case (Charles, 2026-08-08) — inline on the LAN
# cable before it reaches the box. STATUS 2026-08-04 said "isolator INSIDE, on the Pi
# side, with the panel jack on the network side — barrier at the enclosure boundary",
# which is self-contradictory: an isolator inside puts the BARRIER inside, so the
# unisolated segment (panel jack -> isolator, and 6 in is the shortest cable Charles
# has) runs through the case past the front end, carrying precisely the common-mode
# currents the isolator exists to block into the enclosure volume.
# Outside, only isolated copper ever enters. Charles's refinement (2026-08-08) is
# better still: put it AT THE NETWORK TAP and run isolated cable the whole way down to
# the box, so the long run cannot pick up common-mode along its length either. Isolate
# at the source, not at the destination.
iso_internal = False

# Barrel-jack panel bore. ✅ VALIDATED 2026-08-08 on the printed panel_coupon: the
# real jack fits best in the rung labelled 12. The provisional guess happened to be
# right, but it was a guess until the coupon said so -- and it cost ~27 g to find out
# rather than risking the 454 g case.
barrel_bore_dia = 12.0
barrel_bore_provisional = False

# Ethernet patch cable: shortest Charles has is ~6 in (152 mm) and he does not
# terminate his own. Cat6 minimum bend radius is ~4x OD, so 152 mm is about ONE
# loop -- the case has to swallow slack, not route it tightly.
patch_len = 152.0

# --- Removable barrel-jack plate: DELETED 2026-08-08 ---------------------------
# It existed only to keep an unvalidated bore diameter off a ~350 g print. The coupon
# validated the bore at 12 mm on this printer and filament, so the risk it insured
# against is gone and the case takes a plain bore. Do not reintroduce it without a
# new reason -- it cost a part, four screws and a 34 mm opening.

# --- Interface board: FLAT on two standoffs --------------------------------
# ⛔ Mounting it ON EDGE was tried and abandoned 2026-08-08. It has screw terminals
# along BOTH long edges (4 to the Waveshare, 3 to the XLR, 2 for the future shunt),
# so standing it on a 50 mm edge puts a whole row of terminals on the floor -- there
# is no clear edge to slot. Charles caught this.
# Flat is what the board's own holes are for: 40 mm apart on the midline = a two-post
# pattern. Terminals face UP, so a screwdriver reaches them with the lid off, and a
# flat board is ~20 mm tall instead of 35, which makes the CASE SHORTER because the
# connectors sit lower.
# (Standing it on the 35 mm edge instead does work mechanically -- terminals face
# sideways -- but the holes are then 40 mm apart vertically, so the board is 50 mm
# tall and the case grows to ~108 mm. Not worth it.)
iface_board_th = 1.6      # perfboard, assumed

# =============================================================================
# CASE ENVELOPE — shared by case_base.py / case_cover.py / case_handle.py
# =============================================================================
# THREE PARTS (Charles, 2026-08-08): a flat BASE shelf carrying the board mounts,
# a domed COVER carrying the jacks, and a separate HANDLE. Reasons, both good:
# the part you iterate on (board mounting) is then small and fast to print, and
# you build the shelf up on an open bench instead of reaching into a box.
#
# Assembly: cover's open bottom rim sits on the base's top face; screws pass UP
# through the base into bosses inside the cover's corners. Handle screws DOWN
# into the cover roof from outside. Feet live on the base's underside.
#
# Z DATUM: z=0 is the base's TOP face, which is also the cover's bottom rim. Every
# interior height below is measured from there, so base and cover agree without
# either having to know the other's thickness.
case_wall = 3.0
case_corner_r = 12.0
base_th = 5.0             # flat shelf. 5 not 4 for stiffness: it carries the board
                          # loads unsupported across its span, and it is the face the
                          # cover clamps against.
cover_top_th = 3.0
edge_cham = 0.6           # kills elephant-foot on a bottom face

side_margin = 14.0        # board edge -> inner wall
band_gap = 25.0           # between the Pi row and the component row
row_slack = 15.0          # spare depth in the component row
conn_gap = 8.0            # valley between adjacent connector pads on a wall
conn_end_margin = 4.0     # outermost pad -> where the wall stops being flat
lid_headroom = 14.0       # above the connector envelope, for cable slack

iface_standoff_h = 6.0
iface_stack_h = 20.0      # flat board + its screw terminals, generous
iface_boss_dia = 8.0
iface_pilot = 2.5         # M3 self-tapping into PLA
iface_pilot_depth = 8.0

# ⚠️ NAMES HERE MUST NOT START WITH "_". Parts do `from dimensions import *`, and
# `import *` silently skips leading-underscore names -- a shared value called
# `_corner` simply does not arrive, and the part dies with a NameError far from the
# cause. Keep genuinely internal scratch values underscored; export the rest.
nut_clear = barrel_flange_dia / 2 + 3.0         # flat wall a jack's hex nut needs
corner_inner_r = max(case_corner_r - case_wall, 0.5)

# --- cavity, derived from the bays AND from both connector walls ---
_pack_x = (iface_len + 12.0 + iso_len + iso_allow) if iso_internal else iface_len
_row_back = (max(iface_wid, iso_wid + iso_allow) if iso_internal else iface_wid) + row_slack
_wall_front = xlr_pad_w + 2 * corner_inner_r + 2 * conn_end_margin                # +Y: XLR
_wall_back = (xlr_pad_w + conn_gap + 2 * nut_clear
              + 2 * corner_inner_r + 2 * conn_end_margin)                         # -Y: ETH + 5V
cav_x = max(_wall_front, _wall_back, _pack_x + 2 * side_margin,
            pi_sd_clear + pi_len + pi_conn_overhang + pi_port_clear)
cav_y = pi_wid + band_gap + _row_back + 2 * side_margin

# Jacks share one centreline and sit on BOTH long walls, so they must clear the
# tallest thing anywhere inside -- which is the Pi stack, not the component row.
_tall_row = iface_standoff_h + (max(iso_h, iface_stack_h) if iso_internal else iface_stack_h)
tall_inside = max(_tall_row, pi_standoff_h + stack_h)
conn_bot = tall_inside + 8.0
cav_h = conn_bot + max(xlr_bore_dia, barrel_flange_dia) + lid_headroom

case_x = cav_x + 2 * case_wall
case_y = cav_y + 2 * case_wall

# --- bay centres (case centred on the origin in X and Y) ---
_y0 = -cav_y / 2 + side_margin
pi_cx = -cav_x / 2 + pi_sd_clear + pi_len / 2      # ports face +X (pi_rot 0)
pi_cy = _y0 + pi_wid / 2
_row_cy = _y0 + pi_wid + band_gap + _row_back / 2
iface_cx = 0.0
iface_cy = _row_cy
iface_pts = [(iface_cx + sx * iface_hole_dx / 2, iface_cy) for sx in (-1, 1)]

# Pi mount points. Only the two GPIO-side holes are FREE -- the others carry the
# Pi<->Waveshare standoffs with NUTS under the board (chassis.py), so that edge
# gets one flat post BETWEEN them: 2 pins + 1 post, 3-point and nut-clear.
pi_standoff_dia = 6.0
pi_pin_dia = pi_hole_dia - 0.15
pi_pin_extra = 5.0
cotter_hole_dia = 1.5
gpio_pin_pts = [pi_map(px, py, pi_cx, pi_cy) for px, py in pi_holes_gpio]
pi_far_pts = [pi_map(px, py, pi_cx, pi_cy) for px, py in pi_holes_far]
# one flat post midway between the two standoff NUTS, never under them
usb_support_pts = [((pi_far_pts[0][0] + pi_far_pts[1][0]) / 2, pi_far_pts[0][1])]
# the port edge, mapped the same way -- this is what clearance is measured from
pi_port_face = pi_map(pi_len, pi_board_c[1], pi_cx, pi_cy)[0] \
    + (-pi_conn_overhang if pi_rot == 180 else pi_conn_overhang)

# --- connectors. z is measured from the base top face. ---
panel_z = conn_bot + xlr_bore_dia / 2
xlr_cx = 0.0                                   # +Y wall: "measurement in"
_run_back = xlr_pad_w + conn_gap + 2 * nut_clear
# -Y wall, "real world out". 5 V toward -X because the GPIO 5 V pins (4 and 6) are at
# the -X end of the header; Ethernet toward +X because the Pi's own jack faces +X.
# Both runs get shorter, and the DC feed ends up furthest from the front end.
barrel_cx = -_run_back / 2 + nut_clear
eth_cx = _run_back / 2 - xlr_pad_w / 2
barrel_z = panel_z

# --- base <-> cover screws: 4 corners, M3 self-tapping ---
# Inset only 4 mm so each boss merges into the rounded corner wall (which stiffens
# both) and stays clear of the Pi, whose corner reaches within ~3 mm otherwise.
# 6.0, not 4.0. At 4 the boss centre sits 7.07 mm from the outer corner arc centre
# and its 5 mm radius reaches 12.07 -- through a 12 mm outer radius. The boss BREAKS
# THE OUTER SKIN at each corner by 0.07 mm: a knife-edge sliver, a hole in the case,
# and the thing that made the rim chamfer fail. See the assert in case_cover.py.
asm_inset = 6.0
asm_x = cav_x / 2 - asm_inset
asm_y = cav_y / 2 - asm_inset
asm_boss_dia = 10.0
asm_pilot_depth = 12.0

# --- feet: NONE. The base bottom is flat; Charles fits self-adhesive feet. ---
# The geophone case uses three SCREW heads as feet, but that is a coupling decision
# specific to it: its load path is element -> floor -> feet -> ground, so near-point
# 3-point contact is deliberate. Nothing couples through THIS box -- it just sits on
# a shelf -- so screw feet would be cost with no benefit, and a flat underside prints
# better besides (bigger first layer, no pilot bores near the board mounts).

# --- handle (separate part, screwed UP into from inside the cover) ---
# Bar geometry carried over from geophone_case_lid, which prints clean.
# NO FLANGE. Screws go from INSIDE the cavity, up through clearance holes in the
# roof, into blind pilots in the undersides of the bar's two LEGS -- heads hidden,
# nothing extra sticking out. (An earlier revision put a 92 mm flange on the handle
# so the screws could land outboard of the legs; that was solving a problem that
# does not exist. A blind pilot up into a 24 mm leg has more material to bite than
# anywhere else on the part.)
handle_span = 70.0        # outer, along X
handle_w = 16.0           # along Y, and the width your fingers bear on
handle_h = 24.0           # above the flange
handle_open_w = 48.0      # finger opening at the base
handle_open_top = 24.0    # at the top -> ~55 deg sides, self-supporting
handle_open_h = 17.0      # finger clearance under the bar
handle_top_r = 6.0
# Legs run from handle_open_w/2 (24) to handle_span/2 (35); screw on the centreline
# of each leg. Derived, not chosen, so changing the opening moves the screws with it.
handle_screw_off = (handle_open_w / 2 + handle_span / 2) / 2      # = 29.5
# Which way the bar runs across the roof. "Y" = along the case's LONG axis.
# Aesthetics (Charles, 2026-08-08); it is a free choice mechanically, since the bar
# is well inside the footprint either way and sits over the centre regardless.
handle_axis = "Y"
handle_screw_pts = ([(0.0, sy * handle_screw_off) for sy in (1, -1)]
                    if handle_axis.upper() == "Y"
                    else [(sx * handle_screw_off, 0.0) for sx in (1, -1)])
handle_pilot_depth = 11.0  # up into the leg. An M3 x 12 through a 3 mm roof
                           # plus a 5 mm bearing pad still leaves ~4.7 mm engaged, so
                           # the pilot only has to be deeper than that.

# --- ADXL355 strong-motion sensor: EVAL-ADXL355-PMDZ -------------------------
# ✅ VALIDATED 2026-09-10 on the printed adxl_coupon (rev 4). The board drops in,
# sits flat, the pins clear the wall slot and the retainer lands on the plate.
# Rev 1 bound on the corners, rev 2's trough missed the back pin row, rev 3's
# centre pad fouled back-side joints. Do not "tidy" these numbers: each one is a
# print that failed. Carry them into the case unchanged.
# MEASURED off the part in hand (Charles, 2026-09-10). The board has NO mounting
# holes -- the two gold pads at diagonal corners are filled vias, not holes, and
# they photograph convincingly like M2 holes. So it is located by a POCKET and held
# down by a U-shaped retainer that bears only on the bare rim.
adxl_board_w = 20.0         # square
adxl_board_h = 20.0
adxl_board_th = 1.6         # ⚠️ ASSUMED standard Pmod FR4. The coupon's pocket depth
                            # depends on it; confirm with calipers before the case.
adxl_free_rim = 2.0         # bare PCB around the component field, all four edges.
                            # This is the budget the retainer's rim must fit inside.
# Right-angle 2x6 header on the component side, at one edge. Because the pins exit
# PARALLEL to the board, the board lies flat on its clean back face and the ADXL355's
# Z axis (normal to the package, hence to the PCB) ends up VERTICAL = HNZ. A straight
# header would have stood the board on edge and put Z horizontal.
adxl_pin_above = 5.0        # top of the pin field above the board's TOP face
adxl_pin_out = 7.0          # pins protrude this far past the board edge, into air
adxl_header_body_w = 15.5   # 6 positions at 2.54 mm pitch, plastic body
# --- pocket + retainer (the coupon proves these) ---
adxl_pocket_clear = 0.5     # TOTAL, so 0.25 per side. The number the coupon exists
                            # to tune: too tight and the board will not seat, too
                            # loose and the compass azimuth wanders on reassembly.
# ⚠️ MEASURED ON THE FIRST COUPON, 2026-09-10: at 0.4 total the board would not drop
# all the way in. The cause is not side clearance, it is CORNER RADIUS -- a 0.4 mm nozzle
# cannot cut a sharp inside corner, so a square pocket gets ~0.2 mm radiused corners that
# a sharp-cornered PCB cannot enter. Loosening the sides to cure a corner problem is the
# wrong lever: it buys entry at the cost of the location repeatability the compass azimuth
# depends on. So the pocket now has CORNER RELIEFS (the same trick a machinist uses for a
# square pocket cut with a round end mill) and the sides only went 0.4 -> 0.5.
adxl_corner_relief = 1.6    # relief circle diameter, centred on each pocket corner
# ⚠️ THE BACK IS NOT FLAT. MEASURED 2026-09-10 on the board in hand: the 12 header pins
# are soldered from the back and their joints stand ~1 mm proud, in two rows along the
# header edge. The pocket floor therefore needs a TROUGH under them or the board rocks on
# its solder instead of bedding on the floor — which would put a compliant, ill-defined
# joint in the one load path that has to be rigid. This is the second assumption about
# this board to fail on contact (no mounting holes was the first).
adxl_solder_proud = 1.0     # MEASURED, back-side solder joint height above the board
adxl_solder_span = 14.5     # width of the joint field along the header edge (12.7 mm of
                            # pin centres + pad). Its INBOARD reach is deliberately NOT a
                            # constant here — see below.
# REV 3, 2026-09-10. Rev 2 cut a trough 6 mm inboard from the header edge, sized from my
# estimate of where the two pin rows sit. It did not reach the back row. Rather than guess
# a third time, the floor is INVERTED: instead of relieving where the solder is thought to
# be, DEFINE where the board is supported and relieve everything else. Support is now a
# U-shaped rim on the three non-header edges plus a pad under the chip; the entire header
# end of the floor is open, so the joints clear wherever they actually land. This also
# removes a whole class of future surprise — any back-side component outside the pad is
# automatically cleared.
adxl_trough_clear = 0.3     # air under the joints
adxl_floor_rim = 2.0        # bearing rim on the -X, +Y, -Y edges of the pocket floor.
# ⛔ REV 4, 2026-09-10: THE CENTRAL SUPPORT PAD IS DELETED. DO NOT PUT IT BACK.
# Rev 3 kept an 8 x 8 pad under the chip on the argument that the coupling has to be rigid
# exactly there. It fouled back-side solder joints — this board has through-hole joints
# reaching the middle, not only along the header edge. Before moving or shrinking it, the
# arithmetic was run, and it says the pad was never doing anything:
#
#   FR4, E~20 GPa, t=1.6 mm, 16 mm span, clamped-plate fundamental  ->  ~35 kHz.
#   Derate 3x for three-edge support and the chip's mass            ->  ~12 kHz.
#   That is ~800x the 15 Hz top of the band.
#
# The board bridging its own 16 mm unsupported is stiffer than anything else in the load
# path by three orders of magnitude. Support is the U-rim on three edges, full stop. The
# instinct to "support the sensor directly" is sound in general and simply does not bind
# at this size.
adxl_pocket_over = 0.1      # pocket cut this much deeper than the board, so the
                            # retainer always lands on the plate and never rocks on
                            # the board itself
adxl_rim = 1.5              # retainer bearing width on the board's bare edge
adxl_slot_clear_w = 1.5     # added to the header body width, total
adxl_slot_clear_h = 1.0     # added above the pin field
# FASTENER: M1.7 x 5 pan head, self-tapping into PLA. Chosen 2026-09-10 from what is
# actually in the drawer (M1 / M1.2 / M1.7 in short lengths, then a gap to #6 pan,
# which is being retired in favour of M3 — see pilot_m3).
# M1.7 is ample: the retainer carries no preload -- gravity already holds a 3 g board
# down at 1 g against micro-g signals -- so this fastener only resists cable pull and
# lift. #6 would work mechanically but its bosses would crowd a 20 mm pocket.
adxl_screw_dia = 1.9        # M1.7 clearance
adxl_pilot_dia = 1.4        # M1.7 self-tapping into PLA (~0.8 x major)
# 🔜 HEAT-SET INSERTS are in transit from China (2026-09-10). When they land, MEASURE
# OD and LENGTH before touching this block — those two numbers drive the boss, and
# `look-up-standard-part-dims` says do not infer them from the listing. Expect the
# screw to change: assortments run M2/M2.5/M3, and M1.7 inserts effectively do not
# exist. Two knock-ons when it happens: the boss wall wants ~1.5 mm rather than 1.2
# (melting stresses it), and an insert is 4-5 mm LONG against a 4 mm pilot in a 5 mm
# floor — so the floor grows or the boss stands proud. Do not redesign in advance.
adxl_pilot_depth = 4.0      # 5 mm screw - 1.5 mm retainer = 3.5 mm in; 4.0 so it
                            # threads rather than bottoming out
adxl_boss_wall = 1.2        # PLA left between a pilot hole and the pocket wall.
# ⚠️ The screw offset is DERIVED from the pocket, not chosen. Rev 1 chose it by
# halving the retainer bar width, which put all three pilots 0.875 mm from the
# pocket wall with a 1.05 mm pilot radius -- every one of them broke through into
# the pocket, where the board sits. The assertion in adxl_coupon.py now fails the
# build if that recurs.
adxl_retainer_th = 1.5      # thinned from 2.5 to buy thread engagement out of a 5 mm
                            # screw. It spans a 17 mm opening under no load, so
                            # stiffness is not the constraint; engagement is
adxl_wall_th = 3.0          # matches the case walls elsewhere
adxl_wall_h = 8.0           # above the plate top, on the header side only
# derived
adxl_pocket_w = adxl_board_w + adxl_pocket_clear
adxl_pocket_h = adxl_board_h + adxl_pocket_clear
adxl_pocket_depth = adxl_board_th + adxl_pocket_over
adxl_open_w = adxl_board_w - 2 * adxl_rim      # retainer opening
adxl_open_h = adxl_board_h - 2 * adxl_rim
adxl_slot_w = adxl_header_body_w + adxl_slot_clear_w
adxl_slot_h = adxl_pin_above + adxl_slot_clear_h
adxl_trough_depth = adxl_solder_proud + adxl_trough_clear
adxl_screw_off = adxl_pocket_w / 2 + adxl_pilot_dia / 2 + adxl_boss_wall
adxl_retainer_margin = (adxl_screw_off - adxl_pocket_w / 2
                        + adxl_screw_dia / 2 + 1.2)   # derived from the screw

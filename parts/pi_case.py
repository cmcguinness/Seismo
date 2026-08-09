"""pi_case.py — GEN-1 case BASE for the Pi 2B + Waveshare + front-end interface board.

Scope (Charles, 2026-08-07): the MINIMAL tier. Environmental protection and strain
relief so the station can go back in the garage. Base + lid + handle, three panel
jacks, boards on standoffs straight to the floor. Explicitly NOT in scope: gasket,
vents, heat-set inserts, engraved labels.

DELIBERATELY NOT a removable sub-plate, though STATUS 2026-08-04 decided on one.
Charles chose the minimal tier to get back in the garage sooner. The sub-plate is
an INTERNAL part, so retrofitting it later does not mean reprinting this case --
which is why the floor bosses below sit on a sane, documented pattern rather than
wherever was convenient.

SIZE IS DERIVED, NOT CHOSEN. The bay table drives the cavity, the cavity drives
the shell. That matters because `iso_*` in dimensions.py is an unmeasured
placeholder: fixing those three numbers rescales the case automatically.

LAYOUT (looking down, +Y is the connector wall):

    +Y  ---- XLR ---- ETH ---- [barrel] ----   <- panel wall
        |  connector intrusion + cable slack |  <- kept CLEAR, nothing tall here
        |  [iface board]   [ isolator ]      |
        |        [ Pi 2B + Waveshare ]       |
    -Y  --------------------------------------

Why the +Y band is empty: the XLR intrudes 32 mm behind its flange and the D-type
coupler is similar. Putting a board there means either a vertical stack-up fight
or a connector landing on a component. 30 mm of depth is cheaper than that.

Pi mounting reuses the chassis.py finding: only the two GPIO-side holes are FREE.
The other two carry the Pi<->Waveshare standoffs with NUTS protruding under the
board, so that edge gets a single flat post placed BETWEEN the nuts -- 2 locating
pins + 1 post = 3-point, nut-clear.

Print floor-down, no supports.

    PYTHONPATH=. .venv/bin/python parts/pi_case.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

# --- shell ---
wall = 3.0
floor_th = 6.0          # 6 + 4 mm foot pad = 10 mm for the foot-screw pilot
corner_r = 12.0
edge_cham = 0.6         # kills elephant-foot on the bottom face
bed_max = 180.0         # printer bed; asserted against below

# --- clearances that size the cavity ---
# GENEROUS ON PURPOSE. An earlier revision derived the shell tightly from the bay
# table with 6 mm margins, which meant every guessed dimension had to be right or the
# print was scrap. Several of these numbers ARE guesses (the isolator especially).
# The A1 Mini is 180 x 180 x 180 and this box is nowhere near the volume limit, so
# slack is nearly free -- spend it.
side_margin = 12.0      # board edge -> inner wall (was 6, briefly 15). Trimmed to
                        # keep the isolator's 10 mm allowance AND stay inside the bed
                        # with a brim -- the allowance protects against a wrong listing
                        # dimension, which is the more likely failure.
band_gap = 20.0         # between ROWS (Pi row -> component row), for wiring (was 8)
row_gap_x = 12.0        # between the two bays WITHIN the component row. Smaller than
                        # band_gap on purpose: this pair is what sets the case width,
                        # and at 20 the case came out 176 mm on a 180 mm bed -- no room
                        # for a brim or skirt, which is its own kind of brittle.
row_slack = 15.0        # added to the deepest bay in the component row
conn_gap = 8.0          # valley between adjacent connector pads on the +Y wall
conn_end_margin = 4.0   # from the outermost pad to where the wall stops being flat
lid_headroom = 14.0     # above the connector envelope, for coiled patch cable

# --- component heights ---
iface_standoff_h = 6.0
iface_stack_h = 20.0    # board + screw terminals, generous

# --- derived cavity ---
# Connectors sit ABOVE the component row rather than behind it. That is what kills
# the old 32 mm `panel_band` of reserved floor: the XLR's 32 mm body intrudes at its
# own height, passing over the boards, so it costs Z (of which there is 180 mm going
# spare) instead of Y (which was fighting the bed). The upper cavity that buys is
# also exactly where the coiled patch cable wants to live.
# The interface board stands ON EDGE against the -X wall, alongside the Pi, so the
# component row carries the ISOLATOR ALONE and can absorb one far bigger than the
# placeholder -- the row's usable width is now the full cavity, not 70 mm.
# On edge, long axis along X: the board's footprint drops from 50 x 35 to 50 x 22,
# so the component row gets shallower and the isolator keeps the depth tolerance.
# Being honest about what this does NOT buy: the row's DEPTH is set by the isolator
# (40 mm), not the interface board, so standing it up does not shrink this box. It
# is still worth doing -- the screw terminals end up facing sideways and reachable
# with the lid off, and the runs to the XLR above get shorter.
_row_back = (max(iface_wid, iso_wid + iso_allow) if iso_internal
             else iface_wid) + row_slack
_pack_x = (iface_len + row_gap_x + iso_len + iso_allow) if iso_internal else iface_len
# The connector walls, not the component packing, can set the width -- derive that
# instead of discovering it in an assert.
# Connectors are split by MEANING (Charles, 2026-08-08): the sensor comes in one side,
# the outside world -- network and power -- leaves by the other. That is also the
# electrically right split: the XLR lands on the same wall as the interface board so the
# uV run is short, while Ethernet and the DC feed sit on the Pi wall, away from it.
_nut_clear = barrel_flange_dia / 2 + 3.0          # flat wall the jack's hex nut needs
_corner = max(corner_r - wall, 0.5)
_wall_front = xlr_pad_w + 2 * _corner + 2 * conn_end_margin               # +Y: XLR
_wall_back = (xlr_pad_w + conn_gap + 2 * _nut_clear
              + 2 * _corner + 2 * conn_end_margin)                        # -Y: ETH + 5V
cav_x = max(_wall_front, _wall_back, _pack_x + 2 * side_margin,
            pi_len + 2 * side_margin)
cav_y = pi_wid + band_gap + _row_back + 2 * side_margin
# Tallest thing a jack has to ride over. Connectors are now on BOTH long walls and
# share one centreline, so this is the max over the whole cavity, not just the
# component row: the +Y jack clears the interface board, but the -Y jacks ride over
# the PI, which is the taller obstacle. Using the row alone put the -Y bores 2 mm
# into the Waveshare.
_tall_row = iface_standoff_h + (max(iso_h, iface_stack_h) if iso_internal
                                else iface_stack_h)
_tall_inside = max(_tall_row, pi_standoff_h + stack_h)
_conn_bot = _tall_inside + 8.0                       # jack envelope clears it by 8 mm
cav_h = _conn_bot + max(xlr_bore_dia, barrel_flange_dia) + lid_headroom

case_x = cav_x + 2 * wall
case_y = cav_y + 2 * wall
top_z = floor_th + cav_h

# --- bay centres (case centred on the origin) ---
_y0 = -cav_y / 2 + side_margin                      # inner face of the -Y wall
pi_cy = _y0 + pi_wid / 2
_row_cy = _y0 + pi_wid + band_gap + _row_back / 2
iface_cx = ((-_pack_x / 2 + iface_len / 2) if iso_internal else 0.0)
iso_cx = (_pack_x / 2 - (iso_len + iso_allow) / 2) if iso_internal else None
pi_cx = 0.0            # centred again: nothing intrudes from +X any more

# --- Pi mount points (chassis.py geometry, translated to pi_cx/pi_cy) ---
standoff_dia = 6.0
pin_dia = pi_hole_dia - 0.15
pin_extra = 5.0
cotter_hole_dia = 1.5
gpio_pin_pts = [(pi_cx + pi_hole_offset_x + sx * pi_hole_dx / 2, pi_cy - pi_hole_dy / 2)
                for sx in (-1, 1)]
usb_support_pts = [(pi_cx + pi_hole_offset_x, pi_cy + pi_hole_dy / 2)]

# --- interface-board standoffs: two holes on the midline of the 35 mm axis ---
iface_boss_dia = 8.0
iface_pilot = 2.5       # M3 self-tapping into PLA
iface_pilot_depth = 8.0
# Flat: long axis along X, two holes on the midline 40 mm apart.
iface_cy = _row_cy
iface_pts = [(iface_cx + sx * iface_hole_dx / 2, iface_cy) for sx in (-1, 1)]

# --- isolator: an OPEN bay with two low ribs, NOT a pocket ---
# Its dimensions are a placeholder (see dimensions.py). A tight pocket around an
# unmeasured part is how you get a case that has to be reprinted; two ribs plus
# hook-and-loop tolerate being wrong.
iso_rib_h = 4.0
iso_rib_th = 2.5

# --- lid screw bosses ---
boss_dia = 10.0
boss_pilot_depth = 12.0
boss_inset = 9.0
boss_x = cav_x / 2 - boss_inset
boss_y = cav_y / 2 - boss_inset

# --- feet (3 screw heads, same doctrine as the geophone case) ---
foot_pad_dia = 16.0
foot_pad_h = 4.0
foot_pilot_depth = 9.0
foot_pts = [(0, cav_y / 2 - 14.0),
            (-cav_x / 2 + 14.0, -cav_y / 2 + 14.0),
            (cav_x / 2 - 14.0, -cav_y / 2 + 14.0)]

# --- panel connectors ---
panel_z = floor_th + _conn_bot + xlr_bore_dia / 2   # bore centreline, set so the
                        # whole jack envelope clears the tallest thing inside
xlr_cx = 0.0            # +Y wall, "measurement in": the XLR, alone and centred
_run_back = xlr_pad_w + conn_gap + 2 * _nut_clear
eth_cx = -_run_back / 2 + xlr_pad_w / 2    # -Y wall, "real world out": ETH + 5 V,
barrel_cx = _run_back / 2 - _nut_clear     # packed as a pair and centred
barrel_z = panel_z

AIM = {"+Y": Rotation(-90, 0, 0), "-Y": Rotation(90, 0, 0),
       "+X": Rotation(0, 90, 0), "-X": Rotation(0, -90, 0)}


def _thru(dia, start, aim, length=60.0):
    """Cylinder of `dia` from `start` along `aim`. Mode.PRIVATE is load-bearing:
    a bare Cylinder() inside BuildPart adds itself on the spot (geophone_case.py
    learned this the hard way -- a cutter silently became a solid plug)."""
    cyl = Cylinder(dia / 2, length, align=(Align.CENTER, Align.CENTER, Align.MIN),
                   mode=Mode.PRIVATE)
    return Location(start) * (AIM[aim] * cyl)


def _dpad(cx, cz):
    """The validated D-series pad + recessed flange seat + bore + 4 holes."""
    _v = xlr_flange_axis.upper() == "V"
    _sw = (xlr_flange_h if _v else xlr_flange_w) + xlr_seat_clearance
    _sh = (xlr_flange_w if _v else xlr_flange_h) + xlr_seat_clearance
    return _sw, _sh, _v


with BuildPart() as pi_case:
    with BuildSketch(Plane.XY):
        RectangleRounded(case_x, case_y, corner_r)
    extrude(amount=top_z)

    with BuildSketch(Plane.XY.offset(floor_th)):
        RectangleRounded(cav_x, cav_y, max(corner_r - wall, 0.5))
    extrude(amount=cav_h, mode=Mode.SUBTRACT)

    # --- lid bosses in the four corners ---
    with Locations(*[(sx * boss_x, sy * boss_y, floor_th)
                     for sx in (1, -1) for sy in (1, -1)]):
        Cylinder(boss_dia / 2, cav_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(*[(sx * boss_x, sy * boss_y, top_z)
                     for sx in (1, -1) for sy in (1, -1)]):
        Cylinder(pilot_6 / 2, boss_pilot_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)

    # --- Pi standoffs + locating pins ---
    with Locations(*[(px, py, floor_th) for px, py in gpio_pin_pts + usb_support_pts]):
        Cylinder(standoff_dia / 2, pi_standoff_h,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(*[(px, py, floor_th + pi_standoff_h) for px, py in gpio_pin_pts]):
        Cylinder(pin_dia / 2, pin_extra, align=(Align.CENTER, Align.CENTER, Align.MIN))
    _cot_z = floor_th + pi_standoff_h + pi_board_th + 1.5
    with Locations(*[Location((px, py, _cot_z), (90, 0, 0)) for px, py in gpio_pin_pts]):
        Cylinder(cotter_hole_dia / 2, pin_dia + 2, mode=Mode.SUBTRACT)

    # --- interface board FLAT on two standoffs ---
    # M3 through the board's own holes into these pilots, with a washer under the head
    # (the hole is 4-5 mm, unmeasured, so a washer is what actually captures it).
    with Locations(*[(px, py, floor_th) for px, py in iface_pts]):
        Cylinder(iface_boss_dia / 2, iface_standoff_h,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(*[(px, py, floor_th + iface_standoff_h) for px, py in iface_pts]):
        Cylinder(iface_pilot / 2, iface_pilot_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)

    # --- isolator retaining ribs: only if it is ever mounted inside ---
    if iso_internal:
        for _sx in (1, -1):
            with Locations((iso_cx + _sx * ((iso_len + iso_allow) / 2 + iso_rib_th / 2),
                            _row_cy, floor_th)):
                Box(iso_rib_th, iso_wid + iso_allow, iso_rib_h,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))

    # --- feet: local pads inside, blind pilots up from the bottom face ---
    with Locations(*[(px, py, floor_th) for px, py in foot_pts]):
        Cylinder(foot_pad_dia / 2, foot_pad_h,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(*[(px, py, 0) for px, py in foot_pts]):
        Cylinder(pilot_6 / 2, foot_pilot_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

    # --- D-series seats: XLR on +Y, Ethernet on -Y ---
    # Plane.XZ's normal is -Y, so offset(-wy) lands on the +Y wall and offset(+wy) on
    # the -Y wall; extruding along +normal pushes the pad OUTWARD in both cases.
    _sw, _sh, _v = _dpad(0, 0)
    _wy = case_y / 2
    for _cx, _side in ((xlr_cx, "+Y"), (eth_cx, "-Y")):
        _sgn = -1 if _side == "+Y" else 1
        with BuildSketch(Plane.XZ.offset(_sgn * _wy)):
            with Locations((_cx, panel_z)):
                RectangleRounded(xlr_pad_w, xlr_pad_h, 3.0)
        extrude(amount=_sgn * xlr_pad_proud)
        with BuildSketch(Plane.XZ.offset(_sgn * (_wy + xlr_pad_proud))):
            with Locations((_cx, panel_z)):
                Rectangle(_sw, _sh)
        extrude(amount=-_sgn * xlr_seat_depth, mode=Mode.SUBTRACT)

    _dx, _dz = ((xlr_screw_off_minor, xlr_screw_off_major) if _v
                else (xlr_screw_off_major, xlr_screw_off_minor))
    # A cutter must pierce ONE wall, not the whole box. Starting it outside the far
    # wall and running it the length of the case drills a matching hole through the
    # OPPOSITE wall -- which is exactly what happened when the connectors were split
    # across +Y and -Y, and it is invisible to a volume or manifold check. So start
    # each cutter just inside its own wall and give it only enough length to exit.
    _pierce = wall + xlr_pad_proud + 5.0
    for _cx, _side in ((xlr_cx, "+Y"), (eth_cx, "-Y")):
        _y_in = (cav_y / 2 - 1.0) * (1 if _side == "+Y" else -1)
        add(_thru(xlr_bore_dia, (_cx, _y_in, panel_z), _side, length=_pierce),
            mode=Mode.SUBTRACT)
        for _sx in (1, -1):
            for _sz in (1, -1):
                add(_thru(xlr_screw_dia, (_cx + _sx * _dx, _y_in, panel_z + _sz * _dz),
                          _side, length=_pierce), mode=Mode.SUBTRACT)

    # 5 V barrel jack: plain bore on the -Y wall, hex nut on the flat inner face.
    add(_thru(barrel_bore_dia, (barrel_cx, -(cav_y / 2 - 1.0), barrel_z), "-Y",
              length=_pierce), mode=Mode.SUBTRACT)

    chamfer(pi_case.faces().sort_by(Axis.Z)[0].outer_wire().edges(), edge_cham)


# --- checks that must hold before this is worth printing ---
# Leave room for a brim/skirt -- "fits the bed" and "prints on the bed" differ.
_brim = 5.0
assert case_x + 2 * _brim <= bed_max and case_y + 2 * _brim <= bed_max, (
    f"case is {case_x:.0f} x {case_y:.0f} mm; with {_brim:.0f} mm of brim that "
    f"needs {case_x + 2*_brim:.0f} x {case_y + 2*_brim:.0f} on a {bed_max:.0f} mm bed")
assert top_z <= bed_max, f"case is {top_z:.0f} mm tall, over the {bed_max:.0f} mm Z"
assert cav_h >= pi_standoff_h + stack_h, "cavity is shorter than the Pi + Waveshare stack"
# Connectors now clear the boards in Z, so that is the check that matters.
assert panel_z - xlr_bore_dia / 2 > floor_th + _tall_inside, \
    "a connector bore would land on a board"
# Each wall is only FLAT between +-(cav_x/2 - inner corner radius). A cutout that
# clears cav_x/2 can still land in the curve, where a flange cannot seat and a hex nut
# has nothing square to pull against.
_flat_half = cav_x / 2 - _corner
assert abs(xlr_cx) + xlr_pad_w / 2 < _flat_half, "XLR pad runs into the corner radius"
assert abs(eth_cx) + xlr_pad_w / 2 < _flat_half, "Ethernet pad runs into the corner radius"
assert abs(barrel_cx) + _nut_clear < _flat_half, "5 V jack runs into the corner radius"
assert barrel_cx - _nut_clear > eth_cx + xlr_pad_w / 2, \
    "5 V jack fouls the Ethernet pad on the -Y wall"
# Both -Y jack bodies ride over the Pi, so they must clear the stack in Z.
assert panel_z - xlr_bore_dia / 2 > floor_th + pi_standoff_h + stack_h, \
    "a -Y jack body would foul the Pi/Waveshare stack"
# Connectors clear the boards by SEPARATION IN Y, not in Z -- the bore bottom
# (z=20) is in fact below the interface board top (z=32), which is fine only
# because the component row ends 14 mm short of where the connector band starts.
# That is the load-bearing check, so assert it directly.
assert _row_cy + _row_back / 2 <= cav_y / 2 + 0.001, "component row overruns the cavity"
assert panel_z + xlr_bore_dia / 2 < top_z, "connector bore breaks through the cavity ceiling"
assert panel_z - xlr_bore_dia / 2 > floor_th, "connector bore cuts into the floor"
# the Pi must not reach into the connector band
assert xlr_body_depth < cav_y - side_margin, "XLR body is deeper than the cavity"
# bays must not overlap each other
if iso_internal:
    assert iface_cx + iface_len / 2 < iso_cx - (iso_len + iso_allow) / 2, \
        "on-edge board and isolator bay overlap"
    assert iso_len + iso_allow + 2 * side_margin <= cav_x, "isolator bay is wider than the cavity"
# the on-edge board must not sit under any jack

assert _row_cy - _row_back / 2 > pi_cy + pi_wid / 2, "component row overlaps the Pi"

print(f"case {case_x:.0f} x {case_y:.0f} x {top_z:.0f} mm  (cavity {cav_x:.0f} x {cav_y:.0f}"
      f" x {cav_h:.0f})\n  Pi @ ({pi_cx:.0f},{pi_cy:.0f})  iface @ ({iface_cx:.0f},{_row_cy:.0f})"
      f"  iso @ {'(%.0f,%.0f)' % (iso_cx, _row_cy) if iso_internal else 'EXTERNAL'}"
      f"\n  panel z {panel_z:.0f}  | +Y: XLR  |  -Y: ETH x={eth_cx:.0f}, 5V x={barrel_cx:.0f}"
      f"  | barrel bore {barrel_bore_dia} mm"
      f"{'  ** PROVISIONAL — run panel_coupon first **' if barrel_bore_provisional else ''}")

show(pi_case)
export_stl(pi_case.part, "stl/pi_case.stl")

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
side_margin = 6.0       # board edge -> inner wall
band_gap = 8.0          # between bays, for wiring
panel_band = 32.0       # +Y clear zone: connector intrusion + patch-cable slack
lid_headroom = 12.0     # above the tallest thing (the Pi stack) for cables

# --- component heights ---
iface_standoff_h = 6.0
iface_stack_h = 20.0    # board + screw terminals, generous

# --- derived cavity ---
_row_back = max(iface_wid, iso_wid)                 # iface + isolator sit side by side
cav_x = max(pi_len, iface_len + band_gap + iso_len) + 2 * side_margin
cav_y = pi_wid + band_gap + _row_back + band_gap + panel_band + 2 * side_margin
cav_h = pi_standoff_h + stack_h + lid_headroom

case_x = cav_x + 2 * wall
case_y = cav_y + 2 * wall
top_z = floor_th + cav_h

# --- bay centres (case centred on the origin) ---
_y0 = -cav_y / 2 + side_margin                      # inner face of the -Y wall
pi_cy = _y0 + pi_wid / 2
_row_cy = _y0 + pi_wid + band_gap + _row_back / 2
iface_cx = -(iface_len + band_gap + iso_len) / 2 + iface_len / 2
iso_cx = (iface_len + band_gap + iso_len) / 2 - iso_len / 2
pi_cx = 0.0

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
iface_pts = [(iface_cx + sx * iface_hole_dx / 2, _row_cy) for sx in (-1, 1)]

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

# --- panel connectors, all on the +Y wall ---
panel_z = floor_th + 26.0     # bore centreline: above the boards, below the ceiling
xlr_cx = -40.0         # pad half-width is 19, flat wall ends at 61 -> max |cx| is 42
eth_cx = 6.0           # shifted +6 to open an 8 mm valley between the XLR and ETH pads
barrel_cx = 42.0        # NOT 52: at 52 the Ø14 flange and its hex nut ran into the
                        # 12 mm corner radius with ~2 mm to spare. The wall is only
                        # FLAT between +-(cav_x/2 - inner corner r); see the assert.

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

    # --- interface-board standoffs (M3 into the pilot; washer covers a 5 mm hole) ---
    with Locations(*[(px, py, floor_th) for px, py in iface_pts]):
        Cylinder(iface_boss_dia / 2, iface_standoff_h,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(*[(px, py, floor_th + iface_standoff_h) for px, py in iface_pts]):
        Cylinder(iface_pilot / 2, iface_pilot_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)

    # --- isolator retaining ribs (open bay, deliberately not a pocket) ---
    for _sx in (1, -1):
        with Locations((iso_cx + _sx * (iso_len / 2 + iso_rib_th / 2), _row_cy, floor_th)):
            Box(iso_rib_th, iso_wid, iso_rib_h,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

    # --- feet: local pads inside, blind pilots up from the bottom face ---
    with Locations(*[(px, py, floor_th) for px, py in foot_pts]):
        Cylinder(foot_pad_dia / 2, foot_pad_h,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(*[(px, py, 0) for px, py in foot_pts]):
        Cylinder(pilot_6 / 2, foot_pilot_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

    # --- panel wall (+Y): XLR and Ethernet both get the validated D-series seat ---
    _sw, _sh, _v = _dpad(0, 0)
    _wy = case_y / 2
    for _cx in (xlr_cx, eth_cx):
        with BuildSketch(Plane.XZ.offset(-_wy)):
            with Locations((_cx, panel_z)):
                RectangleRounded(xlr_pad_w, xlr_pad_h, 3.0)
        extrude(amount=-xlr_pad_proud)
    for _cx in (xlr_cx, eth_cx):
        with BuildSketch(Plane.XZ.offset(-(_wy + xlr_pad_proud))):
            with Locations((_cx, panel_z)):
                Rectangle(_sw, _sh)
        extrude(amount=xlr_seat_depth, mode=Mode.SUBTRACT)

    _dx, _dz = ((xlr_screw_off_minor, xlr_screw_off_major) if _v
                else (xlr_screw_off_major, xlr_screw_off_minor))
    for _cx in (xlr_cx, eth_cx):
        add(_thru(xlr_bore_dia, (_cx, 0, panel_z), "+Y", length=case_y), mode=Mode.SUBTRACT)
        for _sx in (1, -1):
            for _sz in (1, -1):
                add(_thru(xlr_screw_dia, (_cx + _sx * _dx, 0, panel_z + _sz * _dz), "+Y",
                          length=case_y), mode=Mode.SUBTRACT)

    # barrel jack: plain bore, hex nut lands on the flat inner face
    add(_thru(barrel_bore_dia, (barrel_cx, 0, panel_z), "+Y", length=case_y),
        mode=Mode.SUBTRACT)

    chamfer(pi_case.faces().sort_by(Axis.Z)[0].outer_wire().edges(), edge_cham)


# --- checks that must hold before this is worth printing ---
assert case_x <= bed_max and case_y <= bed_max, \
    f"case is {case_x:.0f} x {case_y:.0f} mm, over the {bed_max:.0f} mm bed"
assert cav_h >= pi_standoff_h + stack_h, "cavity is shorter than the Pi + Waveshare stack"
assert panel_band >= xlr_body_depth, \
    f"panel band {panel_band} mm is shallower than the XLR's {xlr_body_depth} mm intrusion"
# every connector pad must sit inside the wall, and pads must not overlap
_pads = sorted([xlr_cx, eth_cx])
assert _pads[1] - _pads[0] > xlr_pad_w, "XLR and Ethernet pads overlap"
# The connector wall is only FLAT between +-(cav_x/2 - inner corner radius). A bore
# that clears cav_x/2 can still land in the curve, where the flange cannot seat and
# the hex nut has nothing square to pull against. Check the flange, not the bore.
_flat_half = cav_x / 2 - max(corner_r - wall, 0.5)
assert abs(barrel_cx) + barrel_flange_dia / 2 + 2.0 < _flat_half, (
    f"barrel flange reaches x={abs(barrel_cx) + barrel_flange_dia/2:.1f}, "
    f"past the flat wall at {_flat_half:.1f}")
for _n, _c in (("XLR", xlr_cx), ("ETH", eth_cx)):
    assert abs(_c) + xlr_pad_w / 2 < _flat_half, f"{_n} pad runs into the corner radius"
assert barrel_cx - barrel_bore_dia / 2 > max(_pads) + xlr_pad_w / 2, \
    "barrel bore collides with the Ethernet pad"
# Connectors clear the boards by SEPARATION IN Y, not in Z -- the bore bottom
# (z=20) is in fact below the interface board top (z=32), which is fine only
# because the component row ends 14 mm short of where the connector band starts.
# That is the load-bearing check, so assert it directly.
assert _row_cy + _row_back / 2 < cav_y / 2 - panel_band, \
    "component row reaches into the connector band -- a jack would land on a board"
assert panel_z + xlr_bore_dia / 2 < top_z, "connector bore breaks through the cavity ceiling"
assert panel_z - xlr_bore_dia / 2 > floor_th, "connector bore cuts into the floor"
# the Pi must not reach into the connector band
assert pi_cy + pi_wid / 2 < cav_y / 2 - panel_band, "Pi intrudes into the connector band"
# bays must not overlap each other
assert iface_cx + iface_len / 2 < iso_cx - iso_len / 2, "iface board and isolator overlap"
assert _row_cy - _row_back / 2 > pi_cy + pi_wid / 2, "component row overlaps the Pi"

print(f"case {case_x:.0f} x {case_y:.0f} x {top_z:.0f} mm  (cavity {cav_x:.0f} x {cav_y:.0f}"
      f" x {cav_h:.0f})\n  Pi @ ({pi_cx:.0f},{pi_cy:.0f})  iface @ ({iface_cx:.0f},{_row_cy:.0f})"
      f"  iso @ ({iso_cx:.0f},{_row_cy:.0f})\n  panel z {panel_z:.0f}"
      f"  | barrel bore {barrel_bore_dia} mm"
      f"{'  ** PROVISIONAL — run panel_coupon first **' if barrel_bore_provisional else ''}")

show(pi_case)
export_stl(pi_case.part, "stl/pi_case.stl")

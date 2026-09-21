"""calibrator_case.py — the tray half of the calibration injector box.

Floor + four walls. The lid (`calibrator_lid.py`) is a featureless plate, which is
the point of splitting it this way: every connector cutout lives in the tray, and
the piece you reprint while fitting connectors is the cheap flat one.

    J1 (XLR female, geophone)  <- -X wall        +X wall ->  J2 (XLR male, Pi)
    +Y wall: J3 1/4" jack, SW1 button
    -Y wall, inside face: the three coin-cell holders tape or screw here

Schematic and build order: doc/calibrator-build.md. Parts and reasoning:
doc/BOM-calibrator.md.

WHY IT IS THIS BIG. None of the three major dimensions is a preference:

  height  A D-series flange needs a 38 mm pad, so a 45 mm outside wall is the FLOOR.
          You cannot make this box shorter without changing the connector.
  length  Two XLRs facing each other intrude 32 mm EACH before the board gets any
          interior at all: 64 + a 60 mm perfboard + working gaps = 132 mm of cavity.
  width   The 1/4" jack and the button intrude ~20 mm from the +Y wall, so the board
          is offset to -Y (`cal_board_cy`) to stay clear of them. That offset is also
          what leaves the -Y wall free for the coin-cell holders.

THE ISOLATION BARRIER IS A LINE ACROSS THIS BOX TOO. Control parts (ATtiny, cell A,
ISP, button) on one side of the board, coil parts (cell B, Rinj, LM4040, both
PhotoMOS outputs) on the other. The box does not enforce it -- the layout does --
but the bays are sized so it is the natural way to fill it.

NOT VALIDATED YET, and both are cheap to fix in PLA rather than in CAD:
  - `ts_bore_dia` (10.0) is derived from the 3/8"-32 nominal thread, not measured on
    a printed coupon the way the XLR cutout was. If the bushing will not pass, drill
    it out to 10.5; the flange and nut are ~14 mm so it cannot fall through.
  - `cal_button_bore` (12.0) is the common panel size and matches the bore
    panel_coupon.py already proved, but CONFIRM THE ACTUAL BUTTON before printing.

Print floor-down, no supports. The XLR pads and their seats are on vertical walls,
so they print as overhangs off the wall face -- at 1.5 mm proud that is a bridge the
slicer handles, but check the first pad before committing to four hours.

    PYTHONPATH=. .venv/bin/python parts/calibrator_case.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

# --- XLR seat geometry, identical to the validated parts/xlr_coupon.py -------
_maj, _min = xlr_screw_off_major, xlr_screw_off_minor
_v = xlr_flange_axis.upper() == "V"
hole_dy, hole_dz = (_min, _maj) if _v else (_maj, _min)
seat_w = (xlr_flange_h if _v else xlr_flange_w) + xlr_seat_clearance
seat_h = (xlr_flange_w if _v else xlr_flange_h) + xlr_seat_clearance
panel_th = cal_wall + xlr_pad_proud - xlr_seat_depth

_half_x = cal_case_x / 2
_half_y = cal_case_y / 2
_cut = cal_wall + xlr_pad_proud + 4.0        # generous: a cutter may overrun inward

# Board standoff centres, and the corner bosses for the lid screws.
_bdx = cal_board_x / 2 - cal_board_hole_inset
_bdy = cal_board_y / 2 - cal_board_hole_inset
board_posts = [(sx * _bdx, cal_board_cy + sy * _bdy)
               for sx in (1, -1) for sy in (1, -1)]
corner_bosses = [(sx * (cal_cav_x / 2 - cal_boss_inset),
                  sy * (cal_cav_y / 2 - cal_boss_inset))
                 for sx in (1, -1) for sy in (1, -1)]

# Panel features on the +Y wall. Placed clear of the board posts in x, and clear of
# the XLR bodies, which occupy |x| > cal_cav_x/2 - xlr_body_depth.
jack_x = -20.0
button_x = 20.0


with BuildPart() as calibrator_case:
    # ---- the tray ----------------------------------------------------------
    with BuildSketch(Plane.XY):
        RectangleRounded(cal_case_x, cal_case_y, cal_corner_r)
    extrude(amount=cal_case_h)

    with BuildSketch(Plane.XY.offset(cal_floor)):
        RectangleRounded(cal_cav_x, cal_cav_y, cal_inner_r)
    extrude(amount=cal_cav_h, mode=Mode.SUBTRACT)

    # ---- lid bosses and board standoffs ------------------------------------
    # Built as explicit Locations rather than sketched planes: a bare Box or
    # Cylinder inside BuildPart adds itself, which is exactly what is wanted here
    # and exactly what must NOT happen for the cutters below (Mode.SUBTRACT).
    with Locations(*[Location((x, y, cal_floor)) for x, y in corner_bosses]):
        Cylinder(cal_boss_dia / 2, cal_cav_h, align=(Align.CENTER, Align.CENTER,
                                                     Align.MIN))
    with Locations(*[Location((x, y, cal_floor)) for x, y in corner_bosses]):
        Cylinder(pilot_m3 / 2, cal_cav_h, align=(Align.CENTER, Align.CENTER,
                                                 Align.MIN), mode=Mode.SUBTRACT)

    with Locations(*[Location((x, y, cal_floor)) for x, y in board_posts]):
        Cylinder(cal_standoff_dia / 2, cal_standoff_h,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(*[Location((x, y, cal_floor)) for x, y in board_posts]):
        Cylinder(pilot_m3 / 2, cal_standoff_h + 0.1,
                 align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

    # ---- XLR pads on the two end walls -------------------------------------
    # The pad stands proud on the OUTSIDE and the flange seat is recessed into it,
    # leaving `panel_th` of material under the flange. That recess, not the two M3
    # screws, is what carries the lateral and torsional load of a latching XLR --
    # see parts/xlr_coupon.py, which validated this exact geometry on the real part.
    for sx in (1, -1):
        with Locations(Location((sx * (_half_x + xlr_pad_proud / 2), 0, cal_xlr_z))):
            Box(xlr_pad_proud, xlr_pad_w, xlr_pad_h)

    for sx in (1, -1):
        face_x = sx * (_half_x + xlr_pad_proud)
        with Locations(Location((face_x - sx * xlr_seat_depth / 2, 0, cal_xlr_z))):
            Box(xlr_seat_depth, seat_w, seat_h, mode=Mode.SUBTRACT)

        # bore + the four-hole pattern, through pad and wall
        with Locations(Location((sx * _half_x, 0, cal_xlr_z), (0, 90, 0))):
            Cylinder(xlr_bore_dia / 2, 2 * _cut, mode=Mode.SUBTRACT)
        for sy in (1, -1):
            for sz in (1, -1):
                with Locations(Location((sx * _half_x, sy * hole_dy,
                                         cal_xlr_z + sz * hole_dz), (0, 90, 0))):
                    Cylinder(xlr_screw_dia / 2, 2 * _cut, mode=Mode.SUBTRACT)

    # ---- 1/4" jack and the panel button, +Y wall ---------------------------
    with Locations(Location((jack_x, _half_y, cal_xlr_z), (90, 0, 0))):
        Cylinder(ts_bore_dia / 2, 2 * _cut, mode=Mode.SUBTRACT)
    with Locations(Location((button_x, _half_y, cal_xlr_z), (90, 0, 0))):
        Cylinder(cal_button_bore / 2, 2 * _cut, mode=Mode.SUBTRACT)


# --- checks that must hold before this is worth four hours of printing -------
assert xlr_bore_dia > xlr_shell_dia, "bore is smaller than the connector shell"
assert 1.0 <= panel_th <= xlr_panel_th_max, f"panel is {panel_th} mm, outside 1-3"
_r = (_maj ** 2 + _min ** 2) ** 0.5
assert _r - xlr_screw_dia / 2 - xlr_bore_dia / 2 > 0.8, "no web left beside the bore"

# The pad has to fit on the wall it is glued to, top and bottom.
_pad_margin = min(cal_xlr_z - xlr_pad_h / 2, cal_case_h - (cal_xlr_z + xlr_pad_h / 2))
assert _pad_margin > 2.0, f"only {_pad_margin:.1f} mm of wall around the XLR pad"

# Both XLR bodies plus the board have to fit end to end.
assert 2 * xlr_body_depth + cal_board_x < cal_cav_x, (
    f"cavity is {cal_cav_x} mm; two connectors and the board need "
    f"{2 * xlr_body_depth + cal_board_x}")

# The jack and button must not land on the board, and must clear the XLR bodies.
_y_gap = cal_cav_y / 2 - (cal_board_cy + cal_board_y / 2)
assert _y_gap > ts_body_depth, (
    f"only {_y_gap} mm from the board to the +Y wall; the jack needs {ts_body_depth}")
assert _y_gap > cal_button_depth, "the button would foul the board"
for _x, _what in ((jack_x, "jack"), (button_x, "button")):
    assert abs(_x) + ts_nut_clear / 2 < cal_cav_x / 2 - xlr_body_depth, (
        f"the {_what} sits over an XLR body")
assert abs(jack_x - button_x) > ts_nut_clear, "jack and button nuts overlap"

# Cell holders live on the -Y wall's inside face; leave them somewhere to sit.
_cell_gap = (cal_board_cy - cal_board_y / 2) + cal_cav_y / 2
assert _cell_gap >= 5.0, f"only {_cell_gap} mm between the board and the -Y wall"

# Standoffs must actually be under the board.
assert _bdx > 0 and _bdy > 0, "board hole inset swallows the board"

print(f"tray {cal_case_x} x {cal_case_y} x {cal_case_h} mm outside, "
      f"cavity {cal_cav_x} x {cal_cav_y} x {cal_cav_h}")
print(f"  XLR: bore {xlr_bore_dia} at z={cal_xlr_z}, seat {seat_w:.1f} x {seat_h:.1f} "
      f"x {xlr_seat_depth} deep, {panel_th:.1f} mm panel, {_pad_margin:.1f} mm wall margin")
print(f"  +Y wall: jack {ts_bore_dia} at x={jack_x}, button {cal_button_bore} "
      f"at x={button_x}  (NEITHER coupon-validated -- see the docstring)")
print(f"  board bay {cal_board_x} x {cal_board_y} at y={cal_board_cy}, "
      f"{_y_gap} mm to +Y wall, {_cell_gap} mm to -Y wall for the cell holders")

show(calibrator_case)
export_stl(calibrator_case.part, "stl/calibrator_case.stl")

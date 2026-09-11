"""adxl_coupon.py — fit test for the ADXL355 sensor bay, before committing to the case.

Two parts printed together: the POCKET (an offcut of the case floor plus the header-side
wall) and the U-shaped RETAINER that holds the board down. ~15 minutes to print instead
of hours for the case, and it settles four numbers that are currently guesses.

WHY A POCKET AND NOT SCREWS. The EVAL-ADXL355-PMDZ has no mounting holes (the two gold
pads at diagonal corners are filled vias; they photograph exactly like M2 holes and are
not). So the board is located by the pocket walls and held by a retainer bearing on its
bare rim.

WHY THE RETAINER BARELY HAS TO DO ANYTHING. The board is ~3 g lying flat: gravity already
presses it to the floor at 1 g, and the signals of interest are tens of ug. Breaking
contact would need the case to accelerate at ~1 g, five orders of magnitude above the
band. The retainer is not a preload -- it is strain relief against the seven-wire loom,
anti-rattle if the box is carried, and orientation repeatability for the compass azimuth.
So the pocket is cut adxl_pocket_over DEEPER than the board: the retainer lands on the
plate, never on the board, and cannot rock.

WHY A U AND NOT A TAB. Only ~2 mm of each edge is free of components, and aiming a
printed tab at a 2 mm strip is a tolerance problem. An opening SMALLER than the board and
LARGER than the component field cannot miss: at a 17 mm opening on a 20 mm board it bears
on 1.5 mm all round, and a 0.4 mm misalignment still leaves >1 mm of bearing on every
edge. Open on the header side, because the header body stands 5 mm proud there.

REV 2, after printing rev 1 (2026-09-10). The board would not drop fully in at 0.4 mm
total clearance. That is a CORNER problem, not a side problem: a 0.4 mm nozzle leaves every
inside corner with a ~0.2 mm radius, and a sharp-cornered PCB cannot enter a radiused
pocket however much side clearance it has. The corners now have relief circles -- exactly
what a machinist does when cutting a square pocket with a round end mill -- and the sides
went only 0.4 -> 0.5. Loosening the sides alone would have bought entry by spending the
location repeatability the compass azimuth needs, which is the wrong trade.

What this proves:
  - that a 20.4 mm pocket actually accepts the 20 mm board, and with how much play
    (this is the number to tune -- too loose and the azimuth wanders on reassembly),
  - that the wall slot clears the right-angle pins (5 mm above the board, 7 mm out),
  - that the floor relief clears the back-side solder joints wherever they land, so the
    board beds on a DEFINED rim-and-pad rather than rocking on twelve solder blobs,
  - that the 17 mm opening clears every component while still bearing on the rim,
  - that M2.5 self-tapping into a 2.1 mm pilot holds in PLA at this wall thickness.

What it does NOT prove: that the female jumper shells clear beyond the wall. That needs
~20 mm of open air past the slot (7 mm of pin + ~10-12 mm of shell) and is a case-level
dimension, not a coupon one. Check it with a real jumper pushed onto the real pins.

Print plate-down, no supports. The slot is a bridge; if it sags, raise adxl_slot_clear_h.

    PYTHONPATH=. .venv/bin/python parts/adxl_coupon.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

plate = 32.0
floor = 5.0
corner_r = 3.0

pocket_x_max = adxl_pocket_w / 2
wall_x0 = pocket_x_max
wall_x1 = wall_x0 + adxl_wall_th
wall_cx = (wall_x0 + wall_x1) / 2

ret_y_half = pocket_x_max + adxl_retainer_margin
ret_x_min = -ret_y_half
ret_x_max = pocket_x_max
open_half = adxl_open_w / 2

# screws: one in the far bar, two flanking the open (header) end. The offset is
# DERIVED from the pocket (see dimensions.py) so a pilot can never break into it.
screw_pts = [(-adxl_screw_off, 0.0),
             (open_half - 2.5, +adxl_screw_off),
             (open_half - 2.5, -adxl_screw_off)]

with BuildPart() as adxl_coupon:
    with BuildSketch(Plane.XY):
        RectangleRounded(plate, plate, corner_r)
    extrude(amount=floor)

    with BuildSketch(Plane.XY.offset(floor)):          # header-side wall
        with Locations((wall_cx, 0.0)):
            Rectangle(adxl_wall_th, plate - 2 * corner_r)
    extrude(amount=adxl_wall_h)

    with BuildSketch(Plane.XY.offset(floor)):          # the pocket, with corner reliefs
        Rectangle(adxl_pocket_w, adxl_pocket_h)
        with Locations(*[(sx * adxl_pocket_w / 2, sy * adxl_pocket_h / 2)
                         for sx in (1, -1) for sy in (1, -1)]):
            Circle(adxl_corner_relief / 2)
    extrude(amount=-adxl_pocket_depth, mode=Mode.SUBTRACT)

    # The back is NOT flat and its joints are not confined to the header edge. Rather
    # than relieve where they are thought to be, DEFINE the bearing surface — a U-rim on
    # three edges, nothing inboard of it — and drop everything else away. (A central pad
    # under the chip was tried and fouled joints; see dimensions.py for why the board
    # bridging its own 16 mm is stiffer than it needs to be by ~800x.)
    _x0, _x1 = -adxl_pocket_w / 2 + adxl_floor_rim, adxl_pocket_w / 2
    _y0, _y1 = -adxl_pocket_h / 2 + adxl_floor_rim, adxl_pocket_h / 2 - adxl_floor_rim
    with BuildSketch(Plane.XY.offset(floor - adxl_pocket_depth)):
        with Locations(((_x0 + _x1) / 2, (_y0 + _y1) / 2)):
            Rectangle(_x1 - _x0, _y1 - _y0)
    extrude(amount=-adxl_trough_depth, mode=Mode.SUBTRACT)

    with BuildSketch(Plane.XY.offset(floor - 0.3)):    # pin slot through the wall
        with Locations((wall_cx, 0.0)):
            Rectangle(adxl_wall_th + 2.0, adxl_slot_w)
    extrude(amount=adxl_slot_h + 0.3, mode=Mode.SUBTRACT)

    with BuildSketch(Plane.XY.offset(floor)):          # blind pilots
        with Locations(*screw_pts):
            Circle(adxl_pilot_dia / 2)
    extrude(amount=-adxl_pilot_depth, mode=Mode.SUBTRACT)

with BuildPart() as adxl_retainer:
    with BuildSketch(Plane.XY):
        with Locations(((ret_x_min + ret_x_max) / 2, 0.0)):
            Rectangle(ret_x_max - ret_x_min, 2 * ret_y_half)
    extrude(amount=adxl_retainer_th)
    with BuildSketch(Plane.XY):                        # opening, open toward +X
        with Locations(((-open_half + ret_x_max + 2.0) / 2, 0.0)):
            Rectangle(ret_x_max + 2.0 + open_half, adxl_open_h)
    extrude(amount=adxl_retainer_th, mode=Mode.SUBTRACT)
    with BuildSketch(Plane.XY):
        with Locations(*screw_pts):
            Circle(adxl_screw_dia / 2)
    extrude(amount=adxl_retainer_th, mode=Mode.SUBTRACT)

# --- checks that must hold before this is worth printing ---
assert adxl_pocket_clear > 0, "pocket is not larger than the board"
assert adxl_rim < adxl_free_rim, (
    f"retainer rim {adxl_rim} mm exceeds the {adxl_free_rim} mm of bare PCB — "
    "it would land on components")
assert adxl_slot_w > adxl_header_body_w, "slot narrower than the header body"
assert adxl_slot_h > adxl_pin_above, "slot shorter than the pin field"
assert adxl_pocket_depth > adxl_board_th, (
    "pocket is not deeper than the board; the retainer would rock on the board")
assert adxl_wall_h > adxl_slot_h, "slot is taller than the wall it is cut through"
assert adxl_trough_depth > adxl_solder_proud, "relief shallower than the solder joints"
# the side rims must sit OUTSIDE the joint field, or they bear on solder again
assert adxl_pocket_h / 2 - adxl_floor_rim > adxl_solder_span / 2, (
    f"side rim reaches y={adxl_pocket_h/2 - adxl_floor_rim:.2f} but the joints reach "
    f"{adxl_solder_span/2:.2f} — the rim would land on solder")
assert floor - adxl_pocket_depth - adxl_trough_depth > 1.0, "relief leaves too thin a floor"
for px, py in screw_pts:                    # screws must land in retainer material
    inside_open = (-open_half < py < open_half) and (px > -open_half)
    assert not inside_open, f"screw ({px:.1f}, {py:.1f}) falls in the retainer opening"
    assert ret_x_min < px < ret_x_max and -ret_y_half < py < ret_y_half, \
        f"screw ({px:.1f}, {py:.1f}) falls outside the retainer"
assert max(abs(px) for px, _ in screw_pts) < plate / 2 - 2.0, "screw too near plate edge"
# THE ONE THAT REV 1 NEEDED: a pilot must not break through into the pocket.
for px, py in screw_pts:
    gap_x = abs(px) - adxl_pocket_w / 2
    gap_y = abs(py) - adxl_pocket_h / 2
    gap = max(gap_x, gap_y)          # outside the pocket in at least one axis
    assert gap >= adxl_pilot_dia / 2, (
        f"pilot at ({px:.2f}, {py:.2f}) is {gap:.2f} mm from the pocket wall but has a "
        f"{adxl_pilot_dia/2:.2f} mm radius — it would open into the pocket")
    assert abs(py) + adxl_pilot_dia / 2 < plate / 2 - 1.0, "pilot too near the plate edge"

print(f"pocket {adxl_pocket_w} x {adxl_pocket_h} x {adxl_pocket_depth} deep "
      f"({adxl_pocket_clear/2:.2f} mm per side) | retainer opening {adxl_open_w} x "
      f"{adxl_open_h}, bearing {adxl_rim} mm of a {adxl_free_rim} mm rim | "
      f"slot {adxl_slot_w} x {adxl_slot_h} | screws at "
      f"{[(round(a,1), round(b,1)) for a, b in screw_pts]}")

show(adxl_coupon, adxl_retainer)
export_stl(adxl_coupon.part, "stl/adxl_coupon.stl")
export_stl(adxl_retainer.part, "stl/adxl_retainer.stl")

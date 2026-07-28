"""geophone_case.py — GEN-1 geophone case body. POC, indoor, deliberately crude.

Scope (Charles, 2026-07-28): "one step up from where we are now." The job is to
make the sensor easy to pick up and set down, and to put the existing XLR on the
case so the cable unplugs instead of being manhandled. Explicitly NOT in scope:
outdoor use, gaskets/seals, ballast, heat-set inserts, insulation. PLA is fine.

  - Rounded SQUARE, not a cylinder. Flat walls give the XLR flange a flat seat
    (a 26 mm flange on a 116 mm cylinder gaps ~1.5 mm at its corners) and are
    nicer to grip. Costs nothing to print.
  - Element pocket = the proven geophone_base fit: flat floor, full bottom rim
    seats, glove-fit bore centers it. Nothing compliant under the element.
  - THREE screw heads as feet, not printed bosses. Three-point contact is
    deterministic where a flat face rocks on unknown high spots, and screws give
    crude leveling. Printed feet would have forced the whole floor to bridge over
    air; this way the floor prints flat on the bed.
  - XLR: the 24 mm bore is modeled. The two flange holes are modeled too, but
    ONLY once xlr_screw_spacing / xlr_screw_axis in dimensions.py are confirmed
    by caliper and proven on parts/xlr_coupon.py — a 10-minute flat plate that
    the connector either bolts to or does not. Do not drill them by hand: the
    flange holes are countersunk (a cone, not a bushing, so a bit wanders), the
    male shell protrudes into where the chuck has to be, and a 3.2 mm bit
    snatching through a 2.4 mm PLA wall cracks it.
    Secure with 2x M3 x 10 COUNTERSUNK machine screws + M3 nuts inside, not
    self-tappers: the +Y wall is thinned to 2.4 mm to land inside the D-series'
    1-3 mm panel range, which leaves ~2 threads of engagement, and the XLR latch
    pulls on that joint every time the cable comes off. The inside face of the
    thinned patch is flat and 34 mm square, so the nuts seat properly.
    Fit the connector BEFORE the geophone — you need the finger room.
  - NO vents. An earlier revision had six; removed 2026-07-28 after checking the
    arithmetic. There is no heat source inside (passive coil; the Pi and ADC are
    in a different case), and the lowest acoustic mode of a 116 mm cavity is
    c/2L ~ 1.5 kHz — 30x above Nyquist at 100 sps and nowhere near the 1-15 Hz
    band. Venting would instead make it a ~210 Hz Helmholtz resonator, equally
    out of band. So the vents bought nothing and cost three things: a through-path
    for garage convection over the element, faster thermal coupling to the room
    (we have a known sub-Hz thermal-settling problem that box lag helps smooth),
    and a way in for dust and spiders. Pressure equalisation needs no holes — an
    FDM print with a bare screwed-on lid and a 24 mm connector bore leaks freely.

Fasteners: #6 x 1/2" sheet-metal screws throughout (4 lid, 3 feet, 2 XLR).
Print floor-down, no supports.
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

# --- case shell ---
case_side = 116.0     # driven by the XLR: cup radius + clearance + xlr_body_depth
corner_r = 20.0
wall = 3.0
floor_th = 8.0        # thick enough for a 6 mm foot-screw pilot, stiff under the element
cavity_h = 66.0       # element is 36 tall; leaves 30 mm for terminals, wire and slack
                      # (was 46 — Charles asked for another 20 mm, 2026-07-28)
edge_cham = 0.6       # kills elephant-foot on the bottom face

inner_side = case_side - 2 * wall
inner_r = corner_r - wall

# --- element pocket (same fit as geophone_base) ---
cup_wall = 3.0
bore_dia = geophone_dia + 2 * fit_clearance
pocket_depth = geophone_height
cup_outer = bore_dia + 2 * cup_wall

# --- feet (3 screw heads) ---
foot_r = 38.0         # wide enough to be tip-stable, short enough not to flex the floor
foot_pad_dia = 16.0
foot_pad_h = 4.0      # local thickening -> 12 mm of plastic for the pilot
foot_pilot_depth = 9.0

# --- lid screw bosses ---
boss_xy = 47.0        # far enough out to merge into the rounded corner wall
boss_dia = 10.0
boss_pilot_depth = 12.0

# --- XLR panel (+Y wall) ---
xlr_z = floor_th + 24.0
xlr_relief = 34.0     # inside relief patch, square
xlr_panel_th = 2.4    # inside the D-series 1-3 mm panel range

top_z = floor_th + cavity_h

# rotations that aim a MIN-aligned cylinder along each outward face normal
AIM = {"+Y": Rotation(-90, 0, 0), "-Y": Rotation(90, 0, 0),
       "+X": Rotation(0, 90, 0), "-X": Rotation(0, -90, 0)}


def _thru(dia, start, aim, length=40.0):
    """A cylinder of `dia` starting at `start` and running along `aim`.

    Mode.PRIVATE is load-bearing: a bare Cylinder() inside an active BuildPart
    context is a *builder operation* and adds itself to the part on the spot.
    Without it this helper silently deposited every cutter as a solid at the
    origin — the XLR one plugged the element bore from z=0 to 40 (found on the
    STL, 2026-07-28), invisible to a manifold/volume check.
    """
    cyl = Cylinder(dia / 2, length, align=(Align.CENTER, Align.CENTER, Align.MIN),
                   mode=Mode.PRIVATE)
    return Location(start) * (AIM[aim] * cyl)


with BuildPart() as geophone_case:
    # solid rounded-square block, floor on the bed
    with BuildSketch(Plane.XY):
        RectangleRounded(case_side, case_side, corner_r)
    extrude(amount=top_z)

    # hollow the cavity from the top
    with BuildSketch(Plane.XY.offset(floor_th)):
        RectangleRounded(inner_side, inner_side, inner_r)
    extrude(amount=cavity_h, mode=Mode.SUBTRACT)

    # element cup rising from the floor; pocket floor IS the case floor
    with Locations((0, 0, floor_th)):
        Cylinder(cup_outer / 2, pocket_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((0, 0, floor_th)):
        Cylinder(bore_dia / 2, pocket_depth + 1,
                 align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)

    # lid screw bosses in the four corners, merged into the wall
    with Locations((boss_xy, boss_xy, floor_th), (-boss_xy, boss_xy, floor_th),
                   (boss_xy, -boss_xy, floor_th), (-boss_xy, -boss_xy, floor_th)):
        Cylinder(boss_dia / 2, cavity_h,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((boss_xy, boss_xy, top_z), (-boss_xy, boss_xy, top_z),
                   (boss_xy, -boss_xy, top_z), (-boss_xy, -boss_xy, top_z)):
        Cylinder(pilot_6 / 2, boss_pilot_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MAX),
                 mode=Mode.SUBTRACT)

    # foot pads on the floor top + blind pilots up from the bottom face
    with PolarLocations(foot_r, 3, start_angle=90):
        with Locations((0, 0, floor_th)):
            Cylinder(foot_pad_dia / 2, foot_pad_h,
                     align=(Align.CENTER, Align.CENTER, Align.MIN))
    with PolarLocations(foot_r, 3, start_angle=90):
        Cylinder(pilot_6 / 2, foot_pilot_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)

    # XLR: inside relief patch to bring the +Y wall down to a legal panel
    # thickness, then the 24 mm bore. Flange holes are drilled by hand.
    with Locations((0, inner_side / 2 + (wall - xlr_panel_th), xlr_z)):
        Box(xlr_relief, 2 * (wall - xlr_panel_th), xlr_relief,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT)
    add(_thru(xlr_bore_dia, (0, 20, xlr_z), "+Y"), mode=Mode.SUBTRACT)
    # flange holes: only once the coupon has said WHICH diagonal (see dimensions.py)
    if xlr_screw_diagonal:
        _s = 1 if xlr_screw_diagonal.upper() == "A" else -1
        for _sx, _sy in ((1, _s), (-1, -_s)):
            add(_thru(xlr_screw_dia,
                      (_sx * xlr_screw_dx, 20, xlr_z + _sy * xlr_screw_dy), "+Y"),
                mode=Mode.SUBTRACT)

    # chamfer the bottom outer edge so the print sits true
    chamfer(geophone_case.faces().sort_by(Axis.Z)[0].outer_wire().edges(), edge_cham)


# --- sanity check: the element must actually be able to drop in ---
# A manifold/volume check does NOT catch a plug inside the bore (it stays
# watertight and the volume looks plausible), so assert the pocket is empty
# before anything gets sliced.
_p = geophone_case.part
for _z in (floor_th + 1, floor_th + pocket_depth / 2, floor_th + pocket_depth - 1):
    assert not _p.is_inside((0, 0, _z)), f"element bore is obstructed at z={_z}"
    assert not _p.is_inside((bore_dia / 2 - 0.5, 0, _z)), f"bore narrowed at z={_z}"

show(geophone_case)
export_stl(geophone_case.part, "stl/geophone_case.stl")

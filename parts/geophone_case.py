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
  - XLR (all VALIDATED on parts/xlr_coupon.py with the real Neutrik D): 24 mm
    bore — the published cutout, oversized so the shank's four alignment ribs
    clear rather than engage; 23 mm fouls them. Flange seats in a 26.4 x 31.4 x
    2.0 recess in a 38 x 38 pad standing 1.5 mm proud, leaving 2.5 mm of panel.
    The recess is structural: it carries the latch's lateral and torsional load
    in shear so the two screws only clamp. Four 3.4 mm holes at +-(10, 11.5) —
    all four sign combinations, so the flange's diagonal handedness never had to
    be established; two take screws and two sit hidden under the flange.
    Secure with 2x M3 x 10 COUNTERSUNK machine screws + M3 nuts inside, not
    self-tappers: 2.5 mm of PLA gives ~2 threads and the latch pulls on that
    joint every time the cable comes off.
    Fit the connector BEFORE the geophone — you need the finger room.
  - Two clamp bosses flank the cup, unused in gen 1. They are the only part of a
    hold-down that cannot be retrofitted; see the note by their parameters.
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

Fasteners: 7x #6 x 1/2" sheet-metal (4 lid, 3 feet) + 2x M3 x 10 countersunk
+ 2x M3 nut (XLR).
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
cup_proud = 2.0       # cup is SHORTER than the element by this, so the element stands
                      # proud of the rim. Flush (cup == element height) meant any real
                      # variation put the rim high and a hold-down would bear on the cup
                      # instead of the element. A pad cannot drop into the bore alongside
                      # the element either — 0.2 mm radial — so the element has to come
                      # up. Also makes it easier to lift out.
cup_h = pocket_depth - cup_proud
cup_outer = bore_dia + 2 * cup_wall

# --- feet (3 screw heads) ---
foot_r = 38.0         # wide enough to be tip-stable, short enough not to flex the floor
foot_pad_dia = 16.0
foot_pad_h = 4.0      # local thickening -> 12 mm of plastic for the pilot
foot_pilot_depth = 9.0

# --- clamp bosses (flanking the element cup) ---
# NOT used by gen 1 — the element is vertical under 1 g, so its rim contact is never
# in tension at seismic amplitudes and gravity is already the preload; putty on the
# flanks handles lateral restraint. These exist because they are the part that cannot
# be retrofitted: with them, a hold-down is a 10-minute print and no case reprint.
# If one is ever made it must be COMPLIANT — a rigid PLA finger at these dimensions is
# ~560 N/mm, so FDM tolerance alone swings the preload by +-80 N. Compliance above the
# element is harmless; it is not in the ground path (element -> floor -> feet).
# Paracord under tension (Charles's suggestion) is the right CLASS of answer for exactly
# that reason, but nylon creeps under sustained load, so the preload decays over weeks
# and knots make it unrepeatable — bad in a station meant to sit undisturbed, because
# you cannot tell when it changed. Same idea without the creep: a silicone O-ring
# stretched over these bosses, or a light extension spring between them, either with a
# small printed saddle so the load lands on the element rim and not the terminal pins.
clamp_boss_x = 20.0   # merges into the cup wall, which stiffens both
clamp_boss_dia = 9.0
clamp_boss_top = floor_th + pocket_depth + 6.0   # 6 mm ABOVE the element top: a tall
                      # anchor, deliberately not sized for one particular hold-down, so a
                      # screwed bar, a silicone O-ring or an extension spring all work and
                      # the retrofit part defines its own interface.
clamp_boss_pilot_depth = 12.0

# --- lid screw bosses ---
boss_xy = 47.0        # far enough out to merge into the rounded corner wall
boss_dia = 10.0
boss_pilot_depth = 12.0

# --- XLR panel (+Y wall) ---
xlr_z = floor_th + 24.0
xlr_panel_th = wall + xlr_pad_proud - xlr_seat_depth   # 2.5 mm under the flange

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
        Cylinder(cup_outer / 2, cup_h,
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

    # clamp bosses flanking the cup (unused in gen 1 — see note above)
    with Locations((clamp_boss_x, 0, floor_th), (-clamp_boss_x, 0, floor_th)):
        Cylinder(clamp_boss_dia / 2, clamp_boss_top - floor_th,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((clamp_boss_x, 0, clamp_boss_top), (-clamp_boss_x, 0, clamp_boss_top)):
        Cylinder(pilot_6 / 2, clamp_boss_pilot_depth,
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

    # XLR mount. The flange seat is a pad standing proud of the OUTSIDE wall with
    # the flange footprint recessed into it: the recess carries the lateral and
    # torsional load of the latch in shear through plastic, leaving the two screws
    # to do nothing but clamp. Net panel under the flange is 2.5 mm, inside the
    # connector's 1-3 mm range. (Nothing on the inside face — the case is a
    # rounded square so that wall is already flat; an inside pocket did nothing.)
    _wall_y = case_side / 2
    if xlr_flange_axis:
        _v = xlr_flange_axis.upper() == "V"
        _sw = (xlr_flange_h if _v else xlr_flange_w) + xlr_seat_clearance
        _sh = (xlr_flange_w if _v else xlr_flange_h) + xlr_seat_clearance
        with BuildSketch(Plane.XZ.offset(-_wall_y)) as _pad:
            with Locations((0, xlr_z)):
                RectangleRounded(xlr_pad_w, xlr_pad_h, 3.0)
        extrude(amount=-xlr_pad_proud)
        with BuildSketch(Plane.XZ.offset(-(_wall_y + xlr_pad_proud))) as _seat:
            with Locations((0, xlr_z)):
                Rectangle(_sw, _sh)
        extrude(amount=xlr_seat_depth, mode=Mode.SUBTRACT)

    add(_thru(xlr_bore_dia, (0, 20, xlr_z), "+Y", length=60.0), mode=Mode.SUBTRACT)
    # Flange holes, once the coupon has said which way the 30 mm flange axis runs
    # (see dimensions.py). All four sign combinations, as on the coupon: two carry
    # the screws and two end up hidden under the 30 x 25 flange, so handedness
    # never has to be established.
    if xlr_flange_axis:
        _dx, _dz = ((xlr_screw_off_minor, xlr_screw_off_major)
                    if xlr_flange_axis.upper() == "V"
                    else (xlr_screw_off_major, xlr_screw_off_minor))
        for _sx in (1, -1):
            for _sz in (1, -1):
                add(_thru(xlr_screw_dia,
                          (_sx * _dx, 20, xlr_z + _sz * _dz), "+Y"),
                    mode=Mode.SUBTRACT)

    # chamfer the bottom outer edge so the print sits true
    chamfer(geophone_case.faces().sort_by(Axis.Z)[0].outer_wire().edges(), edge_cham)


# --- sanity check: the element must actually be able to drop in ---
# A manifold/volume check does NOT catch a plug inside the bore (it stays
# watertight and the volume looks plausible), so assert the pocket is empty
# before anything gets sliced.
_p = geophone_case.part
for _z in (floor_th + 1, floor_th + cup_h / 2, floor_th + cup_h - 1):
    assert not _p.is_inside((0, 0, _z)), f"element bore is obstructed at z={_z}"
    assert not _p.is_inside((bore_dia / 2 - 0.5, 0, _z)), f"bore narrowed at z={_z}"

show(geophone_case)
export_stl(geophone_case.part, "stl/geophone_case.stl")

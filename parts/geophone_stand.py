"""geophone_stand.py — standalone geophone cup + broad ground-coupling base.

Lets the geophone sit a short distance from the Pi as a self-contained unit.
Two functional zones in ONE rigid print (no compliant joint between them):

  - CUP: same slip-fit bore as geophone_base.py — geophone drops in bottom-first,
    seats on its full bottom rim on the pocket floor (broad rigid coupling), the
    glove-fit bore centers it. Terminals sit ~flush with the rim; the lead exits
    a rim notch.
  - BASE: a wide, low, flat disc that couples to the slab. Broad + low = stable
    stance and a large flat contact patch for rigid ground coupling. Print with
    HIGH/solid infill (mass + stiffness; see BACKLOG) — the flat underside is the
    coupling face and prints straight on the bed, no supports.

Prints base-down. Wire for now just drapes out the rim notch (XLR panel connector
comes later, once the connectors arrive).
"""
from build123d import *
from ocp_vscode import show
from dimensions import *   # geophone_dia, geophone_height, fit_clearance

# --- cup (reuses the geophone_base fit logic) ---
cup_wall = 3.0                                 # pocket wall thickness
bore_dia = geophone_dia + 2 * fit_clearance    # slip-fit bore (tune fit_clearance)
pocket_depth = geophone_height                 # element ends ~flush with the rim
cup_outer = bore_dia + 2 * cup_wall            # ~31.8 mm
wire_slot_w = 6.0                              # rim notch for the terminal leads

# --- base foot (ground interface) ---
base_dia = 60.0                                # broad footprint for a stable stance
base_h = 6.0                                   # low + solid: mass, stiffness, flat coupling
edge_cham = 0.6                                # kills FDM elephant-foot on the coupling face

total_h = base_h + pocket_depth                # pocket floor sits at z = base_h

with BuildPart() as geophone_stand:
    # broad ground-coupling base
    Cylinder(base_dia / 2, base_h,
             align=(Align.CENTER, Align.CENTER, Align.MIN))
    # cup column rising from the base
    Cylinder(cup_outer / 2, total_h,
             align=(Align.CENTER, Align.CENTER, Align.MIN))
    # hollow the pocket from the top (over-cut 1 mm through the rim for a clean edge)
    with Locations((0, 0, base_h)):
        Cylinder(bore_dia / 2, pocket_depth + 1,
                 align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)
    # wire-exit notch in the cup rim
    with Locations((0, cup_outer / 2, total_h)):
        Box(wire_slot_w, 2 * cup_wall + 2, 8,
            align=(Align.CENTER, Align.CENTER, Align.MAX),
            mode=Mode.SUBTRACT)
    # chamfer the base bottom outer edge (flat coupling face seats true)
    bottom_edge = geophone_stand.edges().group_by(Axis.Z)[0].filter_by(GeomType.CIRCLE)
    if bottom_edge:
        chamfer(bottom_edge, edge_cham)

show(geophone_stand)
export_stl(geophone_stand.part, "stl/geophone_stand.stl")   # refreshed on every run

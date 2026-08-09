"""case_base.py — flat shelf carrying the Pi 2B + Waveshare and the interface board.

One of three parts (Charles, 2026-08-08): BASE + COVER + HANDLE. This is the piece
you iterate on, so it is deliberately the cheap one — a flat plate, ~90 g and a
fraction of the cover's print time. Get the board mounting wrong and you reprint
this, not the enclosure.

It is also the piece you BUILD ON: boards go down on an open shelf at the bench,
wired with everything reachable from every side, and only then does the cover come
down over the top. That was the other half of the reason for splitting it.

  - Pi: 2 locating pins + 1 flat post. Only the two GPIO-side holes are free (photo,
    2026-08-09); the opposite pair carries the Pi<->Waveshare standoffs with NUTS
    under the board, so nothing may sit beneath them.
  - THE PI IS OFFSET TO -X, hard against that wall, because its Ethernet and USB
    stacks face +X and need 60 mm of clearance for a plug and a bend. Centring it
    would pay that on both sides for nothing. Gen-1 sized the cavity to the 85 mm
    PCB rectangle with 12 mm margins and never modelled a connector or a mating
    plug at all -- that is what scrapped the first base.
  - Interface board: 2 standoffs with M3 pilots, matching its own 40 mm hole
    spacing. FLAT, not on edge — it has screw terminals along both long edges, so
    there is no clear edge to slot into (found 2026-08-08). Use a WASHER: the
    board's holes are an unmeasured 4-5 mm, so the washer is what captures it.
  - 4 clearance holes at the corners for the #6 screws that pull it up into the
    cover's bosses.
  - NO feet. The underside is flat and takes self-adhesive feet. The geophone case
    uses three screw heads instead, but that is a coupling decision specific to it
    (element -> floor -> feet -> ground); nothing couples through this box.

Z datum: z=0 is the BOTTOM face here; the top face (z=base_th) is the shared datum
that dimensions.py measures the cover's interior from.

Print flat, no supports.

    PYTHONPATH=. .venv/bin/python parts/case_base.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

with BuildPart() as case_base:
    with BuildSketch(Plane.XY):
        RectangleRounded(case_x, case_y, case_corner_r)
    extrude(amount=base_th)

    # --- Pi: standoffs under all three support points ---
    with Locations(*[(px, py, base_th) for px, py in gpio_pin_pts + usb_support_pts]):
        Cylinder(pi_standoff_dia / 2, pi_standoff_h,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    # locating pins in the two FREE holes, standing proud of the board
    with Locations(*[(px, py, base_th + pi_standoff_h) for px, py in gpio_pin_pts]):
        Cylinder(pi_pin_dia / 2, pi_pin_extra,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    # transverse cotter hole ~1.5 mm above the board top, axis along Y so the wire
    # inserts toward open space rather than alongside the GPIO header
    _cot_z = base_th + pi_standoff_h + pi_board_th + 1.5
    with Locations(*[Location((px, py, _cot_z), (90, 0, 0)) for px, py in gpio_pin_pts]):
        Cylinder(cotter_hole_dia / 2, pi_pin_dia + 2, mode=Mode.SUBTRACT)

    # --- interface board: 2 standoffs, M3 into the pilot ---
    with Locations(*[(px, py, base_th) for px, py in iface_pts]):
        Cylinder(iface_boss_dia / 2, iface_standoff_h,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(*[(px, py, base_th + iface_standoff_h) for px, py in iface_pts]):
        Cylinder(iface_pilot / 2, iface_pilot_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)

    # --- 4 clearance holes for the screws that pull the base into the cover ---
    with BuildSketch(Plane.XY):
        with Locations(*[(sx * asm_x, sy * asm_y) for sx in (1, -1) for sy in (1, -1)]):
            Circle(clear_6 / 2)
    extrude(amount=base_th, mode=Mode.SUBTRACT)

    chamfer(case_base.faces().sort_by(Axis.Z)[0].outer_wire().edges(), edge_cham)


# --- checks ---
# corner screws must clear the boards
for _n, _cx, _cy, _w, _d in (("Pi", pi_cx, pi_cy, pi_len, pi_wid),
                             ("interface", iface_cx, iface_cy, iface_len, iface_wid)):
    for _sx in (1, -1):
        for _sy in (1, -1):
            assert (abs(_sx * asm_x - _cx) > _w / 2 + clear_6 / 2
                    or abs(_sy * asm_y - _cy) > _d / 2 + clear_6 / 2), \
                f"a corner screw lands under the {_n} board"
# THE CHECK THAT WAS MISSING. The cavity was sized to the PCB rectangle, so the port
# side got 12 mm -- less than a bare RJ45 plug -- and a printed base was wasted.
# Assert against the CONNECTOR FACE and the space a plugged cable actually needs.
_port_face = pi_cx + pi_len / 2 + pi_conn_overhang
assert cav_x / 2 - _port_face >= pi_port_clear - side_margin, (
    f"only {cav_x / 2 - _port_face:.1f} mm past the Pi's connector face; "
    f"an RJ45 plug alone is ~33 mm before it can start to turn")
assert pi_cx - pi_len / 2 >= -cav_x / 2 + side_margin - 0.01, "Pi overhangs the -X wall"
assert cav_x >= pi_len + 2 * side_margin, "Pi does not fit the cavity width"

print(f"base {case_x:.0f} x {case_y:.0f} x {base_th:.0f} mm | Pi @ ({pi_cx:.0f},{pi_cy:.0f})"
      f" | iface @ ({iface_cx:.0f},{iface_cy:.0f}) | corner screws +-({asm_x:.1f},{asm_y:.1f})")

show(case_base)
export_stl(case_base.part, "stl/case_base.stl")

"""barrel_plate.py — removable panel plate carrying the 5 V barrel jack.

WHY THIS EXISTS. The barrel jack's thread OD is the one dimension on the connector
wall that is not validated: the XLR and Ethernet cutouts are D-series and already
proven on a printed coupon against a real part, but the barrel bore is a guess until
panel_coupon.py says otherwise. A ~300 g case print must not depend on a guess. So
the case wall gets a plain square opening and this ~6 g plate carries the bore.

Wrong bore, or a different jack later, or a second DC inlet -> reprint this, not the
case. The same opening also takes a blank plate if the jack ever moves elsewhere.

The plate mounts from the INSIDE, so the case wall takes the pull of a cable tugging
on the jack in shear across four M3s rather than trying to pull the plate out through
its own opening.

    PYTHONPATH=. .venv/bin/python parts/barrel_plate.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

corner_r = 3.0
cham = 0.4

with BuildPart() as barrel_plate:
    with BuildSketch(Plane.XY):
        RectangleRounded(bplate_w, bplate_h, corner_r)
    extrude(amount=bplate_th)

    # the jack bore
    with BuildSketch(Plane.XY):
        Circle(barrel_bore_dia / 2)
    extrude(amount=bplate_th, mode=Mode.SUBTRACT)

    # four M3 clearance holes, matching the case wall
    with BuildSketch(Plane.XY):
        with Locations(*[(sx * bplate_screw_off, sy * bplate_screw_off)
                         for sx in (1, -1) for sy in (1, -1)]):
            Circle(bplate_screw_dia / 2)
    extrude(amount=bplate_th, mode=Mode.SUBTRACT)

    chamfer(barrel_plate.faces().sort_by(Axis.Z)[0].edges(), cham)

# --- checks ---
assert barrel_bore_dia < barrel_flange_dia, "bore is wider than the jack flange"
assert bplate_th < barrel_thread_len, \
    f"plate {bplate_th} mm exceeds the jack's {barrel_thread_len} mm of thread"
# the plate must overlap the case opening on every side, or it falls through
_overlap = (bplate_w - bplate_open) / 2
assert _overlap >= 4.0, f"only {_overlap:.1f} mm of overlap onto the case wall"
# screws must land on that overlap, not in mid-air over the opening
assert bplate_screw_off > bplate_open / 2 + bplate_screw_dia / 2, \
    "screw holes fall inside the case opening"
assert bplate_screw_off + bplate_screw_dia / 2 < bplate_w / 2 - 1.5, \
    "screw holes break out of the plate edge"
# and clear the jack's flange
assert (2 * bplate_screw_off ** 2) ** 0.5 > barrel_flange_dia / 2 + bplate_screw_dia / 2, \
    "screw heads foul the jack flange"

print(f"plate {bplate_w:.0f} x {bplate_h:.0f} x {bplate_th:.0f} | bore {barrel_bore_dia} mm"
      f"{'  ** PROVISIONAL **' if barrel_bore_provisional else ''}"
      f" | overlap {_overlap:.1f} mm onto the wall")

show(barrel_plate)
export_stl(barrel_plate.part, "stl/barrel_plate.stl")

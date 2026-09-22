"""shorting_box.py — the far-end short for the noise-floor test, and a cable tester.

A five-sided shell, open at the BOTTOM, carrying one `NC3MD-L-B` chassis male with
**pins 2-3 bridged and pin 1 unconnected**. It stands in for the geophone at the far
end of the run, so the recorder sees its own electronics plus the whole installed
cable and nothing else.

WHY A BOX AND NOT A BARE PLUG. The bare plug (BACKLOG) measures the same short, but
it dangles: the last stretch of cable ends up routed differently from how it is
routed in service, and cable pickup is exactly what this test is trying to quantify.
This box sits where the geophone sits, at the geophone's own connector height
(`short_xlr_z`, matched to `parts/geophone_case.py`), so the cable drapes the way it
always does and the ONLY thing the test changes is the sensor.

AND IT IS A CABLE TESTER. The mic cable is female->male, so any such cable plugs
into this box at one end and the Pi enclosure at the other. The station's own
archive is then the instrument: swap cables, compare quiet-hour floors, and the
difference is that cable. That makes this a permanent piece of test equipment
rather than a one-night prop -- which is also why it is worth engraving.

THE GENDER IS NOT A CHOICE. `doc/BOM-geophone-case.md`: the cable is female->male,
the sensor case carries a chassis MALE (NC3MDX-TOP), the Pi enclosure a chassis
female (NC3FD-L-B). Anything replacing the geophone is therefore male. This box uses
the plain indoor **NC3MD-L-B**, not the IP65 NC3MDX-TOP -- it spends a night on the
slab, not a winter, and the L-B is the standard D-series cutout `parts/xlr_coupon.py`
already validated against the real part. No new coupon, no Neutrik DXF.

NO TERMINATION RESISTOR, and that is settled with a number rather than a preference:
the coil's Johnson noise is sqrt(4kTR) = 2.46 nV/rtHz against a measured quiet-night
floor of 214 nV/rtHz over 1-15 Hz -- 87x below, 0.013 % of the noise power. A dead
short and a 375 ohm resistor give indistinguishable answers, so the box stays dumb.

WATCH THE FIRST MINUTE FOR RAILING. Bridging 2-3 fixes the differential at zero but
leaves common mode to the board's bias network. If it rails, link the pair to pin 1
as well -- there is room on the connector's own solder cups.

Assembly is one joint: bridge pins 2 and 3 on the connector BEFORE screwing it into
the wall, because once it is in there is no way back inside. That is why there is no
lid and no fasteners beyond the connector's own two M3s.

BUILT 2026-09-22, and one thing was harder than it looks. **Threading the remoter of
the two nuts is awkward** -- this is a five-sided shell open only at the bottom, so the
nuts sit ~20.5 mm and ~43.5 mm up inside a 52 x 42 mm cavity and you work blind through
the open face. Charles's fix, which is worth knowing generally: **daub a fingertip with
a glue stick and the nut sticks to it by tack**, so it can be carried in and held against
the hole without a third hand.

**Do not "fix" this with a captive hex pocket or a heat-set insert.** There is no room.
The screw pattern sits hypot(11.5, 10) = 15.24 mm from the bore centre; with a 12.0 mm
bore radius and a 1.7 mm screw hole that leaves **1.54 mm of web**. An M3 nut's
circumradius is 3.18 mm, so a pocket would reach 12.07 mm from the centre -- through the
bore wall. A heat-set insert is barely better. D-series geometry has nothing behind those
screws, which is also why `dimensions.py` specifies a washer and a plain nut.

The calibrator box does not inherit this: it is an open tray with a removable lid, so its
four XLR nuts are reachable from directly above.

PRINT IT IN RED (Charles, 2026-09-22), and treat that as the convention rather than a
whim: **red means a test fixture that must come out of the run again.** Permanent
hardware -- the geophone case, the calibrator box -- prints in whatever is loaded.
There are about to be three boxes with XLRs on one cable, two of which belong there
permanently and one of which silently turns the station into a dead short, and the
failure mode is not noticing at 6 a.m. that the sensor never went back on. The
pre-flight check is then one glance: **is there anything red in the run?**

Print CLOSED FACE DOWN -- i.e. upside-down from how it is used -- so the roof lands
on the bed and the open face is uppermost. No supports. The XLR pad is a 1.5 mm
overhang off a vertical wall, which bridges, the same as on the calibrator box.

    PYTHONPATH=. .venv/bin/python parts/shorting_box.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

# Same validated seat geometry as parts/xlr_coupon.py and parts/calibrator_case.py.
_maj, _min = xlr_screw_off_major, xlr_screw_off_minor
_v = xlr_flange_axis.upper() == "V"
hole_dx, hole_dz = (_min, _maj) if _v else (_maj, _min)
seat_w = (xlr_flange_h if _v else xlr_flange_w) + xlr_seat_clearance
seat_h = (xlr_flange_w if _v else xlr_flange_h) + xlr_seat_clearance
panel_th = short_wall + xlr_pad_proud - xlr_seat_depth

_face_y = short_y / 2                       # the wall the connector sits on
_cut = short_wall + xlr_pad_proud + 6.0


with BuildPart() as shorting_box:
    with BuildSketch(Plane.XY):
        RectangleRounded(short_x, short_y, short_corner_r)
    extrude(amount=short_h)

    # Hollow from the OPEN face (z=0) up to the underside of the roof.
    with BuildSketch(Plane.XY):
        RectangleRounded(short_x - 2 * short_wall, short_y - 2 * short_wall,
                         max(short_corner_r - short_wall, 0.5))
    extrude(amount=short_h - short_roof, mode=Mode.SUBTRACT)

    # ---- XLR pad, seat, bore and the four-hole pattern ---------------------
    with Locations(Location((0, _face_y + xlr_pad_proud / 2, short_xlr_z))):
        Box(xlr_pad_w, xlr_pad_proud, xlr_pad_h)
    with Locations(Location((0, _face_y + xlr_pad_proud - xlr_seat_depth / 2,
                             short_xlr_z))):
        Box(seat_w, xlr_seat_depth, seat_h, mode=Mode.SUBTRACT)

    with Locations(Location((0, _face_y, short_xlr_z), (90, 0, 0))):
        Cylinder(xlr_bore_dia / 2, 2 * _cut, mode=Mode.SUBTRACT)
    for sx in (1, -1):
        for sz in (1, -1):
            with Locations(Location((sx * hole_dx, _face_y,
                                     short_xlr_z + sz * hole_dz), (90, 0, 0))):
                Cylinder(xlr_screw_dia / 2, 2 * _cut, mode=Mode.SUBTRACT)

    # ---- engraved on the roof ---------------------------------------------
    # A box with an XLR on it that is actually a dead short is exactly the object
    # that gets plugged in by mistake on a dark morning. Say what it is.
    with BuildSketch(Plane.XY.offset(short_h)):
        Text(short_label, font_size=short_label_h)
    extrude(amount=-short_label_depth, mode=Mode.SUBTRACT)


# --- checks -------------------------------------------------------------------
assert xlr_bore_dia > xlr_shell_dia, "bore is smaller than the connector shell"
assert 1.0 <= panel_th <= xlr_panel_th_max, f"panel is {panel_th} mm, outside 1-3"
_r = (_maj ** 2 + _min ** 2) ** 0.5
assert _r - xlr_screw_dia / 2 - xlr_bore_dia / 2 > 0.8, "no web left beside the bore"

_pad_margin = min(short_xlr_z - xlr_pad_h / 2,
                  short_h - (short_xlr_z + xlr_pad_h / 2))
assert _pad_margin > 2.0, f"only {_pad_margin:.1f} mm of wall around the XLR pad"
assert short_x - 2 * short_corner_r > xlr_pad_w, "pad wider than the flat wall run"
assert short_y - 2 * short_wall > xlr_body_depth, (
    f"interior is {short_y - 2 * short_wall} mm deep; the connector needs "
    f"{xlr_body_depth}")
# The whole reason for matching: same connector height as the sensor it replaces.
assert short_xlr_z == 32.0, (
    "short_xlr_z must match geophone_case.py's floor_th + 24; if that moved, "
    "the cable no longer drapes the same and the test gains a variable")
assert short_label_depth < short_roof, "the engraving would break through the roof"

print(f"shorting box {short_x} x {short_y} x {short_h} mm outside, "
      f"{short_wall} mm wall, open bottom")
print(f"  NC3MD-L-B (chassis MALE) at z={short_xlr_z} — same height as the geophone "
      f"case's XLR, so the cable drapes unchanged")
print(f"  seat {seat_w:.1f} x {seat_h:.1f} x {xlr_seat_depth} deep, "
      f"{panel_th:.1f} mm panel, {_pad_margin:.1f} mm wall margin")
print(f"  interior {short_x - 2*short_wall} x {short_y - 2*short_wall} x "
      f"{short_h - short_roof}, connector intrudes {xlr_body_depth}")

show(shorting_box)
export_stl(shorting_box.part, "stl/shorting_box.stl")

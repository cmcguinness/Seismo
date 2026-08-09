"""case_cover.py — domed shell carrying the three panel jacks. Drops over case_base.

One of three parts (Charles, 2026-08-08): BASE + COVER + HANDLE. This is the big,
slow print, which is exactly why the board mounting was moved OUT of it — iterating
on standoffs must not mean reprinting this.

Open-bottomed shell: its rim lands on the base's top face and four #6 screws pull
the two together, into the bosses in the corners here.

CONNECTORS ARE SPLIT BY MEANING (Charles, 2026-08-08): the sensor comes in one side,
the outside world leaves by the other.
  +Y wall  — XLR, the geophone. Same wall as the interface board, so the uV run
             is short.
  -Y wall  — Ethernet + 5 V. The Pi wall, and the noisy pair kept away from the
             front end.
Both use the D-series cutout validated on parts/xlr_coupon.py, and the coupon
confirmed 2026-08-08 that the RJ45 feedthrough takes the same one. The 5 V bore is
12 mm, also from the coupon.

Jacks share one centreline and ride ABOVE everything inside — that is what lets the
floor carry boards right up to both walls instead of reserving a band behind them.
The clearance is set against the TALLEST obstacle anywhere in the cavity, which is
the Pi stack, not the component row.

Print rim-down (open side on the bed). The roof is the last layer; the connector
pads and their recesses print on vertical walls with no support.

    PYTHONPATH=. .venv/bin/python parts/case_cover.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

top_z = cav_h + cover_top_th        # local z=0 is the rim, on the base's top face

# handle mount pads, inside the roof, so a #6 pilot has material to bite
handle_pad_dia = 14.0
handle_pad_h = 8.0

AIM = {"+Y": Rotation(-90, 0, 0), "-Y": Rotation(90, 0, 0),
       "+X": Rotation(0, 90, 0), "-X": Rotation(0, -90, 0)}


def _thru(dia, start, aim, length):
    """Cylinder of `dia` from `start` along `aim`. Mode.PRIVATE is load-bearing: a
    bare Cylinder() inside BuildPart adds itself on the spot, silently turning a
    cutter into a solid plug (geophone_case.py learned this on the STL)."""
    cyl = Cylinder(dia / 2, length, align=(Align.CENTER, Align.CENTER, Align.MIN),
                   mode=Mode.PRIVATE)
    return Location(start) * (AIM[aim] * cyl)


_v = xlr_flange_axis.upper() == "V"
_seat_w = (xlr_flange_h if _v else xlr_flange_w) + xlr_seat_clearance
_seat_h = (xlr_flange_w if _v else xlr_flange_h) + xlr_seat_clearance
_dx, _dz = ((xlr_screw_off_minor, xlr_screw_off_major) if _v
            else (xlr_screw_off_major, xlr_screw_off_minor))

with BuildPart() as case_cover:
    with BuildSketch(Plane.XY):
        RectangleRounded(case_x, case_y, case_corner_r)
    extrude(amount=top_z)
    with BuildSketch(Plane.XY):
        RectangleRounded(cav_x, cav_y, corner_inner_r)
    extrude(amount=cav_h, mode=Mode.SUBTRACT)

    # --- corner bosses: the base screws up into these ---
    # Inset only 4 mm so each merges into the rounded corner wall, stiffening both
    # and staying clear of the Pi, whose corner otherwise reaches within ~3 mm.
    with Locations(*[(sx * asm_x, sy * asm_y, 0) for sx in (1, -1) for sy in (1, -1)]):
        Cylinder(asm_boss_dia / 2, cav_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(*[(sx * asm_x, sy * asm_y, 0) for sx in (1, -1) for sy in (1, -1)]):
        Cylinder(pilot_6 / 2, asm_pilot_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

    # --- handle mount: bearing pads INSIDE the roof + clearance holes through it ---
    # The handle screws in from inside, so the roof carries the screw HEAD, not a
    # thread. Thicken it locally: a #6 head bearing on 3 mm of PLA is what lets go
    # when the case is lifted.
    with Locations(*[(px, py, cav_h) for px, py in handle_screw_pts]):
        Cylinder(handle_pad_dia / 2, handle_pad_h,
                 align=(Align.CENTER, Align.CENTER, Align.MAX))
    with Locations(*[(px, py, cav_h - handle_pad_h) for px, py in handle_screw_pts]):
        Cylinder(clear_6 / 2, handle_pad_h + cover_top_th,
                 align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

    # --- D-series seats: XLR on +Y, Ethernet on -Y ---
    # Plane.XZ's normal is -Y, so offset(-wy) lands on +Y and offset(+wy) on -Y;
    # extruding along +normal pushes the pad OUTWARD in both cases.
    _wy = case_y / 2
    for _cx, _side in ((xlr_cx, "+Y"), (eth_cx, "-Y")):
        _sgn = -1 if _side == "+Y" else 1
        with BuildSketch(Plane.XZ.offset(_sgn * _wy)):
            with Locations((_cx, panel_z)):
                RectangleRounded(xlr_pad_w, xlr_pad_h, 3.0)
        extrude(amount=_sgn * xlr_pad_proud)
        with BuildSketch(Plane.XZ.offset(_sgn * (_wy + xlr_pad_proud))):
            with Locations((_cx, panel_z)):
                Rectangle(_seat_w, _seat_h)
        extrude(amount=-_sgn * xlr_seat_depth, mode=Mode.SUBTRACT)

    # A cutter must pierce ONE wall, not the whole box. Running it the length of the
    # case drills a matching hole through the OPPOSITE wall -- which is exactly what
    # happened once the jacks were split across +Y and -Y, and it is invisible to a
    # volume or manifold check. Start each cutter just inside its own wall.
    _pierce = case_wall + xlr_pad_proud + 5.0
    for _cx, _side in ((xlr_cx, "+Y"), (eth_cx, "-Y")):
        _y_in = (cav_y / 2 - 1.0) * (1 if _side == "+Y" else -1)
        add(_thru(xlr_bore_dia, (_cx, _y_in, panel_z), _side, _pierce), mode=Mode.SUBTRACT)
        for _sx in (1, -1):
            for _sz in (1, -1):
                add(_thru(xlr_screw_dia, (_cx + _sx * _dx, _y_in, panel_z + _sz * _dz),
                          _side, _pierce), mode=Mode.SUBTRACT)

    # 5 V barrel jack: plain bore on -Y, hex nut on the flat inner face
    add(_thru(barrel_bore_dia, (barrel_cx, -(cav_y / 2 - 1.0), barrel_z), "-Y", _pierce),
        mode=Mode.SUBTRACT)

    # The rim is NOT a solid face -- it is an annulus with four bosses merged into
    # it -- so `faces().sort_by(Axis.Z)[0]` grabs a boss underside and the chamfer
    # fails. Take the horizontal face at z=0 with the largest area (the rim itself)
    # and chamfer only its OUTER wire.
    _rim = max((f for f in case_cover.faces().filter_by(Plane.XY)
                if abs(f.center().Z) < 1e-6), key=lambda f: f.area)
    chamfer(_rim.outer_wire().edges(), edge_cham)


# --- checks ---
_flat_half = cav_x / 2 - corner_inner_r
assert abs(xlr_cx) + xlr_pad_w / 2 < _flat_half, "XLR pad runs into the corner radius"
assert abs(eth_cx) + xlr_pad_w / 2 < _flat_half, "Ethernet pad runs into the corner radius"
assert abs(barrel_cx) + nut_clear < _flat_half, "5 V jack runs into the corner radius"
assert barrel_cx - nut_clear > eth_cx + xlr_pad_w / 2, "5 V jack fouls the Ethernet pad"
assert panel_z - xlr_bore_dia / 2 > tall_inside, "a jack bore would land on a board"
assert panel_z + xlr_bore_dia / 2 < cav_h, "a jack bore breaks through the roof"
_panel_th = case_wall + xlr_pad_proud - xlr_seat_depth
assert 1.0 <= _panel_th <= xlr_panel_th_max, f"panel is {_panel_th} mm, outside 1-3"
_web = (_dx ** 2 + _dz ** 2) ** 0.5 - xlr_screw_dia / 2 - xlr_bore_dia / 2
assert _web > 0.8, f"only {_web:.2f} mm of web between a screw hole and its bore"
assert asm_pilot_depth < cav_h, "corner pilot is deeper than the boss"
# A corner boss must stay INSIDE the outer corner skin. The outer corner is an arc of
# radius case_corner_r centred at (case_x/2 - r, case_y/2 - r); a boss whose centre is
# d from that point reaches d + boss_r. Exceed the radius and the boss erupts through
# the outside of the case -- which at asm_inset=4 it did, by 0.07 mm, and the only
# symptom was the rim chamfer refusing to build.
_ccx, _ccy = case_x / 2 - case_corner_r, case_y / 2 - case_corner_r
_d = ((asm_x - _ccx) ** 2 + (asm_y - _ccy) ** 2) ** 0.5
_skin = case_corner_r - (_d + asm_boss_dia / 2)
assert _skin > 1.0, (
    f"corner boss leaves {_skin:.2f} mm of skin at the rounded corner "
    f"(negative = it breaks through the outside of the case)")
# The roof bears the screw HEAD now, so what matters is bearing thickness, not depth.
assert cover_top_th + handle_pad_h >= 8.0, \
    "too little roof under the handle screw heads -- this is the joint that carries the case"
for _hx, _hy in handle_screw_pts:
    assert (abs(_hx) + handle_pad_dia / 2 < cav_x / 2
            and abs(_hy) + handle_pad_dia / 2 < cav_y / 2), "handle pad overruns the cavity"
    for _sx in (1, -1):
        for _sy in (1, -1):
            _dd = ((_hx - _sx * asm_x) ** 2 + (_hy - _sy * asm_y) ** 2) ** 0.5
            assert _dd > (handle_pad_dia + asm_boss_dia) / 2 + 1.0, \
                "handle pad collides with a corner boss"
_brim = 5.0
assert case_x + 2 * _brim <= 180 and case_y + 2 * _brim <= 180, \
    f"cover is {case_x:.0f} x {case_y:.0f}; with brim that exceeds the 180 mm bed"

print(f"cover {case_x:.0f} x {case_y:.0f} x {top_z:.0f} mm (cavity {cav_x:.0f} x {cav_y:.0f}"
      f" x {cav_h:.0f}) | panel z {panel_z:.0f} | +Y XLR | -Y ETH x={eth_cx:.0f},"
      f" 5V x={barrel_cx:.0f} | panel {_panel_th:.1f} mm, web {_web:.2f} mm")

show(case_cover)
export_stl(case_cover.part, "stl/case_cover.stl")

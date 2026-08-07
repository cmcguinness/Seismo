"""panel_coupon.py — fit test for the TWO new panel connectors, before the case print.

Same doctrine as xlr_coupon.py: prove the cutouts against the real parts on a
~15 minute print instead of discovering them in a ~5 hour case print. The XLR is
already validated and is NOT re-tested here.

TWO things on one plate:

  1. BARREL JACK — a LADDER of candidate bores, 9.5 .. 13.0 mm in 0.5 steps, each
     with its size engraved beside it. The RuiLing jack's thread OD is not
     published anywhere trustworthy, and even a caliper reading would not survive
     print shrinkage. So do not measure: thread the actual jack through the ladder
     and use the smallest bore it passes. That number goes into dimensions.py as
     `barrel_bore_dia` and the ladder is never needed again.

     Every ladder bore stays under the 14.0 mm flange OD so the jack cannot fall
     through whichever hole it ends up in.

  2. ETHERNET D-TYPE — one D-series cutout, reusing the XLR's already-validated
     bore and hole pattern. This is a GO/NO-GO on one question: is the RJ45
     coupler's flange really D-series? If it seats and the screws line up, the
     case can treat Ethernet and XLR as the same cutout. If not, the coupler
     needs its own dimensions and this is the cheap place to find that out.

Panel under the barrel jack is `wall` (3.0 mm), well inside the jack's 11.8 mm of
thread, so the hex nut has plenty to bite.

Print face down, no supports.

    PYTHONPATH=. .venv/bin/python parts/panel_coupon.py
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

wall = 3.0              # matches geophone_case.py and xlr_coupon.py
corner_r = 4.0
label_h = 4.0           # engraved digit height
label_depth = 0.6       # engrave, not emboss: no elephant-foot on the first layer
ladder_pitch = 17.0     # centre-to-centre within a ladder row
ladder_cols = 4         # 2 rows of 4, not 1 row of 8 -- keeps the coupon small.
                        # A fit test should be cheap; a 148 mm plate was ~60 g of
                        # PLA to answer one question.
ladder_row_gap = 22.0   # between the two ladder rows. Must clear the largest bore
                        # (r 6.5) PLUS the label below it, or the 4 mm digits run
                        # into the next row's hole.

_n = len(barrel_ladder)
_rows = -(-_n // ladder_cols)                       # ceil
plate_x = ladder_cols * ladder_pitch + 12.0
plate_y = _rows * ladder_row_gap + 62.0
_y_top = plate_y / 2 - 15.0                         # first ladder row
_y_eth = _y_top - (_rows - 1) * ladder_row_gap - 34.0   # D-series cutout, below

# ladder positions: row-major, centred
_x0 = -(ladder_cols - 1) * ladder_pitch / 2
_pos = [(_x0 + (i % ladder_cols) * ladder_pitch,
         _y_top - (i // ladder_cols) * ladder_row_gap) for i in range(_n)]

with BuildPart() as panel_coupon:
    with BuildSketch(Plane.XY):
        RectangleRounded(plate_x, plate_y, corner_r)
    extrude(amount=wall)

    # --- barrel-jack ladder ---
    with BuildSketch(Plane.XY):
        for (x, y), d in zip(_pos, barrel_ladder):
            with Locations((x, y)):
                Circle(d / 2)
    extrude(amount=wall, mode=Mode.SUBTRACT)

    # --- Ethernet D-series cutout: bore + all four hole positions ---
    with BuildSketch(Plane.XY):
        with Locations((0, _y_eth)):
            Circle(eth_bore_dia / 2)
        for sx in (1, -1):
            for sy in (1, -1):
                with Locations((sx * xlr_screw_off_minor,
                                _y_eth + sy * xlr_screw_off_major)):
                    Circle(xlr_screw_dia / 2)
    extrude(amount=wall, mode=Mode.SUBTRACT)

    # --- engraved size labels, one under each ladder bore ---
    with BuildSketch(Plane.XY.offset(wall)):
        # BELOW each bore, not beside it: at 17 mm pitch a label placed to the
        # right of a 13 mm bore overlaps the next bore in the row.
        for (x, y), d in zip(_pos, barrel_ladder):
            with Locations((x, y - max(barrel_ladder) / 2 - 2.0)):
                Text(f"{d:g}", font_size=label_h, align=(Align.CENTER, Align.MAX))
    extrude(amount=-label_depth, mode=Mode.SUBTRACT)

# --- checks that must hold before this is worth printing ---
assert max(barrel_ladder) < barrel_flange_dia, \
    "a ladder bore is bigger than the jack flange -- the jack would fall through"
assert wall < barrel_thread_len, \
    f"panel {wall} mm exceeds the jack's {barrel_thread_len} mm of thread"
assert ladder_pitch > max(barrel_ladder) + 3.0, "ladder bores are too close together"
_label_bottom = max(barrel_ladder) / 2 + 2.0 + label_h      # below a bore centre
assert ladder_row_gap > _label_bottom + max(barrel_ladder) / 2 + 1.5, (
    f"row gap {ladder_row_gap} lets labels run into the next row's bores")
_eth_web = ((xlr_screw_off_major ** 2 + xlr_screw_off_minor ** 2) ** 0.5
            - xlr_screw_dia / 2 - eth_bore_dia / 2)
assert _eth_web > 0.8, f"only {_eth_web:.2f} mm of web on the Ethernet cutout"
assert _y_eth - eth_flange_w / 2 > -plate_y / 2 + 3.0, "Ethernet flange overruns the plate"

print(f"ladder {barrel_ladder} mm | pitch {ladder_pitch} | plate {plate_x:.0f} x {plate_y:.0f}"
      f" | eth bore {eth_bore_dia} web {_eth_web:.2f} mm | panel {wall} mm")

show(panel_coupon)
export_stl(panel_coupon.part, "stl/panel_coupon.stl")

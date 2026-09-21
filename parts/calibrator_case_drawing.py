"""calibrator_case_drawing.py — panel elevations for the calibration injector box.

Writes parts/calibrator_case.png: the two drilled walls and the tray plan, at
scale, with every hole centre dimensioned. Everything is read from dimensions.py
and from parts/calibrator_case.py's own placement rule, so the drawing cannot drift
from the model the way a screenshot does.

WHY A DRAWING RATHER THAN A RENDER. A shaded 3D view of a box is a picture of a
box. What this part actually needs checking against is a set of hole positions on
two flat walls, and that is what you hold a caliper to -- or drill by hand if the
1/4" jack bushing turns out not to pass a 10 mm bore.

    PYTHONPATH=. .venv/bin/python parts/calibrator_case_drawing.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyBboxPatch
from dimensions import *

# Must match parts/calibrator_case.py.
JACK_X, BUTTON_X = -20.0, 20.0
_maj, _min = xlr_screw_off_major, xlr_screw_off_minor
_v = xlr_flange_axis.upper() == "V"
hole_dy, hole_dz = (_min, _maj) if _v else (_maj, _min)
seat_w = (xlr_flange_h if _v else xlr_flange_w) + xlr_seat_clearance
seat_h = (xlr_flange_w if _v else xlr_flange_h) + xlr_seat_clearance

EDGE = "#37474f"
HOLE = "#c62828"
GHOST = "#b0bec5"
DIM = "#546e7a"


def outline(ax, w, h, r, x0=0.0, y0=0.0, **kw):
    ax.add_patch(FancyBboxPatch((x0 - w / 2 + r, y0 + r), w - 2 * r, h - 2 * r,
                                boxstyle=f"round,pad={r}", linewidth=1.6,
                                edgecolor=kw.get("ec", EDGE), facecolor="none"))


def hole(ax, x, y, d, label=None, lw=1.4):
    ax.add_patch(Circle((x, y), d / 2, fill=False, edgecolor=HOLE, linewidth=lw))
    ax.plot([x - d / 2 - 2, x + d / 2 + 2], [y, y], color=HOLE, lw=0.5)
    ax.plot([x, x], [y - d / 2 - 2, y + d / 2 + 2], color=HOLE, lw=0.5)
    if label:
        ax.annotate(label, (x, y - d / 2 - 4.5), ha="center", va="top",
                    fontsize=7.5, color=HOLE)


def dim_h(ax, x1, x2, y, text, off=0.0):
    ax.annotate("", (x1, y + off), (x2, y + off),
                arrowprops=dict(arrowstyle="<->", color=DIM, lw=0.8))
    ax.text((x1 + x2) / 2, y + off + 1.2, text, ha="center", va="bottom",
            fontsize=7, color=DIM)


def dim_v(ax, y1, y2, x, text):
    ax.annotate("", (x, y1), (x, y2), arrowprops=dict(arrowstyle="<->", color=DIM,
                                                      lw=0.8))
    ax.text(x + 1.5, (y1 + y2) / 2, text, ha="left", va="center", fontsize=7,
            color=DIM, rotation=90)


fig = plt.figure(figsize=(15.5, 9.2))
gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.25], hspace=0.28, wspace=0.16)

# ---------------------------------------------------------------- END WALL
ax = fig.add_subplot(gs[0, 0])
ax.set_title("END WALL (both ends)  —  J1 geophone side / J2 Pi side\n"
             "looking at the outside face", fontsize=9.5)
outline(ax, cal_case_y, cal_case_h, cal_corner_r)
ax.add_patch(Rectangle((-xlr_pad_w / 2, cal_xlr_z - xlr_pad_h / 2),
                       xlr_pad_w, xlr_pad_h, fill=False, edgecolor=EDGE,
                       linewidth=1.1, linestyle="-"))
ax.add_patch(Rectangle((-seat_w / 2, cal_xlr_z - seat_h / 2), seat_w, seat_h,
                       fill=False, edgecolor=GHOST, linewidth=1.0, linestyle="--"))
hole(ax, 0, cal_xlr_z, xlr_bore_dia, f"bore Ø{xlr_bore_dia:g}", lw=1.8)
for sy in (1, -1):
    for sz in (1, -1):
        hole(ax, sy * hole_dy, cal_xlr_z + sz * hole_dz, xlr_screw_dia)
ax.text(0, cal_case_h + 8.5,
        f"pad {xlr_pad_w:g}×{xlr_pad_h:g}, {xlr_pad_proud:g} proud   ·   "
        f"seat {seat_w:.1f}×{seat_h:.1f} × {xlr_seat_depth:g} deep (dashed)",
        ha="center", va="bottom", fontsize=7, color=DIM)
ax.text(0, -4.5, f"4 × Ø{xlr_screw_dia:g} at ±{hole_dy:g}, ±{hole_dz:g}  —  all four "
                 f"signs, so handedness is a non-issue",
        ha="center", va="top", fontsize=7, color=DIM)
dim_v(ax, 0, cal_xlr_z, cal_case_y / 2 + 2, f"{cal_xlr_z:g}")
dim_h(ax, -cal_case_y / 2, cal_case_y / 2, cal_case_h + 3, f"{cal_case_y:g}")
ax.set_xlim(-cal_case_y / 2 - 16, cal_case_y / 2 + 16)
ax.set_ylim(-13, cal_case_h + 16)
ax.set_aspect("equal"); ax.axis("off")

# --------------------------------------------------------------- SIDE WALL
ax = fig.add_subplot(gs[0, 1])
ax.set_title("+Y SIDE WALL  —  J3 1/4\" jack and SW1 button\n"
             "looking at the outside face", fontsize=9.5)
outline(ax, cal_case_x, cal_case_h, cal_corner_r)
hole(ax, JACK_X, cal_xlr_z, ts_bore_dia, f"J3  Ø{ts_bore_dia:g}", lw=1.8)
hole(ax, BUTTON_X, cal_xlr_z, cal_button_bore, f"SW1  Ø{cal_button_bore:g}", lw=1.8)
for sx in (1, -1):
    ax.plot([sx * (cal_cav_x / 2 - xlr_body_depth)] * 2, [0, cal_case_h],
            color=GHOST, lw=1.0, ls=":")
ax.text(-cal_cav_x / 2 + xlr_body_depth / 2, cal_case_h - 5,
        "XLR body\nintrudes here", ha="center", va="top", fontsize=6.5, color=GHOST)
ax.text(cal_cav_x / 2 - xlr_body_depth / 2, cal_case_h - 5,
        "XLR body\nintrudes here", ha="center", va="top", fontsize=6.5, color=GHOST)
dim_h(ax, JACK_X, BUTTON_X, cal_xlr_z + 9, f"{BUTTON_X - JACK_X:g}")
dim_h(ax, -cal_case_x / 2, cal_case_x / 2, cal_case_h + 3, f"{cal_case_x:g}")
dim_v(ax, 0, cal_xlr_z, cal_case_x / 2 + 3, f"{cal_xlr_z:g}")
ax.text(0, 2.5, "NEITHER bore is coupon-validated — drill out if the part will not pass",
        ha="center", va="bottom", fontsize=7, color=HOLE)
ax.set_xlim(-cal_case_x / 2 - 12, cal_case_x / 2 + 12)
ax.set_ylim(-6, cal_case_h + 14)
ax.set_aspect("equal"); ax.axis("off")

# -------------------------------------------------------------------- PLAN
ax = fig.add_subplot(gs[1, :])
ax.set_title("TRAY PLAN  —  looking down into the open box  "
             "(lid removed; the lid is this outline with the four Ø3.4 holes only)",
             fontsize=9.5)
outline(ax, cal_case_x, cal_case_y, cal_corner_r, y0=-cal_case_y / 2)
ax.add_patch(FancyBboxPatch((-cal_cav_x / 2 + cal_inner_r,
                             -cal_cav_y / 2 + cal_inner_r),
                            cal_cav_x - 2 * cal_inner_r, cal_cav_y - 2 * cal_inner_r,
                            boxstyle=f"round,pad={cal_inner_r}", linewidth=1.2,
                            edgecolor=EDGE, facecolor="none"))

# board bay
ax.add_patch(Rectangle((-cal_board_x / 2, cal_board_cy - cal_board_y / 2),
                       cal_board_x, cal_board_y, fill=False, edgecolor="#2e7d32",
                       linewidth=1.2, linestyle="--"))
ax.text(0, cal_board_cy, f"perfboard bay\n{cal_board_x:g} × {cal_board_y:g}",
        ha="center", va="center", fontsize=8, color="#2e7d32")

# the isolation barrier, carried onto the board
ax.plot([0, 0], [cal_board_cy - cal_board_y / 2 - 3,
                 cal_board_cy + cal_board_y / 2 + 3],
        color="#c0392b", lw=1.3, ls="--")
ax.text(-cal_board_x / 4, cal_board_cy + cal_board_y / 2 - 9.0, "CONTROL",
        ha="center", fontsize=7, color="#c0392b")
ax.text(cal_board_x / 4, cal_board_cy + cal_board_y / 2 - 9.0, "COIL",
        ha="center", fontsize=7, color="#c0392b")

for sx in (1, -1):
    for sy in (1, -1):
        hole(ax, sx * (cal_cav_x / 2 - cal_boss_inset),
             sy * (cal_cav_y / 2 - cal_boss_inset), pilot_m3, lw=1.2)
        hole(ax, sx * (cal_board_x / 2 - cal_board_hole_inset),
             cal_board_cy + sy * (cal_board_y / 2 - cal_board_hole_inset),
             pilot_m3, lw=1.2)
ax.text(-cal_case_x / 2 - 2, cal_cav_y / 2 - cal_boss_inset,
        f"lid boss\nM3 pilot Ø{pilot_m3:g}\n(×4)", ha="right", va="center",
        fontsize=7, color=DIM)
ax.text(0, cal_board_cy + cal_board_y / 2 + 4.0,
        f"board standoffs {cal_standoff_h:g} mm tall, M3 pilot (×4)",
        ha="center", va="bottom", fontsize=7, color=DIM)

# XLR bodies, plan view
for sx in (1, -1):
    ax.add_patch(Rectangle((sx * cal_cav_x / 2 - (0 if sx < 0 else xlr_body_depth),
                            -xlr_shell_dia / 2), xlr_body_depth, xlr_shell_dia,
                           fill=False, edgecolor=GHOST, linewidth=1.0, ls=":"))
ax.text(-cal_cav_x / 2 + xlr_body_depth / 2, 0, f"J1\n{xlr_body_depth:g} deep",
        ha="center", va="center", fontsize=7, color=DIM)
ax.text(cal_cav_x / 2 - xlr_body_depth / 2, 0, f"J2\n{xlr_body_depth:g} deep",
        ha="center", va="center", fontsize=7, color=DIM)

# jack / button bodies, plan view
for _x, _d, _lbl in ((JACK_X, ts_body_depth, "J3"), (BUTTON_X, cal_button_depth, "SW1")):
    ax.add_patch(Rectangle((_x - ts_nut_clear / 2, cal_cav_y / 2 - _d),
                           ts_nut_clear, _d, fill=False, edgecolor=GHOST,
                           linewidth=1.0, ls=":"))
    ax.text(_x, cal_cav_y / 2 - _d / 2, _lbl, ha="center", va="center", fontsize=7,
            color=DIM)

# cell-holder strip
ax.add_patch(Rectangle((-cal_cav_x / 2, -cal_cav_y / 2), cal_cav_x, 6.0,
                       fill=True, facecolor="#fff3e0", edgecolor="#ef6c00",
                       linewidth=1.0, ls="--"))
ax.text(0, -cal_cav_y / 2 + 3, "coin-cell holders mount on THIS wall",
        ha="center", va="center", fontsize=6.8, color="#ef6c00")

dim_h(ax, -cal_case_x / 2, cal_case_x / 2, cal_case_y / 2 + 4, f"{cal_case_x:g}")
dim_v(ax, -cal_case_y / 2, cal_case_y / 2, cal_case_x / 2 + 4, f"{cal_case_y:g}")
ax.set_xlim(-cal_case_x / 2 - 30, cal_case_x / 2 + 16)
ax.set_ylim(-cal_case_y / 2 - 16, cal_case_y / 2 + 14)
ax.set_aspect("equal"); ax.axis("off")

fig.suptitle(
    f"Calibration injector box — {cal_case_x:g} × {cal_case_y:g} × {cal_case_h:g} mm "
    f"outside, {cal_wall:g} mm wall.  All dimensions mm.\n"
    "Every number here comes from dimensions.py; the model is parts/calibrator_case.py "
    "and parts/calibrator_lid.py.", fontsize=10.5)
fig.savefig("parts/calibrator_case.png", dpi=115, facecolor="white",
            bbox_inches="tight")
print("wrote parts/calibrator_case.png")

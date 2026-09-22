"""shorting_box_drawing.py — elevation and section for parts/shorting_box.py.

Writes parts/shorting_box.png. Numbers come from dimensions.py, so the drawing
cannot drift from the model. The section exists for one reason: to show the
connector height matched to the geophone case it replaces.

    PYTHONPATH=. .venv/bin/python parts/shorting_box_drawing.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyBboxPatch
from dimensions import *

_v = xlr_flange_axis.upper() == "V"
hole_dx, hole_dz = (xlr_screw_off_minor, xlr_screw_off_major) if _v else \
                   (xlr_screw_off_major, xlr_screw_off_minor)
seat_w = (xlr_flange_h if _v else xlr_flange_w) + xlr_seat_clearance
seat_h = (xlr_flange_w if _v else xlr_flange_h) + xlr_seat_clearance

EDGE, HOLE, GHOST, DIM = "#37474f", "#c62828", "#b0bec5", "#546e7a"


def hole(ax, x, y, d, label=None, lw=1.4):
    ax.add_patch(Circle((x, y), d / 2, fill=False, edgecolor=HOLE, linewidth=lw))
    ax.plot([x - d / 2 - 2, x + d / 2 + 2], [y, y], color=HOLE, lw=0.5)
    ax.plot([x, x], [y - d / 2 - 2, y + d / 2 + 2], color=HOLE, lw=0.5)
    if label:
        ax.annotate(label, (x, y - d / 2 - 4.0), ha="center", va="top",
                    fontsize=7.5, color=HOLE)


def dim_v(ax, y1, y2, x, text):
    ax.annotate("", (x, y1), (x, y2),
                arrowprops=dict(arrowstyle="<->", color=DIM, lw=0.8))
    ax.text(x + 1.5, (y1 + y2) / 2, text, ha="left", va="center", fontsize=7.5,
            color=DIM, rotation=90)


def dim_h(ax, x1, x2, y, text):
    ax.annotate("", (x1, y), (x2, y),
                arrowprops=dict(arrowstyle="<->", color=DIM, lw=0.8))
    ax.text((x1 + x2) / 2, y + 1.0, text, ha="center", va="bottom", fontsize=7.5,
            color=DIM)


fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 6.2))

# ---------------------------------------------------- CONNECTOR WALL
ax1.set_title("CONNECTOR WALL — outside face\nNC3MD-L-B chassis MALE, "
              "pins 2–3 bridged inside", fontsize=9.5)
ax1.add_patch(FancyBboxPatch((-short_x / 2 + short_corner_r, short_corner_r),
                             short_x - 2 * short_corner_r,
                             short_h - 2 * short_corner_r,
                             boxstyle=f"round,pad={short_corner_r}", linewidth=1.6,
                             edgecolor=EDGE, facecolor="none"))
ax1.add_patch(Rectangle((-xlr_pad_w / 2, short_xlr_z - xlr_pad_h / 2),
                        xlr_pad_w, xlr_pad_h, fill=False, edgecolor=EDGE, lw=1.1))
ax1.add_patch(Rectangle((-seat_w / 2, short_xlr_z - seat_h / 2), seat_w, seat_h,
                        fill=False, edgecolor=GHOST, lw=1.0, ls="--"))
hole(ax1, 0, short_xlr_z, xlr_bore_dia, f"bore Ø{xlr_bore_dia:g}", lw=1.8)
for sx in (1, -1):
    for sz in (1, -1):
        hole(ax1, sx * hole_dx, short_xlr_z + sz * hole_dz, xlr_screw_dia)
dim_v(ax1, 0, short_xlr_z, short_x / 2 + 3, f"{short_xlr_z:g}")
dim_h(ax1, -short_x / 2, short_x / 2, short_h + 3, f"{short_x:g}")
ax1.text(0, -6.0, "OPEN FACE — sits on the slab", ha="center", va="top",
         fontsize=8, color=DIM)
ax1.text(0, short_h + 9.5,
         f"the same validated cutout as xlr_coupon.py:\n"
         f"pad {xlr_pad_w:g}×{xlr_pad_h:g} × {xlr_pad_proud:g} proud, seat "
         f"{seat_w:.1f}×{seat_h:.1f} × {xlr_seat_depth:g} deep, 4 × Ø{xlr_screw_dia:g}",
         ha="center", va="bottom", fontsize=7.5, color=DIM)
ax1.set_xlim(-short_x / 2 - 18, short_x / 2 + 18)
ax1.set_ylim(-16, short_h + 22)
ax1.set_aspect("equal"); ax1.axis("off")

# ---------------------------------------------------- SECTION
ax2.set_title("SECTION — why the height is not arbitrary", fontsize=9.5)
# outer
ax2.add_patch(Rectangle((-short_y / 2, 0), short_y, short_h, fill=False,
                        edgecolor=EDGE, lw=1.6))
# cavity (open at the bottom)
ax2.add_patch(Rectangle((-short_y / 2 + short_wall, 0),
                        short_y - 2 * short_wall, short_h - short_roof,
                        facecolor="#eceff1", edgecolor=EDGE, lw=1.0, ls="--"))
# connector body intruding
ax2.add_patch(Rectangle((short_y / 2 - xlr_body_depth,
                         short_xlr_z - xlr_shell_dia / 2),
                        xlr_body_depth, xlr_shell_dia, fill=False,
                        edgecolor=GHOST, lw=1.1, ls=":"))
ax2.text(short_y / 2 - xlr_body_depth / 2, short_xlr_z + xlr_shell_dia / 2 + 1.5,
         f"connector body, {xlr_body_depth:g} deep", ha="center", va="bottom",
         fontsize=7, color=DIM)
ax2.plot([-short_y / 2 - 10, short_y / 2 + 16], [0, 0], color="#6d4c41", lw=2.2)
ax2.text(-short_y / 2 - 9, -3.5, "garage slab", fontsize=8, color="#6d4c41",
         va="top")
ax2.annotate("", (short_y / 2 + 10, 0), (short_y / 2 + 10, short_xlr_z),
             arrowprops=dict(arrowstyle="<->", color="#c0392b", lw=1.1))
ax2.text(short_y / 2 + 11.5, short_xlr_z / 2,
         f"{short_xlr_z:g} mm — the SAME height as\nthe geophone case's XLR\n"
         f"(geophone_case.py: floor_th 8 + 24)",
         fontsize=8, color="#c0392b", va="center")
ax2.text(0, short_h - short_roof / 2, "roof", ha="center", va="center", fontsize=7,
         color=DIM)
ax2.text(0, 8.0,
         "hollow, open below — no lid, no fasteners.\n"
         "Bridge 2–3 on the connector BEFORE fitting it.",
         ha="center", va="center", fontsize=7.5, color=DIM)
dim_v(ax2, 0, short_h, -short_y / 2 - 6, f"{short_h:g}")
ax2.set_xlim(-short_y / 2 - 22, short_y / 2 + 52)
ax2.set_ylim(-14, short_h + 14)
ax2.set_aspect("equal"); ax2.axis("off")

fig.suptitle(f"Shorting / cable-test box — {short_x:g} × {short_y:g} × {short_h:g} mm "
             f"outside, {short_wall:g} mm wall.  All dimensions mm.", fontsize=11)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig("parts/shorting_box.png", dpi=115, facecolor="white", bbox_inches="tight")
print("wrote parts/shorting_box.png")

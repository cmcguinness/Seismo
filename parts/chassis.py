"""chassis.py — combined base: geophone pocket + Raspberry Pi 2B mount.

MVP: an OPEN mounting tray (no walls/lid yet). One flat plate carries the
geophone coupling pocket and four drop-over standoffs for the Pi 2B. The plate
is sized to the eventual envelope, including Wi-Fi dongle clearance, so walls
added later will clear everything. Verify the Pi + geophone physically fit,
then add walls, a Pi/geophone divider, and a lid.

LAYOUT (from the user's Pi 2B photo + drawing):
  - Pi board centered at origin, long axis = X (85mm), short axis = Y (56mm).
  - -Y long edge: GPIO 40-pin header + HAT. Its two FREE mount holes take the
    locating pins.
  - +Y long edge: power / HDMI / audio, plus the Pi<->HAT standoff nuts + HAT
    screw terminals -> the single flat support post. (A wall here needs a power
    cutout later.)
  - -X short edge: USB + Ethernet + Wi-Fi dongle. Plate extends `usb_support_ext`
    to underlie the USB connectors; the dongle overhangs into air / a future wall
    slot (keeps the plate printable on the 180mm bed).
  - +X short edge: DSI/RUN only -> port-free, so the geophone pocket goes here;
    wire notch faces -X (toward the Pi/HAT).
  - Pi held by 2 locating pins in the FREE (GPIO-side) mount holes. The opposite
    (USB-side) holes are occupied by the user's Pi<->HAT standoffs, with NUTS
    protruding below the board there — so that edge gets a single flat support
    post placed between the two nuts. 3-point support (2 pins + 1 post) = stable,
    nut-clear. No screws yet (gravity + putty).
"""
from build123d import *
from ocp_vscode import show
from dimensions import *

# --- geophone pocket (matches geophone_base.py) ---
wall = 3.0
floor = 4.0
bore_dia = geophone_dia + 2 * fit_clearance
pocket_depth = geophone_height
pocket_outer = bore_dia + 2 * wall
wire_slot_w = 6.0

# --- plate + Pi mount ---
plate_th = 4.0
margin = 6.0
gap = 5.0                       # clearance between Pi board edge and pocket
standoff_dia = 6.0
pin_dia = pi_hole_dia - 0.15    # locating pin (snug slip fit through the Pi hole)
pin_extra = 5.0                 # protrudes above the board for the cotter
cotter_hole_dia = 1.5           # transverse hole for a solid-wire cotter (near the
                                # max the ~2.6mm pin allows before walls get too thin)

# geophone pocket: off the +X short edge (the port-free DSI end), centered on the
# board's width.
pocket_cx = pi_len / 2 + gap + pocket_outer / 2
pocket_cy = 0.0

# USB + dongle exit the -X short edge. Plate extends far enough to underlie the
# USB connectors; the dongle overhangs into air / a future wall slot, so the
# plate stays printable on the 180mm bed.
usb_support_ext = 20.0

# plate extents: +X holds the geophone, -X supports the USB connectors.
x_min = -pi_len / 2 - usb_support_ext
x_max = pocket_cx + pocket_outer / 2 + margin
y_min = -pi_wid / 2 - margin
y_max = pi_wid / 2 + margin
plate_x, plate_y = x_max - x_min, y_max - y_min
plate_cx, plate_cy = (x_min + x_max) / 2, (y_min + y_max) / 2

# Pi mount points. GPIO side = -Y (free holes -> locating pins). USB side = +Y
# (holes occupied by Pi<->HAT standoffs + nuts -> a single flat post BETWEEN the
# two nuts, no pin, nothing over a nut).
gpio_pin_pts = [(pi_hole_offset_x + sx * pi_hole_dx / 2, -pi_hole_dy / 2)
                for sx in (-1, 1)]
usb_support_pts = [(pi_hole_offset_x, pi_hole_dy / 2)]  # center of the USB edge

with BuildPart() as chassis:
    # base plate
    with Locations((plate_cx, plate_cy, 0)):
        Box(plate_x, plate_y, plate_th,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

    # geophone pocket (floor = plate top; coupling path -> plate -> ground)
    with Locations((pocket_cx, pocket_cy, plate_th)):
        Cylinder(pocket_outer / 2, pocket_depth,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((pocket_cx, pocket_cy, plate_th)):
        Cylinder(bore_dia / 2, pocket_depth + 1,
                 align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    # wire notch, facing -X (toward the Pi/terminals)
    with Locations((pocket_cx - pocket_outer / 2, pocket_cy, plate_th + pocket_depth)):
        Box(2 * wall + 2, wire_slot_w, 8,
            align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)

    # standoffs under all three support points
    with Locations(*[(px, py, plate_th) for px, py in gpio_pin_pts + usb_support_pts]):
        Cylinder(standoff_dia / 2, pi_standoff_h,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    # locating pins in the two free GPIO-side holes, standing proud of the board
    with Locations(*[(px, py, plate_th + pi_standoff_h) for px, py in gpio_pin_pts]):
        Cylinder(pin_dia / 2, pin_extra,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    # transverse cotter hole in each pin, ~1.5mm above the board top. Axis along Y
    # (perpendicular to the GPIO header on the -Y edge) so the wire inserts toward
    # open space, not alongside the header. Drill/ream clean after printing.
    cotter_z = plate_th + pi_standoff_h + pi_board_th + 1.5
    with Locations(*[Location((px, py, cotter_z), (90, 0, 0)) for px, py in gpio_pin_pts]):
        Cylinder(cotter_hole_dia / 2, pin_dia + 2, mode=Mode.SUBTRACT)

show(chassis)
export_stl(chassis.part, "stl/chassis.stl")

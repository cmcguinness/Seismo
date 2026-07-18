"""starter.py — template part. Copy this file to begin a new part."""
from build123d import *
from ocp_vscode import show
from dimensions import *   # shared dims live in dimensions.py

# --- parameters (mm) ---
size = 10  # 1 cm cube, à la Blender

# --- model ---
with BuildPart() as part:
    Box(size, size, size)

# --- view / export ---
show(part)
# export_stl(part.part, "stl/starter.stl")   # uncomment to export

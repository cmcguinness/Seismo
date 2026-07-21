#!/usr/bin/env python3
"""heli_render.py — draw the helicorder drum from precomputed interval envelopes.

The DUMB, fast half of the fix: no miniSEED, no obspy, no signal processing.
Load the ~32 per-interval npz files that heli_build.py banked, stack them into a
1920x1080 drum plot, return PNG bytes. This is what a web request hits, so it
must be cheap enough to render on every pull (or serve pre-rendered).

Scaling (see dashboard/HELICORDER.md): one global counts->pixels factor keyed to
the median interval sigma so amplitude is comparable across rows and refreshes.
1 sigma ~= 1/4 of the row spacing; excursions clip at +/-3 rows (a "big" event
swings 3 lines up and down, then clips -- dramatic but not lossy).
"""
import datetime
import glob
import io
import os

import numpy as np

HELI = os.environ.get("SEISMO_HELI", "/data/heli")
STATION = os.environ.get("SEISMO_STATION", "OAKMT")
NETWORK = os.environ.get("SEISMO_NETWORK", "XX")
LOCATION = os.environ.get("SEISMO_LOCATION", "00")
CHANNEL = os.environ.get("SEISMO_CHANNEL", "SHZ")
PLACE = os.environ.get("SEISMO_PLACE", "Oakmont, Santa Rosa, CA")
SID = f"{NETWORK}.{STATION}.{LOCATION}.{CHANNEL}"

IMG_W, IMG_H = 1920, 1080
MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 85, 15, 72, 48   # labels 5 px from edge, plot starts at 85;
                                                          # top holds the 3-line webicorder header
                                                          # (gutter clears the HH:MM label); bottom = x-axis
INTERVAL_MIN = 15                             # minutes per row (x-axis span)
PLOT_W = IMG_W - MARGIN_L - MARGIN_R          # 1835
PLOT_H = IMG_H - MARGIN_T - MARGIN_B          # 1010
ENV_FRAC = 0.15                               # median envelope excursion -> this fraction
                                              # of a row. Half the pixels exceed the
                                              # median (heavy upper tail), so the drawn
                                              # noise band reads ~2-3x this. By-eye knob;
                                              # final value set on real 8 h pi5 data.
CLIP_ROWS = 3.0                               # excursion clip, +/- rows
ROW_COLORS = ["#a01818", "#186a18", "#1c4fa0", "#111"]   # dark red, dark green, blue, black


def _load(heli_dir):
    """Load interval files, newest 8 h worth, sorted oldest-first (top-down)."""
    out = []
    for p in sorted(glob.glob(os.path.join(heli_dir, "heli.*.npz"))):
        try:
            with np.load(p) as d:
                out.append({"t0": float(d["t0"]), "mins": d["mins"],
                            "maxs": d["maxs"], "env": float(d["env"])})
        except Exception:
            pass
    out.sort(key=lambda r: r["t0"])
    return out


def helicorder_png(heli_dir=HELI, station_id=SID, place=PLACE):
    rows = _load(heli_dir)
    if not rows:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    n = len(rows)
    row_h = PLOT_H / max(n, 1)
    ev = np.array([r["env"] for r in rows], dtype=float)
    ev = ev[np.isfinite(ev) & (ev > 0)]
    env_ref = float(np.median(ev)) if ev.size else 1.0
    k = (row_h * ENV_FRAC) / env_ref              # counts -> pixels
    clip = CLIP_ROWS * row_h
    npix = rows[0]["mins"].size
    xs = MARGIN_L + (np.arange(npix) + 0.5) / npix * PLOT_W

    segs = []
    for r_i, r in enumerate(rows):
        base = MARGIN_T + (r_i + 0.5) * row_h
        lo = np.clip(k * r["mins"], -clip, clip)   # up = smaller y (inverted axis)
        hi = np.clip(k * r["maxs"], -clip, clip)
        good = np.isfinite(lo) & np.isfinite(hi)
        for i in np.nonzero(good)[0]:
            segs.append([(xs[i], base - hi[i]), (xs[i], base - lo[i])])

    fig = plt.figure(figsize=(IMG_W / 100, IMG_H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, IMG_W)
    ax.set_ylim(IMG_H, 0)                          # image coords: y down
    ax.axis("off")
    colors = [ROW_COLORS[i % len(ROW_COLORS)] for i, r in enumerate(rows)
              for _ in np.nonzero(np.isfinite(np.clip(k * r["maxs"], -clip, clip))
                                  & np.isfinite(r["mins"]))[0]]
    ax.add_collection(LineCollection(segs, colors=colors, linewidths=0.6))

    for r_i, r in enumerate(rows):                 # per-row HH:MM label (left)
        base = MARGIN_T + (r_i + 0.5) * row_h
        lbl = datetime.datetime.fromtimestamp(
            r["t0"], datetime.timezone.utc).strftime("%H:%M")
        ax.text(5, base, lbl, ha="left", va="center",
                fontsize=16, color="#444", family="monospace")

    # header (USGS/PNSN webicorder style): date · station · location
    last = rows[-1]
    valid = np.nonzero(np.isfinite(last["maxs"]))[0]
    end_frac = (valid[-1] + 1) / last["maxs"].size if valid.size else 1.0
    end = datetime.datetime.fromtimestamp(
        last["t0"] + end_frac * INTERVAL_MIN * 60, datetime.timezone.utc)
    d0 = datetime.datetime.fromtimestamp(rows[0]["t0"], datetime.timezone.utc).date()
    date_txt = (f"{end:%Y-%m-%d}" if d0 == end.date()
                else f"{d0:%Y-%m-%d} – {end:%Y-%m-%d}")
    ax.text(5, 6, f"{date_txt}  (UTC)", ha="left", va="top",
            fontsize=20, fontweight="bold", color="#222")
    ax.text(5, 33, station_id, ha="left", va="top",
            fontsize=15, color="#444", family="monospace")
    ax.text(5, 54, f"({place})", ha="left", va="top", fontsize=13, color="#666")
    ax.text(IMG_W - MARGIN_R, 8, f"data to {end:%H:%M} UTC", ha="right", va="top",
            fontsize=12, color="#888")

    # --- x-axis: a minute tick along the bottom (each row spans 15 min) ---
    axis_y = MARGIN_T + PLOT_H                 # bottom of the plot area
    ax.plot([MARGIN_L, MARGIN_L + PLOT_W], [axis_y, axis_y], color="#888", lw=0.8)
    for m in range(INTERVAL_MIN + 1):          # 0..15 min
        x = MARGIN_L + m / INTERVAL_MIN * PLOT_W
        ax.plot([x, x], [axis_y, axis_y + 6], color="#888", lw=0.8)
        ax.text(x, axis_y + 9, str(m), ha="center", va="top",
                fontsize=11, color="#666")
    ax.text(MARGIN_L + PLOT_W / 2, axis_y + 26, "minutes into each 15-min row",
            ha="center", va="top", fontsize=10, color="#888")

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


if __name__ == "__main__":
    import sys
    heli = sys.argv[1] if len(sys.argv) > 1 else HELI
    png = helicorder_png(heli)
    if not png:
        sys.exit(f"no interval files in {heli}")
    out = sys.argv[2] if len(sys.argv) > 2 else "heli_test.png"
    with open(out, "wb") as f:
        f.write(png)
    print(f"wrote {out} ({len(png)} bytes)")

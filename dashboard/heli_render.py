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
ENV_FRAC = float(os.environ.get("SEISMO_HELI_ENV_FRAC", "0.05"))
                                              # median envelope excursion -> this fraction
                                              # of a row. Half the pixels exceed the
                                              # median (heavy upper tail), so the drawn
                                              # noise band reads ~2-3x this. By-eye knob;
                                              # was 0.15, set on real 8 h pi5 data.
                                              # Cut to 0.05 (/3) on 2026-07-24: the
                                              # post-epoch front end is noisier, so rows
                                              # were spilling into their neighbours. Now
                                              # env-tunable -- `dokku config:set seismo
                                              # SEISMO_HELI_ENV_FRAC=0.15` to restore
                                              # without a rebuild once the floor is fixed.
CLIP_ROWS = 3.0                               # excursion clip, +/- rows
ROW_COLORS = ["#a01818", "#186a18", "#1c4fa0", "#111"]   # dark red, dark green, blue, black
# USGS catalog marks. Muted on purpose: they are an annotation over the data, and must
# never be mistaken for the trace itself or for a detection this station made.
# Hues are deliberately far apart: the first pass used #c2410c and #b45309, which are
# neighbouring oranges and indistinguishable at 10 pt (Charles could not tell "strong"
# from "likely"). Size varies with tier too, so the coding does not rely on colour
# alone. None of these collide with ROW_COLORS.
MARK_COLORS = {"strong": "#ea580c", "likely": "#7c3aed",
               "marginal": "#64748b", "unlikely": "#cbd5e1", "unknown": "#cbd5e1"}
MARK_SIZE = {"strong": (7.0, 2.0), "likely": (5.5, 1.5), "marginal": (4.5, 1.1),
             "unlikely": (3.5, 0.8), "unknown": (3.5, 0.8)}


WINDOW_H = float(os.environ.get("SEISMO_HELI_HOURS", "4"))   # hours per drum
INTERVAL_S = INTERVAL_MIN * 60


def _load(heli_dir, t_start=None, t_end=None):
    """Interval files in [t_start, t_end), sorted oldest-first (top-down).

    Bounds are epoch seconds; either may be None for open-ended. Selection is on
    the `t0` INSIDE each npz, not the filename, so a window that straddles the
    00:00 UTC day rollover needs no special handling.
    """
    out = []
    for p in sorted(glob.glob(os.path.join(heli_dir, "heli.*.npz"))):
        try:
            with np.load(p) as d:
                t0 = float(d["t0"])
                if (t_start is not None and t0 < t_start) or \
                   (t_end is not None and t0 >= t_end):
                    continue
                out.append({"t0": t0, "mins": d["mins"],
                            "maxs": d["maxs"], "env": float(d["env"])})
        except Exception:
            pass
    out.sort(key=lambda r: r["t0"])
    return out


def _blank_row(t0, npix):
    """Placeholder for an interval with no envelope on disk (gap, or before the
    archive starts). Keeps the drum's row-to-time mapping honest: a fixed window
    always draws the same number of rows, so a missing interval reads as an empty
    line rather than silently shifting every row below it."""
    nan = np.full(npix, np.nan, dtype=np.float32)
    return {"t0": t0, "mins": nan, "maxs": nan.copy(), "env": float("nan")}


def helicorder_png(heli_dir=HELI, station_id=SID, place=PLACE,
                   t_start=None, hours=None):
    """Drum PNG bytes for a time window, or None if it holds no data at all.

    t_start=None  -> the LIVE view: the newest `hours` worth of intervals on disk.
    t_start=<ts>  -> a HISTORICAL window: exactly [t_start, t_start + hours), with
                     missing intervals drawn as blank rows so the row-to-time
                     mapping stays fixed.
    """
    hours = WINDOW_H if hours is None else float(hours)
    if t_start is None:
        rows = _load(heli_dir)
        if rows:                                  # trim to the newest `hours`
            cut = rows[-1]["t0"] - (hours - 1) * 3600
            rows = [r for r in rows if r["t0"] >= cut]
        historical = False
    else:
        t_start = float(t_start) // INTERVAL_S * INTERVAL_S      # snap to interval
        t_end = t_start + hours * 3600
        have = {r["t0"]: r for r in _load(heli_dir, t_start, t_end)}
        if not have:
            return None
        npix = next(iter(have.values()))["mins"].size
        rows = [have.get(t, _blank_row(t, npix))
                for t in np.arange(t_start, t_end, INTERVAL_S)]
        historical = True
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
    start = datetime.datetime.fromtimestamp(rows[0]["t0"], datetime.timezone.utc)
    if historical:                                 # fixed window -> show its full span
        end = start + datetime.timedelta(hours=hours)
    d0 = start.date()
    date_txt = (f"{end:%Y-%m-%d}" if d0 == end.date()
                else f"{d0:%Y-%m-%d} – {end:%Y-%m-%d}")
    ax.text(5, 6, f"{date_txt}  (UTC)", ha="left", va="top",
            fontsize=20, fontweight="bold", color="#222")
    ax.text(5, 33, station_id, ha="left", va="top",
            fontsize=15, color="#444", family="monospace")
    ax.text(5, 54, f"({place})", ha="left", va="top", fontsize=13, color="#666")
    corner = (f"{start:%H:%M} – {end:%H:%M} UTC" if historical
              else f"data to {end:%H:%M} UTC")
    ax.text(IMG_W - MARGIN_R, 8, corner, ha="right", va="top",
            fontsize=12, color="#888")

    # --- USGS catalog marks: where a known quake SHOULD have landed ---
    # Drawn from a cache written by the poller; never touches the network here. The
    # mark sits at the PREDICTED P arrival (origin + hypo/5.19 + 0.30 s, the station's
    # own measured relation), so it points at where to look, not at what was found.
    # Deliberately NOT a detection claim -- the eye decides.
    try:
        import usgs_events
        marks = usgs_events.load()
    except Exception:
        marks = []
    if marks:
        t_lo = rows[0]["t0"]
        t_hi = rows[-1]["t0"] + INTERVAL_S
        seen = 0
        for ev in marks:
            ta = ev.get("arrival")
            if ta is None or not (t_lo <= ta < t_hi):
                continue
            r_i = int((ta - t_lo) // INTERVAL_S)
            if not (0 <= r_i < len(rows)):
                continue
            frac = (ta - rows[r_i]["t0"]) / INTERVAL_S
            x = MARGIN_L + frac * PLOT_W
            base = MARGIN_T + (r_i + 0.5) * row_h
            tier = ev.get("tier")
            color = MARK_COLORS.get(tier, "#999")
            msize, mlw = MARK_SIZE.get(tier, (4.5, 1.1))
            # a caret under the trace plus a tick, so it never hides the waveform
            y = base + row_h * 0.42
            ax.plot([x, x], [y, y - row_h * 0.18], color=color, lw=mlw,
                    solid_capstyle="butt", zorder=5)
            ax.plot([x], [y], marker="^", color=color, markersize=msize, zorder=5)
            ax.text(x + 4, y, f"M{ev.get('mag')}", ha="left", va="center",
                    fontsize=9, color=color, zorder=5)
            seen += 1
        if seen:
            # Each tier word is drawn in ITS OWN colour -- the whole point of the
            # legend is to decode the caret colours, and a single grey string says
            # nothing (which is what the first version did).
            x = IMG_W - MARGIN_R
            for key in ("marginal", "likely", "strong"):        # right to left
                ax.text(x, 30, key, ha="right", va="top", fontsize=10,
                        color=MARK_COLORS[key], zorder=5)
                ax.plot([x - 7.4 * len(key) - 13], [35], marker="^",
                        color=MARK_COLORS[key], markersize=MARK_SIZE[key][0],
                        zorder=5)
                # Step per WORD, not a constant: a fixed 62 px fitted "strong" and let
                # "marginal" collide with its neighbour.
                x -= 7.4 * len(key) + 32   # word + its caret + gap
            ax.text(x + 6, 30, "▲ USGS catalog, predicted arrival:", ha="right",
                    va="top", fontsize=10, color="#888", zorder=5)

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

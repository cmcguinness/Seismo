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
import threading

import numpy as np

# One lock for EVERY matplotlib render in this process (helicorder, history, spectrum,
# activity). pyplot's figure registry is not thread-safe, and the helicorder refresh
# runs in a background thread while /history.png renders in request threads: two
# overlapping renders produced a drum with half its rows missing (2026-08-26 06:06 UTC,
# seen by Charles; refresh fixed it). The figures below also use the object API
# (Figure + FigureCanvasAgg) so no pyplot global state is touched at all.
MPL_LOCK = threading.Lock()

HELI = os.environ.get("SEISMO_HELI", "/data/heli")
STATION = os.environ.get("SEISMO_STATION", "OAKM1")
NETWORK = os.environ.get("SEISMO_NETWORK", "SS")
LOCATION = os.environ.get("SEISMO_LOCATION", "00")
CHANNEL = os.environ.get("SEISMO_CHANNEL", "EHZ")
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
# --- cultural-noise shading -------------------------------------------------------
# A loud row is not necessarily an earthquake. Columns whose energy is mostly ABOVE
# 15 Hz can only come from a source metres away -- path attenuation strips that band
# from any real quake (measured: quakes 0.09-0.98, garage activity 1.95-5.26; see
# station/stalta.py). Those columns are drawn in a distinct colour so a burst reads as
# environmental at a glance instead of looking like a detection.
#
# ONLY columns that are also LOUD are coloured. A quiet column's ratio is measuring
# the noise floor, which is itself HF-dominated (the floor sits near 4.5), so
# colouring on ratio alone would tint the entire quiet drum.
CULTURAL_HF = float(os.environ.get("SEISMO_HELI_CULTURAL_HF", "1.4"))
CULTURAL_MIN_ENV = 3.0                        # x the row's own median excursion
# FADED, not recoloured (2026-08-14). Cyan was tried first and read as a signal in its
# own right; grey replaced it and receded, but it still OVERWROTE the trace -- a shaded
# burst lost its row colour entirely, which Charles found distracting and which breaks
# the drum's one reliable visual rule (row colour = which row you are reading).
# Cultural columns now keep their row colour and are drawn at CULTURAL_ALPHA, so the
# annotation costs the trace nothing but weight. Still on the lower zorder so a genuine
# arrival overlapping the same seconds draws over it at full strength.
CULTURAL_ALPHA = 0.5
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
                # `hf` (per-pixel >15/1-8 Hz ratio) is newer than the oldest
                # envelopes on disk; those render uncoloured rather than wrongly.
                nan = np.full(d["mins"].size, np.nan, dtype=np.float32)
                hf = d["hf"] if "hf" in d.files else nan
                # `lo_mins`/`lo_maxs` are the 1-8 Hz core of each column, on the same
                # counts scale as mins/maxs. Newer still than `hf`; where absent the
                # renderer falls back to fading the whole column.
                lo_mins = d["lo_mins"] if "lo_mins" in d.files else nan
                lo_maxs = d["lo_maxs"] if "lo_maxs" in d.files else nan
                out.append({"t0": t0, "mins": d["mins"], "maxs": d["maxs"],
                            "hf": hf, "lo_mins": lo_mins, "lo_maxs": lo_maxs,
                            "env": float(d["env"])})
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
    return {"t0": t0, "mins": nan, "maxs": nan.copy(), "hf": nan.copy(),
            "lo_mins": nan.copy(), "lo_maxs": nan.copy(), "env": float("nan")}


def helicorder_png(heli_dir=HELI, station_id=SID, place=PLACE,
                   t_start=None, hours=None):
    """Thread-safe entry point: see MPL_LOCK."""
    with MPL_LOCK:
        return _helicorder_png(heli_dir, station_id, place, t_start, hours)


def _helicorder_png(heli_dir, station_id, place, t_start, hours):
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
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
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

    segs, colors = [], []                 # true signal, drawn on top
    cult_segs, cult_colors = [], []       # local activity: same colour, drawn faded
    n_cultural = 0
    for r_i, r in enumerate(rows):
        base = MARGIN_T + (r_i + 0.5) * row_h
        lo = np.clip(k * r["mins"], -clip, clip)   # up = smaller y (inverted axis)
        hi = np.clip(k * r["maxs"], -clip, clip)
        good = np.isfinite(lo) & np.isfinite(hi)
        row_color = ROW_COLORS[r_i % len(ROW_COLORS)]
        # Cultural columns: high-frequency AND loud. `env` is this row's own median
        # excursion, so the loudness test is relative to the row -- a quiet row does
        # not get tinted just because the noise floor is HF-dominated.
        excursion = np.maximum(np.abs(r["mins"]), np.abs(r["maxs"]))
        ref = r["env"] if np.isfinite(r["env"]) and r["env"] > 0 else np.inf
        with np.errstate(invalid="ignore"):
            cultural = (np.nan_to_num(r["hf"], nan=0.0) >= CULTURAL_HF) & \
                       (np.nan_to_num(excursion, nan=0.0) >= CULTURAL_MIN_ENV * ref)
        # The 1-8 Hz CORE of each column, on the same counts scale. On a cultural
        # column this is the part of the excursion that could be seismic at all: the
        # faded halo is what the total exceeds it by, which is HF and therefore local.
        c_lo = np.clip(k * r["lo_mins"], -clip, clip)
        c_hi = np.clip(k * r["lo_maxs"], -clip, clip)
        have_core = np.isfinite(c_lo) & np.isfinite(c_hi)
        for i in np.nonzero(good)[0]:
            seg = [(xs[i], base - hi[i]), (xs[i], base - lo[i])]
            if cultural[i]:
                cult_segs.append(seg)
                cult_colors.append(row_color)
                if have_core[i]:               # full-colour core inside the halo
                    segs.append([(xs[i], base - c_hi[i]), (xs[i], base - c_lo[i])])
                    colors.append(row_color)
            else:
                segs.append(seg)
                colors.append(row_color)
        n_cultural += int(cultural[good].sum())

    fig = Figure(figsize=(IMG_W / 100, IMG_H / 100), dpi=100)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, IMG_W)
    ax.set_ylim(IMG_H, 0)                          # image coords: y down
    ax.axis("off")
    if cult_segs:
        ax.add_collection(LineCollection(cult_segs, colors=cult_colors,
                                         alpha=CULTURAL_ALPHA,
                                         linewidths=0.6, zorder=1))
    ax.add_collection(LineCollection(segs, colors=colors, linewidths=0.6, zorder=2))

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
            # Label goes to the LEFT of the caret. The caret marks the PREDICTED
            # ARRIVAL, so everything after it is the burst the label would otherwise
            # be drawn on top of; the seconds before it are quiet by construction.
            # Flip back to the right only when the caret is too close to the left
            # edge for the label to fit.
            lbl = f"M{ev.get('mag')}"
            if x - 4 - 7.0 * len(lbl) >= MARGIN_L:
                ax.text(x - 4, y, lbl, ha="right", va="center",
                        fontsize=9, color=color, zorder=5)
            else:
                ax.text(x + 4, y, lbl, ha="left", va="center",
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

    # --- cultural-noise key: only drawn when something was actually shaded ---
    # Placed bottom-left, clear of the USGS tier legend along the top edge.
    if n_cultural:
        # Swatch mimics the drawing itself: a faded thick bar (the total excursion)
        # with a solid thin one through it (the 1-8 Hz core). A side-by-side pair was
        # tried and read as two separate things rather than one nested inside the other.
        ax.plot([MARGIN_L + 4, MARGIN_L + 26], [IMG_H - 14, IMG_H - 14],
                color=ROW_COLORS[0], lw=6.0, alpha=CULTURAL_ALPHA,
                solid_capstyle="butt", zorder=5)
        ax.plot([MARGIN_L + 4, MARGIN_L + 26], [IMG_H - 14, IMG_H - 14],
                color=ROW_COLORS[0], lw=1.8, solid_capstyle="butt", zorder=6)
        # The wording has to carry BOTH halves, or the fading misleads: faded is a
        # positive identification, but full strength is not a negative one. Only bursts
        # whose energy is unambiguously above 15 Hz get faded, so quieter or
        # lower-frequency local sources -- and anything the 1.4 cut lands near --
        # stay at full strength. Reading "not faded" as "earthquake" is the exact
        # confusion this legend exists to prevent.
        # Wording is length-constrained: the x-axis caption is centred at
        # MARGIN_L + PLOT_W/2, so anything past ~120 characters runs into it.
        ax.text(MARGIN_L + 32, IMG_H - 14,
                "faded = local (>15 Hz); solid core = its 1–8 Hz part, where a quake "
                "shows. Full-strength bursts may be local too",
                ha="left", va="center", fontsize=9, color="#666", zorder=5)

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

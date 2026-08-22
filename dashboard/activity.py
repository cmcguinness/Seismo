#!/usr/bin/env python3
"""activity.py — day x hour noise heatmaps, the station's portrait of local activity.

Two views of the same quantity, both built from the helicorder interval files that
`heli_build` already writes (no miniSEED decode, no obspy):

  "days"  the last N local days, one row each -- what happened lately
  "week"  every interval collapsed onto weekday x hour -- the typical week

The value in a cell is the median of that hour's interval `env` values, converted to
microvolts. `env` is the median per-pixel excursion the drum actually draws (see
HELICORDER.md), so it is a robust noise level, already de-meaned and high-passed at
1 Hz, and it costs nothing to reuse -- each interval file is ~8 KB and the grid is a
few hundred medians.

LOCAL TIME, not UTC, and that is the whole point: this chart is about people. A
portrait of human activity indexed by UTC hour would put the morning rush in the
middle of the night and be unreadable.

⚠️ The colour scale is ABSOLUTE (µV), so a change to the instrument or its siting
shows up as a step across rows and WILL be misread as the neighbourhood going quiet --
the first render of this chart was mostly the 2026-08-12 enclosure/siting change, not
activity at all. So the register in `analysis/epochs.py` is drawn on the chart as a
staircase, and the weekday view refuses to build until the current noise epoch is long
enough to fill one. `epochs.py` is NOT duplicated here: deploy.sh syncs the analysis
copy into the image (it is the kind of file that must never fork), and this module
degrades to "no marks" if the import fails.

Standalone render, for development against a local copy of the interval files:

    python activity.py <heli_dir> days out.png
"""
import datetime as dt
import glob
import os
from zoneinfo import ZoneInfo

import numpy as np

HELI = os.environ.get("SEISMO_HELI", "/data/heli")
TZ = ZoneInfo(os.environ.get("SEISMO_TZ", "America/Los_Angeles"))
GAIN = int(os.environ.get("SEISMO_GAIN", "64"))
UV_PER_COUNT = 2.5 * 2 / (GAIN * (2 ** 23 - 1)) * 1e6
DAYS = int(os.environ.get("SEISMO_ACTIVITY_DAYS", "7"))

IMG_W, IMG_H = 1500, 500
# SEQUENTIAL ramp: lightness falls monotonically from 0.925 to 0.345 (OKLCH L) across
# the 13 steps, so magnitude is carried by value alone and the chart still reads in
# greyscale, in print, and to a colourblind eye. Hue rotates blue -> violet -> magenta
# -> deep red along the way as a REDUNDANT second cue: the single-hue blue version was
# correct but muddy, with the whole 5-20 uV midrange landing on near-identical mid-blues
# (that band is most of the chart, and most of the day).
#
# This is NOT a diverging blue/red ramp, which would be wrong here: diverging encodes
# polarity around a meaningful midpoint and puts its palest step in the MIDDLE, so
# typical hours would vanish while both the quietest and the busiest shouted. Noise
# level has no midpoint. The lightness ramp is what makes this sequential; the hue
# travel is decoration on top of it.
#
# The warm end is a deep crimson rather than a bright red on purpose -- pure red is an
# intrinsically light colour, so reaching it would have broken the lightness monotonicity
# that does the actual encoding.
RAMP = ["#d4e9ff", "#bcd9ff", "#a8c8fc", "#98b7f8", "#8fa3f3", "#8e8deb", "#9175de",
        "#975bc9", "#9f3ea8", "#a0217e", "#960854", "#850030", "#71000d"]
SURFACE = "#fcfcfb"
INK, INK_2 = "#0b0b0b", "#52514e"
PRIOR = "#dcdbd7"      # cells from a superseded configuration: shown, but not scaled
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# A weekday x hour portrait is only meaningful once every weekday has been sampled a
# few times in ONE configuration. Below this, the cells are mostly single samples and
# the pattern is which weekday happened to fall in which epoch.
WEEK_MIN_DAYS = 14


def _boundaries():
    """[(utc_epoch, description)] for changes that move the noise floor.

    Single source of truth is `analysis/epochs.py`; deploy.sh copies it in. If it is
    not importable (a partial deploy, someone running this file bare) the chart simply
    draws no marks -- an unmarked chart is a smaller lie than a stale hardcoded list.
    """
    try:
        import epochs
    except ImportError:
        try:
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))
            import epochs
        except Exception:
            return []
    out = []
    for iso, _approx, affects, desc in epochs.BOUNDARIES:
        if {"noise", "amplitude"} & set(affects):
            out.append((epochs._t(iso).timestamp(), desc))
    return sorted(out)


def has_prior_cells(days=DAYS, now=None):
    """True if the day view currently contains cells from a superseded configuration.

    Pure date arithmetic against the boundary register -- deliberately NOT a call to
    `grid()`, which reads every interval file. The page only needs to know whether to
    explain the grey cells and the dashed staircase, and both appear exactly when the
    last configuration change falls inside the displayed date range.
    """
    now = dt.datetime.now(TZ) if now is None else now.astimezone(TZ)
    first = now.date() - dt.timedelta(days=days - 1)
    start = dt.datetime.combine(first, dt.time(0), tzinfo=TZ).timestamp()
    last = max([t for t, _ in _boundaries() if t <= now.timestamp()], default=None)
    return last is not None and last > start


def _pre_epoch_mask(values, got):
    """True for cells recorded BEFORE the last configuration change in the window."""
    labels, now = got["labels"], got["now"]
    last = max([t for t, _ in _boundaries() if t <= now.timestamp()], default=None)
    mask = np.zeros(values.shape, dtype=bool)
    if last is None:
        return mask
    when = dt.datetime.fromtimestamp(last, TZ)
    for r, lb in enumerate(labels):
        try:
            day = dt.datetime.strptime(f"{lb} {when.year}", "%a %d %b %Y").date()
        except ValueError:
            continue
        if day < when.date():
            mask[r, :] = True
        elif day == when.date():
            mask[r, :when.hour + 1] = True
    return mask


def _current_epoch_cells(values, got):
    """Cell values from after the last configuration change inside the window."""
    keep = ~_pre_epoch_mask(values, got) & np.isfinite(values)
    return values[keep]


def _ink_on(rgba):
    """Black or white, whichever has more contrast on that fill.

    Was `white if val > sqrt(lo*hi)`, which silently assumed the fill at the scale's
    geometric mean was dark -- true of the old single-hue blue ramp, not of a ramp whose
    middle is a mid-violet. Ask the colour, not the value.
    """
    def _lum(c):
        c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c[:3]]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    l = _lum(rgba)
    return "#ffffff" if (1.05 / (l + 0.05)) > ((l + 0.05) / 0.05) else INK


def _intervals(heli_dir):
    """[(utc_epoch, env_uv)] for every interval file that carries a usable envelope."""
    out = []
    for p in sorted(glob.glob(os.path.join(heli_dir, "heli.*.npz"))):
        try:
            with np.load(p) as d:
                env = float(d["env"])
                if np.isfinite(env) and env > 0:
                    out.append((float(d["t0"]), env * UV_PER_COUNT))
        except Exception:
            pass                      # a torn file must not take the page down
    return out


def grid(heli_dir=HELI, mode="days", days=DAYS, now=None):
    """(values, counts, row_labels, hour_labels, subtitle) for the requested view.

    values[r][h] is the median µV for that cell, NaN where no interval landed in it;
    counts[r][h] is how many did, which the caller uses to mark thin cells.
    """
    rows = _intervals(heli_dir)
    if not rows:
        return None
    now = dt.datetime.now(TZ) if now is None else now.astimezone(TZ)
    local = [(dt.datetime.fromtimestamp(t, TZ), v) for t, v in rows]

    if mode == "week":
        # ONE configuration only. Mixing epochs here does not merely add noise, it
        # invents pattern: before 2026-08-12 the floor was ~4x higher, so whichever
        # weekdays fell on the old side come out "busy" for a reason that has nothing
        # to do with the neighbourhood.
        bounds = [t for t, _ in _boundaries()]
        start = max([t for t in bounds if t <= now.timestamp()], default=0.0)
        local = [(d, v) for d, v in local if d.timestamp() >= start]
        if not local:
            return None
        span_days = (now.timestamp() - max(start, min(d.timestamp() for d, _ in local))) / 86400
        if span_days < WEEK_MIN_DAYS:
            return {"short": True, "have": span_days, "need": WEEK_MIN_DAYS,
                    "since": dt.datetime.fromtimestamp(start, TZ)}
        keys = [d.weekday() for d, _ in local]
        labels = WEEKDAYS
        subtitle = (f"{span_days:.0f} days since the last configuration change, "
                    "collapsed onto one week")
    else:
        # Most recent `days` local dates ending today, oldest at the top -- same
        # reading order as the drum.
        today = now.date()
        wanted = [today - dt.timedelta(days=i) for i in range(days - 1, -1, -1)]
        index = {d: i for i, d in enumerate(wanted)}
        keys = [index.get(d.date(), -1) for d, _ in local]
        labels = [f"{d:%a} {d:%-d %b}" for d in wanted]
        subtitle = f"{wanted[0]:%-d %b} &ndash; {wanted[-1]:%-d %b} &middot; local time"

    n_rows = len(labels)
    buckets = [[[] for _ in range(24)] for _ in range(n_rows)]
    for (d, v), r in zip(local, keys):
        if 0 <= r < n_rows:
            buckets[r][d.hour].append(v)
    values = np.full((n_rows, 24), np.nan)
    counts = np.zeros((n_rows, 24), dtype=int)
    for r in range(n_rows):
        for h in range(24):
            b = buckets[r][h]
            counts[r][h] = len(b)
            if b:
                values[r][h] = float(np.median(b))
    first = min(d for d, _ in local)
    return {"values": values, "counts": counts, "labels": labels,
            "subtitle": subtitle, "mode": mode, "first": first, "now": now}


def heatmap_png(heli_dir=HELI, mode="days", days=DAYS, now=None):
    """PNG bytes for the day x hour heatmap, or None if there is nothing to draw."""
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, LogNorm

    got = grid(heli_dir, mode=mode, days=days, now=now)
    if not got or got.get("short"):
        return None
    values, counts, labels = got["values"], got["counts"], got["labels"]
    finite = values[np.isfinite(values)]
    if not finite.size:
        return None

    cmap = LinearSegmentedColormap.from_list("seismo_blue", RAMP)
    cmap.set_bad(SURFACE)                       # empty cells recede into the page
    # Robust limits, and LOG: the day/night swing is ~7x and the extremes are ~100x, so
    # a linear scale would paint every quiet hour the same near-white and throw away
    # exactly the detail this chart exists to show.
    # Scale off the CURRENT configuration only. Otherwise a hardware change three days
    # ago sets the top of the range and every cell since is squeezed into two shades --
    # the chart ends up depicting the change instead of the neighbourhood. Older rows
    # then saturate, which is the honest reading: they are a different instrument, and
    # the staircase plus the caption say so.
    scale_from = _current_epoch_cells(values, got) if mode == "days" else finite
    if scale_from.size < 12:
        scale_from = finite
    # p1/p99, not p2/p98: the current epoch is only a few days, so the high tail IS
    # the daytime peak this chart exists to show -- clipping it flattens every busy
    # hour to one shade.
    lo = max(float(np.percentile(scale_from, 1)), 1.0)
    hi = float(np.percentile(scale_from, 99))
    if hi <= lo * 1.5:
        hi = lo * 1.5

    fig = plt.figure(figsize=(IMG_W / 100, IMG_H / 100), dpi=100, facecolor=SURFACE)
    ax = fig.add_axes([0.085, 0.20, 0.845, 0.75])
    ax.set_facecolor(SURFACE)
    # Cells from BEFORE the last configuration change get a FLAT neutral grey, not a
    # colour off this ramp. Fading them was tried first and read as "quiet-ish": a
    # dimmed dark blue and a mid blue land on nearly the same grey, so half the chart
    # became a mid-tone smear that still invited comparison. They belong to a
    # different instrument; the honest encoding is "no value shown".
    norm = LogNorm(vmin=lo, vmax=hi)
    old_mask = _pre_epoch_mask(values, got) if mode == "days" else np.zeros(values.shape, bool)
    kw = dict(cmap=cmap, norm=norm, edgecolors=SURFACE, linewidth=1.6)
    x, y = np.arange(25), np.arange(len(labels) + 1)
    mesh = ax.pcolormesh(x, y, np.ma.masked_where(old_mask, np.ma.masked_invalid(values)), **kw)
    if old_mask.any():
        flatgrey = LinearSegmentedColormap.from_list("prior", [PRIOR, PRIOR])
        ax.pcolormesh(x, y, np.ma.masked_where(~(old_mask & np.isfinite(values)),
                                               np.ones_like(values)),
                      cmap=flatgrey, vmin=0, vmax=1,
                      edgecolors=SURFACE, linewidth=1.6)

    ax.set_xlim(0, 24)
    ax.set_ylim(len(labels), 0)                 # oldest/Monday at the top
    ax.set_xticks(np.arange(0, 25, 3))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 25, 3)], fontsize=10, color=INK_2)
    ax.set_yticks(np.arange(len(labels)) + 0.5)
    ax.set_yticklabels(labels, fontsize=10.5, color=INK)
    ax.tick_params(length=0, pad=6)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("hour of the day, local time", fontsize=10, color=INK_2, labelpad=8)

    # Selective direct labels: the loudest and quietest cells only, as a number in the
    # cell plus one caption line. A number in all 168 cells is the classic heatmap
    # anti-pattern -- it turns a picture back into a table. Leader lines were tried
    # first and collided with the top row.
    # Extremes are quoted from the CURRENT configuration when there is one in view:
    # "loudest 361 uV" off a retired instrument is a true number about nothing.
    flat = np.where(np.isfinite(values), values, np.nan)
    if mode == "days" and old_mask.any() and np.isfinite(flat[~old_mask]).sum() >= 12:
        flat = np.where(old_mask, np.nan, flat)
    caption, marks = [], []
    for idx, tag in ((np.nanargmax(flat), "loudest"), (np.nanargmin(flat), "quietest")):
        r, h = np.unravel_index(idx, flat.shape)
        val = flat[r, h]
        ax.text(h + 0.5, r + 0.5, f"{val:.0f}", ha="center", va="center", fontsize=8.5,
                color=_ink_on(cmap(norm(val))), zorder=4)
        caption.append(f"{tag} {val:.0f} µV ({labels[r]}, {h:02d}:00)")

    # Configuration changes, drawn as the staircase they actually are: time runs left
    # to right within a row and then down, so the boundary between "old instrument"
    # and "new" cuts across one row at the hour it happened. Labelled in the caption
    # rather than on the chart -- an inline label lands either on the cells or under
    # the colorbar.
    if mode == "days":
        for tstamp, desc in _boundaries():
            when = dt.datetime.fromtimestamp(tstamp, TZ)
            label = f"{when:%a} {when:%-d %b}"
            if label not in labels:
                continue
            r = labels.index(label)
            h = when.hour + when.minute / 60.0
            ax.plot([0, h, h, 24], [r, r, r + 1, r + 1], color=INK, lw=1.4,
                    dashes=(4, 3), zorder=6, solid_capstyle="butt")
            short = desc.split("--")[0].split(";")[0].strip()
            marks.append(f"{when:%-d %b} {short}")
    if old_mask.any():
        marks.append("grey cells are the configuration before it, not comparable")
    fig.text(0.085, 0.075, "   ·   ".join(caption), fontsize=9.5, color=INK_2)
    if marks:
        fig.text(0.085, 0.028, "dashed line: configuration change — " + "; ".join(marks),
                 fontsize=9, color=INK_2)

    # Cells built from fewer than half the expected intervals get a corner tick, so a
    # partial hour is never read as a genuinely quiet one.
    expect = 4 if mode == "days" else 4 * max(1, counts.max() // 4)
    for r in range(values.shape[0]):
        for h in range(24):
            if 0 < counts[r][h] < expect / 2:
                ax.plot([h + 0.12], [r + 0.15], marker="o", markersize=2.2,
                        color=SURFACE, zorder=5)

    cax = fig.add_axes([0.945, 0.20, 0.014, 0.75])
    cb = fig.colorbar(mesh, cax=cax, extend="max")
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=0, labelsize=9, colors=INK_2, pad=5)
    # Explicit ticks: matplotlib's log locator falls back to "6 x 10^0" style labels
    # over a narrow decade, which is unreadable on a chart whose whole point is
    # "how many microvolts".
    nice = [1, 1.5, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50, 80, 100, 150, 200, 300, 500]
    ticks = [t for t in nice if lo <= t <= hi]
    cb.set_ticks(ticks)
    cb.ax.set_yticklabels([f"{t:g}" for t in ticks])
    cb.ax.minorticks_off()
    cb.set_label("typical excursion, µV  (log scale)", fontsize=9.5, color=INK_2,
                 labelpad=10)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=SURFACE)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else HELI
    mode = sys.argv[2] if len(sys.argv) > 2 else "days"
    out = sys.argv[3] if len(sys.argv) > 3 else f"activity_{mode}.png"
    png = heatmap_png(d, mode=mode)
    if not png:
        sys.exit(f"no interval files in {d}")
    with open(out, "wb") as fh:
        fh.write(png)
    print(f"wrote {out} ({len(png)} bytes)")

#!/usr/bin/env python3
"""magtag.py — render pages for the MagTag, a 296x128 4-grey e-ink desk display.

The device is dumb on purpose: it fetches one finished bitmap and blits it. All
layout lives here, where a change is a deploy rather than a re-flash.

Wire format: an uncompressed 8-bit indexed BMP, TOP-DOWN (negative height), with a
4-entry palette whose indices ARE the e-ink grey levels (0 black .. 3 white). A
browser shows it as-is, so the page can be previewed; the MagTag reads the pixel
offset from bytes 10..13 and hands the rest straight to bitmaptools.arrayblit. 296
is a multiple of 4, so rows carry no padding.

Helicorder page: the same 15-min interval envelopes the big drum uses
(heli_build.py), re-binned into 1-hour rows ~278 px wide, so one pixel is ~13 s.
At this size an earthquake is a blob, not a waveform. That's all a glance-at-it
display is for.
"""
import datetime
import glob
import os
import struct
import threading

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import heli_render

W, H = 296, 128
BLACK, DARK, LIGHT, WHITE = 0, 1, 2, 3
PALETTE = [(0, 0, 0), (0x55, 0x55, 0x55), (0xAA, 0xAA, 0xAA), (0xFF, 0xFF, 0xFF)]

HOURS = float(os.environ.get("SEISMO_MAGTAG_HOURS", "12"))
ENV_FRAC = float(os.environ.get("SEISMO_MAGTAG_ENV_FRAC", "0.12"))
                                   # median RE-BINNED column excursion -> this fraction
                                   # of a row (~1 px on a 10 px row): a visible noise
                                   # band is the "is it alive" cue, and anything real
                                   # stands clear of it.
TZ = os.environ.get("SEISMO_MAGTAG_TZ", "America/Los_Angeles")
                                   # LOCAL time, unlike the big drum's UTC: this sits on a
                                   # desk and gets read as "that was at 3 am".
ROW_S = 3600
HEADER_H = 12
LABEL_W = 16
PLOT_X0 = LABEL_W + 2
PLOT_W = W - PLOT_X0
PLOT_Y0 = HEADER_H + 1
PLOT_H = H - PLOT_Y0


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TZ)
    except Exception:
        return datetime.timezone.utc


def _font(size):
    # DejaVu ships inside matplotlib, which the image already carries.
    import matplotlib
    path = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _fname(t0):
    d = datetime.datetime.fromtimestamp(t0, datetime.timezone.utc)
    return f"heli.{d:%Y}.{d:%j}.{d:%H%M}.npz"


def _newest_t0(heli_dir):
    """Start time of the newest interval on disk. By NAME, not by opening files:
    the directory holds every interval since the epoch began (5,000+), and the
    YYYY.JJJ.HHMM names sort chronologically."""
    names = glob.glob(os.path.join(heli_dir, "heli.*.npz"))
    if not names:
        return None
    _, y, j, hm, _ = os.path.basename(max(names)).split(".")
    d = (datetime.datetime(int(y), 1, 1, int(hm[:2]), int(hm[2:]),
                           tzinfo=datetime.timezone.utc)
         + datetime.timedelta(days=int(j) - 1))
    return d.timestamp()


def _interval(heli_dir, t0, npix):
    """One interval's columns, with a blank (all-NaN) stand-in when it's missing."""
    nan = np.full(npix, np.nan, dtype=np.float32)
    out = {"mins": nan, "maxs": nan, "lo_mins": nan, "lo_maxs": nan,
           "cult": np.zeros(npix, bool), "env": np.nan}
    try:
        with np.load(os.path.join(heli_dir, _fname(t0))) as d:
            mins, maxs = d["mins"], d["maxs"]
            if mins.size != npix:
                return out
            hf = d["hf"] if "hf" in d.files else nan
            env = float(d["env"])
            out.update(mins=mins, maxs=maxs, env=env,
                       lo_mins=d["lo_mins"] if "lo_mins" in d.files else nan,
                       lo_maxs=d["lo_maxs"] if "lo_maxs" in d.files else nan)
    except (OSError, KeyError, ValueError):
        return out
    # Same local-activity rule as the big drum: loud AND mostly above 15 Hz.
    ref = env if np.isfinite(env) and env > 0 else np.inf
    exc = np.maximum(np.abs(mins), np.abs(maxs))
    with np.errstate(invalid="ignore"):
        out["cult"] = ((np.nan_to_num(hf, nan=0.0) >= heli_render.CULTURAL_HF) &
                       (np.nan_to_num(exc, nan=0.0) >=
                        heli_render.CULTURAL_MIN_ENV * ref))
    return out


def _rebin(a, edges, fn):
    """Reduce columns into PLOT_W bins. fmin/fmax skip NaN unless the whole bin is NaN."""
    return fn.reduceat(a, edges[:-1])


def _to_bmp(img):
    """8-bit indexed, top-down BMP with a 4-colour palette (see module docstring)."""
    px = img.tobytes()
    pal = b"".join(bytes((b, g, r, 0)) for r, g, b in PALETTE)
    off = 14 + 40 + len(pal)
    hdr = struct.pack("<2sIHHI", b"BM", off + len(px), 0, 0, off)
    dib = struct.pack("<IiiHHIIiiII", 40, W, -H, 1, 8, 0, len(px),
                      2835, 2835, len(PALETTE), len(PALETTE))
    return hdr + dib + pal + px


def _render_heli(heli_dir, hours):
    newest = _newest_t0(heli_dir)
    if newest is None:
        return None
    tz = _tz()
    n_rows = max(1, int(hours))
    last_row = newest // ROW_S * ROW_S
    row_t0s = [last_row - (n_rows - 1 - i) * ROW_S for i in range(n_rows)]
    per_row = ROW_S // heli_render.INTERVAL_S          # 4 intervals per row
    npix = None
    for p in glob.glob(os.path.join(heli_dir, _fname(newest))):
        with np.load(p) as d:
            npix = d["mins"].size
    if not npix:
        return None

    rows = []
    for t in row_t0s:
        parts = [_interval(heli_dir, t + k * heli_render.INTERVAL_S, npix)
                 for k in range(per_row)]
        rows.append({key: np.concatenate([p[key] for p in parts])
                     for key in ("mins", "maxs", "lo_mins", "lo_maxs", "cult")}
                    )

    # Re-bin first, THEN scale. Each column is now the extreme of ~13 s of envelope,
    # which runs several times the interval's median excursion (`env`): keying the
    # scale to `env`, as the big drum does, filled every daytime row solid.
    edges = np.linspace(0, per_row * npix, PLOT_W + 1).astype(int)
    with np.errstate(invalid="ignore", all="ignore"):
        for r in rows:
            for key, fn in (("mins", np.fmin), ("maxs", np.fmax),
                            ("lo_mins", np.fmin), ("lo_maxs", np.fmax)):
                r[key] = _rebin(r[key], edges, fn)
            r["cult"] = np.logical_or.reduceat(r["cult"], edges[:-1])
        exc = np.concatenate([np.maximum(np.abs(r["mins"]), np.abs(r["maxs"]))
                              for r in rows])
    exc = exc[np.isfinite(exc) & (exc > 0)]
    if not exc.size:
        return None
    row_h = PLOT_H / n_rows
    k = row_h * ENV_FRAC / float(np.median(exc))
    knee = heli_render.ASINH_ROWS * row_h

    def squash(a):
        return knee * np.arcsinh(a / knee) if knee else a

    img = Image.new("P", (W, H), WHITE)
    img.putpalette([c for rgb in PALETTE for c in rgb])
    dr = ImageDraw.Draw(img)
    dr.fontmode = "1"                                   # no anti-aliasing on e-ink
    f_small, f_head = _font(9), _font(10)

    for i, r in enumerate(rows):
        base = PLOT_Y0 + (i + 0.5) * row_h
        with np.errstate(invalid="ignore"):
            lo, hi = squash(k * r["mins"]), squash(k * r["maxs"])
            clo, chi = squash(k * r["lo_mins"]), squash(k * r["lo_maxs"])
        cult = r["cult"]
        for x in range(PLOT_W):
            if not (np.isfinite(lo[x]) and np.isfinite(hi[x])):
                continue
            X = PLOT_X0 + x
            y0, y1 = round(base - hi[x]), round(base - lo[x])
            if cult[x]:
                # Faded halo is the >15 Hz (local) part; the 1-8 Hz core stays black.
                dr.line((X, y0, X, y1), fill=LIGHT)
                if np.isfinite(clo[x]) and np.isfinite(chi[x]):
                    dr.line((X, round(base - chi[x]), X, round(base - clo[x])), fill=BLACK)
            else:
                dr.line((X, y0, X, y1), fill=BLACK)
        lbl = datetime.datetime.fromtimestamp(row_t0s[i], tz).strftime("%H")
        dr.text((0, base), lbl, font=f_small, fill=DARK, anchor="lm")

    # USGS catalog: a small caret at the PREDICTED arrival, dark grey so it never
    # reads as trace. Only tiers that had a real chance of showing up.
    try:
        import usgs_events
        marks = usgs_events.load()
    except Exception:
        marks = []
    t_lo, t_hi = row_t0s[0], row_t0s[-1] + ROW_S
    for ev in marks:
        ta = ev.get("arrival")
        if ta is None or not (t_lo <= ta < t_hi) or \
                ev.get("tier") not in ("strong", "likely", "marginal"):
            continue
        i = int((ta - t_lo) // ROW_S)
        X = PLOT_X0 + int((ta - row_t0s[i]) / ROW_S * PLOT_W)
        y = PLOT_Y0 + (i + 1) * row_h - 1
        dr.polygon([(X, y - 3), (X - 2, y), (X + 2, y)], fill=DARK)

    # Header: station + span on the left, freshness on the right.
    last = rows[-1]["maxs"]
    valid = np.nonzero(np.isfinite(last))[0]
    t_end = row_t0s[-1] + ((valid[-1] + 1) / last.size * ROW_S if valid.size else 0)
    end = datetime.datetime.fromtimestamp(t_end, tz)
    dr.text((0, 0), f"{heli_render.STATION}  {n_rows} h", font=f_head, fill=BLACK)
    dr.text((W - 1, 0), f"data to {end:%H:%M %Z}", font=f_head, fill=BLACK, anchor="ra")
    dr.line((0, HEADER_H, W - 1, HEADER_H), fill=LIGHT)
    return _to_bmp(img)


# The device asks every few minutes; the envelopes change once a minute. Cache on
# the newest file's (name, mtime) so a burst of requests renders once.
_cache = {"key": None, "bmp": None}
_lock = threading.Lock()


def heli_bmp(heli_dir=heli_render.HELI, hours=HOURS):
    names = glob.glob(os.path.join(heli_dir, "heli.*.npz"))
    if not names:
        return None
    newest = max(names)
    try:
        key = (newest, os.path.getmtime(newest), hours)
    except OSError:
        key = None
    with _lock:
        if key is not None and key == _cache["key"]:
            return _cache["bmp"]
        bmp = _render_heli(heli_dir, hours)
        _cache.update(key=key, bmp=bmp)
        return bmp


if __name__ == "__main__":
    import sys
    heli = sys.argv[1] if len(sys.argv) > 1 else heli_render.HELI
    out = sys.argv[2] if len(sys.argv) > 2 else "magtag_heli.bmp"
    bmp = heli_bmp(heli)
    if not bmp:
        sys.exit(f"no interval files in {heli}")
    with open(out, "wb") as f:
        f.write(bmp)
    print(f"wrote {out} ({len(bmp)} bytes)")

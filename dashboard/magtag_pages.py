#!/usr/bin/env python3
"""magtag_pages.py — the MagTag's other pages (stats, weather, last event) + dispatch.

magtag.py owns the wire format, the fonts and the helicorder; this module adds the
text-heavy pages. Same rules: 296x128, four greys, ~3 mm text (13 px is the floor),
local time. Every page reads only what the PUBLIC copy has -- the files pi5 pushes
(events.log, env/, heli/, the live ring) -- so the device works on any network.

  A  heli     the 6-hour drum                          magtag.heli_bmp
  B  stats    live/noise, last trigger, nearest quake  _stats
  C  weather  Open-Meteo outside + the garage barometer _weather
  D  event    the most recent quake this station saw   _event
"""
import datetime
import glob
import json
import os
import threading
import time
import urllib.request

import numpy as np
from PIL import Image, ImageDraw

import magtag
from magtag import BLACK, DARK, LIGHT, WHITE, W, H, HEADER_H

EVENTS = os.environ.get("SEISMO_EVENTS", "/data/events.log")
ENV_DIR = os.environ.get("SEISMO_ENV_DIR", "/data/env")
QUIET_UV = float(os.environ.get("SEISMO_MAGTAG_QUIET_UV", "0.8"))
                        # 1-15 Hz RMS on a quiet night (STATUS "Current system"). The
                        # noise line is read against it: "x4" means a busy afternoon.
LAT = os.environ.get("SEISMO_MAGTAG_LAT", "38.45")      # city-level on purpose:
LON = os.environ.get("SEISMO_MAGTAG_LON", "-122.62")    # it's a weather query
UNITS = os.environ.get("SEISMO_MAGTAG_UNITS", "us")
                        # Weather page only: "us" (F, mph, inHg -- how a desk in Sonoma
                        # County reads the weather) or "metric". Seismic numbers stay SI.
US = UNITS == "us"
HPA_TO_INHG = 0.0295300
SEEN_SNR = 5.0          # the validated-range `seen` bar (CLAUDE.md), not conf's 3


# --- shared drawing ---------------------------------------------------------------

def _canvas():
    img = Image.new("P", (W, H), WHITE)
    img.putpalette([c for rgb in magtag.PALETTE for c in rgb])
    dr = ImageDraw.Draw(img)
    dr.fontmode = "1"
    return img, dr


def _header(dr, left, right):
    f = magtag._font(15)
    dr.text((0, 0), left, font=f, fill=BLACK)
    dr.text((W - 1, 0), right, font=f, fill=BLACK, anchor="ra")
    dr.line((0, HEADER_H, W - 1, HEADER_H), fill=LIGHT)


def _fit(dr, text, font, width):
    """Truncate with an ellipsis to fit `width` px -- USGS place names run long."""
    if dr.textlength(text, font=font) <= width:
        return text
    while text and dr.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _ago(t, now=None):
    s = max(0, (now or time.time()) - t)
    if s < 90:
        return f"{int(s)} s ago"
    if s < 90 * 60:
        return f"{round(s / 60)} min ago"
    if s < 36 * 3600:
        return f"{round(s / 3600)} h ago"
    return f"{round(s / 86400)} d ago"


def _local(t, fmt="%H:%M"):
    return datetime.datetime.fromtimestamp(t, magtag._tz()).strftime(fmt)


def _ts(iso):
    t = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.timestamp()


# --- data --------------------------------------------------------------------------

def _last_trigger():
    """Newest line of events.log. Read from the END: the log grows forever."""
    try:
        with open(EVENTS, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 8192))
            lines = f.read().decode(errors="replace").splitlines()
    except OSError:
        return None
    best = None
    for line in lines[1:] if len(lines) > 1 else lines:   # first may be cut mid-line
        try:
            e = json.loads(line)
            t = _ts(e["start"])
        except (ValueError, KeyError):
            continue
        if best is None or t > best[0]:
            best = (t, e)
    return best


def _usgs():
    try:
        import usgs_events
        return usgs_events.load() or []
    except Exception:
        return []


def _catalog_quakes():
    """Quakes this station saw or should have: confirmed catches at the `seen` bar,
    plus the last 24 h of USGS events tiered strong/likely. confirmed.json is only
    refreshed by hand, so the live cache fills the gap until it is."""
    out = []
    try:
        import catches
        _, evs = catches._confirmed()
    except Exception:
        evs = []
    for e in evs:
        try:
            if float(e.get("snr") or 0) < SEEN_SNR:
                continue
            t0 = _ts(e["origin"])
            out.append({"origin": t0, "arrival": t0 + float(e.get("tp_s") or 0),
                        "mag": e.get("mag"), "km": e.get("dist_km"),
                        "place": e.get("place", ""), "how": f"seen, SNR {float(e['snr']):.0f}"})
        except (ValueError, KeyError, TypeError):
            continue
    for e in _usgs():
        if e.get("tier") in ("strong", "likely") and e.get("arrival"):
            out.append({"origin": e["origin"], "arrival": e["arrival"], "mag": e.get("mag"),
                        "km": e.get("hypo_km"), "place": e.get("place", ""),
                        "how": f"predicted {e['tier']}"})
    out.sort(key=lambda q: q["origin"])
    return out


# --- B: stats ----------------------------------------------------------------------

def _stats():
    img, dr = _canvas()
    _header(dr, f"{magtag.heli_render.STATION}  status", _local(time.time()))
    fb, fr = magtag._font(15), magtag._font(14, bold=False)
    y, step = HEADER_H + 4, 21

    # 1-2: is it alive, and how loud is it right now (1-15 Hz, vs a quiet night)
    try:
        import render
        live = render.live_ring_json()
    except Exception:
        live = {}
    age = live.get("age")
    if age is None:
        dr.text((0, y), "No live data", font=fb, fill=BLACK)
    elif age < 120:
        dr.text((0, y), f"Live, {age:.0f} s behind", font=fb, fill=BLACK)
    else:
        dr.text((0, y), f"STALE: {_ago(time.time() - age)}", font=fb, fill=BLACK)
    rb = live.get("rms_band")
    if rb:
        dr.text((0, y + step), f"Noise {rb:.1f} µV  (×{rb / QUIET_UV:.0f} quiet night)",
                font=fr, fill=BLACK)
    y += 2 * step + 3
    dr.line((0, y - 3, W - 1, y - 3), fill=LIGHT)

    # 3: last trigger and what the classifier made of it
    trig = _last_trigger()
    if trig:
        t, e = trig
        p = e.get("p_quake")
        ptxt = f"p {p:.2f}" if isinstance(p, (int, float)) else "not scored"
        dr.text((0, y), f"Trigger {_local(t)}  {float(e.get('peak_uv', 0)):.0f} µV  {ptxt}",
                font=fr, fill=BLACK)
    else:
        dr.text((0, y), "No triggers logged", font=fr, fill=BLACK)
    y += step + 3
    dr.line((0, y - 3, W - 1, y - 3), fill=LIGHT)

    # 4-5: newest USGS quake with a real chance of showing up; else the nearest one
    evs = _usgs()
    good = [e for e in evs if e.get("tier") in ("strong", "likely", "marginal")]
    q = max(good, key=lambda e: e["origin"]) if good else \
        (min(evs, key=lambda e: e.get("hypo_km") or 1e9) if evs else None)
    if q:
        dr.text((0, y), f"M{q.get('mag')}  {q.get('hypo_km', 0):.0f} km  "
                        f"{_ago(q['origin'])}", font=fb, fill=BLACK)
        dr.text((W - 1, y), q.get("tier", ""), font=fr, fill=DARK, anchor="ra")
        dr.text((0, y + step), _fit(dr, q.get("place", ""), fr, W), font=fr, fill=BLACK)
    else:
        dr.text((0, y), "No USGS quakes in 24 h", font=fr, fill=BLACK)
    return img


# --- C: weather --------------------------------------------------------------------

# WMO weather codes, as Open-Meteo reports them, cut to what fits the panel.
WMO = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog",
       48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
       56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain",
       65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain", 71: "Light snow",
       73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Showers", 81: "Showers",
       82: "Heavy showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm",
       96: "Thunder + hail", 99: "Thunder + hail"}
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
_wx = {"t": 0.0, "data": None}
WX_TTL = 900            # Open-Meteo updates every 15 min; asking more often gains nothing


def _open_meteo():
    if _wx["data"] is not None and time.time() - _wx["t"] < WX_TTL:
        return _wx["data"]
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={LAT}&longitude={LON}"
           "&current=temperature_2m,relative_humidity_2m,weather_code,"
           "wind_speed_10m,wind_direction_10m"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           f"&timezone={magtag.TZ.replace('/', '%2F')}&forecast_days=1"
           + ("&temperature_unit=fahrenheit&wind_speed_unit=mph" if US else ""))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OAKM1-seismo-dashboard"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        _wx.update(t=time.time(), data=data)
    except Exception:
        _wx["t"] = time.time() - WX_TTL + 120      # failed: retry in 2 min, keep stale data
    return _wx["data"]


_press = {"t": 0.0, "data": None}


def _pressure_24h():
    """(epoch[], hPa[]) from the CLUE CSVs, one sample a minute. The files are ~10 MB
    a day at 1 Hz, so this keeps every 60th row and is cached for 10 minutes."""
    if _press["data"] is not None and time.time() - _press["t"] < 600:
        return _press["data"]
    cut = time.time() - 86400
    ts, ps = [], []
    for path in sorted(glob.glob(os.path.join(ENV_DIR, "env-*.csv")))[-2:]:
        try:
            with open(path) as f:
                for i, line in enumerate(f):
                    if i % 60:
                        continue
                    parts = line.split(",", 5)
                    if len(parts) < 5 or parts[0] == "utc":
                        continue
                    try:
                        t = _ts(parts[0])
                        if t >= cut:
                            ts.append(t)
                            ps.append(float(parts[3]))
                    except ValueError:
                        continue
        except OSError:
            continue
    _press.update(t=time.time(), data=(np.array(ts), np.array(ps)))
    return _press["data"]


def _weather():
    img, dr = _canvas()
    _header(dr, "Oakmont", _local(time.time()))
    wx = _open_meteo()
    f_big, fb, fr = magtag._font(38), magtag._font(15), magtag._font(14, bold=False)

    # Left half: outside, from Open-Meteo.
    if wx:
        c, d = wx.get("current", {}), wx.get("daily", {})
        dr.text((0, HEADER_H + 2), f"{c.get('temperature_2m', 0):.0f}°", font=f_big, fill=BLACK)
        dr.text((0, 64), WMO.get(c.get("weather_code"), "—"),
                font=fb, fill=BLACK)
        try:
            hi, lo = d["temperature_2m_max"][0], d["temperature_2m_min"][0]
            dr.text((0, 84), f"{hi:.0f}° / {lo:.0f}°", font=fr, fill=BLACK)
            rain = d.get("precipitation_probability_max", [None])[0]
            if rain:
                dr.text((70, 84), f"rain {rain}%", font=fr, fill=BLACK)
        except (KeyError, IndexError, TypeError):
            pass
        wd = c.get("wind_direction_10m")
        wdir = COMPASS[int((wd + 22.5) // 45) % 8] if wd is not None else ""
        dr.text((0, 104), f"{c.get('wind_speed_10m', 0):.0f} {'mph' if US else 'km/h'} {wdir}", font=fr, fill=BLACK)
        dr.text((70 + 45, 104), f"{c.get('relative_humidity_2m', 0)}%", font=fr, fill=DARK)
    else:
        dr.text((0, HEADER_H + 10), "No forecast", font=fb, fill=BLACK)

    # Right half: the garage barometer -- the instrument's own weather, and the thing
    # that explains slow station noise.
    x0 = 158
    dr.line((x0 - 6, HEADER_H + 3, x0 - 6, H - 1), fill=LIGHT)
    # STATION pressure, not sea-level: the garage is ~135 m up, so this reads ~0.5 inHg
    # (~16 hPa) below a weather report's altimeter setting. It's the instrument's
    # channel, so it stays as measured; the trend is what matters.
    ts, ps = _pressure_24h()
    k_p, unit, dec, flat = (HPA_TO_INHG, "inHg", 2, 0.006) if US else (1.0, "hPa", 1, 0.2)
    ps = ps * k_p
    if ps.size:
        dr.text((x0, HEADER_H + 2), f"{ps[-1]:.{dec}f}", font=fb, fill=BLACK)
        dr.text((W - 1, HEADER_H + 4), unit, font=fr, fill=DARK, anchor="ra")
        prior = ps[ts <= ts[-1] - 3 * 3600]
        if prior.size:
            dp = ps[-1] - prior[-1]
            arrow = "▲" if dp > flat else "▼" if dp < -flat else "→"
            dr.text((x0, HEADER_H + 22), f"{arrow} {dp:+.{dec}f} in 3 h", font=fr, fill=BLACK)
        # 24 h sparkline, min/max labelled so the scale is honest
        sx0, sx1, sy0, sy1 = x0, W - 1, 64, 112
        lo_p, hi_p = float(ps.min()), float(ps.max())
        span = max(hi_p - lo_p, 0.5 * k_p)
        xs = sx0 + (ts - ts[0]) / max(ts[-1] - ts[0], 1) * (sx1 - sx0)
        ys = sy1 - (ps - lo_p) / span * (sy1 - sy0)
        dr.line(list(zip(xs.tolist(), ys.tolist())), fill=BLACK, width=2)
        fs = magtag._font(11, bold=False)
        dr.text((sx0, H - 1), "24 h", font=fs, fill=DARK, anchor="ls")
        dr.text((sx1, H - 1), f"{lo_p:.{dec}f}–{hi_p:.{dec}f}", font=fs, fill=DARK, anchor="rs")
    else:
        dr.text((x0, HEADER_H + 2), "No barometer", font=fr, fill=BLACK)
    return img


# --- D: last event -----------------------------------------------------------------

PRE_S, POST_S = 20, 100


def _event():
    img, dr = _canvas()
    qs = _catalog_quakes()
    if not qs:
        _header(dr, "Last quake", "")
        dr.text((0, HEADER_H + 10), "None on record", font=magtag._font(15), fill=BLACK)
        return img
    q = qs[-1]
    _header(dr, f"M{q['mag']}  {q['km']:.0f} km", _ago(q["origin"]))
    fr, fs = magtag._font(14, bold=False), magtag._font(12, bold=False)
    how_w = dr.textlength(q["how"], font=fs) + 8
    dr.text((0, HEADER_H + 2), _fit(dr, q["place"], fr, W - how_w), font=fr, fill=BLACK)
    dr.text((W - 1, HEADER_H + 4), q["how"], font=fs, fill=DARK, anchor="ra")

    # Trace: the helicorder envelopes (~0.5 s a column), PRE_S before the P arrival
    # to POST_S after. Two intervals at most; a missing one draws as a gap.
    t_a = float(q["arrival"])
    t_lo, t_hi = t_a - PRE_S, t_a + POST_S
    iv = magtag.heli_render.INTERVAL_S
    first = t_lo // iv * iv
    npix = None
    for t0 in (first, first + iv):
        p = os.path.join(magtag.heli_render.HELI, magtag._fname(t0))
        if os.path.exists(p):
            with np.load(p) as d:
                npix = d["mins"].size
            break
    y0, y1 = HEADER_H + 22, H - 16
    mid = (y0 + y1) / 2
    if npix:
        parts = [magtag._interval(magtag.heli_render.HELI, t0, npix)
                 for t0 in (first, first + iv)]
        col_s = iv / npix
        i0, i1 = int((t_lo - first) / col_s), int((t_hi - first) / col_s)
        cat = {key: np.concatenate([p[key] for p in parts])[i0:i1]
               for key in ("mins", "maxs", "lo_mins", "lo_maxs", "cult")}
        ncol = W // magtag.COL_W
        edges = np.linspace(0, cat["mins"].size, ncol + 1).astype(int)
        with np.errstate(invalid="ignore", all="ignore"):
            lo = magtag._rebin(cat["mins"], edges, np.fmin)
            hi = magtag._rebin(cat["maxs"], edges, np.fmax)
            clo = magtag._rebin(cat["lo_mins"], edges, np.fmin)
            chi = magtag._rebin(cat["lo_maxs"], edges, np.fmax)
        cult = np.logical_or.reduceat(cat["cult"], edges[:-1])
        # Scale to what could be the quake: non-local columns, plus the 1-8 Hz cores
        # of local ones. The faded halo is then clipped rather than setting the scale.
        with np.errstate(invalid="ignore", all="ignore"):
            exc = np.where(cult, np.maximum(np.abs(clo), np.abs(chi)),
                           np.maximum(np.abs(lo), np.abs(hi)))
            peak = float(np.nanmax(exc)) if np.isfinite(exc).any() else 0.0
        k = (y1 - y0) / 2 / peak if peak else 0
        # Local (>15 Hz) activity drawn light with its 1-8 Hz core in black, as on the
        # drum. It matters more here: the first render of the M2.3 near Orinda put a
        # garage burst 55 s after P at twice the quake's height.
        for x in range(ncol):
            if not (np.isfinite(lo[x]) and np.isfinite(hi[x])):
                continue
            X = x * magtag.COL_W
            box = (X, max(y0, round(mid - k * hi[x])), X + magtag.COL_W - 1,
                   min(y1, round(mid - k * lo[x])))
            if cult[x]:
                dr.rectangle(box, fill=LIGHT)
                if np.isfinite(clo[x]) and np.isfinite(chi[x]):
                    dr.rectangle((X, round(mid - k * chi[x]), X + magtag.COL_W - 1,
                                  round(mid - k * clo[x])), fill=BLACK)
            else:
                dr.rectangle(box, fill=BLACK)
    else:
        dr.text((0, mid), "trace not on this server", font=fr, fill=DARK, anchor="lm")

    # P marker and a seconds-after-P axis
    px = round(PRE_S / (PRE_S + POST_S) * W)
    # Ticks above and below, not a line through: a line would hide the arrival itself.
    dr.line((px, y0 - 2, px, y0 + 3), fill=BLACK, width=2)
    dr.line((px, y1 - 3, px, y1 + 2), fill=BLACK, width=2)
    dr.text((px + 4, y0 - 3), "P", font=fs, fill=BLACK)
    today = _local(q["origin"], "%Y%m%d") == _local(time.time(), "%Y%m%d")
    when = _local(q["origin"], "%H:%M" if today else "%b %-d %H:%M")
    dr.text((0, H - 1), when, font=fs, fill=BLACK, anchor="ls")
    when_end = dr.textlength(when, font=fs) + 4
    for s in range(30, POST_S, 30):
        x = round((PRE_S + s) / (PRE_S + POST_S) * W)
        dr.line((x, y1 + 1, x, y1 + 4), fill=DARK)
        lbl = f"+{s}s"
        if x - dr.textlength(lbl, font=fs) / 2 > when_end:     # never overprint the date
            dr.text((x, H - 1), lbl, font=fs, fill=DARK, anchor="ms")
    return img


# --- dispatch ------------------------------------------------------------------------

PAGES = {"stats": (_stats, 55), "weather": (_weather, 300), "event": (_event, 300)}
_cache = {}
_lock = threading.Lock()


def page_bmp(name):
    """BMP bytes for a page name, or None if unknown / no data. Text pages are cached
    for their TTL, so a device (or several) polling costs one render per TTL."""
    if name == "heli":
        return magtag.heli_bmp()
    if name not in PAGES:
        return None
    fn, ttl = PAGES[name]
    with _lock:
        hit = _cache.get(name)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        bmp = magtag._to_bmp(fn())
        _cache[name] = (time.time(), bmp)
        return bmp


if __name__ == "__main__":
    import sys
    for name in sys.argv[1:] or ["stats", "weather", "event"]:
        with open(f"magtag_{name}.bmp", "wb") as f:
            f.write(page_bmp(name))
        print("wrote", name)

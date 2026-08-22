#!/usr/bin/env python3
"""heli_service.py — background helicorder builder + on-demand renderer.

Two jobs with different economics, so they are scheduled differently:

  BUILD (envelopes) runs on a timer. It is incremental and the ARCHIVE depends on
  it -- /history can only draw a past window if that window's envelope was banked
  while the data was in the mirror. Skipping it while nobody watches would leave
  permanent holes. Since the plan-before-decode fix it costs ~0.2 s per cycle.

  RENDER (the drum PNG) is ON DEMAND. It is a view: if nobody asks for the picture,
  drawing it is pure waste, and it was the expensive half (~1.4 s per cycle, every
  cycle, forever). Now a request gets the cached bytes instantly and, if the data
  has moved on since that render, a refresh runs in the background -- so the next
  viewer sees fresh pixels and nobody ever waits behind matplotlib.

Rendering used to sit on the request path directly, which cost 24-37 s per hit and
multiplied by viewers; that is what the precompute was for. Stale-while-revalidate
keeps that property (requests stay O(1) served bytes) without paying for renders
nobody wanted.
"""
import glob
import os
import threading
import time

import dc_watch
import heli_build
import heli_render
import usgs_events

DATA = os.environ.get("SEISMO_DATA", "/data/data")
HELI = os.environ.get("SEISMO_HELI", "/data/heli")
POLL_S = float(os.environ.get("SEISMO_HELI_POLL", "20"))   # how often to check mtime
# Catalog poll. The USGS summary feed is CDN-cached and refreshes each minute; small
# events take minutes to hours to be published anyway, so polling faster buys nothing.
USGS_POLL_S = float(os.environ.get("SEISMO_USGS_POLL", "180"))
# DC watchdog. Nothing it looks at moves faster than a 15-minute interval, so polling
# faster than the interval itself only re-reads the same files.
DC_POLL_S = float(os.environ.get("SEISMO_DC_POLL", "300"))

_png = None
_png_stamp = None            # _latest_mtime() as of the cached render
_lock = threading.Lock()
_rendering = False
_started = False


def _latest_mtime():
    files = glob.glob(os.path.join(DATA, "*.mseed"))
    return max((os.path.getmtime(f) for f in files), default=0.0)


def _render_now():
    """Render and cache. Returns the bytes, or None on failure."""
    global _png, _png_stamp, _rendering
    stamp = _latest_mtime()
    try:
        png = heli_render.helicorder_png(HELI)
    except Exception as e:
        print(f"heli_service render: {e}", flush=True)
        png = None
    with _lock:
        if png:
            _png, _png_stamp = png, stamp
        _rendering = False
    return png


def current_png():
    """Drum PNG bytes, or None until the first render completes.

    Serves the cache immediately. If the mirror has advanced since that render,
    kicks a background refresh for the NEXT caller rather than making this one wait.
    The very first request has nothing to serve, so it renders inline.
    """
    global _rendering
    with _lock:
        png, stamp, busy = _png, _png_stamp, _rendering
        if png is None and not busy:
            _rendering = True                 # cold: render inline, below
            cold = True
        else:
            cold = False
    if cold:
        return _render_now()
    if png is not None and stamp != _latest_mtime() and not busy:
        with _lock:
            if _rendering:                    # another thread got there first
                return png
            _rendering = True
        threading.Thread(target=_render_now, daemon=True,
                         name="heli-render").start()
    return png


def _worker():
    """Keep the envelope archive current. Does NOT render -- see module docstring."""
    last = -1.0
    last_usgs = 0.0
    last_dc = 0.0
    while True:
        try:
            m = _latest_mtime()
            if m != last:
                heli_build.build(DATA, HELI)
                last = m
        except Exception as e:                 # never let the worker die on one cycle
            print(f"heli_service build: {e}", flush=True)
        try:
            # Catalog marks ride the same thread: it already wakes on a timer, and a
            # failed poll must not disturb the build (refresh() swallows its own
            # errors and leaves the previous cache in place).
            if time.time() - last_usgs >= USGS_POLL_S:
                last_usgs = time.time()
                usgs_events.refresh()
        except Exception as e:
            print(f"heli_service usgs: {e}", flush=True)
        try:
            # The watchdog rides this thread for the same reason the catalog does: it
            # already wakes on a timer, and it must never be able to disturb the build.
            if time.time() - last_dc >= DC_POLL_S:
                last_dc = time.time()
                dc_watch.poll(HELI)
        except Exception as e:
            print(f"heli_service dc_watch: {e}", flush=True)
        time.sleep(POLL_S)


def start():
    """Spawn the builder thread once (idempotent)."""
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_worker, daemon=True, name="heli").start()

#!/usr/bin/env python3
"""heli_service.py — background helicorder builder+renderer for the dashboard.

Takes rendering off the request path entirely. A daemon thread watches the
mirrored miniSEED; when new data lands (mtime changes) it rebuilds the changed
interval envelope (heli_build) and re-renders the drum PNG (heli_render) ONCE,
into a module-level byte buffer. The web route just hands back those bytes --
O(1), always warm, and N viewers cost nothing extra.

This is the "compute once per new-data, not once per request-per-viewer" fix.
Keeps backend work (obspy ingest, plotting) out of the route handlers.
"""
import glob
import os
import threading
import time

import heli_build
import heli_render

DATA = os.environ.get("SEISMO_DATA", "/data/data")
HELI = os.environ.get("SEISMO_HELI", "/data/heli")
POLL_S = float(os.environ.get("SEISMO_HELI_POLL", "20"))   # how often to check mtime

_png = None
_lock = threading.Lock()
_started = False


def current_png():
    """Latest rendered drum PNG bytes, or None until the first build completes."""
    with _lock:
        return _png


def _latest_mtime():
    files = glob.glob(os.path.join(DATA, "*.mseed"))
    return max((os.path.getmtime(f) for f in files), default=0.0)


def _worker():
    global _png
    last = -1.0
    while True:
        try:
            m = _latest_mtime()
            if m != last:                      # new data -> rebuild + re-render once
                heli_build.build(DATA, HELI)
                png = heli_render.helicorder_png(HELI)
                if png:
                    with _lock:
                        _png = png
                    last = m
        except Exception as e:                 # never let the worker die on one bad cycle
            print(f"heli_service: {e}", flush=True)
        time.sleep(POLL_S)


def start():
    """Spawn the builder/render thread once (idempotent)."""
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_worker, daemon=True, name="heli").start()

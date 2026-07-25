#!/usr/bin/env python3
"""seismo_server.py — the station's data server: middleware between the acquisition
Pi and every downstream consumer (dashboard, future ML/alert apps).

This is the *pure server* half of the pi5 split. It owns the rsync mirror and
re-exposes it as ONE versioned HTTP/JSON contract, so consumers stop reaching
into `/data/*` file paths and stop knowing the Pi's LAN address. All storage
knowledge lives in store.SeismoStore; this file is only HTTP flow -- parse the
request, call the store, serialize the result. (Deliberately no framework: the
payload is data, not HTML, and stdlib http.server already runs the ADC-free
live_server.py on the station -- same idiom.)

Contract (v1):
  GET /                       -> this contract, as JSON
  GET /v1/health              -> station acq counters + mirror freshness
  GET /v1/live                -> rolling 30 s window (uv, fs, gain, t_end, age)
  GET /v1/events?limit&since&min_ratio
                              -> detections, newest first (unfiltered by default)
  GET /v1/waveform?start&end&format=json|mseed
                              -> recorded trace over the window

Every response carries `Access-Control-Allow-Origin: *` so a separate-origin app
can consume it directly. Read-only: there are no mutating routes by design.

  python seismo_server.py         # serves on SEISMO_SERVER_PORT (default 8351)
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from store import SeismoStore

PORT = int(os.environ.get("SEISMO_SERVER_PORT", "8351"))
STORE = SeismoStore()

CONTRACT = {
    "service": "seismo-server",
    "version": "v1",
    "endpoints": {
        "/v1/health": "station acquisition counters + mirror freshness",
        "/v1/live": "rolling 30 s live window (uv microvolts, fs, gain, t_end, age)",
        "/v1/events": "detections, newest first; params: limit, since (ISO), min_ratio",
        "/v1/waveform": "recorded trace; params: start (ISO), end (ISO), format=json|mseed",
    },
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):        # quiet; systemd journal would double-log
        pass

    # -- response helpers -----------------------------------------------------
    def _send(self, body: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status: int = 200):
        self._send(json.dumps(obj).encode(), "application/json", status)

    def _error(self, status: int, msg: str):
        self._json({"error": msg}, status)

    # -- routing --------------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        q = parse_qs(url.query)

        def one(name, default=None):
            v = q.get(name, [default])
            return v[0] if v else default

        try:
            if path == "/":
                self._json(CONTRACT)
            elif path == "/v1/health":
                self._json(STORE.health())
            elif path == "/v1/live":
                self._json(STORE.live())
            elif path == "/v1/events":
                self._json(STORE.events(
                    limit=int(one("limit", "200")),
                    since=one("since"),
                    min_ratio=float(one("min_ratio", "0")),
                ))
            elif path == "/v1/waveform":
                start, end = one("start"), one("end")
                if not start or not end:
                    return self._error(400, "waveform requires start and end (ISO-8601)")
                fmt = one("format", "json")
                if fmt not in ("json", "mseed"):
                    return self._error(400, "format must be json or mseed")
                try:
                    body, ctype = STORE.waveform(start, end, fmt)
                except ImportError:
                    return self._error(
                        503, "waveform needs obspy, which is not installed on this server")
                self._send(body, ctype)
            else:
                self._error(404, f"no such endpoint: {path}")
        except ValueError as e:
            self._error(400, f"bad parameter: {e}")
        except Exception as e:          # never leak a stack to a consumer
            self._error(500, f"{type(e).__name__}: {e}")


def main() -> None:
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"seismo-server -> http://0.0.0.0:{PORT}/   (mirror {STORE.data_dir}; Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()

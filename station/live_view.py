#!/usr/bin/env python3
"""live_view.py — real-time geophone waveform in a browser.

Run on the Pi:   cd ~/seismo/station && ../venv/bin/python live_view.py
Then open on any machine:   http://seismo.local:8347

A background thread reads the AIN0-AIN1 differential channel as fast as the
ADS1256 allows and pushes microvolt samples into a ring buffer. A tiny stdlib
HTTP server serves a canvas strip-chart that polls the ring and scrolls it.
No Flask, no numpy, no browser deps — stdlib only.

Ctrl-C to stop.
"""
import json
import os
import signal
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import waveshare_config
from pipyadc import ADS1256
from pipyadc.ADS1256_definitions import *

PORT = 8347
DIFF = POS_AIN0 | NEG_AIN1
GAIN = int(os.environ.get("SEISMO_GAIN", "1"))   # PGA: 1..64. 1=taps, 64=weak motion
if GAIN not in (1, 2, 4, 8, 16, 32, 64):
    raise SystemExit(f"SEISMO_GAIN must be one of 1,2,4,8,16,32,64 (got {GAIN})")
WINDOW_S = 20                    # seconds of trace held in the ring
RING = deque(maxlen=WINDOW_S * 120)   # ~120 sps ceiling
_lock = threading.Lock()
_fs = 0.0                        # measured sample rate, updated by the reader
_stop = threading.Event()        # set on Ctrl-C / SIGTERM -> reader releases ADC


def reader() -> None:
    """Read the differential channel into RING (microvolts) until _stop is set.

    The finally clause ALWAYS releases the ADC (SPI handle + pigpio + CS pins),
    so a killed process never leaves the chip locked for the next launch.
    """
    global _fs
    # Set PGA gain via the config's ADCON register. The installed PiPyADC's
    # pga_gain/adcon property setters are broken (they read self._status, which
    # is never initialized), but __init__ writes conf.adcon straight to the
    # register, bypassing that path. Gain flag = log2(gain) in the low 3 bits.
    waveshare_config.adcon = CLKOUT_OFF | SDCS_OFF | (GAIN.bit_length() - 1)
    ads = ADS1256(waveshare_config)
    try:
        ads.drate = DRATE_60         # station rate: low noise + 60 Hz notch (see noise_compare)
        ads.cal_self()               # self-cal at the configured gain
        vpd = ads.v_per_digit
        print(f"reading at PGA gain {GAIN}  (full-scale +/-{ads.v_ref / GAIN * 1e3:.1f} mV, "
              f"{vpd * 1e9:.1f} nV/LSB)")
        buf = [0]
        ads.read_oneshot(DIFF)   # prime the cyclic read
        n, t0 = 0, time.time()
        while not _stop.is_set():
            uv = ads.read_continue([DIFF], buf)[0] * vpd * 1e6
            with _lock:
                RING.append(uv)
            n += 1
            if n >= 100:          # refresh the rate estimate ~once/sec
                now = time.time()
                _fs = n / (now - t0)
                n, t0 = 0, now
    finally:
        ads.stop_close_all()


PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>Seismo live</title>
<style>
  body{margin:0;background:#111;color:#8f8;font:14px monospace}
  #hud{position:fixed;top:8px;left:12px;text-shadow:0 0 4px #000}
  canvas{display:block}
</style></head><body>
<div id=hud></div><canvas id=c></canvas>
<script>
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),hud=document.getElementById('hud');
function fit(){cv.width=innerWidth;cv.height=innerHeight;}
addEventListener('resize',fit);fit();
async function tick(){
  let r;try{r=await (await fetch('/data')).json();}catch(e){requestAnimationFrame(tick);return;}
  const d=r.uv,n=d.length,W=cv.width,H=cv.height;
  ctx.fillStyle='#111';ctx.fillRect(0,0,W,H);
  if(n>1){
    // symmetric autoscale with a floor so idle noise stays visible
    let amp=20;for(const v of d)amp=Math.max(amp,Math.abs(v));amp*=1.1;
    ctx.strokeStyle='#333';ctx.beginPath();ctx.moveTo(0,H/2);ctx.lineTo(W,H/2);ctx.stroke();
    ctx.strokeStyle='#3f8';ctx.lineWidth=1;ctx.beginPath();
    for(let i=0;i<n;i++){const x=i/(n-1)*W,y=H/2-d[i]/amp*(H/2*0.9);i?ctx.lineTo(x,y):ctx.moveTo(x,y);}
    ctx.stroke();
    hud.textContent=`gain ${r.gain}   fs ${r.fs.toFixed(1)} sps   pp ${r.pp.toFixed(0)} uV   scale +/-${amp.toFixed(0)} uV`;
  }
  requestAnimationFrame(tick);
}
tick();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):        # quiet
        pass

    def do_GET(self):
        if self.path.startswith("/data"):
            with _lock:
                data = list(RING)
            if data:
                m = sum(data) / len(data)
                uv = [round(v - m, 2) for v in data]      # detrend for display
                pp = max(data) - min(data)
            else:
                uv, pp = [], 0.0
            body = json.dumps({"uv": uv, "pp": pp, "fs": _fs, "gain": GAIN}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def main() -> None:
    # optional self-limit: `live_view.py 15` runs 15s then exits cleanly
    # (used for smoke tests so nothing ever needs an external kill).
    limit = float(sys.argv[1]) if len(sys.argv) > 1 else None

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)

    def shutdown(*_):
        _stop.set()
        threading.Thread(target=srv.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    if limit:
        threading.Timer(limit, shutdown).start()

    print(f"live view -> http://seismo.local:{PORT}   (Ctrl-C to stop)")
    srv.serve_forever()          # returns once shutdown() runs
    t.join(timeout=2)            # let the reader hit its finally + release the ADC
    print("stopped, ADC released.")


if __name__ == "__main__":
    main()

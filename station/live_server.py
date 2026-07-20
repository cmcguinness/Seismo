#!/usr/bin/env python3
"""live_server.py — real-time waveform viewer, served from the recorder's
shared-memory ring (/dev/shm/seismo_live.npz).

Does NOT touch the ADC, so it runs happily ALONGSIDE recorder.py (which owns the
chip). The recorder mirrors a rolling 30 s window to shared memory; this serves
it as a scrolling strip-chart. Browser polling load lands here, not on the
acquisition loop.

  python live_server.py          # then open http://seismo.local:8347
"""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

PORT = 8347
LIVE_PATH = Path("/dev/shm/seismo_live.npz")

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>Seismo live</title>
<style>
  body{margin:0;background:#111;color:#8f8;font:14px monospace}
  #hud{position:fixed;top:8px;left:12px;text-shadow:0 0 4px #000}
  #stale{position:fixed;top:8px;right:12px;color:#f66;display:none}
  canvas{display:block}
</style></head><body>
<div id=hud></div><div id=stale>● NO LIVE DATA (recorder stopped?)</div>
<canvas id=c></canvas>
<script>
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),
      hud=document.getElementById('hud'),stale=document.getElementById('stale');
function fit(){cv.width=innerWidth;cv.height=innerHeight;}
addEventListener('resize',fit);fit();
async function tick(){
  try{
    const r=await (await fetch('/data')).json();
    const d=r.uv,n=d.length,W=cv.width,H=cv.height;
    ctx.fillStyle='#111';ctx.fillRect(0,0,W,H);
    stale.style.display=(r.age==null||r.age>3)?'block':'none';
    if(n>1){
      let amp=20;for(const v of d)amp=Math.max(amp,Math.abs(v));amp*=1.1;
      ctx.strokeStyle='#333';ctx.beginPath();ctx.moveTo(0,H/2);ctx.lineTo(W,H/2);ctx.stroke();
      ctx.strokeStyle='#3f8';ctx.lineWidth=1;ctx.beginPath();
      for(let i=0;i<n;i++){const x=i/(n-1)*W,y=H/2-d[i]/amp*(H/2*0.9);i?ctx.lineTo(x,y):ctx.moveTo(x,y);}
      ctx.stroke();
      hud.textContent=`gain ${r.gain}   fs ${r.fs.toFixed(1)} sps   pp ${r.pp.toFixed(0)} uV`
                     +`   scale +/-${amp.toFixed(0)} uV   lag ${r.age}s`;
    }
  }catch(e){}
  setTimeout(tick,150);          // ~7 Hz poll; ring republishes every 0.3 s
}
tick();
</script></body></html>"""


def read_live():
    """Return (uv microvolts detrended, fs, gain, age_seconds) or (None,...)."""
    try:
        age = time.time() - LIVE_PATH.stat().st_mtime
        with np.load(LIVE_PATH) as d:               # atomic file (os.replace), never partial
            counts = d["counts"].astype(float)
            fs = float(d["fs"])
            gain = int(d["gain"])
    except Exception:
        return None, 0.0, 0, None
    uv_per_count = (2.5 * 2 / (gain * (2 ** 23 - 1))) * 1e6
    uv = counts * uv_per_count
    if uv.size:
        uv -= uv.mean()
    return uv, fs, gain, age


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/data"):
            uv, fs, gain, age = read_live()
            if uv is None or uv.size == 0:
                payload = {"uv": [], "pp": 0.0, "fs": 0.0, "gain": 0, "age": age}
            else:
                payload = {"uv": [round(v, 2) for v in uv], "pp": float(uv.ptp()),
                           "fs": fs, "gain": gain, "age": round(age, 1)}
            body = json.dumps(payload).encode()
            ctype = "application/json"
        else:
            body = PAGE.encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"live view -> http://seismo.local:{PORT}   (reads {LIVE_PATH}; Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()

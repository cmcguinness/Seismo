#!/usr/bin/env python3
"""app.py — public seismo dashboard (FastHTML), served on the Dokku host.

Reads the rsync-mirrored miniSEED + events (no ADC, no acquisition here), renders
the helicorder/spectrum with ObsPy, and proxies the Pi's live feed so the
acquisition box stays private on the LAN.
"""
import json
import os
import urllib.request

from fasthtml.common import FastHTML, serve
from starlette.responses import JSONResponse, Response

import render

STATION = os.environ.get("SEISMO_STATION", "OAKMT")
NETWORK = os.environ.get("SEISMO_NETWORK", "XX")
PLACE = os.environ.get("SEISMO_PLACE", "Oakmont, Santa Rosa, CA")
EVENTS = os.environ.get("SEISMO_EVENTS", "/data/events.log")
LIVE_URL = os.environ.get("SEISMO_LIVE_URL", "")     # http://<pi-ip>:8347/data

app = FastHTML()


def _recent_events(n=10):
    try:
        with open(EVENTS) as f:
            evs = [json.loads(line) for line in f if line.strip()]
        return evs[-n:][::-1]
    except Exception:
        return []


PAGE = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{net}.{sta} — DIY seismometer</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0c0c0e;color:#cfe;font:15px/1.5 system-ui,sans-serif}}
 header{{padding:14px 20px;border-bottom:1px solid #222;background:#111}}
 h1{{margin:0;font-size:20px;color:#8f8}} .sub{{color:#7a8;font-size:13px}}
 main{{max-width:1100px;margin:0 auto;padding:16px 20px}}
 section{{margin:22px 0}} h2{{font-size:15px;color:#9ab;border-bottom:1px solid #1c1c22;padding-bottom:4px}}
 canvas{{width:100%;height:200px;background:#111;border:1px solid #222;border-radius:6px;display:block}}
 #hud{{font:12px monospace;color:#8f8;margin:4px 2px}}
 img{{max-width:100%;border:1px solid #222;border-radius:6px;background:#fff}}
 table{{width:100%;border-collapse:collapse;font-size:13px}}
 td,th{{text-align:left;padding:4px 8px;border-bottom:1px solid #1a1a20}} th{{color:#7a8}}
 .none{{color:#678}} footer{{color:#556;font-size:12px;padding:16px 20px;border-top:1px solid #1a1a20}}
 a{{color:#6cf}}
</style></head><body>
<header><h1>{net}.{sta}.00.SHZ &mdash; DIY geophone seismometer</h1>
<div class=sub>{place} &nbsp;·&nbsp; vertical 4.5&nbsp;Hz &nbsp;·&nbsp; independent station (not for scientific use)</div></header>
<main>
 <section><h2>Live (last 30&nbsp;s)</h2>
   <canvas id=c></canvas><div id=hud>connecting…</div></section>
 <section><h2>Helicorder — last 8 hours (UTC)</h2>
   <img id=heli src="/helicorder.png" alt="helicorder"></section>
 <section><h2>Spectrum</h2><img id=spec src="/spectrum.png" alt="spectrum"></section>
 <section><h2>Recent detections</h2>
   <table><tr><th>start (UTC)</th><th>duration</th><th>STA/LTA</th><th>peak</th></tr>
   {events}</table></section>
</main>
<footer>rendered on the LAN from rsync-mirrored miniSEED · images refresh every 60&nbsp;s ·
 built by <a href="https://www.linkedin.com/in/charlesmcguinness/">Charles McGuinness</a></footer>
<script>
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),hud=document.getElementById('hud');
function fit(){{cv.width=cv.clientWidth;cv.height=cv.clientHeight;}}
addEventListener('resize',fit);fit();
async function live(){{
  try{{
    const r=await (await fetch('/live-data')).json();
    const d=r.uv||[],n=d.length,W=cv.width,H=cv.height;
    ctx.fillStyle='#111';ctx.fillRect(0,0,W,H);
    if(n>1){{let amp=20;for(const v of d)amp=Math.max(amp,Math.abs(v));amp*=1.1;
      ctx.strokeStyle='#3f8';ctx.beginPath();
      for(let i=0;i<n;i++){{const x=i/(n-1)*W,y=H/2-d[i]/amp*(H/2*0.9);i?ctx.lineTo(x,y):ctx.moveTo(x,y);}}
      ctx.stroke();
      hud.textContent=`gain ${{r.gain}}  fs ${{(r.fs||0).toFixed(1)}} sps  pp ${{(r.pp||0).toFixed(0)}} µV`;
    }} else hud.textContent='live feed unavailable';
  }}catch(e){{hud.textContent='live feed unavailable';}}
  setTimeout(live,300);
}}
live();
setInterval(()=>{{heli.src='/helicorder.png?'+Date.now();spec.src='/spectrum.png?'+Date.now();}},60000);
</script></body></html>"""


@app.get("/")
def home():
    evs = _recent_events()
    if evs:
        rows = "".join(
            f"<tr><td>{e.get('start','')}</td><td>{e.get('duration_s','')}s</td>"
            f"<td>{e.get('peak_ratio','')}</td><td>{e.get('peak_uv','')} µV</td></tr>"
            for e in evs)
    else:
        rows = "<tr><td colspan=4 class=none>no detections yet</td></tr>"
    html = PAGE.format(net=NETWORK, sta=STATION, place=PLACE, events=rows)
    return Response(html, media_type="text/html")


@app.get("/helicorder.png")
def helicorder():
    png = render.helicorder_png()
    return Response(png, media_type="image/png") if png else Response("no data", status_code=503)


@app.get("/spectrum.png")
def spectrum():
    png = render.spectrum_png()
    return Response(png, media_type="image/png") if png else Response("no data", status_code=503)


@app.get("/live-data")
def live_data():
    if not LIVE_URL:
        return JSONResponse({"uv": [], "pp": 0, "fs": 0, "gain": 0})
    try:
        with urllib.request.urlopen(LIVE_URL, timeout=2) as r:
            return JSONResponse(json.loads(r.read()))
    except Exception:
        return JSONResponse({"uv": [], "pp": 0, "fs": 0, "gain": 0})


if __name__ == "__main__":
    serve(port=int(os.environ.get("PORT", "5001")), reload=False)

#!/usr/bin/env python3
"""app.py — public seismo dashboard (FastHTML + Bootstrap 5), served on the Dokku host.

Reads the rsync-mirrored miniSEED + events (no ADC, no acquisition here), serves the
pre-rendered helicorder + cached spectrum, and streams the mirrored live ring. UI is
Bootstrap 5 (light mode, subtle palette); the route handlers stay thin (build data,
hand HTML/PNG back) with page markup in module-level template helpers.
"""
import json
import os
import time

from fasthtml.common import FastHTML, serve
from starlette.responses import JSONResponse, Response

import heli_service
import render

STATION = os.environ.get("SEISMO_STATION", "OAKMT")
NETWORK = os.environ.get("SEISMO_NETWORK", "XX")
PLACE = os.environ.get("SEISMO_PLACE", "Oakmont, Santa Rosa, CA")
EVENTS = os.environ.get("SEISMO_EVENTS", "/data/events.log")
SID = f"{NETWORK}.{STATION}.00.SHZ"
BRAND = "Charles&rsquo; Seismology Station"
# Display filter for the detections table: the recorder logs EVERY STA/LTA trigger
# (down to ratio 4.0) for analysis, but most are cultural noise. Only surface
# detections at/above this ratio. Tune live via `dokku config:set SEISMO_MIN_RATIO=N`.
MIN_RATIO = float(os.environ.get("SEISMO_MIN_RATIO", "20"))

app = FastHTML()


def _recent_events(n=10):
    try:
        with open(EVENTS) as f:
            evs = [json.loads(line) for line in f if line.strip()]
        evs = [e for e in evs if float(e.get("peak_ratio", 0) or 0) >= MIN_RATIO]
        return evs[-n:][::-1]
    except Exception:
        return []


# --- shared chrome -----------------------------------------------------------

BOOT = (
    '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" '
    'rel="stylesheet" crossorigin="anonymous">'
    '<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" '
    'crossorigin="anonymous" defer></script>'
)

CSS = """<style>
 :root{--accent:#2f6f6b}
 body{background:#f6f7f9}
 .navbar-brand{font-weight:600;color:var(--accent)}
 .page-title{color:var(--accent);font-weight:600}
 .card-header{background:#fff;font-weight:600;color:#39484a;border-bottom:1px solid #eef0f2}
 .card{border-color:#e6e8eb}
 .plot{width:100%;height:auto;display:block;border:1px solid #e6e8eb;border-radius:.25rem}
 #c{width:100%;height:200px;display:block;background:#fff;border:1px solid #e6e8eb;border-radius:.25rem}
 #hud{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;color:#6c757d;margin-top:.5rem}
 a{color:var(--accent)}
</style>"""

FOOTER = (
    '<footer class="border-top bg-body-tertiary py-3 mt-4"><div class="container text-muted small">'
    'rendered on the LAN from rsync-mirrored miniSEED &middot; '
    'built by <a href="https://www.linkedin.com/in/charlesmcguinness/">Charles McGuinness</a>'
    '</div></footer>'
)


def _nav(active):
    def link(href, label, key):
        cls = "nav-link active" if key == active else "nav-link"
        aria = ' aria-current="page"' if key == active else ""
        return f'<li class="nav-item"><a class="{cls}"{aria} href="{href}">{label}</a></li>'
    return (
        '<nav class="navbar navbar-expand-sm bg-body-tertiary border-bottom">'
        '<div class="container">'
        f'<a class="navbar-brand" href="/">{BRAND}</a>'
        '<button class="navbar-toggler" type="button" data-bs-toggle="collapse" '
        'data-bs-target="#nav" aria-controls="nav" aria-expanded="false" aria-label="Toggle navigation">'
        '<span class="navbar-toggler-icon"></span></button>'
        '<div class="collapse navbar-collapse" id="nav"><ul class="navbar-nav ms-auto">'
        + link("/", "Live", "live")
        + link("/spectrum", "Spectrum", "spectrum")
        + link("/about", "About this station", "about")
        + '</ul></div></div></nav>'
    )


def _shell(title, active, body, script=""):
    return (
        '<!doctype html><html lang="en" data-bs-theme="light"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title}</title>{BOOT}{CSS}</head><body>'
        + _nav(active)
        + '<main class="container py-4">' + body + '</main>'
        + FOOTER + script + '</body></html>'
    )


def _titleblock(title, subtitle):
    return (f'<div class="mb-4"><h1 class="h3 page-title mb-1">{title}</h1>'
            f'<div class="text-muted">{subtitle}</div></div>')


# --- home --------------------------------------------------------------------

HOME_JS = """<script>
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),hud=document.getElementById('hud');
function fit(){cv.width=cv.clientWidth;cv.height=cv.clientHeight;}
addEventListener('resize',fit);fit();
async function live(){
  try{
    const r=await (await fetch('/live-data')).json();
    const d=r.uv||[],n=d.length,W=cv.width,H=cv.height;
    ctx.clearRect(0,0,W,H);
    if(n>1){let amp=20;for(const v of d)amp=Math.max(amp,Math.abs(v));amp*=1.1;
      ctx.strokeStyle='#2f6f6b';ctx.lineWidth=1;ctx.beginPath();
      for(let i=0;i<n;i++){const x=i/(n-1)*W,y=H/2-d[i]/amp*(H/2*0.9);i?ctx.lineTo(x,y):ctx.moveTo(x,y);}
      ctx.stroke();
      hud.textContent=`gain ${r.gain}  fs ${(r.fs||0).toFixed(1)} sps  pp ${(r.pp||0).toFixed(0)} µV`;
    } else hud.textContent='live feed unavailable';
  }catch(e){hud.textContent='live feed unavailable';}
  setTimeout(live,300);
}
live();
setInterval(()=>{document.getElementById('heli').src='/helicorder.png?'+Date.now();},60000);
</script>"""


def _card(header, inner, body_class="card-body"):
    return (f'<div class="card shadow-sm mb-4"><div class="card-header">{header}</div>'
            f'<div class="{body_class}">{inner}</div></div>')


@app.get("/")
def home():
    evs = _recent_events()
    if evs:
        rows = "".join(
            f'<tr><td>{e.get("start","")}</td><td>{e.get("duration_s","")}s</td>'
            f'<td>{e.get("peak_ratio","")}</td><td>{e.get("peak_uv","")} µV</td></tr>'
            for e in evs)
    else:
        rows = (f'<tr><td colspan="4" class="text-muted">no detections above '
                f'STA/LTA {MIN_RATIO:g}</td></tr>')
    ts = int(time.time())
    body = (
        _titleblock(SID, f'DIY geophone seismometer &middot; {PLACE} &middot; vertical '
                         '4.5&nbsp;Hz &middot; independent station (not for scientific use)')
        + _card("Live &middot; last 30&nbsp;s",
                '<canvas id="c"></canvas><div id="hud">connecting…</div>')
        + _card("Helicorder &middot; last 4 hours (UTC)",
                f'<img id="heli" class="plot" src="/helicorder.png?{ts}" alt="helicorder">')
        + _card(f"Recent detections &middot; STA/LTA &ge; {MIN_RATIO:g}",
                '<table class="table table-sm table-striped mb-0 align-middle">'
                '<thead><tr><th>start (UTC)</th><th>duration</th><th>STA/LTA</th><th>peak</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>',
                body_class="table-responsive")
    )
    return Response(_shell(BRAND, "live", body, HOME_JS), media_type="text/html")


# --- spectrum ----------------------------------------------------------------

SPEC_JS = """<script>
// re-fetch once per 30-min cache window (bucketed param aligns with the server TTL,
// so it hits the cache rather than forcing a fresh ~30 s render)
setInterval(()=>{document.getElementById('spec').src='/spectrum.png?'+Math.floor(Date.now()/1800000);},1800000);
</script>"""


@app.get("/spectrum")
def spectrum_page():
    # ts bucketed to the 30-min TTL so the image URL is stable within a window
    # (per-load timestamps would defeat browser/CDN caching)
    ts = int(time.time() // 1800)
    inner = (
        '<p class="text-muted" id="note">Rendering… the spectrum is computed on request and '
        'can take up to a minute on the little Pi — hang tight.</p>'
        f'<img id="spec" class="plot" src="/spectrum.png?{ts}" alt="spectrum" '
        'onload="document.getElementById(\'note\').style.display=\'none\'">'
        '<p class="mt-3 mb-0">Frequency <em>content</em> of the ground motion over the '
        'last hour (amplitude spectral density, µV/√Hz, Welch-averaged). See '
        '<a href="/about">About</a> for how to read the microseism, quake band, 4.5&nbsp;Hz '
        'corner, and noise floor.</p>'
    )
    body = (_titleblock("Spectrum &middot; Welch ASD", f"{SID} &middot; {PLACE}")
            + '<div class="row"><div class="col-xl-8 col-lg-10">'
            + _card("Amplitude spectral density", inner) + '</div></div>')
    return Response(_shell(f"Spectrum — {BRAND}", "spectrum", body, SPEC_JS),
                    media_type="text/html")


# --- about -------------------------------------------------------------------

ABOUT_SECTIONS = [
    ("What this is",
     '<p class="mb-0 prose">A homemade (&ldquo;DIY&rdquo;) seismometer &mdash; an amateur '
     'instrument that senses the ground moving: earthquakes, the ocean, and everyday cultural '
     'vibration. It records continuously and is <b>independent</b> (not part of a formal seismic '
     'network), built for curiosity and learning. <b>Not for scientific or emergency use.</b> '
     'The station is still being <b>tested, tuned, and modified</b>, so spurious signals '
     '(from the work itself, not the ground) may appear in the data.</p>'),
    ("Hardware",
     '<ul class="mb-0"><li><b>Sensor:</b> LGT-4.5 geophone &mdash; a 4.5&nbsp;Hz vertical geophone '
     '(a coil-and-magnet <i>velocity</i> sensor), ~28.8&nbsp;V per m/s, 385&nbsp;&#8486; coil.</li>'
     '<li><b>Digitizer:</b> Waveshare High-Precision <b>ADS1256</b> &mdash; 24-bit ADC, read '
     'differentially at gain&nbsp;64, ~57&nbsp;samples/sec.</li>'
     '<li><b>Computers:</b> a Raspberry&nbsp;Pi&nbsp;2B does acquisition (owns the ADC); a '
     'Raspberry&nbsp;Pi&nbsp;5 renders these charts and serves this page.</li>'
     '<li><b>Front end:</b> differential bias network into the ADC (shunt damping to come).</li></ul>'),
    ("How to read the charts",
     '<p class="prose"><b>Live waveform</b> &mdash; the ground moving <i>right now</i>, in microvolts '
     'of sensor output (proportional to ground velocity). Flat = quiet; wiggles = motion. It '
     'auto-scales, so a calm trace and a busy one can look similar in height &mdash; watch the '
     '&ldquo;pp&rdquo; number.</p>'
     '<p class="prose"><b>Helicorder (drum plot)</b> &mdash; the classic seismograph view. Each row '
     'is 15&nbsp;minutes; read it like a book &mdash; left&nbsp;&rarr;&nbsp;right, then down to the '
     'next row. The last 4&nbsp;hours (UTC). Earthquakes and bumps appear as bursts standing out from '
     'the steady background hum.</p>'
     '<p class="prose"><b>Spectrum (Welch ASD)</b> &mdash; the ground&rsquo;s frequency <i>content</i>: '
     'how much signal sits at each frequency. &ldquo;ASD&rdquo; is amplitude spectral density '
     '(&micro;V per &radic;Hz); &ldquo;Welch&rdquo; is the averaging method that turns a jittery '
     'signal into a smooth, trustworthy curve. Shaded/annotated zones: the <b>ocean microseism</b> '
     '(~0.1&ndash;0.35&nbsp;Hz, the ever-present hum of Pacific swell), the <b>local-earthquake band</b> '
     '(~1&ndash;15&nbsp;Hz), the geophone&rsquo;s <b>4.5&nbsp;Hz corner</b> (it&rsquo;s flat/sensitive '
     'above this, and goes progressively deaf below it), and the flat <b>electronic noise floor</b> at '
     'high frequency. The plot stops at 0.05&nbsp;Hz on the left: below the microseism, a 4.5&nbsp;Hz '
     'geophone is ~60&nbsp;dB down, so anything lower is the instrument&rsquo;s own noise, not the '
     'ground. Seeing below that (distant &ldquo;teleseismic&rdquo; quakes, Earth&rsquo;s slow hum) takes '
     'a different sensor &mdash; a force-balance broadband, or a DIY long-period pendulum.</p>'
     '<p class="mb-0 prose"><b>Recent detections</b> &mdash; automatic STA/LTA triggers (sudden energy '
     'jumps). Most are <i>cultural</i> (footsteps, machinery, doors), not earthquakes &mdash; a genuine '
     'local quake would show a sharp P&nbsp;arrival followed seconds later by a larger S.</p>'),
    ("Where it sits",
     '<p class="mb-0 prose">{place} &mdash; on valley-margin alluvium at the foot of the '
     'Sonoma/Mayacamas volcanics, essentially atop the active <b>Rodgers Creek fault</b> system. A '
     'sensitive spot for local events, at the cost of a bit more everyday noise.</p>'),
]


@app.get("/about")
def about():
    cards = "".join(_card(h, inner.replace("{place}", PLACE)) for h, inner in ABOUT_SECTIONS)
    body = _titleblock("About this station", f"{SID} &middot; {PLACE}") + \
        f'<div class="row"><div class="col-lg-9">{cards}</div></div>'
    return Response(_shell(f"About — {BRAND}", "about", body),
                    media_type="text/html")


# --- images + live data (unchanged behaviour) --------------------------------

NOCACHE = {"Cache-Control": "no-store, max-age=0"}   # dynamic renders — never let Cloudflare cache


@app.get("/helicorder.png")
def helicorder():
    # Pre-rendered off the request path by heli_service (built from precomputed
    # interval envelopes, not a live obspy re-parse). Always warm; O(1) here.
    png = heli_service.current_png()
    return Response(png, media_type="image/png", headers=NOCACHE) if png \
        else Response("warming up", status_code=503)


SPEC_CACHE = {"Cache-Control": "public, max-age=1800"}   # 30 min, matches render TTL


@app.get("/spectrum.png")
def spectrum():
    # Memoized with a 30-min TTL (render.spectrum_png_cached): the ~30 s Welch
    # render runs at most once per half hour, so bouncing around never re-triggers it.
    png = render.spectrum_png_cached()
    return Response(png, media_type="image/png", headers=SPEC_CACHE) if png \
        else Response("no data", status_code=503)


@app.get("/live-data")
def live_data():
    # Served from pi5 off the locally-mirrored /dev/shm ring (pulled by
    # seismo-live-pull), NOT proxied to the Pi -- so watching the live feed never
    # makes the acquisition Pi transmit (WiFi/Ethernet TX conducts noise into the ADC).
    return JSONResponse(render.live_ring_json())


heli_service.start()      # background: build envelopes + pre-render the drum

if __name__ == "__main__":
    serve(port=int(os.environ.get("PORT", "5001")), reload=False)

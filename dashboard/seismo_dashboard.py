#!/usr/bin/env python3
"""seismo_dashboard.py — public seismo dashboard (FastHTML + Bootstrap 5), served on the Dokku host.

Reads the rsync-mirrored miniSEED + events (no ADC, no acquisition here), serves the
pre-rendered helicorder + cached spectrum, and streams the mirrored live ring. UI is
Bootstrap 5 (light mode, subtle palette); the route handlers stay thin (build data,
hand HTML/PNG back) with page markup in module-level template helpers.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

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
# Time window for the detections table: show every trigger at/above MIN_RATIO in
# the last WINDOW_H hours (UTC), rather than a fixed row count. Tune live via
# `dokku config:set SEISMO_DETECT_WINDOW_H=N`.
WINDOW_H = float(os.environ.get("SEISMO_DETECT_WINDOW_H", "24"))
# Most rows to SHOW. The window stays 24 h; this just keeps a noisy day (or a
# misbehaving front end) from filling the page. When it truncates, the header says
# so -- a silently short list would read as "quiet day".
MAX_ROWS = int(os.environ.get("SEISMO_DETECT_MAX_ROWS", "10"))

app = FastHTML()


def _recent_events(max_rows=2000):
    """Detections in the last WINDOW_H hours (UTC) at/above MIN_RATIO, newest
    first. max_rows only bounds the parse; the DISPLAY cap is MAX_ROWS, applied by
    the caller so it can report how many were withheld."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_H)
    try:
        with open(EVENTS) as f:
            evs = [json.loads(line) for line in f if line.strip()]
    except Exception:
        return []
    out = []
    for e in evs:
        if float(e.get("peak_ratio", 0) or 0) < MIN_RATIO:
            continue
        try:
            t = datetime.fromisoformat(e.get("start", ""))
        except ValueError:
            continue
        if t.tzinfo is None:                       # treat naive stamps as UTC
            t = t.replace(tzinfo=timezone.utc)
        if t >= cutoff:
            out.append(e)
    out.sort(key=lambda e: e.get("start", ""), reverse=True)   # newest first
    return out[:max_rows]


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
 #c{width:100%;height:220px;display:block;background:#fff;border:1px solid #e6e8eb;border-radius:.25rem}
 #s{width:100%;height:230px;display:block;background:#fff;border:1px solid #e6e8eb;border-radius:.25rem}
 #hud{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;color:#6c757d;margin-top:.5rem}
 td.spark-cell{width:196px}
 svg.spark{display:block;width:180px;height:40px;background:#eaf0f4;border:1px solid #c7d4de;border-radius:3px}
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
const AX=18;                                  // bottom strip reserved for the time axis
function fit(){cv.width=cv.clientWidth;cv.height=cv.clientHeight;}
addEventListener('resize',fit);fit();
function hms(t){return new Date(t*1000).toISOString().slice(11,19);}
// Time axis: 1 s minor ticks, labelled + gridded every 10 s. Tick positions come
// from absolute UTC (t_end = time of the newest sample), so they scroll leftward
// with the trace instead of sitting at fixed pixels.
function axis(t0,t1,W,H){
  const plotH=H-AX;
  ctx.strokeStyle='#dee2e6';ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(0,plotH+.5);ctx.lineTo(W,plotH+.5);ctx.stroke();
  ctx.fillStyle='#6c757d';ctx.font='10px ui-monospace,Menlo,monospace';ctx.textAlign='center';
  for(let t=Math.ceil(t0);t<=t1;t++){
    const x=Math.round((t-t0)/(t1-t0)*W)+.5,ten=t%10===0;
    ctx.beginPath();ctx.moveTo(x,plotH);ctx.lineTo(x,plotH+(ten?6:3));ctx.stroke();
    if(ten){
      ctx.strokeStyle='#f1f3f5';ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,plotH);ctx.stroke();
      ctx.strokeStyle='#dee2e6';
      if(x>22&&x<W-22)ctx.fillText(hms(t),x,H-4);
    }
  }
}
// Live spectrum: log-log ASD from the same 30 s ring. ML/MB = axis margins.
const sv=document.getElementById('s'),sx=sv?sv.getContext('2d'):null;
const ML=46,MB=20,MT=6,MR=8;
function fitS(){if(sv){sv.width=sv.clientWidth;sv.height=sv.clientHeight;}}
addEventListener('resize',fitS);fitS();
function spectrum(sp){
  if(!sx)return;
  const W=sv.width,H=sv.height;sx.clearRect(0,0,W,H);
  if(!sp||!sp.f||sp.f.length<3){sx.fillStyle='#6c757d';sx.font='11px ui-monospace,Menlo,monospace';
    sx.fillText('spectrum unavailable',ML,H/2);return;}
  const f=sp.f,a=sp.asd;
  const lx=v=>Math.log10(v), pw=W-ML-MR, ph=H-MB-MT;
  const x0=lx(f[0]),x1=lx(f[f.length-1]);
  let amin=Infinity,amax=-Infinity;for(const v of a){if(v>0){amin=Math.min(amin,v);amax=Math.max(amax,v);}}
  const y0=Math.floor(lx(amin)),y1=Math.ceil(lx(amax));   // whole decades
  const X=v=>ML+(lx(v)-x0)/(x1-x0)*pw, Y=v=>MT+(y1-lx(v))/(y1-y0)*ph;
  sx.font='10px ui-monospace,Menlo,monospace';
  // y decades
  sx.textAlign='right';
  for(let d=y0;d<=y1;d++){
    const y=Y(Math.pow(10,d));
    sx.strokeStyle='#f1f3f5';sx.beginPath();sx.moveTo(ML,y+.5);sx.lineTo(W-MR,y+.5);sx.stroke();
    sx.fillStyle='#6c757d';sx.fillText('1e'+d,ML-4,y+3);
  }
  // x decade + minor ticks
  sx.textAlign='center';
  // start at the PARTIAL decade containing f[0], else 0.2/0.5 go unlabelled
  for(let d=Math.floor(x0);d<=Math.floor(x1);d++){
    for(let m=1;m<10;m++){
      const v=m*Math.pow(10,d);if(lx(v)<x0||lx(v)>x1)continue;
      const x=X(v);
      sx.strokeStyle=m===1?'#e9ecef':'#f8f9fa';
      sx.beginPath();sx.moveTo(x+.5,MT);sx.lineTo(x+.5,MT+ph);sx.stroke();
      if(m===1||m===2||m===5){sx.fillStyle='#6c757d';
        sx.fillText(v<1?v.toString():v.toFixed(0),x,H-6);}
    }
  }
  // 4.5 Hz geophone corner
  if(4.5>=f[0]&&4.5<=f[f.length-1]){
    const x=X(4.5);sx.strokeStyle='#dc322f';sx.setLineDash([3,3]);sx.beginPath();
    sx.moveTo(x+.5,MT);sx.lineTo(x+.5,MT+ph);sx.stroke();sx.setLineDash([]);
    sx.fillStyle='#dc322f';sx.textAlign='left';sx.fillText('4.5 Hz',x+3,MT+10);
  }
  sx.strokeStyle='#2f6f6b';sx.lineWidth=1.25;sx.beginPath();
  for(let i=0;i<f.length;i++){const x=X(f[i]),y=Y(Math.max(a[i],1e-12));i?sx.lineTo(x,y):sx.moveTo(x,y);}
  sx.stroke();
  sx.strokeStyle='#dee2e6';sx.lineWidth=1;sx.strokeRect(ML+.5,MT+.5,pw,ph);
}
async function live(){
  try{
    const r=await (await fetch('/live-data')).json();
    const d=r.uv||[],n=d.length,W=cv.width,H=cv.height;
    ctx.clearRect(0,0,W,H);
    if(n>1){
      const fs=r.fs||0,t1=r.t_end,haveT=!!t1&&fs>0,t0=haveT?t1-(n-1)/fs:0;
      const plotH=haveT?H-AX:H;
      if(haveT)axis(t0,t1,W,H);
      let amp=20;for(const v of d)amp=Math.max(amp,Math.abs(v));amp*=1.1;
      ctx.strokeStyle='#2f6f6b';ctx.lineWidth=1;ctx.beginPath();
      for(let i=0;i<n;i++){const x=i/(n-1)*W,y=plotH/2-d[i]/amp*(plotH/2*0.9);i?ctx.lineTo(x,y):ctx.moveTo(x,y);}
      ctx.stroke();
      spectrum(r.spec);
      const band=(r.rms_band==null)?'':`  rms(1–15 Hz) ${r.rms_band.toFixed(2)} µV`;
      hud.textContent=`gain ${r.gain}  fs ${fs.toFixed(1)} sps  pp ${(r.pp||0).toFixed(0)} µV`
        +`  rms ${(r.rms||0).toFixed(2)} µV`+band
        +(haveT?`  ends ${hms(t1)} UTC (${(r.age||0).toFixed(1)} s behind)`:'');
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


_CHAR_BADGE = {                       # character class -> (bootstrap class, text)
    "cultural": ("text-bg-warning", "impulsive"),
    "weak": ("text-bg-light border", "near-threshold"),
    "plain": ("text-bg-light border", "sustained"),
}


def _char_badge(ch):
    """Waveform-character badge for a detection. Presentation only -- the scoring
    lives in render._build_character. Empty when the window isn't scored yet."""
    if not ch:
        return '<span class="text-muted">&mdash;</span>'
    cls, text = _CHAR_BADGE.get(ch.get("cls", ""), ("text-bg-light border", "?"))
    hf = "n/a" if ch.get("hf") is None else f'{ch["hf"]:.2f}'
    tip = (f'envelope kurtosis {ch.get("kurt")} &middot; {ch.get("dur")} s above 25% of '
           f'peak &middot; peak/median {ch.get("snr")} &middot; HF fraction {hf} '
           f'(informational)')
    return (f'<span class="badge {cls}" title="{tip}">{text}</span>')


@app.get("/")
def home():
    all_evs = _recent_events()
    evs = all_evs[:MAX_ROWS]                  # newest MAX_ROWS only
    withheld = len(all_evs) - len(evs)
    # off the request path: fills in a background thread (the day-file parse is
    # ~90 s cold), so the page always renders now and unscored rows fill in later.
    # Only the DISPLAYED rows are scored -- capping the table caps this work too.
    render.ensure_sparklines_async([e.get("start", "") for e in evs])
    if evs:
        rows = "".join(
            f'<tr><td>{e.get("start","").replace("+00:00","")}</td><td>{e.get("duration_s","")}s</td>'
            f'<td>{e.get("peak_ratio","")}</td><td>{e.get("peak_uv","")} µV</td>'
            f'<td class="spark-cell">{render.event_sparkline(e.get("start",""))}</td>'
            f'<td>{_char_badge(render.event_character(e.get("start","")))}</td></tr>'
            for e in evs)
    else:
        rows = (f'<tr><td colspan="6" class="text-muted">no detections in the last '
                f'{WINDOW_H:g}&nbsp;h above STA/LTA {MIN_RATIO:g}</td></tr>')
    ts = int(time.time())
    body = (
        _titleblock(SID, f'DIY geophone seismometer &middot; {PLACE} &middot; vertical '
                         '4.5&nbsp;Hz &middot; independent station (not for scientific use)')
        + _card("Live &middot; last 30&nbsp;s (UTC)",
                '<canvas id="c"></canvas><div id="hud">connecting…</div>')
        + _card("Live spectrum &middot; same 30&nbsp;s window "
                '<span class="fw-normal text-muted">&middot; ASD µV/&radic;Hz, log&ndash;log</span>',
                '<canvas id="s"></canvas>'
                '<div class="text-muted small mt-2 mb-0">Welch over the live 30&nbsp;s ring '
                '(~0.12&nbsp;Hz resolution). Updates as the ring does, ~every 3&nbsp;s. '
                'The dashed line marks the geophone&rsquo;s 4.5&nbsp;Hz corner &mdash; response '
                'falls steeply below it, so the rise at the left is instrument, not ground.</div>')
        + _card("Helicorder &middot; last 4 hours (UTC)",
                f'<img id="heli" class="plot" src="/helicorder.png?{ts}" alt="helicorder">')
        + _card(f"Detections &middot; last {WINDOW_H:g}&nbsp;h &middot; STA/LTA &ge; {MIN_RATIO:g}"
                + (f' <span class="fw-normal text-muted">&middot; newest {MAX_ROWS} of '
                   f'{len(all_evs)}</span>' if withheld else ""),
                '<table class="table table-sm table-striped mb-0 align-middle">'
                '<thead><tr><th>start (UTC)</th><th>duration</th><th>STA/LTA</th><th>peak</th>'
                '<th>waveform <span class="fw-normal text-muted">&plusmn;30&nbsp;s, 1&ndash;15&nbsp;Hz</span></th>'
                '<th>character <span class="fw-normal text-muted">shape only</span></th></tr></thead>'
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
     'local quake would show a sharp P&nbsp;arrival followed seconds later by a larger S. '
     'The <b>character</b> column describes the <i>shape</i> of each detection, nothing more: '
     '&ldquo;impulsive&rdquo; means a single sharp spike in an otherwise quiet window, which is what '
     'household thumps look like; &ldquo;sustained&rdquo; means the energy lasts, and '
     '&ldquo;near-threshold&rdquo; means it barely cleared the trigger. It is deliberately <b>not</b> an '
     'earthquake/not-earthquake verdict &mdash; a very close quake is impulsive too, and this station has '
     'yet to record a confirmed one to check the labels against.</p>'),
    ("Where it sits",
     '<p class="mb-0 prose">{place} &mdash; on valley-margin alluvium at the foot of the '
     'Sonoma/Mayacamas volcanics, essentially atop the active <b>Rodgers Creek fault</b> system. A '
     'sensitive spot for local events, at the cost of a bit more everyday noise.</p>'),
]


@app.get("/about")
def about():
    photo = _card(
        "The station",
        '<img src="/station.jpg" class="plot" alt="The assembled seismometer '
        'station on the workbench">'
        '<p class="text-muted small mb-0 mt-2">The complete station assembled on '
        'the bench &mdash; geophone, ADS1256 digitizer, and Raspberry&nbsp;Pi.</p>',
    ) if _STATION_JPG else ""
    cards = photo + "".join(_card(h, inner.replace("{place}", PLACE))
                            for h, inner in ABOUT_SECTIONS)
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

# Static station photo, baked into the image and read once at startup.
_STATION_JPG_PATH = os.path.join(os.path.dirname(__file__), "station.jpg")
try:
    with open(_STATION_JPG_PATH, "rb") as _f:
        _STATION_JPG = _f.read()
except OSError:
    _STATION_JPG = None
STATIC_CACHE = {"Cache-Control": "public, max-age=86400"}   # static asset — 1 day


@app.get("/station.jpg")
def station_photo():
    return Response(_STATION_JPG, media_type="image/jpeg", headers=STATIC_CACHE) \
        if _STATION_JPG else Response("not found", status_code=404)


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

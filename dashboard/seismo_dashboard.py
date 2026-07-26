#!/usr/bin/env python3
"""seismo_dashboard.py — public seismo dashboard (FastHTML + Bootstrap 5), served on the Dokku host.

Reads the rsync-mirrored miniSEED + events (no ADC, no acquisition here), serves the
pre-rendered helicorder + cached spectrum, and streams the mirrored live ring. UI is
Bootstrap 5 (light mode, subtle palette); the route handlers stay thin (build data,
hand HTML/PNG back) with page markup in module-level template helpers.
"""
import glob
import json
import math
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
# Environmental node (CLUE -> pi4env -> mirrored here). Directory of daily CSVs
# `env-YYYY-MM-DD.csv` (schema utc,clue_mono_s,temp_C,press_hPa,humid_pct,ax,ay,az).
ENV_DIR = os.environ.get("SEISMO_ENV_DIR", "/data/env")
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
        + link("/detections", "Detections", "detections")
        + link("/spectrum", "Spectrum", "spectrum")
        + link("/env", "Environment", "env")
        + link("/learn", "Seismology 101", "learn")
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
    )
    return Response(_shell(BRAND, "live", body, HOME_JS), media_type="text/html")


# --- detections --------------------------------------------------------------


_DET_HEAD = (
    '<thead><tr><th>start (UTC)</th><th>duration</th><th>STA/LTA</th><th>peak</th>'
    # Window is asymmetric (SPARK_PRE before the trigger, SPARK_POST after), so the
    # red onset marker sits ~1/3 in, NOT centred -- the label must not say "+/-".
    f'<th>waveform <span class="fw-normal text-muted">'
    f'{render.SPARK_PRE + render.SPARK_POST:g}&nbsp;s</span></th>'
    '<th>character <span class="fw-normal text-muted">shape only</span></th></tr></thead>')


def _det_row(e):
    """One detections row. The waveform + character cells carry data-spark/data-char
    (keyed by event start) so the client can fill any that weren't cached at render
    time -- see SPARK_JS."""
    s = e.get("start", "")
    return (f'<tr><td>{s.replace("+00:00","")}</td><td>{e.get("duration_s","")}s</td>'
            f'<td>{e.get("peak_ratio","")}</td><td>{e.get("peak_uv","")} µV</td>'
            f'<td class="spark-cell" data-spark="{s}">{render.event_sparkline(s)}</td>'
            f'<td data-char="{s}">{_char_badge(render.event_character(s))}</td></tr>')


def _det_table(events, empty_msg):
    rows = ("".join(_det_row(e) for e in events) if events
            else f'<tr><td colspan="6" class="text-muted">{empty_msg}</td></tr>')
    return ('<table class="table table-sm table-striped mb-0 align-middle">'
            f'{_DET_HEAD}<tbody>{rows}</tbody></table>')


# Client-side fill for sparkline/character cells not cached at render time (the
# day-file slice runs off the request path). Each pending cell polls /sparkline
# until its SVG is ready, then swaps it in -- so a cold load no longer looks broken
# and needs no manual reload. Gives up after ~40 s (data genuinely not mirrored yet).
SPARK_JS = """<script>
(function(){
  const pend=()=>[...document.querySelectorAll('td.spark-cell[data-spark]')].filter(td=>!td.querySelector('svg'));
  let tries=0;
  async function poll(){
    const cells=pend();
    if(!cells.length||tries++>20)return;
    const seen=new Set();
    for(const td of cells){
      const s=td.getAttribute('data-spark');
      if(seen.has(s))continue; seen.add(s);
      try{
        const r=await(await fetch('/sparkline?start='+encodeURIComponent(s))).json();
        if(r.ready){
          const q=CSS.escape(s);
          document.querySelectorAll('td.spark-cell[data-spark="'+q+'"]').forEach(c=>c.innerHTML=r.spark);
          document.querySelectorAll('td[data-char="'+q+'"]').forEach(c=>c.innerHTML=r.char);
        }
      }catch(e){}
    }
    setTimeout(poll,2000);
  }
  if(pend().length)setTimeout(poll,1500);
})();
</script>"""


@app.get("/detections")
def detections_page():
    all_evs = _recent_events()                       # newest-first, >=MIN_RATIO, 24 h
    recent = all_evs[:5]                              # 5 most recent
    # "Strongest" = highest STA/LTA ratio, NOT peak amplitude. Amplitude ranks a
    # nearby cultural thump above a distant real quake (a close-small event out-shakes
    # a far-bigger one); the ratio measures how far a signal rose above background, so
    # a genuine event surfaces (the M2.5 was ratio 645, #1; #6 by amplitude).
    strongest = sorted(all_evs, key=lambda e: float(e.get("peak_ratio", 0) or 0),
                       reverse=True)[:5]
    # Build sparkline+character for every row shown, off the request path (union so a
    # detection in both tables is built once).
    starts = list({e.get("start", "") for e in recent} | {e.get("start", "") for e in strongest})
    render.ensure_sparklines_async(starts)
    empty = f'no detections in the last {WINDOW_H:g}&nbsp;h above STA/LTA {MIN_RATIO:g}'
    body = (
        _titleblock("Detections", f'{SID} &middot; automatic STA/LTA triggers &middot; '
                                  'almost all of these are cultural noise, not earthquakes')
        + _card('5 most recent <span class="fw-normal text-muted">&middot; last '
                f'{WINDOW_H:g}&nbsp;h &middot; STA/LTA &ge; {MIN_RATIO:g}</span>',
                _det_table(recent, empty), body_class="table-responsive")
        + _card('5 strongest <span class="fw-normal text-muted">&middot; last '
                f'{WINDOW_H:g}&nbsp;h &middot; by STA/LTA ratio</span>',
                _det_table(strongest, empty), body_class="table-responsive")
        + '<p class="text-muted mb-0">The trigger fires on any sudden jump in energy. '
          'Footsteps, doors, machinery and passing vehicles all qualify, so treat these '
          'as a log of <i>things that moved the ground</i> rather than a list of earthquakes. '
          'The <b>character</b> column describes waveform shape only &mdash; see '
          '<a href="/about">About</a>.</p>'
    )
    return Response(_shell(f"Detections — {BRAND}", "detections", body, SPARK_JS),
                    media_type="text/html")


@app.get("/sparkline")
def sparkline(start: str = ""):
    """The (possibly still-building) sparkline SVG + character badge for one detection,
    as JSON. The detections page polls this to fill cells not cached at render time."""
    if not start:
        return JSONResponse({"ready": False, "spark": "", "char": ""})
    render.ensure_sparklines_async([start])          # re-kick if the page's fill died
    svg = render.event_sparkline(start)
    return JSONResponse({"ready": bool(svg), "spark": svg,
                         "char": _char_badge(render.event_character(start))})


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
            + _card("Amplitude spectral density", inner))
    return Response(_shell(f"Spectrum — {BRAND}", "spectrum", body, SPEC_JS),
                    media_type="text/html")


# --- about -------------------------------------------------------------------

# --- seismology 101 ------------------------------------------------------------
# Written for a curious non-specialist (Charles's ask: "a family member who gets
# curious"). Plain language, concrete numbers from THIS station, and honest about
# what the instrument cannot do -- the deaf-below-4.5-Hz part is the bit people
# most often misread as a fault.
LEARN_SECTIONS = [
    ("Start here: what this thing actually measures",
     '<p class="prose">A seismometer does not measure earthquakes &mdash; it measures '
     '<b>ground motion</b>, continuously, whether or not anything interesting is happening. '
     'Earthquakes are just one of the things that move it.</p>'
     '<p class="prose"><b>This</b> instrument measures one specific thing: <b>how fast the ground '
     'moves up and down</b>. &ldquo;Up and down&rdquo; because it is a single vertical sensor '
     '(others add the two horizontal directions), and &ldquo;how fast&rdquo; &mdash; velocity '
     '&mdash; because of how it works. Instruments built differently report the ground&rsquo;s '
     'displacement or its acceleration instead; see the glossary.</p>'
     '<p class="prose">Inside the sensor (a <i>geophone</i>) is a heavy magnet hanging on a spring '
     'inside a coil of wire. When the ground jolts, the case moves but the magnet&rsquo;s inertia '
     'makes it lag behind &mdash; and a magnet moving inside a coil generates a voltage. That '
     'voltage is the measurement. It is <b>tiny</b>: the quietest signals here are under a '
     'millionth of a volt, which is why so much of this project is about fighting electrical '
     'noise.</p>'
     '<p class="mb-0 prose">The speeds involved are small too. A quiet night here is ground motion '
     'of roughly <b>25 nanometres per second</b> &mdash; about the width of a virus, per second. '
     'A person walking past is thousands of times bigger than that.</p>'),

    ("Putting real numbers on it",
     '<p class="prose">The voltage the sensor produces converts straight to a ground speed, because '
     'this geophone gives <b>28.8 volts for every metre-per-second</b> of motion. Working that down '
     'to the sizes we actually see:</p>'
     '<div class="table-responsive"><table class="table table-sm align-middle">'
     '<thead><tr><th>At the sensor</th><th>Ground speed</th></tr></thead><tbody>'
     '<tr><td><b>1 microvolt</b> (µV)</td><td><b>34.7 nm/s</b> &mdash; the working unit here</td></tr>'
     '<tr><td>1 nanometre/second</td><td>0.029 µV, or about 3 of the digitizer&rsquo;s steps</td></tr>'
     '<tr><td>Smallest step the digitizer can resolve</td><td>0.32 nm/s</td></tr>'
     '<tr><td>Quiet-night noise floor (~0.7 µV)</td><td>~24 nm/s</td></tr>'
     '</tbody></table></div>'
     '<p class="prose"><b>How far does the ground actually travel?</b> That is a different question '
     'from how fast, and the answer depends on frequency &mdash; a fast wiggle covers less distance '
     'than a slow one at the same speed (distance = speed &divide; 2&pi;&#8202;&times;&#8202;'
     'frequency). At the quiet-night floor, the ground is physically moving by about:</p>'
     '<div class="table-responsive"><table class="table table-sm align-middle">'
     '<thead><tr><th>Frequency</th><th>How far it moves</th></tr></thead><tbody>'
     '<tr><td>4.5 Hz</td><td>~0.8 nm</td></tr>'
     '<tr><td>10 Hz</td><td>~0.4 nm</td></tr>'
     '<tr><td>20 Hz</td><td>~0.2 nm</td></tr>'
     '</tbody></table></div>'
     '<p class="prose">Those distances are <b>smaller than a single atom is wide</b> '
     '(an atom is about 0.1&ndash;0.5&nbsp;nm). Detecting motion that small on thirty dollars of '
     'hardware sitting on a garage floor is the part worth being slightly amazed by.</p>'
     '<p class="mb-0 prose"><b>One catch</b>, and it is why the <a href="/spectrum">spectrum</a> is '
     'cut off at the left: the &ldquo;34.7 nm/s per µV&rdquo; figure only holds <b>above about '
     '4.5&nbsp;Hz</b>. Below that the sensor goes progressively deaf, so the same voltage means '
     '<i>much</i> more real ground motion &mdash; roughly 5× more at 2&nbsp;Hz, 20× at 1&nbsp;Hz. '
     'It is a velocity meter with an honest range, not a universal ruler.</p>'),

    ("P waves, S waves, and how one station can guess the distance",
     '<p class="prose">An earthquake sends out several kinds of wave, and they travel at different '
     'speeds. That difference is the single most useful fact in seismology.</p>'
     '<div class="table-responsive"><table class="table table-sm align-middle">'
     '<thead><tr><th>Wave</th><th>Speed</th><th>Motion</th><th>What you see</th></tr></thead>'
     '<tbody>'
     '<tr><td><b>P</b> (primary)</td><td>~6 km/s</td><td>push&ndash;pull, like sound</td>'
     '<td>arrives <b>first</b>, usually smaller &mdash; a sharp tick</td></tr>'
     '<tr><td><b>S</b> (secondary)</td><td>~3.5 km/s</td><td>side-to-side shear</td>'
     '<td>arrives <b>later</b>, usually <b>bigger</b> &mdash; the real shaking</td></tr>'
     '<tr><td><b>Surface</b></td><td>~3 km/s</td><td>rolling, like ocean swell</td>'
     '<td>slowest, longest-lasting; dominates <i>distant</i> quakes</td></tr>'
     '</tbody></table></div>'
     '<p class="prose">Because P outruns S, the gap between them grows with distance &mdash; and a '
     '<b>single</b> station can therefore estimate how far away a quake was, even though it cannot '
     'tell which <i>direction</i> it came from. The rule of thumb: <b>multiply the P&ndash;S gap in '
     'seconds by about 8 to get kilometres.</b> A 3-second gap means roughly 25 km away; a '
     '10-second gap, about 80 km.</p>'
     '<p class="prose">If that feels familiar, it is <i>exactly</i> the same trick as '
     '<b>counting the seconds between the lightning flash and the thunder</b> and dividing by '
     'five for miles. One event, two signals, different speeds: the gap between their arrivals '
     'grows in proportion to distance, at a rate set only by the <b>difference between the two '
     'speeds</b>. For light and sound that difference works out to five seconds per mile; for '
     'P and S waves, about eight kilometres per second of gap. Same law, different numbers.</p>'
     '<p class="mb-0 prose">This is also the honest way to tell a real earthquake from someone '
     'closing a door: a quake shows <b>two arrivals</b> a few seconds apart, then a long tail that '
     'fades slowly (the <i>coda</i>). A door is one thump that stops.</p>'),

    ("Microseisms: the ocean, humming, forever",
     '<p class="prose">Even with no earthquakes anywhere and nobody moving, the ground is never '
     'still. Ocean waves press rhythmically on the seafloor, and that pressure radiates through '
     'the crust as a continuous, worldwide vibration called the <b>microseism</b>. It is the '
     'loudest thing in most seismic records &mdash; a permanent background hum, strongest in '
     'winter storm season.</p>'
     '<p class="prose">It is slow: peaks around <b>0.07&nbsp;Hz and 0.15&nbsp;Hz</b>, meaning one '
     'cycle every 7 to 14 seconds. You could not feel it, but a good instrument sees it '
     'constantly.</p>'
     '<p class="prose"><b>This station cannot hear it</b>, and that is by design rather than by '
     'fault &mdash; see the next section for why. If you wonder why the spectrum page is cut off '
     'at the left, that is the reason.</p>'
     '<p class="mb-0 prose">There <i>are</i> peaks down in that range on our spectrum, but they '
     'are not the ocean, and the shape gives it away. A microseism is a <b>broad hump</b> '
     'spreading across 0.05&ndash;0.2&nbsp;Hz. What we actually have is a set of <b>narrow '
     'spikes</b> at 0.035, 0.07, 0.14 and 0.195&nbsp;Hz &mdash; a fundamental with a period of '
     '28.6&nbsp;seconds plus its harmonics, which is the fingerprint of a machine cycling on and '
     'off somewhere in the house, not of an ocean. (Confirmed by measurement, 2026-07-23. It is '
     'a nice coincidence trap: the 0.07&nbsp;Hz harmonic lands squarely in the microseism band.) '
     'Underneath them the curve rises smoothly toward the left, and that part is the '
     'instrument&rsquo;s own electrical noise.</p>'
     '<p class="mb-0 prose small text-muted">The <a href="/spectrum">spectrum page</a> does shade the microseism band, but only to show you <i>where</i> it lives relative to what this sensor can reach &mdash; it is labelled &ldquo;below our response&rdquo; for that reason.</p>'),

    ("What this geophone can and cannot hear",
     '<p class="prose">Every sensor has a band of frequencies it responds to. This one is a '
     '<b>4.5&nbsp;Hz geophone</b>: it hears things that vibrate a few times per second and faster, '
     'and it goes progressively deaf below that. By the microseism it is around '
     '<b>60&nbsp;dB down</b> &mdash; a factor of a thousand &mdash; so those slow ocean waves are '
     'simply below the instrument, not missing from the world.</p>'
     '<div class="table-responsive"><table class="table table-sm align-middle">'
     '<thead><tr><th>Source</th><th>Frequency</th><th>Heard here?</th></tr></thead><tbody>'
     '<tr><td>Footsteps, doors, appliances, cars</td><td>2&ndash;30 Hz</td>'
     '<td class="text-success"><b>Loud and clear</b> &mdash; most of what we record</td></tr>'
     '<tr><td>Small local earthquake, tens of km</td><td>2&ndash;20 Hz</td>'
     '<td class="text-success"><b>Yes</b> &mdash; the target</td></tr>'
     '<tr><td>Moderate quake, a few hundred km</td><td>1&ndash;10 Hz</td>'
     '<td>Usually, if big enough</td></tr>'
     '<tr><td>Great quake on the far side of the planet</td><td>0.01&ndash;0.05 Hz</td>'
     '<td class="text-danger"><b>No</b> &mdash; arrives as slow swells we are deaf to</td></tr>'
     '<tr><td>Ocean microseism</td><td>0.07&ndash;0.15 Hz</td>'
     '<td class="text-danger"><b>No</b> &mdash; ~1000× below our response</td></tr>'
     '<tr><td>Earth&rsquo;s &ldquo;hum&rdquo; (free oscillations)</td><td>0.002&ndash;0.007 Hz</td>'
     '<td class="text-danger"><b>No</b> &mdash; needs a million-dollar gravimeter</td></tr>'
     '</tbody></table></div>'
     '<p class="mb-0 prose">So this is a <b>local earthquake instrument</b>. The trade is '
     'deliberate: a sensor that hears the whole planet costs thousands and needs a vault, while '
     'this one costs about thirty dollars and sits on a garage floor above an active fault '
     'system.</p>'),

    ("Why most &ldquo;detections&rdquo; are not earthquakes",
     '<p class="prose">The station watches for sudden jumps in energy (see <i>STA/LTA</i> in the '
     'glossary) and logs each one. Nearly all of them are <b>cultural noise</b> &mdash; the '
     'seismologist&rsquo;s word for humans and machinery. Footsteps, a door, the fridge '
     'compressor, a car in the driveway.</p>'
     '<p class="prose">Frustratingly, you cannot filter them out by size: a sharp thump right next '
     'to the sensor produces a <i>bigger</i> reading than a genuine earthquake fifty kilometres '
     'away. So the table shows a <b>character</b> label describing the <i>shape</i> of each '
     'detection, which is a better clue than its amplitude. It is a description, not a verdict.</p>'
     '<p class="mb-0 prose">If you want to check something yourself, the '
     '<a href="https://earthquake.usgs.gov/earthquakes/map/">USGS map</a> lists real quakes with '
     'times in UTC. A detection here that matches a catalogue entry, at a sensible P&ndash;S gap, '
     'is the real thing.</p>'),

    ("Reading the views on the front page",
     '<p class="prose"><b>Live waveform</b> &mdash; the last 30 seconds, scrolling. Flat means '
     'quiet. The numbers underneath give the current noise level; the smaller the better.</p>'
     '<p class="prose"><b>Live spectrum</b> &mdash; the same 30 seconds, but broken out by '
     'frequency instead of time: <i>which</i> vibrations are present rather than <i>when</i>. '
     'The rise at the left is the instrument going deaf, not real ground motion.</p>'
     '<p class="mb-0 prose"><b>Helicorder</b> &mdash; the classic paper-drum view, one row per '
     '15&nbsp;minutes, four hours per screen. This is where an earthquake looks like an '
     'earthquake: a sudden fat burst that tapers off, unlike the even fuzz of ordinary noise. '
     'Fat rows during the day and thin rows at 4&nbsp;AM are people, not geology.</p>'),

    ("Glossary",
     '<div class="table-responsive"><table class="table table-sm align-middle"><tbody>'
     '<tr><td><b>Geophone</b></td><td>The sensor: magnet on a spring inside a coil. Converts '
     'ground <i>velocity</i> into a voltage.</td></tr>'
     '<tr><td><b>4.5&nbsp;Hz</b></td><td>This geophone&rsquo;s corner frequency &mdash; roughly '
     'where it stops responding well as frequencies fall.</td></tr>'
     '<tr><td><b>Hz (hertz)</b></td><td>Cycles per second. 10&nbsp;Hz = ten vibrations per '
     'second.</td></tr>'
     '<tr><td><b>µV (microvolt)</b></td><td>A millionth of a volt. Our quiet-night signal is under '
     'one.</td></tr>'
     '<tr><td><b>nm/s</b></td><td>Nanometres per second &mdash; actual ground speed. A quiet night '
     'here is ~25.</td></tr>'
     '<tr><td><b>Velocity / displacement / acceleration</b></td><td>Three ways to describe the '
     'same motion. A geophone (this station) senses <i>velocity</i> &mdash; how fast the ground '
     'moves. Broadband seismometers report <i>displacement</i> (how far) and accelerometers '
     'report <i>acceleration</i> (how hard the shove); each suits a different job.</td></tr>'
     '<tr><td><b>Component</b></td><td>The direction a sensor listens along &mdash; vertical (Z, '
     'like ours), or the two horizontals (N and E). A full station runs all three.</td></tr>'
     '<tr><td><b>ADC / counts</b></td><td>The analogue-to-digital converter turns the voltage into '
     'whole numbers (&ldquo;counts&rdquo;) 100 times a second.</td></tr>'
     '<tr><td><b>sps</b></td><td>Samples per second. This station records 100.</td></tr>'
     '<tr><td><b>P wave / S wave</b></td><td>The fast push&ndash;pull arrival and the slower, '
     'larger shear arrival. Their gap gives distance.</td></tr>'
     '<tr><td><b>Coda</b></td><td>The long fading tail after a quake, from waves scattering off '
     'underground structure.</td></tr>'
     '<tr><td><b>Microseism</b></td><td>Continuous worldwide background hum driven by ocean waves, '
     '0.07&ndash;0.15&nbsp;Hz. Below this instrument.</td></tr>'
     '<tr><td><b>Cultural noise</b></td><td>Vibration from people and machines. Dominates any '
     'suburban station.</td></tr>'
     '<tr><td><b>Teleseism</b></td><td>A distant earthquake, thousands of km away. Needs a '
     'broadband sensor, not this one.</td></tr>'
     '<tr><td><b>STA/LTA</b></td><td>Short-Term Average over Long-Term Average: compares recent '
     'energy to the recent past. A big ratio means &ldquo;something just started&rdquo; and trips '
     'a detection.</td></tr>'
     '<tr><td><b>Helicorder</b></td><td>Drum-style plot, one row per time interval &mdash; named '
     'for the rotating paper drums of mechanical seismographs.</td></tr>'
     '<tr><td><b>Spectrum / ASD</b></td><td>Amplitude spectral density: signal strength per '
     'frequency, in µV per root-hertz. Lets you compare noise at one frequency against '
     'another.</td></tr>'
     '<tr><td><b>High-pass filter</b></td><td>Throws away slow drift and keeps the fast wiggles, '
     'so slow temperature-driven tilt does not swamp the quake band.</td></tr>'
     '<tr><td><b>Magnitude</b></td><td>Earthquake size on a logarithmic scale: each whole number '
     'is ~32× more energy. M2 is barely felt; M6 damages buildings.</td></tr>'
     '<tr><td><b>UTC</b></td><td>Universal time, used for everything here so records worldwide '
     'line up. Local time is UTC&nbsp;&minus;&nbsp;7 in summer.</td></tr>'
     '<tr><td><b>miniSEED</b></td><td>The standard file format for seismic data, so this '
     'station&rsquo;s recordings work with professional tools.</td></tr>'
     '<tr><td><b>Noise floor</b></td><td>The smallest motion the instrument can distinguish from '
     'its own electrical hiss. Lowering it is most of the work.</td></tr>'
     '</tbody></table></div>'),

    ("Where this station sits, and why here",
     '<p class="prose">{place} &mdash; on valley-margin sediments essentially on top of the active '
     '<b>Rodgers Creek</b> fault system, with the <b>Maacama</b> fault nearby and '
     '<b>The Geysers</b> geothermal field about 30&nbsp;km north. The Geysers is the most '
     'seismically active spot in Northern California, producing hundreds of small quakes a year, '
     'which makes it the most likely source of anything genuine this station records.</p>'
     '<p class="mb-0 prose">Sitting on soft sediment is a mixed blessing: it <i>amplifies</i> '
     'shaking, which helps a sensitive instrument, but it also carries more everyday noise. For a '
     'station whose goal is catching small local events, that is the right side of the trade.</p>'),
]


ABOUT_SECTIONS = [
    ("What this is",
     '<p class="mb-0 prose">A homemade (&ldquo;DIY&rdquo;) seismometer &mdash; an amateur '
     'instrument that senses the ground moving: earthquakes, the ocean, and everyday cultural '
     'vibration. It records continuously and is <b>independent</b> (not part of a formal seismic '
     'network), built for curiosity and learning. <b>Not for scientific or emergency use.</b> '
     'The station is still being <b>tested, tuned, and modified</b>, so spurious signals '
     '(from the work itself, not the ground) may appear in the data.</p>'
     '<p class="mb-0 prose">New to any of this? <a href="/learn">Seismology&nbsp;101</a> explains P and S waves, microseisms, what this sensor can and cannot hear, and every term used on these pages.</p>'),
    ("Hardware",
     '<ul class="mb-0"><li><b>Sensor:</b> LGT-4.5 geophone &mdash; a 4.5&nbsp;Hz vertical geophone '
     '(a coil-and-magnet <i>velocity</i> sensor), ~28.8&nbsp;V per m/s, 385&nbsp;&#8486; coil.</li>'
     '<li><b>Digitizer:</b> Waveshare High-Precision <b>ADS1256</b> &mdash; 24-bit ADC, read '
     'differentially at gain&nbsp;64, 100&nbsp;samples/sec.</li>'
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
     '<p class="mb-0 prose"><b>Detections</b> (on their <a href="/detections">own page</a>) &mdash; '
     'automatic STA/LTA triggers (sudden energy '
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


@app.get("/learn")
def learn():
    cards = "".join(_card(h, inner.replace("{place}", PLACE))
                    for h, inner in LEARN_SECTIONS)
    body = (_titleblock("Seismology 101",
                        "what this instrument hears, and the words for it")
            + '<div class="row"><div class="col-lg-9">'
            + '<p class="text-muted">No background assumed. If a term on the other pages '
              'looks like jargon, it is in the glossary at the bottom.</p>'
            + cards + '</div></div>')
    return Response(_shell(f"Seismology 101 — {BRAND}", "learn", body),
                    media_type="text/html")


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


# --- environmental node ------------------------------------------------------


def _env_now():
    """Latest reading from the mirrored CLUE CSVs, or None. Reads the newest
    env-*.csv and returns the last row whose fields all parse as numbers (so a
    reboot-banner line can't surface); adds host-clock age (s) and tilt (deg)."""
    try:
        files = sorted(glob.glob(os.path.join(ENV_DIR, "env-*.csv")))
        if not files:
            return None
        with open(files[-1]) as f:
            lines = f.readlines()
    except Exception:
        return None
    for line in reversed(lines):
        parts = line.strip().split(",")
        if len(parts) != 8 or parts[0] == "utc":
            continue
        try:
            _mono, temp, press, humid, ax, ay, az = (float(x) for x in parts[1:])
        except ValueError:
            continue
        try:
            t = datetime.fromisoformat(parts[0])
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - t).total_seconds()
        except ValueError:
            age = None
        amag = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
        tilt = math.degrees(math.acos(min(1.0, abs(az) / amag)))
        return {"utc": parts[0], "temp": temp, "press": press, "humid": humid,
                "ax": ax, "ay": ay, "az": az, "tilt": tilt, "age": age}
    return None


@app.get("/env-data")
def env_data():
    return JSONResponse(_env_now() or {})


def _env_tile(label, span_id, value, unit, sub=""):
    val = "&mdash;" if value is None else value
    sub = f'<div class="text-muted small mt-1">{sub}</div>' if sub else ""
    return (
        '<div class="col-6 col-lg-3"><div class="border rounded p-3 h-100 bg-white">'
        f'<div class="text-muted small text-uppercase">{label}</div>'
        f'<div class="fs-3 lh-1 mt-2"><span id="{span_id}">{val}</span> '
        f'<span class="fs-6 text-muted">{unit}</span></div>{sub}</div></div>')


ENV_JS = """<script>
async function envpoll(){
  try{
    const e=await(await fetch('/env-data')).json();
    const set=(id,v)=>{const el=document.getElementById(id);if(el&&v!=null)el.textContent=v;};
    if(e.utc){
      set('e_press',e.press.toFixed(2));set('e_temp',e.temp.toFixed(1));
      set('e_humid',e.humid.toFixed(1));set('e_tilt',e.tilt.toFixed(1));
      set('e_accel',`ax ${e.ax.toFixed(2)}  ay ${e.ay.toFixed(2)}  az ${e.az.toFixed(2)}`);
      set('e_utc',e.utc.replace('+00:00','')+' UTC');
      const st=document.getElementById('e_status'),age=(e.age==null)?null:Math.round(e.age);
      if(st&&age!=null){
        if(age<180){st.textContent=`live · ${age}s behind`;st.className='small text-success';}
        else{st.textContent=`stale · last reading ${Math.round(age/60)} min ago`;st.className='small text-danger';}
      }
    }
  }catch(err){}
  setTimeout(envpoll,15000);
}
envpoll();
</script>"""


@app.get("/env")
def env_page():
    e = _env_now()
    def g(k, fmt):
        return None if e is None or e.get(k) is None else fmt(e[k])
    tiles = (
        _env_tile("Pressure", "e_press", g("press", lambda v: f"{v:.2f}"), "hPa")
        + _env_tile("Temperature", "e_temp", g("temp", lambda v: f"{v:.1f}"), "&deg;C",
                    "board self-heat &mdash; read <b>changes</b>, not the absolute")
        + _env_tile("Humidity", "e_humid", g("humid", lambda v: f"{v:.1f}"), "%")
        + _env_tile("Tilt from level", "e_tilt", g("tilt", lambda v: f"{v:.1f}"), "&deg;",
                    "from the gravity vector")
    )
    accel = ("&mdash;" if e is None else
             f'ax {e["ax"]:.2f}&nbsp;&nbsp;ay {e["ay"]:.2f}&nbsp;&nbsp;az {e["az"]:.2f}')
    utc = "&mdash;" if e is None else e["utc"].replace("+00:00", "") + " UTC"
    inner = (
        f'<div class="row g-3">{tiles}</div>'
        '<div class="d-flex flex-wrap justify-content-between mt-3 text-muted small">'
        f'<div>acceleration (m/s&sup2;): <span id="e_accel">{accel}</span></div>'
        f'<div>last reading <span id="e_utc">{utc}</span> '
        f'&middot; <span id="e_status" class="small"></span></div></div>')
    body = (
        _titleblock("Environment",
                    "CLUE sensor node in the garage beside the station &middot; pressure, "
                    "tilt, temperature, humidity at 1&nbsp;Hz")
        + _card("Current conditions", inner)
        + _card("What this is",
                '<p class="mb-2">A small sensor node (Adafruit CLUE) sits ~1&nbsp;m from the '
                'geophone, logging pressure, tilt, temperature and humidity once a second. '
                'It exists to explain slow station noise: <b>pressure</b> and <b>tilt</b> are the '
                'leading suspects for the sub-Hz ground undulation the seismometer sees.</p>'
                '<p class="mb-0 text-muted small">Temperature reads the board&rsquo;s own '
                'self-heat, not room air, so only its <i>changes</i> are meaningful. Values '
                'mirror here about once a minute; the page refreshes every 15&nbsp;s.</p>'))
    return Response(_shell(BRAND, "env", body, ENV_JS), media_type="text/html")


heli_service.start()      # background: build envelopes + pre-render the drum

if __name__ == "__main__":
    serve(port=int(os.environ.get("PORT", "5001")), reload=False)

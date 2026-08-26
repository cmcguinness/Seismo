#!/usr/bin/env python3
"""seismo_dashboard.py — public seismo dashboard (FastHTML + Bootstrap 5), served on the Dokku host.

Reads the UDP-streamed miniSEED mirror + events (no ADC, no acquisition here), serves the
pre-rendered helicorder + cached spectrum, and streams the mirrored live ring. UI is
Bootstrap 5 (light mode, subtle palette); the route handlers stay thin (build data,
hand HTML/PNG back) with page markup in module-level template helpers.
"""
import glob
import json
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone

from fasthtml.common import FastHTML, serve
from starlette.responses import JSONResponse, Response

import activity
import catches
import content
import heli_build
import heli_render
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
 .srcpill{border-radius:999px;padding:.3em .85em;font-size:.78rem;font-weight:500;
   background:#e7f1f0;color:#2f6f6b;border:1px solid #cfe3e1;cursor:help}
 .srcpill.active{background:var(--accent);color:#fff;border-color:var(--accent)}
 .tooltip-inner{max-width:360px;text-align:left;line-height:1.45}
 a{color:var(--accent)}
</style>"""

# Two copies of this app run from the same image: pi5 on the LAN owns the miniSEED
# archive (UDP-streamed from the station) and builds the envelopes; the public copy on
# apps02 (SEISMO_HELI_BUILD=0) renders envelopes pi5 pushes to it every minute.
_PUBLIC_COPY = os.environ.get("SEISMO_HELI_BUILD", "1") != "1"
FOOTER = (
    '<footer class="border-top bg-body-tertiary py-3 mt-4"><div class="container text-muted small">'
    + ('public copy &middot; data pushed from the station every minute, live trace every 3 s &middot; '
       if _PUBLIC_COPY else
       'rendered on the LAN from the station\'s UDP-streamed miniSEED &middot; ')
    + 'built by <a href="https://www.linkedin.com/in/charlesmcguinness/">Charles McGuinness</a>'
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
        + ("" if _PUBLIC_COPY else link("/detections", "Detections", "detections"))
        + link("/history", "History", "history")
        + link("/activity", "Activity", "activity")
        + link("/spectrum", "Spectrum", "spectrum")
        + link("/env", "Environment", "env")
        + link("/catches", "Catches", "catches")
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
// Source badges: which characterised signature (if any) the live ring matches.
// SOFT LABEL -- informational only, never gates anything. Provisional signatures
// (seen on fewer than two separate days) are marked so nobody reads them as fact.
// Source pills. The element is rebuilt ONLY when the matched set changes -- live()
// polls at 300 ms, and rewriting innerHTML that often destroys and recreates the
// span, so a native title tooltip's hover timer never completes and nothing ever
// appears. Same trap that ate the injected badge during testing. Between rebuilds we
// only refresh the tooltip TEXT in place, and not while it is being read.
let _srcKey=null,_srcTips=[];
function srcTip(s){
  const d=s.detail||{};
  return [s.hint,
          d.hz?`${d.hz} Hz mount resonance`:null,
          d.asd?`${d.asd} µV/√Hz`:null,
          d.peak_shoulder?`×${d.peak_shoulder} over continuum`:null,
          'anything that shakes the floor can ring it',
          s.status!=='active'?'provisional — one day of observation':null]
         .filter(Boolean).join(' · ');
}
function sources(list){
  const box=document.getElementById('srcbadges');
  if(!box)return;
  list=list||[];
  const key=list.map(s=>s.id).join(',');
  if(key!==_srcKey){
    _srcTips.forEach(t=>{try{t.dispose();}catch(e){}});
    _srcTips=[];
    box.innerHTML=list.map(s=>
      `<span class="srcpill${s.status==='active'?' active':''}"></span>`).join(' ');
    [...box.children].forEach((el,i)=>{
      el.textContent=list[i].pill||list[i].label;
      const tip=srcTip(list[i]);
      el.dataset.tip=tip;
      if(window.bootstrap&&bootstrap.Tooltip){
        _srcTips.push(new bootstrap.Tooltip(el,{title:tip,placement:'bottom'}));
      } else { el.title=tip; }        // bootstrap.js is deferred; degrade gracefully
    });
    _srcKey=key;
    return;
  }
  // Same signatures still matching -- keep the numbers current, but never swap the
  // text out from under someone reading it. Three guards, because setContent() on a
  // visible tooltip dismisses it: skip entirely while ANY tooltip is open, skip the
  // hovered pill, and skip when the text has not actually changed (the values only
  // move every ~3 s with the ring, not every 300 ms with the poll).
  if(document.querySelector('.tooltip'))return;
  [...box.children].forEach((el,i)=>{
    if(el.matches(':hover'))return;
    const tip=srcTip(list[i]);
    if(el.dataset.tip===tip)return;
    el.dataset.tip=tip;
    if(_srcTips[i]){_srcTips[i].setContent({'.tooltip-inner':tip});} else {el.title=tip;}
  });
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
      sources(r.sources);
      const band=(r.rms_band==null)?'':`  rms(1–15 Hz) ${r.rms_band.toFixed(2)} µV`;
      hud.textContent=`gain ${r.gain}  fs ${fs.toFixed(1)} sps  pp ${(r.pp||0).toFixed(0)} µV`
        +`  rms ${(r.rms||0).toFixed(2)} µV`+band
        +(haveT?`  ends ${hms(t1)} UTC (${(r.age||0).toFixed(1)} s behind)`:'');
      
    } else { hud.textContent='live feed unavailable'; sources(null); }
  }catch(e){hud.textContent='live feed unavailable';}
  setTimeout(live,300);
}
live();
setInterval(()=>{document.getElementById('heli').src='/helicorder.png?'+Date.now();},60000);
</script>"""


def _card(header, inner, body_class="card-body", card_id=None):
    hid = f' id="{card_id}"' if card_id else ""
    return (f'<div class="card shadow-sm mb-4"{hid}><div class="card-header">{header}</div>'
            f'<div class="{body_class}">{inner}</div></div>')


def _slug(header):
    """Anchor id from a section header, so other pages can deep-link to it."""
    txt = re.sub(r"&[a-z]+;|<[^>]+>", " ", header).lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", txt)).strip("-")


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
        + _card('Live &middot; last 30&nbsp;s (UTC)<span id="srcbadges" '
                'class="float-end"></span>',
                '<canvas id="c"></canvas><div id="hud">connecting…</div>')
        + _card("Live spectrum &middot; same 30&nbsp;s window "
                '<span class="fw-normal text-muted">&middot; ASD µV/&radic;Hz, log&ndash;log</span>',
                '<canvas id="s"></canvas>'
                '<div class="text-muted small mt-2 mb-0">Welch over the live 30&nbsp;s ring '
                '(~0.12&nbsp;Hz resolution). Updates as the ring does, ~every 3&nbsp;s. '
                'The dashed line marks the geophone&rsquo;s 4.5&nbsp;Hz corner &mdash; response '
                'falls steeply below it, so the rise at the left is instrument, not ground.</div>')
        + _card("Helicorder &middot; last 4 hours (UTC)",
                f'<img id="heli" class="plot" src="/helicorder.png?{ts}" alt="helicorder">'
                + content.HELI_HOWTO)
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
    # Not on the public copy: it is a raw trigger log, mostly cultural noise, and it
    # reads as a diary of when the house is active. Charles's call, 2026-08-26.
    if _PUBLIC_COPY:
        return Response("not found", status_code=404)
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

@app.get("/learn")
def learn():
    # Each section gets an id derived from its header so other pages can deep-link
    # (the drum's "full guide" link points at #how-to-read-the-helicorder).
    cards = "".join(_card(h, inner.replace("{place}", PLACE), card_id=_slug(h))
                    for h, inner in content.LEARN_SECTIONS)
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
        '<img src="/station.jpg" class="plot" alt="The seismometer during bring-up '
        'on the workbench, before the printed enclosures">'
        '<p class="text-muted small mb-0 mt-2">The station during bring-up, July 2026 '
        '&mdash; geophone, ADS1256 digitizer and Raspberry&nbsp;Pi, before the printed '
        'enclosures. It now lives in two cases on the garage floor.</p>',
    ) if _STATION_JPG else ""
    cards = photo + "".join(_card(h, inner.replace("{place}", PLACE))
                            for h, inner in content.ABOUT_SECTIONS)
    if _PUBLIC_COPY:                                  # no detections page to link to
        cards = cards.replace('(on their <a href="/detections">own page</a>) ', "")
    body = _titleblock("About this station", f"{SID} &middot; {PLACE}") + \
        f'<div class="row"><div class="col-lg-9">{cards}</div></div>'
    return Response(_shell(f"About — {BRAND}", "about", body),
                    media_type="text/html")


@app.get("/catches")
def catches_page():
    # Content and images live in catches.py / catches/ -- this handler only assembles.
    cards = _card("How far can this station hear?",
                  '<img src="/catches/detection-range-map.png" class="plot" '
                  'alt="Detection range by magnitude">' + catches.MAP_TEXT)
    cards += "".join(_card(c["head"], catches.catch_html(c)) for c in catches.CATCHES)
    cards += "".join(_card(c["head"], catches.catch_html(c)) for c in catches.NOT_CAUGHT)
    body = _titleblock("Catches", f"earthquakes {SID} has recorded, confirmed by the USGS catalog") + \
        f'<div class="row"><div class="col-lg-9">{catches.INTRO}{cards}</div></div>'
    return Response(_shell(f"Catches — {BRAND}", "catches", body), media_type="text/html")


@app.get("/catches/{name}")
def catches_image(name: str):
    p = catches.image_path(name)
    if not p:
        return Response("not found", status_code=404)
    with open(p, "rb") as f:
        return Response(f.read(), media_type="image/png", headers=STATIC_CACHE)


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


# --- activity heatmap ---------------------------------------------------------


@app.get("/activity")
def activity_page():
    ts = int(time.time() // 600)                 # bucketed to the render TTL
    # The grey-cell paragraph is only true when a configuration change actually falls
    # inside the window; otherwise the page explains marks that are not on the chart.
    prose = content.ACTIVITY_TEXT
    if activity.has_prior_cells():
        prose += content.ACTIVITY_PRIOR_TEXT
    days = _card(f"Last {activity.DAYS} days &middot; hour by hour",
                 f'<img class="plot" src="/activity.png?mode=days&amp;t={ts}" '
                 'alt="noise level by day and hour">' + prose)
    # The weekday portrait needs a fortnight in ONE configuration or it is mostly an
    # artefact of which weekday fell on which side of a hardware change. Until then,
    # say so and show the countdown rather than drawing something misleading.
    g = activity.grid(mode="week")
    if g and g.get("short"):
        week = _card("A typical week &middot; not yet",
                     '<p class="mb-0">Collapsing every hour onto one week is the better '
                     'portrait &mdash; it averages out one-off events and shows the '
                     'weekday/weekend difference. It needs '
                     f'<b>{g["need"]} days</b> of settled configuration and the station '
                     f'has <b>{g["have"]:.1f}</b> since the last change on '
                     f'{g["since"]:%-d %B}. This card fills itself in around '
                     f'<b>{(g["since"] + timedelta(days=g["need"])):%-d %B}</b>, assuming '
                     'nothing else is rebuilt before then.</p>')
    else:
        week = _card("A typical week",
                     f'<img class="plot" src="/activity.png?mode=week&amp;t={ts}" '
                     'alt="noise level by weekday and hour">'
                     '<p class="text-muted small mt-2 mb-0">Every hour since the last '
                     'configuration change, collapsed onto one week.</p>')
    body = (_titleblock("Activity", "when the neighbourhood is noisy &mdash; local time")
            + days + week)
    return Response(_shell(f"Activity — {BRAND}", "activity", body),
                    media_type="text/html")


@app.get("/activity.png")
def activity_png(mode: str = "days"):
    png = _activity_cached("week" if mode == "week" else "days")
    if not png:
        return Response(status_code=404)
    return Response(png, media_type="image/png", headers=NOCACHE)


_ACT_CACHE = {}


def _activity_cached(mode, ttl=600):
    """Render at most once per `ttl`. Scanning ~1300 interval files plus the draw is
    well under a second, but the page holds two of them and the drum service is
    already the busy thing on this box."""
    hit = _ACT_CACHE.get(mode)
    now = time.time()
    if hit and now - hit[0] < ttl:
        return hit[1]
    png = activity.heatmap_png(mode=mode)
    _ACT_CACHE[mode] = (now, png)
    return png


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


# --- history ------------------------------------------------------------------
# A drum for any past 4 h window, rendered from the same interval envelopes the
# live view uses -- so /history costs one npz load per row and no miniSEED parse.
# Scope is deliberately the CURRENT EPOCH ONLY (see heli_build.EPOCH_START): the
# archive before 2026-07-25 ran at 57/60 sps through a different analog front end,
# and putting those drums behind the same picker would invite comparing them.

HIST_H = float(os.environ.get("SEISMO_HISTORY_HOURS", "4"))    # hours per window
_hist_cache = {}                  # datetime string -> PNG bytes (windows are immutable)
_HIST_MAX = 24


def _utc(ts):
    """Epoch seconds -> aware UTC datetime. A module-level helper because
    history_page's `datetime` query param shadows the imported class."""
    return datetime.fromtimestamp(ts, timezone.utc)


_avail_cache = {"at": 0.0, "val": ({}, None, None)}
AVAIL_TTL = 60.0


def _available():
    """What the picker is allowed to offer: ({YYYY-MM-DD: [start hours]}, lo, hi).

    Derived from the interval envelopes actually on disk, NOT from
    epoch-start..now -- so a gap in the archive, or a range not yet backfilled,
    shows up as an hour you cannot select rather than as a drum of blank rows.
    An hour is offered when its FIRST hour holds data, so every drum you can
    reach begins on real signal. "Anywhere in the 4 h" was too lax: with the
    archive starting at 23:45, hours 20/21/22 would each have been offered and
    drawn fifteen blank rows above one live one.

    Reads only filenames (heli.YYYY.JJJ.HHMM.npz); no npz is opened. Cached for
    AVAIL_TTL because the page is cheap and the interval set changes every 15 min.
    """
    now = time.time()
    if now - _avail_cache["at"] < AVAIL_TTL:
        return _avail_cache["val"]
    t0s = []
    for p in glob.glob(os.path.join(heli_render.HELI, "heli.*.npz")):
        try:
            t0s.append(heli_build._fname_t0(p))
        except Exception:
            pass
    floor = heli_build.epoch_start_ts()
    t0s = sorted(t for t in t0s if t >= floor)
    val = ({}, None, None)
    if t0s:
        have = set(t0s)
        # candidate start hours: every hour from the first interval's hour to the
        # last, keeping those whose OPENING hour holds at least one interval
        first_h = int(t0s[0]) // 3600 * 3600
        last_h = int(t0s[-1]) // 3600 * 3600
        days = {}
        for hr in range(first_h, last_h + 3600, 3600):
            if any((hr + k) in have
                   for k in range(0, 3600, heli_render.INTERVAL_S)):
                dt = _utc(hr)
                days.setdefault(dt.strftime("%Y-%m-%d"), []).append(dt.hour)
        if days:
            lo = min(t0s) // 3600 * 3600
            hi = last_h
            val = (days, lo, hi)
    _avail_cache.update(at=now, val=val)
    return val


def _epoch_bounds():
    """(first selectable hour, last selectable hour) as epoch seconds, both on the
    hour, from what is actually on disk. Falls back to the epoch start when the
    envelope directory is empty (nothing built yet)."""
    _, lo, hi = _available()
    if lo is None:
        lo = -(-heli_build.epoch_start_ts() // 3600) * 3600     # round UP to the hour
        hi = max(lo, time.time() // 3600 * 3600)
    return lo, hi


def _parse_dt(s):
    """YYYYmmDDHHMM -> epoch seconds, or None. Minutes must be :00 -- windows are
    hour-aligned so the picker and the prev/next steps stay on one grid."""
    if not s or len(s) != 12 or not s.isdigit() or s[10:] != "00":
        return None
    try:
        return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]),
                        tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def _fmt_dt(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y%m%d%H%M")


@app.get("/history.png")
def history_png(datetime: str = ""):
    ts = _parse_dt(datetime)
    if ts is None:
        return Response("bad datetime", status_code=400)
    if datetime in _hist_cache:
        return Response(_hist_cache[datetime], media_type="image/png", headers=NOCACHE)
    png = heli_render.helicorder_png(heli_render.HELI, t_start=ts, hours=HIST_H)
    if not png:
        return Response("no data in that window", status_code=404)
    # Only cache windows that are fully in the past; the current one is still filling.
    if ts + HIST_H * 3600 < time.time():
        if len(_hist_cache) >= _HIST_MAX:
            _hist_cache.pop(next(iter(_hist_cache)), None)
        _hist_cache[datetime] = png
    return Response(png, media_type="image/png", headers=NOCACHE)


HISTORY_JS = """<script>
// The picker's job is to build the canonical URL: /history?datetime=YYYYmmDDHHMM.
// AVAIL maps each available UTC date to the start hours that actually have data,
// so an hour with no archive behind it can't be chosen at all.
const AVAIL=%s;
const dEl=document.getElementById('h_date'),hEl=document.getElementById('h_hour');
const urlEl=document.getElementById('h_url'),goEl=document.getElementById('h_go');
function hoursFor(date){return AVAIL[date]||[];}
function fillHours(keep){
  const hs=hoursFor(dEl.value);
  hEl.innerHTML='';
  for(const h of hs){
    const o=document.createElement('option');
    o.value=String(h).padStart(2,'0');
    o.textContent=o.value+':00';
    hEl.appendChild(o);
  }
  if(keep!=null&&hs.includes(+keep))hEl.value=String(keep).padStart(2,'0');
  hEl.disabled=hs.length===0;
  goEl.classList.toggle('disabled',hs.length===0);
  sync();
}
function target(){
  if(!dEl.value||!hEl.value)return null;
  return '/history?datetime='+dEl.value.replaceAll('-','')+hEl.value+'00';
}
function sync(){
  const t=target();
  urlEl.textContent=t?location.origin+t:'\u2014';
  goEl.href=t||'#';
}
dEl.addEventListener('change',()=>fillHours(null));
hEl.addEventListener('change',sync);
sync();
</script>"""


@app.get("/history")
def history_page(datetime: str = "", d: str = "", h: str = ""):
    days, _, _ = _available()
    lo, hi = _epoch_bounds()
    if not datetime and d and h:            # tolerate a plain date+hour GET too
        datetime = d.replace("-", "") + h.zfill(2) + "00"
    ts = _parse_dt(datetime)
    if ts is None:
        # Newest FULL window, not the newest selectable hour: `hi` is the last hour
        # that has any data, so starting there would draw one live row and fifteen
        # blanks. Backing up a window-minus-an-hour ends the drum on current data.
        ts = max(lo, hi - HIST_H * 3600 + 3600)
    ts = min(max(ts // 3600 * 3600, lo), hi)
    cur = _fmt_dt(ts)
    step = HIST_H * 3600
    dt0, end = _utc(ts), _utc(ts + step)

    def offered(target):
        t = _utc(target)
        return t.hour in days.get(t.strftime("%Y-%m-%d"), [])

    def nav_btn(target, label):
        if not offered(target):
            return f'<span class="btn btn-outline-secondary btn-sm disabled">{label}</span>'
        return (f'<a class="btn btn-outline-secondary btn-sm" '
                f'href="/history?datetime={_fmt_dt(target)}">{label}</a>')

    cur_day = dt0.strftime("%Y-%m-%d")
    hours = "".join(
        f'<option value="{hh:02d}"{" selected" if hh == dt0.hour else ""}>{hh:02d}:00</option>'
        for hh in days.get(cur_day, []))
    picker = (
        '<div class="row row-cols-lg-auto g-2 align-items-center">'
        '<div class="col"><label class="col-form-label" for="h_date">Date (UTC)</label></div>'
        f'<div class="col"><input type="date" class="form-control form-control-sm" id="h_date" '
        f'value="{cur_day}" min="{_utc(lo):%Y-%m-%d}" max="{_utc(hi):%Y-%m-%d}"></div>'
        '<div class="col"><label class="col-form-label" for="h_hour">start hour</label></div>'
        f'<div class="col"><select class="form-select form-select-sm" id="h_hour">{hours}'
        '</select></div>'
        f'<div class="col"><a class="btn btn-primary btn-sm" id="h_go" href="#">Show '
        f'{HIST_H:g}&nbsp;h</a></div></div>'
        '<div class="text-muted small mt-2">link: <code id="h_url"></code></div>')
    controls = (
        '<div class="d-flex justify-content-between align-items-center flex-wrap gap-2">'
        f'{nav_btn(ts - step, "&larr; earlier")}'
        f'<div class="text-muted small">{dt0:%Y-%m-%d %H:%M} &ndash; {end:%H:%M} UTC</div>'
        f'{nav_btn(ts + step, "later &rarr;")}</div>')
    body = (
        _titleblock("History",
                    f'{SID} &middot; any {HIST_H:g}&nbsp;h window since the station switched '
                    'to 100&nbsp;sps')
        + _card("Choose a window", picker + '<hr class="my-3">' + controls)
        + _card(f"Drum &middot; {dt0:%Y-%m-%d %H:%M} UTC +{HIST_H:g} h",
                f'<img src="/history.png?datetime={cur}" class="img-fluid" '
                f'alt="helicorder drum for {dt0:%Y-%m-%d %H:%M} UTC">'
                '<p class="text-muted small mb-0 mt-2">Same 1&nbsp;Hz high-pass as the live '
                'drum. The amplitude scale is keyed to each window&rsquo;s own median noise, '
                'so a quiet night is not drawn smaller than a busy afternoon &mdash; compare '
                'shapes across windows, not heights. A blank row means no data for that '
                '15&nbsp;minutes.</p>'
                + content.HELI_HOWTO)
        + _card("Why it starts on 2026-07-25",
                '<p class="mb-0 small">The station switched to 100&nbsp;sps late on '
                '2026-07-25, and before that ran at 57/60&nbsp;sps through a different analog '
                'front end. Earlier recordings exist but are not comparable to these, so they '
                'are deliberately not offered here rather than inviting a like-for-like '
                'reading that would be wrong.</p>'))
    return Response(_shell(BRAND, "history", body, HISTORY_JS % json.dumps(days)),
                    media_type="text/html")


heli_service.start()      # background: build envelopes + pre-render the drum

if __name__ == "__main__":
    serve(port=int(os.environ.get("PORT", "5001")), reload=False)

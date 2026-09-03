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
import listen
import content
import heli_build
import heli_render
import heli_service
import render

STATION = os.environ.get("SEISMO_STATION", "OAKM1")
NETWORK = os.environ.get("SEISMO_NETWORK", "SS")
PLACE = os.environ.get("SEISMO_PLACE", "Oakmont, Santa Rosa, CA")
EVENTS = os.environ.get("SEISMO_EVENTS", "/data/events.log")
CHANNEL = os.environ.get("SEISMO_CHANNEL", "EHZ")
LOCATION = os.environ.get("SEISMO_LOCATION", "00")
SID = f"{NETWORK}.{STATION}.{LOCATION}.{CHANNEL}"
# "Oakmont, Santa Rosa, CA" -> "Oakmont, CA"
_pl = [x.strip() for x in PLACE.split(",")]
_SHORT_PLACE = f"{_pl[0]}, {_pl[-1]}" if len(_pl) > 2 else PLACE
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
    # Collapse near-duplicates (starts within 3 s: the same burst re-detected across
    # two polls with a shifted start) -- keep the stronger row. The detector now
    # dedupes at the source too; this also cleans the rows logged before it did.
    kept = []
    for e in out:
        try:
            t = datetime.fromisoformat(e["start"]).timestamp()
        except Exception:
            kept.append(e); continue
        for k in kept:
            try:
                if abs(datetime.fromisoformat(k["start"]).timestamp() - t) <= 3.0:
                    if float(e.get("peak_ratio", 0) or 0) > float(k.get("peak_ratio", 0) or 0):
                        k.update(e)
                    break
            except Exception:
                continue
        else:
            kept.append(e)
    return kept[:max_rows]


# --- shared chrome -----------------------------------------------------------

BOOT = (
    '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" '
    'rel="stylesheet" crossorigin="anonymous">'
    '<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" '
    'crossorigin="anonymous" defer></script>'
    # Barlow was drawn from Californian public signage, which is the right accent for
    # a station on a Californian fault; Newsreader carries the long explanatory passages
    # (this site is more reading than dashboard); DM Mono reads like a lab display and
    # sets every number, with tabular figures so columns line up.
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Barlow:wght@400;500;600&'
    'family=Barlow+Semi+Condensed:wght@500;600&'
    'family=DM+Mono:wght@300;400;500&'
    'family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400'
    '&display=swap">'
)

# Theme is resolved before first paint so a dark-mode reader never gets a white flash.
# Stored choice wins; with none stored we follow the OS and keep following it live.
THEME_BOOT_JS = """<script>
(function(){
  var K='seismo-theme';
  function sys(){return matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
  function apply(t){document.documentElement.setAttribute('data-bs-theme',t);}
  var st=null; try{st=localStorage.getItem(K);}catch(e){}
  apply(st==='light'||st==='dark'?st:sys());
  try{
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change',function(){
      var v=null; try{v=localStorage.getItem(K);}catch(e){}
      if(v!=='light'&&v!=='dark'){apply(sys());
        window.dispatchEvent(new CustomEvent('seismo:theme'));}
    });
  }catch(e){}
  window.seismoToggleTheme=function(){
    var t=document.documentElement.getAttribute('data-bs-theme')==='dark'?'light':'dark';
    apply(t); try{localStorage.setItem(K,t);}catch(e){}
    window.dispatchEvent(new CustomEvent('seismo:theme'));
  };
})();
</script>"""

# Sun in dark mode ("switch to light"), moon in light mode. CSS picks which is shown.
THEME_BUTTON = (
    '<button class="themebtn" type="button" onclick="seismoToggleTheme()" '
    'aria-label="Toggle light or dark theme" title="Toggle light / dark">'
    '<svg class="ico-moon" width="16" height="16" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
    '<svg class="ico-sun" width="16" height="16" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
    'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
    '</button>'
)

CSS = r'''<style>
 /* ---------------------------------------------------------------------------
    Every pair that meets on screen is gated by contrast_check.py against WCAG 2.1:
    AAA (7:1) for anything paragraph-length, AA (4.5:1) for links and axis labels,
    3:1 for the trace, the axes and the lamp. Run it before changing a colour here.

    Copper on slate. The palette is the instrument: a copper coil (the accent, and
    the ink every trace is drawn in) against blue-grey rock (the ground). Two
    themes, one identity -- the copper darkens for a light ground, nothing else
    changes role. Every colour on the site is a token here; nothing hard-codes one.
    --------------------------------------------------------------------------- */
 :root{
   --ui:'Barlow',system-ui,-apple-system,'Segoe UI',sans-serif;
   --cond:'Barlow Semi Condensed','Barlow',system-ui,sans-serif;
   --prose:'Newsreader',Georgia,'Times New Roman',serif;
   --mono:'DM Mono',ui-monospace,SFMono-Regular,Menlo,monospace;

   --ground:#eef0f1;      /* the page */
   --panel:#ffffff;       /* the few surfaces that still need to lift */
   --rail:#e3e6e8;        /* the fixed instrument rail */
   --rule:#cfd5d8;        /* structural hairlines */
   --rule-soft:#e0e4e6;   /* hairlines inside a block */
   --ink:#131a1e;
   --ink-dim:#414a50;
   --copper:#8a4f1c;
   --copper-lit:#6d3c12;  /* hover: darker on a light ground */
   --rose:#ab3d31;
   --plate:#ffffff;       /* the paper the server-rendered plots print on */
   --lamp:#2c7a5b;
   --yes:#1c5540;         /* inline verdicts in prose -- held to the body target */
   --no:#8e2b21;

   --plot-axis:#7e888e; --plot-grid:#dfe4e6; --plot-grid-faint:#e9eced;
   --plot-label:#414a50; --plot-trace:#8a4f1c; --plot-mark:#ab3d31;
 }
 [data-bs-theme="dark"]{
   --ground:#101519;
   --panel:#161c21;
   --rail:#0b0f12;
   --rule:#232b31;
   --rule-soft:#1a2126;
   --ink:#dfe5e8;
   --ink-dim:#9aa7ae;
   --copper:#e09b4a;
   --copper-lit:#f0b268;
   --rose:#d2695e;
   --plate:#efedE8;
   --lamp:#4fbf8f;
   --yes:#7fc9a4;
   --no:#e89a90;

   --plot-axis:#5e686e; --plot-grid:#1e262b; --plot-grid-faint:#171e22;
   --plot-label:#9aa7ae; --plot-trace:#e09b4a; --plot-mark:#d2695e;
 }

 /* Bootstrap stays for tooltips, collapse and table mechanics; the look is ours. */
 [data-bs-theme]{
   --bs-body-bg:var(--ground); --bs-body-color:var(--ink);
   --bs-body-font-family:var(--ui); --bs-body-font-size:1rem;
   --bs-emphasis-color:var(--ink); --bs-secondary-color:var(--ink-dim);
   --bs-border-color:var(--rule); --bs-border-color-translucent:var(--rule);
   --bs-tertiary-bg:var(--rail); --bs-secondary-bg:var(--rail);
   --bs-primary:var(--copper); --bs-heading-color:var(--ink);
   --bs-link-color:var(--copper); --bs-link-hover-color:var(--copper-lit);
   --bs-code-color:var(--copper);
   --bs-table-color:var(--ink); --bs-table-bg:transparent;
   --bs-table-border-color:var(--rule-soft);
   --bs-table-striped-bg:transparent; --bs-table-striped-color:var(--ink);
   --bs-border-radius:2px; --bs-border-radius-sm:2px; --bs-border-radius-lg:2px;
 }
 *{-webkit-font-smoothing:antialiased}
 body{background:var(--ground);color:var(--ink);font-family:var(--ui)}
 a{color:var(--copper);text-underline-offset:.18em;text-decoration-thickness:.06em}
 a:hover{color:var(--copper-lit)}
 :focus-visible{outline:2px solid var(--copper);outline-offset:2px}
 .text-muted,.text-body-secondary{color:var(--ink-dim)!important}

 /* --- frame ---------------------------------------------------------------- */
 .frame{display:grid;grid-template-columns:17rem minmax(0,1fr);min-height:100vh}
 .rail{position:sticky;top:0;align-self:start;height:100vh;overflow-y:auto;
   background:var(--rail);border-right:1px solid var(--rule);
   display:flex;flex-direction:column;padding:1.75rem 1.5rem 1.25rem}
 .stage{padding:3.25rem 3.5rem 4rem;max-width:64rem}
 .stage-narrow{max-width:46rem}

 /* --- rail: identity ------------------------------------------------------- */
 .r-net{font-family:var(--mono);font-size:.68rem;font-weight:400;letter-spacing:.16em;
   text-transform:uppercase;color:var(--ink-dim)}
 .r-code{display:block;text-decoration:none;
   font-family:var(--cond);font-weight:600;font-size:2.3rem;line-height:.95;
   letter-spacing:-.01em;color:var(--ink);margin:.35rem 0 .3rem}
 .r-chan{font-family:var(--mono);font-size:.7rem;line-height:1.5;color:var(--ink-dim)}

 /* --- rail: vitals (the signature -- live on every page) ------------------- */
 .rail::-webkit-scrollbar{width:0}
 .rail{scrollbar-width:none}
 .vitals{margin-top:1.35rem;padding-top:1rem;border-top:1px solid var(--rule)}
 .v-state{display:flex;align-items:center;gap:.5rem;font-family:var(--mono);
   font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-dim)}
 .lamp{width:7px;height:7px;border-radius:50%;background:var(--ink-dim);flex:0 0 auto}
 .vitals.on .lamp{background:var(--lamp);box-shadow:0 0 0 0 var(--lamp);
   animation:beat 3s ease-out infinite}
 .vitals.stale .lamp{background:var(--rose)}
 @keyframes beat{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--lamp) 55%,transparent)}
   70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}
 @media (prefers-reduced-motion:reduce){.vitals.on .lamp{animation:none}}
 .v-age{margin-left:auto;font-variant-numeric:tabular-nums}
 .v-read{display:flex;align-items:baseline;gap:.4rem;margin:.55rem 0 .1rem}
 .v-num{font-family:var(--mono);font-weight:300;font-size:2.1rem;line-height:1;
   letter-spacing:-.02em;color:var(--copper);font-variant-numeric:tabular-nums}
 .v-unit{font-family:var(--mono);font-size:.72rem;color:var(--ink-dim)}
 .v-what{font-family:var(--mono);font-size:.62rem;letter-spacing:.1em;
   text-transform:uppercase;color:var(--ink-dim)}
 #v-spark{display:block;width:100%;height:34px;margin:.7rem 0 .2rem}
 .v-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:.15rem .5rem;margin:.4rem 0 0}
 .v-grid dt{font-family:var(--mono);font-size:.6rem;letter-spacing:.09em;
   color:var(--ink-dim);font-weight:400}
 .v-grid dd{font-family:var(--mono);font-size:.82rem;margin:0;color:var(--ink);
   font-variant-numeric:tabular-nums}

 /* --- rail: nav, grouped by how far back you are looking ------------------- */
 .r-nav{margin-top:1.35rem;padding-top:1rem;border-top:1px solid var(--rule);flex:1 1 auto}
 .r-group{font-family:var(--mono);font-size:.6rem;letter-spacing:.15em;
   text-transform:uppercase;color:var(--ink-dim);margin:.85rem 0 .25rem}
 .r-group:first-child{margin-top:0}
 .r-nav-a{display:block;font-family:var(--cond);font-size:1.02rem;font-weight:500;
   line-height:1.45;color:var(--ink-dim);text-decoration:none;
   padding-left:.7rem;border-left:2px solid transparent}
 .r-code:hover{color:var(--copper)}
 .ext{font-size:.8em;color:var(--ink-dim)}
 .r-nav-a:hover{color:var(--ink);border-left-color:var(--rule)}
 .r-nav-a:hover .ext{color:var(--copper)}
 .r-nav-a.on{color:var(--ink);border-left-color:var(--copper)}
 .r-foot{padding-top:.9rem;border-top:1px solid var(--rule);margin-top:1rem;
   display:flex;align-items:center;gap:.6rem;
   font-family:var(--mono);font-size:.62rem;line-height:1.5;color:var(--ink-dim)}
 .themebtn{display:inline-flex;align-items:center;justify-content:center;
   width:1.9rem;height:1.9rem;flex:0 0 auto;padding:0;border-radius:2px;
   background:transparent;border:1px solid var(--rule);color:var(--ink-dim);cursor:pointer}
 .themebtn:hover{color:var(--copper);border-color:var(--copper)}
 .themebtn .ico-sun{display:none}
 [data-bs-theme="dark"] .themebtn .ico-sun{display:block}
 [data-bs-theme="dark"] .themebtn .ico-moon{display:none}

 /* --- page head ------------------------------------------------------------ */
 .pagehead{margin-bottom:2.75rem}
 .pagehead h1{font-family:var(--cond);font-weight:600;font-size:2.55rem;line-height:1.02;
   letter-spacing:-.015em;color:var(--ink);margin:0 0 .45rem}
 .pagehead .lede{font-family:var(--ui);font-size:1rem;color:var(--ink-dim);
   max-width:62ch;margin:0}

 /* --- panels: a rule and a copper tick, not a box -------------------------- */
 .panel{margin:0 0 3.25rem}
 .panel-head{display:flex;align-items:baseline;gap:.55rem;
   border-top:1px solid var(--rule);padding-top:.6rem;margin-bottom:1.15rem}
 .panel-head::before{content:"";flex:0 0 auto;width:6px;height:6px;
   background:var(--copper);transform:translateY(-1px)}
 .panel-title{font-family:var(--cond);font-weight:600;font-size:1.12rem;
   letter-spacing:.005em;color:var(--ink);flex:1 1 auto}
 .panel-title .fw-normal{font-family:var(--ui);font-weight:400;font-size:.88rem;
   color:var(--ink-dim)}

 /* --- hero: the ground, right now ------------------------------------------ */
 .hero{margin:0 0 3.25rem}
 .hero-read{display:flex;align-items:baseline;gap:.55rem;flex-wrap:wrap;
   margin-bottom:.85rem}
 .hero-num{font-family:var(--mono);font-weight:300;font-size:4.2rem;line-height:.92;
   letter-spacing:-.035em;color:var(--copper);font-variant-numeric:tabular-nums}
 .hero-unit{font-family:var(--mono);font-size:.95rem;color:var(--ink-dim)}
 .hero-what{font-family:var(--mono);font-size:.66rem;letter-spacing:.12em;
   text-transform:uppercase;color:var(--ink-dim);margin-left:.2rem}
 .hero-src{margin-left:auto;align-self:center}
 #c{display:block;width:100%;height:270px;
   border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
 #s{display:block;width:100%;height:250px}
 #hud{font-family:var(--mono);font-size:.72rem;line-height:1.5;color:var(--ink-dim);
   margin-top:.6rem;font-variant-numeric:tabular-nums}

 /* --- prose ---------------------------------------------------------------- */
 .stage p,.stage li,.stage dd{font-family:var(--prose);font-size:1.075rem;
   line-height:1.62;max-width:66ch}
 .stage .panel-head p,.stage td p,.stage th p,.stage .small,.stage small,
 .stage .form-text,.stage figcaption{font-family:var(--ui);max-width:none}
 .stage .small,.stage small{font-size:.85rem;line-height:1.55;color:var(--ink-dim);
   max-width:78ch}
 .stage h2,.stage h3,.stage h4,.stage h5{font-family:var(--cond);font-weight:600;
   letter-spacing:.005em}
 .stage strong,.stage b{font-weight:600}
 code,kbd,samp,pre,.mono,.tnum{font-family:var(--mono);font-variant-numeric:tabular-nums}
 code{font-size:.88em}
 table{font-family:var(--ui);font-variant-numeric:tabular-nums;font-size:.92rem}
 thead th{font-family:var(--mono);font-size:.65rem;font-weight:400;letter-spacing:.1em;
   text-transform:uppercase;color:var(--ink-dim);border-bottom-color:var(--rule)!important}
 .badge{font-family:var(--mono);font-weight:400;letter-spacing:.04em;border-radius:2px}
 /* Bootstrap's .text-success/.text-danger are ~4:1 on both grounds, below even AA */
 .text-yes{color:var(--yes)!important} .text-no{color:var(--no)!important}
 .badge-hot{background:var(--rose);color:var(--ground)}
 .badge-warn{background:var(--copper);color:var(--ground)}
 .badge-quiet{background:transparent;color:var(--ink-dim);border:1px solid var(--rule)}
 /* the Catches page's per-event stat strip: the vitals grid, wider */
 .stat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(7.5rem,1fr));
   gap:.3rem .9rem;margin:0 0 .9rem;padding:.55rem 0;border-top:1px solid var(--rule-soft);
   border-bottom:1px solid var(--rule-soft)}
 .stat-grid dt{font-family:var(--mono);font-size:.6rem;letter-spacing:.09em;
   text-transform:uppercase;color:var(--ink-dim);margin:0}
 .stat-grid dd{font-family:var(--mono);font-size:.92rem;margin:0;color:var(--ink);
   font-variant-numeric:tabular-nums}

 /* --- server-rendered plots ------------------------------------------------ */
 /* The drum, spectrum and activity images are matplotlib on white and cannot follow
    a client-side toggle. Inverting or dimming them would misstate the data, so they
    print on paper and the frame carries the theme -- which is what a drum recorder
    does anyway. A theme= param through the renderers is the real fix. */
 .plot{display:block;width:100%;height:auto;background:var(--plate);
   border:1px solid var(--rule);border-radius:2px}
 /* Until the whole PNG has arrived the element is empty, not blank paper: the drum's
    own aspect ratio holds the space so the page does not jump when it lands. */
 .plot[data-loading]{background:transparent;aspect-ratio:16/9}
 td.spark-cell{width:196px}
 svg.spark{display:block;width:180px;height:40px;background:transparent;
   border:1px solid var(--rule-soft);border-radius:2px}
 .spark-base{stroke:var(--plot-axis)} .spark-onset{stroke:var(--plot-mark)}
 .spark-fill{fill:var(--plot-trace)}

 /* --- bits ----------------------------------------------------------------- */
 .srcpill{display:inline-block;font-family:var(--mono);font-size:.68rem;
   letter-spacing:.06em;padding:.28em .7em;border-radius:2px;cursor:help;
   background:transparent;color:var(--ink-dim);border:1px solid var(--rule)}
 .srcpill.active{color:var(--copper);border-color:var(--copper)}
 .tooltip-inner{max-width:360px;text-align:left;line-height:1.45;font-family:var(--ui)}
 .btn-primary{--bs-btn-bg:var(--copper);--bs-btn-border-color:var(--copper);
   --bs-btn-hover-bg:var(--copper-lit);--bs-btn-hover-border-color:var(--copper-lit);
   --bs-btn-color:var(--ground);--bs-btn-hover-color:var(--ground)}
 .form-control,.form-select{background-color:transparent;border-color:var(--rule);
   color:var(--ink);font-family:var(--mono);font-size:.9rem}
 .form-control:focus,.form-select:focus{background-color:transparent;color:var(--ink);
   border-color:var(--copper);box-shadow:none}
 .stagefoot{margin-top:3.5rem;padding-top:1rem;border-top:1px solid var(--rule);
   font-family:var(--mono);font-size:.68rem;line-height:1.7;color:var(--ink-dim);
   max-width:66ch}
 .stagefoot a{color:var(--ink-dim);text-decoration:underline}

 /* --- narrow --------------------------------------------------------------- */
 @media (max-width:62rem){
   .frame{grid-template-columns:1fr}
   .rail{position:static;height:auto;flex-direction:row;flex-wrap:wrap;
     align-items:flex-start;gap:1.5rem 2rem;border-right:0;
     border-bottom:1px solid var(--rule);padding:1.25rem 1.5rem}
   .r-id{flex:0 0 auto}
   .r-code{font-size:1.9rem}
   .vitals{margin-top:0;padding-top:0;border-top:0;flex:1 1 14rem;min-width:12rem}
   .r-nav{margin-top:0;padding-top:0;border-top:0;flex:1 1 100%;
     display:flex;flex-wrap:wrap;gap:.15rem 1.5rem;align-items:baseline}
   .r-group{margin:0;flex:0 0 100%}
   .r-group:not(:first-child){margin-top:.5rem}
   .r-nav-a{padding-left:0;border-left:0;border-bottom:2px solid transparent}
   .r-nav-a.on{border-left:0;border-bottom-color:var(--copper)}
   .r-foot{margin-top:0;padding-top:0;border-top:0;flex:0 0 auto}
   .stage{padding:2rem 1.5rem 3rem}
   .hero-num{font-size:3rem}
   .pagehead h1{font-size:2rem}
 }
</style>'''

# Two copies of this app run from the same image: pi5 on the LAN owns the miniSEED
# archive (UDP-streamed from the station) and builds the envelopes; the public copy on
# apps02 (SEISMO_HELI_BUILD=0) renders envelopes pi5 pushes to it every minute.
_PUBLIC_COPY = os.environ.get("SEISMO_HELI_BUILD", "1") != "1"

# The rail's vitals run on every page, which is the point: the station does not stop
# while you read the glossary. The Live page polls /live-data far faster than 3 s to
# keep its trace smooth, so it announces each payload on `seismo:live` and this loop
# stands down while those keep arriving -- one fetch cadence per page, never two.
VITALS_JS = r"""<script>
(function(){
  const el=id=>document.getElementById(id);
  // The Live page drops the rail's big reading (its hero shows it), so every write
  // here has to tolerate a missing element rather than throwing past the sparkline.
  const put=(id,v)=>{const e=el(id);if(e)e.textContent=v;};
  const box=el('vitals'),spark=el('v-spark');
  if(!box)return;
  let fed=0;
  function tokens(){const cs=getComputedStyle(document.documentElement);
    return {trace:cs.getPropertyValue('--plot-trace').trim(),
            axis:cs.getPropertyValue('--plot-axis').trim()};}
  function drawSpark(d){
    if(!spark)return;
    const dpr=devicePixelRatio||1,W=spark.clientWidth,H=spark.clientHeight;
    spark.width=W*dpr;spark.height=H*dpr;
    const g=spark.getContext('2d');g.scale(dpr,dpr);g.clearRect(0,0,W,H);
    const t=tokens();
    if(!d||d.length<2){g.strokeStyle=t.axis;g.lineWidth=1;
      g.beginPath();g.moveTo(0,H/2);g.lineTo(W,H/2);g.stroke();return;}
    // one column of pixels per min/max pair: 3000 samples into ~250 px
    const n=d.length,cols=Math.max(1,Math.floor(W));
    let amp=1;for(const v of d)amp=Math.max(amp,Math.abs(v));
    g.strokeStyle=t.trace;g.beginPath();
    for(let c=0;c<cols;c++){
      const a=Math.floor(c*n/cols),b=Math.max(a+1,Math.floor((c+1)*n/cols));
      let lo=Infinity,hi=-Infinity;
      for(let i=a;i<b;i++){if(d[i]<lo)lo=d[i];if(d[i]>hi)hi=d[i];}
      const y=v=>H-2-(v/amp*.5+.5)*(H-4);
      g.moveTo(c+.5,y(lo));g.lineTo(c+.5,y(hi));
    }
    g.stroke();
  }
  function show(r){
    const ok=r&&r.uv&&r.uv.length>1;
    box.classList.toggle('on',!!ok&&(r.age==null||r.age<30));
    box.classList.toggle('stale',!!ok&&r.age!=null&&r.age>=30);
    if(!ok){put('v-state','no feed');put('v-age','');put('v-rms','––');
      drawSpark(null);return;}
    put('v-state',(r.age!=null&&r.age>=30)?'stale':'recording');
    put('v-age',(r.age==null)?'':(r.age.toFixed(1)+' s behind'));
    const v=(r.rms_band==null)?r.rms:r.rms_band;
    put('v-rms',(v==null)?'––':v.toFixed(2));
    put('v-fs',(r.fs==null)?'–':r.fs.toFixed(1));
    put('v-gain',(r.gain==null)?'–':r.gain);
    put('v-pp',(r.pp==null)?'–':r.pp.toFixed(0));
    drawSpark(r.uv);
  }
  addEventListener('seismo:live',e=>{fed=Date.now();show(e.detail);});
  addEventListener('seismo:theme',()=>{if(window._vLast)drawSpark(window._vLast.uv);});
  addEventListener('resize',()=>{if(window._vLast)drawSpark(window._vLast.uv);});
  const _show=show;show=r=>{window._vLast=r;_show(r);};
  async function poll(){
    if(Date.now()-fed<8000){setTimeout(poll,3000);return;}   // the page is feeding us
    try{show(await (await fetch('/live-data')).json());}catch(e){show(null);}
    setTimeout(poll,3000);
  }
  poll();
})();
</script>"""

STAGE_FOOT = (
    '<div class="stagefoot">'
    'Independent station. Times are UTC. '
    'Built by <a href="https://www.linkedin.com/in/charlesmcguinness/">Charles McGuinness</a>.'
    '</div>'
)


def _rail(active):
    """The fixed instrument rail: who this station is, what it is reading right now,
    and where to go. Present on every page -- the vitals keep running while you read
    the glossary, because the station does too.

    The nav is grouped by how far back you are looking, which is the only thing that
    actually separates these pages from one another."""
    def link(href, label, key):
        on = " on" if key == active else ""
        aria = ' aria-current="page"' if key == active else ""
        return f'<a class="r-nav-a{on}"{aria} href="{href}">{label}</a>'

    groups = [
        ("Now", [("/", "Live", "live"), ("/listen", "Listen", "listen")]),
        ("Recent", ([] if _PUBLIC_COPY else [("/detections", "Detections", "detections")])
                   + [("/history", "History", "history"),
                      ("/activity", "Activity", "activity")]),
        ("The record", [("/catches", "Catches", "catches")]),
        ("The instrument", [("/range", "Range", "range"), ("/spectrum", "Spectrum", "spectrum"),
                            ("/env", "Environment", "env"),
                            ("/about", "About this station", "about")]),
        ("Background", [("/learn", "Seismology 101", "learn")]),
    ]
    # Framed on us and out past anything this station is likely to hear, so the catalogue
    # view and the drum answer the same question. Opens out of the site, hence the marker.
    usgs = ("https://earthquake.usgs.gov/earthquakes/map/"
            "?extent=31.33487,-133.65967&extent=45.52174,-110.6543"
            "&magnitude=all&listOnlyShown=true&timeZone=utc&settings=true")
    nav = "".join(f'<div class="r-group">{g}</div>' + "".join(link(*i) for i in items)
                  for g, items in groups)
    nav += ('<div class="r-group">Elsewhere</div>'
            f'<a class="r-nav-a" href="{usgs}" target="_blank" rel="noopener">'
            'USGS map <span class="ext">&#8599;</span></a>')

    provenance = ("public copy &middot; pushed from the station"
                  if _PUBLIC_COPY else "on the LAN &middot; from the archive")

    # On Live the hero shows this reading four times larger a few inches away, so the
    # rail drops it there and keeps the lamp, the sparkline and the settings.
    reading = ("" if active == "live" else
               '<div class="v-read"><span class="v-num" id="v-rms">&ndash;&ndash;</span>'
               '<span class="v-unit">µV</span></div>'
               '<div class="v-what">ground motion &middot; 1&ndash;15&nbsp;Hz rms</div>')

    return (
        '<aside class="rail">'
        f'<div class="r-id"><div class="r-net">{NETWORK} &middot; {_SHORT_PLACE}</div>'
        f'<a class="r-code" href="/">{STATION}</a>'
        f'<div class="r-chan">{LOCATION}.{CHANNEL} &middot; vertical 4.5&nbsp;Hz<br>'
        '100&nbsp;sps &middot; geophone + ADS1256</div></div>'

        '<div class="vitals" id="vitals">'
        '<div class="v-state"><span class="lamp"></span>'
        '<span id="v-state">connecting</span><span class="v-age" id="v-age"></span></div>'
        + reading +
        '<canvas id="v-spark" aria-hidden="true"></canvas>'
        '<dl class="v-grid">'
        '<div><dt>SPS</dt><dd id="v-fs">&ndash;</dd></div>'
        '<div><dt>GAIN</dt><dd id="v-gain">&ndash;</dd></div>'
        '<div><dt>PP µV</dt><dd id="v-pp">&ndash;</dd></div>'
        '</dl></div>'

        f'<nav class="r-nav">{nav}</nav>'

        f'<div class="r-foot">{THEME_BUTTON}<span>{provenance}</span></div>'
        '</aside>'
    )

# Rendered images reload when a page comes back from the browser's back/forward cache
# or a hidden tab. Navigating away cancels an in-flight image download, and "back"
# restores the page WITH the half-decoded PNG still in the <img> (PNGs decode top-down,
# so the drum shows its first rows and blank below -- Charles, 2026-08-26, twice). The
# 60 s refresh timer would eventually fix it; this fixes it on the spot. Only the
# dynamic renders are touched; static catch images and the photo are left alone.
BFCACHE_JS = r"""<script>
(function(){
  var DYN=/\/(helicorder|history|spectrum|activity)\.png/;
  // A rendered image starts with data-src and no src; the loader below is what ever
  // puts a src on it, so nothing half-decoded is ever on screen.
  function srcOf(im){return im.getAttribute('src')||im.getAttribute('data-src')||'';}
  // Double-buffered reload: fetch into an off-screen Image and swap ONLY when the whole
  // file has arrived and decoded. Assigning img.src directly makes Chrome paint the PNG
  // progressively as bytes arrive, so a stalled or aborted transfer leaves a half-drawn
  // drum on screen (Charles, 2026-08-26, three times). With this, a bad transfer costs
  // staleness, never a broken picture; the old image stays until a complete one exists.
  function reload(im){
    var s=srcOf(im); if(!DYN.test(s)) return;
    var b=s.split('?')[0]; var q=s.indexOf('?')>0?s.slice(s.indexOf('?')+1):'';
    q=q.split('&').filter(function(kv){return kv&&kv.indexOf('_r=')!==0;}).join('&');
    var url=b+'?'+(q?q+'&':'')+'_r='+Date.now();
    var pre=new Image();
    pre.onload=function(){ if(pre.naturalWidth>0){ im.src=url; im.removeAttribute('data-loading'); } };
    pre.onerror=function(){ setTimeout(function(){reload(im);},3000); };
    pre.src=url;
  }
  window.seismoReload=reload;
  document.querySelectorAll('img[data-src]').forEach(function(im){
    im.setAttribute('data-loading','');reload(im);});
  function fresh(){document.querySelectorAll('img').forEach(reload);}
  window.addEventListener('pageshow',function(e){if(e.persisted)fresh();});
  document.addEventListener('visibilitychange',function(){if(document.visibilityState==='visible')fresh();});
  document.querySelectorAll('img').forEach(function(im){
    im.addEventListener('error',function(){setTimeout(function(){reload(im);},2000);});});
})();
</script>"""


def _shell(title, active, body, script="", narrow=False):
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title}</title>{THEME_BOOT_JS}{BOOT}{CSS}</head><body>'
        + '<div class="frame">' + _rail(active)
        + f'<main class="stage{" stage-narrow" if narrow else ""}">'
        + body + STAGE_FOOT + '</main></div>'
        + script + VITALS_JS + BFCACHE_JS + '</body></html>'
    )


def _titleblock(title, subtitle):
    return (f'<header class="pagehead"><h1>{title}</h1>'
            f'<p class="lede">{subtitle}</p></header>')


# --- home --------------------------------------------------------------------

HOME_JS = """<script>
// The two canvases are drawn by hand, so they read the theme's --plot-* tokens at
// draw time instead of carrying their own colours. Toggling re-reads them; the live
// loop repaints within 3 s, and the spectrum is repainted on the spot.
const P={};
function pal(){
  const cs=getComputedStyle(document.documentElement);
  for(const k of ['axis','grid','grid-faint','label','trace','mark'])
    P[k]=cs.getPropertyValue('--plot-'+k).trim();
}
pal();
let _lastSpec=null;
addEventListener('seismo:theme',function(){pal();if(_lastSpec)spectrum(_lastSpec);});
const heroNum=document.getElementById('hero-num');
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),hud=document.getElementById('hud');
const AX=18;                                  // bottom strip reserved for the time axis
function fit(){const d=devicePixelRatio||1;
  cv.width=cv.clientWidth*d;cv.height=cv.clientHeight*d;ctx.setTransform(d,0,0,d,0,0);}
addEventListener('resize',fit);fit();
function hms(t){return new Date(t*1000).toISOString().slice(11,19);}
// Time axis: 1 s minor ticks, labelled + gridded every 10 s. Tick positions come
// from absolute UTC (t_end = time of the newest sample), so they scroll leftward
// with the trace instead of sitting at fixed pixels.
function axis(t0,t1,W,H){
  const plotH=H-AX;
  ctx.strokeStyle=P.axis;ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(0,plotH+.5);ctx.lineTo(W,plotH+.5);ctx.stroke();
  ctx.fillStyle=P.label;ctx.font='10px "IBM Plex Mono",ui-monospace,Menlo,monospace';ctx.textAlign='center';
  for(let t=Math.ceil(t0);t<=t1;t++){
    const x=Math.round((t-t0)/(t1-t0)*W)+.5,ten=t%10===0;
    ctx.beginPath();ctx.moveTo(x,plotH);ctx.lineTo(x,plotH+(ten?6:3));ctx.stroke();
    if(ten){
      ctx.strokeStyle=P.grid;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,plotH);ctx.stroke();
      ctx.strokeStyle=P.axis;
      if(x>22&&x<W-22)ctx.fillText(hms(t),x,H-4);
    }
  }
}
// Live spectrum: log-log ASD from the same 30 s ring. ML/MB = axis margins.
const sv=document.getElementById('s'),sx=sv?sv.getContext('2d'):null;
const ML=46,MB=20,MT=6,MR=8;
function fitS(){if(!sv)return;const d=devicePixelRatio||1;
  sv.width=sv.clientWidth*d;sv.height=sv.clientHeight*d;sx.setTransform(d,0,0,d,0,0);}
addEventListener('resize',fitS);fitS();
function spectrum(sp){
  if(!sx)return;
  _lastSpec=sp;
  const W=sv.clientWidth,H=sv.clientHeight;sx.clearRect(0,0,W,H);
  if(!sp||!sp.f||sp.f.length<3){sx.fillStyle=P.label;sx.font='11px "IBM Plex Mono",ui-monospace,Menlo,monospace';
    sx.fillText('spectrum unavailable',ML,H/2);return;}
  const f=sp.f,a=sp.asd;
  const lx=v=>Math.log10(v), pw=W-ML-MR, ph=H-MB-MT;
  const x0=lx(f[0]),x1=lx(f[f.length-1]);
  let amin=Infinity,amax=-Infinity;for(const v of a){if(v>0){amin=Math.min(amin,v);amax=Math.max(amax,v);}}
  const y0=Math.floor(lx(amin)),y1=Math.ceil(lx(amax));   // whole decades
  const X=v=>ML+(lx(v)-x0)/(x1-x0)*pw, Y=v=>MT+(y1-lx(v))/(y1-y0)*ph;
  sx.font='10px "IBM Plex Mono",ui-monospace,Menlo,monospace';
  // y decades
  sx.textAlign='right';
  for(let d=y0;d<=y1;d++){
    const y=Y(Math.pow(10,d));
    sx.strokeStyle=P.grid;sx.beginPath();sx.moveTo(ML,y+.5);sx.lineTo(W-MR,y+.5);sx.stroke();
    sx.fillStyle=P.label;sx.fillText('1e'+d,ML-4,y+3);
  }
  // x decade + minor ticks
  sx.textAlign='center';
  // start at the PARTIAL decade containing f[0], else 0.2/0.5 go unlabelled
  for(let d=Math.floor(x0);d<=Math.floor(x1);d++){
    for(let m=1;m<10;m++){
      const v=m*Math.pow(10,d);if(lx(v)<x0||lx(v)>x1)continue;
      const x=X(v);
      sx.strokeStyle=m===1?P.grid:P['grid-faint'];
      sx.beginPath();sx.moveTo(x+.5,MT);sx.lineTo(x+.5,MT+ph);sx.stroke();
      if(m===1||m===2||m===5){sx.fillStyle=P.label;
        sx.fillText(v<1?v.toString():v.toFixed(0),x,H-6);}
    }
  }
  // 4.5 Hz geophone corner
  if(4.5>=f[0]&&4.5<=f[f.length-1]){
    const x=X(4.5);sx.strokeStyle=P.mark;sx.setLineDash([3,3]);sx.beginPath();
    sx.moveTo(x+.5,MT);sx.lineTo(x+.5,MT+ph);sx.stroke();sx.setLineDash([]);
    sx.fillStyle=P.mark;sx.textAlign='left';sx.fillText('4.5 Hz',x+3,MT+10);
  }
  sx.strokeStyle=P.trace;sx.lineWidth=1.25;sx.beginPath();
  for(let i=0;i<f.length;i++){const x=X(f[i]),y=Y(Math.max(a[i],1e-12));i?sx.lineTo(x,y):sx.moveTo(x,y);}
  sx.stroke();
  // axis lines only -- the trace above this one is not in a box either
  sx.strokeStyle=P.axis;sx.lineWidth=1;sx.beginPath();
  sx.moveTo(ML+.5,MT);sx.lineTo(ML+.5,MT+ph+.5);sx.lineTo(ML+pw,MT+ph+.5);sx.stroke();
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
    const d=r.uv||[],n=d.length,W=cv.clientWidth,H=cv.clientHeight;
    ctx.clearRect(0,0,W,H);
    if(n>1){
      const fs=r.fs||0,t1=r.t_end,haveT=!!t1&&fs>0,t0=haveT?t1-(n-1)/fs:0;
      const plotH=haveT?H-AX:H;
      if(haveT)axis(t0,t1,W,H);
      let amp=20;for(const v of d)amp=Math.max(amp,Math.abs(v));amp*=1.1;
      ctx.strokeStyle=P.trace;ctx.lineWidth=1;ctx.beginPath();
      for(let i=0;i<n;i++){const x=i/(n-1)*W,y=plotH/2-d[i]/amp*(plotH/2*0.9);i?ctx.lineTo(x,y):ctx.moveTo(x,y);}
      ctx.stroke();
      spectrum(r.spec);
      sources(r.sources);
      dispatchEvent(new CustomEvent('seismo:live',{detail:r}));
      const band=(r.rms_band==null)?'':`  rms(1–15 Hz) ${r.rms_band.toFixed(2)} µV`;
      hud.textContent=`gain ${r.gain}  fs ${fs.toFixed(1)} sps  pp ${(r.pp||0).toFixed(0)} µV`
        +`  rms ${(r.rms||0).toFixed(2)} µV`+band
        +(haveT?`  ends ${hms(t1)} UTC (${(r.age||0).toFixed(1)} s behind)`:'');
      
      const big=(r.rms_band==null)?r.rms:r.rms_band;
      heroNum.textContent=(big==null)?'––':big.toFixed(2);
    } else { hud.textContent='live feed unavailable'; sources(null);
      heroNum.textContent='––'; }
  }catch(e){hud.textContent='live feed unavailable'; heroNum.textContent='––';}
  setTimeout(live,300);
}
live();
setInterval(()=>{window.seismoReload(document.getElementById('heli'));},60000);
</script>"""


def _card(header, inner, body_class="", card_id=None):
    """A section, not a box: a hairline, a copper tick and a title. Kept under the old
    name because every page builds itself out of it."""
    hid = f' id="{card_id}"' if card_id else ""
    cls = f' class="{body_class}"' if body_class else ""
    return (f'<section class="panel"{hid}>'
            f'<div class="panel-head"><h2 class="panel-title">{header}</h2></div>'
            f'<div{cls}>{inner}</div></section>')


def _slug(header):
    """Anchor id from a section header, so other pages can deep-link to it."""
    txt = re.sub(r"&[a-z]+;|<[^>]+>", " ", header).lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", txt)).strip("-")


_CHAR_BADGE = {                       # character class -> (badge class, text)
    "cultural": ("badge-warn", "impulsive"),
    "weak": ("badge-quiet", "near-threshold"),
    "plain": ("badge-quiet", "sustained"),
}


def _char_badge(ch):
    """Waveform-character badge for a detection. Presentation only -- the scoring
    lives in render._build_character. Empty when the window isn't scored yet."""
    if not ch:
        return '<span class="text-muted">&mdash;</span>'
    cls, text = _CHAR_BADGE.get(ch.get("cls", ""), ("badge-quiet", "?"))
    hf = "n/a" if ch.get("hf") is None else f'{ch["hf"]:.2f}'
    tip = (f'envelope kurtosis {ch.get("kurt")} &middot; {ch.get("dur")} s above 25% of '
           f'peak &middot; peak/median {ch.get("snr")} &middot; HF fraction {hf} '
           f'(informational)')
    return (f'<span class="badge {cls}" title="{tip}">{text}</span>')


@app.get("/")
def home():
    ts = int(time.time())
    body = (
        # No title block: the trace introduces the station better than a heading does.
        '<section class="hero">'
        '<div class="hero-read">'
        '<span class="hero-num" id="hero-num">&ndash;&ndash;</span>'
        '<span class="hero-unit">µV</span>'
        '<span class="hero-what">ground motion &middot; 1&ndash;15&nbsp;Hz rms '
        '&middot; last 30&nbsp;s</span>'
        '<span class="hero-src" id="srcbadges"></span></div>'
        '<canvas id="c"></canvas><div id="hud">connecting…</div>'
        '</section>'
        + _card("Live spectrum &middot; same 30&nbsp;s window "
                '<span class="fw-normal text-muted">&middot; ASD µV/&radic;Hz, log&ndash;log</span>',
                '<canvas id="s"></canvas>'
                '<div class="text-muted small mt-2 mb-0">Welch over the live 30&nbsp;s ring '
                '(~0.12&nbsp;Hz resolution). Updates as the ring does, ~every 3&nbsp;s. '
                'The dashed line marks the geophone&rsquo;s 4.5&nbsp;Hz corner &mdash; response '
                'falls steeply below it, so the rise at the left is instrument, not ground.</div>')
        + _card("Helicorder &middot; last 4 hours (UTC)",
                f'<img id="heli" class="plot" data-src="/helicorder.png?{ts}" '
                f'alt="helicorder">'
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
    '<th>character <span class="fw-normal text-muted">shape only</span></th>'
    # p_quake: the Stage-1 trigger classifier (analysis/trigger_train.py), scored on pi5
    # by the detector for triggers with peak_ratio >= its floor. Advisory, not a gate.
    '<th>p(quake) <span class="fw-normal text-muted">model</span></th></tr></thead>')


def _det_row(e):
    """One detections row. The waveform + character cells carry data-spark/data-char
    (keyed by event start) so the client can fill any that weren't cached at render
    time -- see SPARK_JS."""
    s = e.get("start", "")
    return (f'<tr><td>{s.replace("+00:00","")}</td><td>{e.get("duration_s","")}s</td>'
            f'<td>{e.get("peak_ratio","")}</td><td>{e.get("peak_uv","")} µV</td>'
            f'<td class="spark-cell" data-spark="{s}">{render.event_sparkline(s)}</td>'
            f'<td data-char="{s}">{_char_badge(render.event_character(s))}</td>'
            f'<td>{_pq_badge(e.get("p_quake"))}</td></tr>')


def _pq_badge(p):
    if p in (None, ""):
        return '<span class="text-muted">&ndash;</span>'
    p = float(p)
    cls = "badge-hot" if p >= 0.7 else "badge-warn" if p >= 0.4 else "badge-quiet"
    return f'<span class="badge {cls}">{p:.2f}</span>'


def _det_table(events, empty_msg):
    rows = ("".join(_det_row(e) for e in events) if events
            else f'<tr><td colspan="7" class="text-muted">{empty_msg}</td></tr>')
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
setInterval(()=>{window.seismoReload(document.getElementById('spec'));},1800000);
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
            + '<div class="row"><div class="col-12">'
            + '<p class="text-muted">No background assumed. If a term on the other pages '
              'looks like jargon, it is in the glossary at the bottom.</p>'
            + cards + '</div></div>')
    return Response(_shell(f"Seismology 101 — {BRAND}", "learn", body, narrow=True),
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
    serves = (" and pushes them, outbound only, to this public copy on a cloud host "
              "every minute &mdash; nothing at the house is reachable from the internet."
              if _PUBLIC_COPY else " and serves this page on the home network.")
    cards = photo + "".join(_card(h, inner.replace("{place}", PLACE).replace("{serves}", serves))
                            for h, inner in content.ABOUT_SECTIONS)
    if _PUBLIC_COPY:                                  # no detections page to link to
        cards = cards.replace('(on their <a href="/detections">own page</a>) ', "")
    body = _titleblock("About this station", f"{SID} &middot; {PLACE}") + \
        f'<div class="row"><div class="col-12">{cards}</div></div>'
    return Response(_shell(f"About — {BRAND}", "about", body, narrow=True),
                    media_type="text/html")


@app.get("/listen")
def listen_page():
    # The synth is entirely browser-side (listen.py assembles it); the server does no
    # audio work and needs no new endpoint -- it runs on the samples /live-data already
    # serves. See listen.py's docstring for why it is a compression, not a transposition.
    body = _titleblock("Listen", "the ground, live, moved into hearing") + \
        '<div class="row"><div class="col-12">' + \
        _card("Hear it", listen.INTRO + listen.markup()) + \
        _card("What you are actually hearing", listen.CAVEAT) + \
        '</div></div>'
    return Response(_shell(f"Listen — {BRAND}", "listen", body,
                           listen.CSS + listen.script(), narrow=True),
                    media_type="text/html")


@app.get("/catches")
def catches_page():
    # Two jobs only: the computed superlatives, then the log. The range map and the
    # reference-station comparison moved to /range -- they are the instrument's
    # performance argument, consulted rather than read, and they were what made this
    # page a 15-minute read doing six different things.
    cards = "".join(_card(h, inner, card_id="s-" + sl["slug"])
                    for sl, (h, inner) in
                    ((sl, catches.stellar_html(sl)) for sl in catches.stellar()))
    cards += _card("Every confirmed event", catches.table_html(), card_id="table")
    body = _titleblock("Catches", f"earthquakes {SID} has recorded, confirmed by the USGS catalog") + \
        f'<div class="row"><div class="col-lg-9">{catches.INTRO}' \
        f'{listen.WHY_QUAKES}{listen.mode_control()}{cards}</div></div>'
    return Response(_shell(f"Catches — {BRAND}", "catches", body,
                           listen.CSS + listen.script(live=False) + catches.CATCH_AUDIO_JS),
                    media_type="text/html")


@app.get("/range")
def range_page():
    cards = _card("How far can this station hear?",
                  '<img src="/catches/detection-range-map.png?v='
                  + catches._ver(os.path.join(catches.CATCH_DIR, "detection-range-map.png"))
                  + '" class="plot" alt="Detection range by magnitude">' + catches.MAP_TEXT,
                  card_id="map")
    cards += _card("Against the reference station", catches.ref_text(), card_id="reference")
    body = _titleblock("Range", "how far this station hears, and how hard that was to pin down") + \
        f'<div class="row"><div class="col-lg-9">{cards}</div></div>'
    return Response(_shell(f"Range — {BRAND}", "range", body), media_type="text/html")


@app.get("/catch/{slug}")
def catch_single(slug: str):
    # Singular /catch/ on purpose: /catches/{name} already serves the PNGs and would
    # swallow a slug. These URLs are the shareable artefact, so they get their own space.
    e = catches.event_by_slug(slug)
    if not e:
        return Response("not found", status_code=404)
    head, inner = catches.single_html(e)
    body = _titleblock(head, f"one catch &middot; {SID}") + \
        '<div class="row"><div class="col-lg-9">' + _card(head, inner) + '</div></div>'
    return Response(_shell(f"{head} — {BRAND}", "catches", body,
                           listen.CSS + listen.script(live=False) + catches.CATCH_AUDIO_JS),
                    media_type="text/html")


@app.get("/catches/audio/{name}")
def catches_audio(name: str):
    # Pre-rendered by analysis/catch_audio.py and committed, exactly like the images --
    # the public copy has no day-files to read from.
    p = catches.audio_path(name)
    if not p:
        return Response("not found", status_code=404)
    with open(p, "rb") as f:
        return Response(f.read(), media_type="application/json", headers=STATIC_CACHE)


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
    if _PUBLIC_COPY:
        # No miniSEED here to Welch: pi5 renders the spectrum and pushes the PNG with
        # the rest of the feed (seismo-public-sync.sh), so serve that file.
        try:
            with open("/data/spectrum.png", "rb") as f:
                return Response(f.read(), media_type="image/png", headers=SPEC_CACHE)
        except OSError:
            return Response("no data", status_code=503)
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
        '<div class="col-6 col-lg-3"><div class="border rounded p-3 h-100 bg-body-tertiary">'
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
                f'<img class="plot" data-src="/history.png?datetime={cur}" '
                f'alt="helicorder drum for {dt0:%Y-%m-%d %H:%M} UTC">'
                '<p class="small mb-0 mt-2">Same 1&nbsp;Hz high-pass as the live '
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

#!/usr/bin/env python3
"""listen.py — the "Listen" page: the ground, live, moved into hearing.

Presentation + the browser-side synth, in the content.py style: this module assembles
HTML and JS, and the server does no audio work at all. Everything runs on the samples
`/live-data` already delivers.

WHY IT IS BUILT THE WAY IT IS. Each constraint below came from a decision, not a default,
and BACKLOG.md carries the full reasoning:

  FREQUENCY ONLY, NEVER TIME. "I want to hear the earth live." That rules out the
  obvious trick -- playing samples back fast -- because a speed-up moves the time axis
  and you are then listening to the past, compressed.

  A CARRIER CANNOT WORK. Beating the signal against 440 Hz shifts it ADDITIVELY:
  440 + [1,15] Hz spans 0.045 octaves, which is one note with a faint waver. No choice of
  carrier fixes that; the problem is additive versus multiplicative.

  SO IT IS A COMPRESSION, NOT A TRANSPOSITION. 1-15 Hz is 3.91 octaves. Multiplying by 64
  would transpose it faithfully to 64-960 Hz, all intervals intact -- but the ask was two
  octaves centred on A3, and squeezing 3.91 into 2 is a log-frequency warp:

      f_out = OUT_HZ * (f_in / PIVOT) ** P

  It costs something real and the page says so: a 4:1 ratio in the ground arrives as 2:1
  in the ear, so an octave is no longer audible as an octave. This is a sonification, not
  a rendering.

  BUFFER FIRST, THEN A BOUNDED SESSION. Playback runs at 1:1 real time, so the buffer
  NEVER refills beyond its head start -- there is no speed-up to catch up with. PREBUFFER_S
  therefore IS the dropout tolerance, exactly. And the 60 s cap is not a limit but a
  simplification: no long-lived connection, no reconnect state machine, bounded memory, no
  fight with background-tab throttling, and it fits browser autoplay policy, which needs a
  user gesture anyway. It also makes "muted tab left running for a week" -- 5.3 GB of
  polling that nobody hears -- structurally unreachable rather than something a watchdog
  has to notice.

HOW THE SOUND IS MADE. A filter-bank vocoder, chosen over a phase vocoder because the
output frequencies are then explicit: the two-octave span and where it sits are
configuration rather
than a consequence. N band-passes across 1-15 Hz run on the 100 sps ground samples in
JavaScript; each band's envelope drives one oscillator's gain. The ground signal never
enters the audio graph as audio -- it only ever controls gains, which is what makes a
100 sps source and a 48 kHz context a non-problem.
"""
import json

# --- the mapping. Changing these changes what you hear; see the module docstring. ---
BAND_LO, BAND_HI = 1.0, 15.0     # the station's working band
N_BANDS = 13                     # log-spaced across the band. Chosen by ear first and
                                 # justified afterwards (2026-09-02) -- the justification
                                 # holds, but it was not a derivation:
                                 #
                                 #   THE EAR. Critical bandwidth is ~1/3 octave; tones
                                 #   closer than that blend rather than being heard
                                 #   apart. 13 over 3.91 octaves is 0.33 octave spacing,
                                 #   right at that limit. In compressed mode it is 0.17,
                                 #   already finer than you can resolve as pitches.
                                 #
                                 #   AND 13, NOT 12, BECAUSE OF THE TUNING. 13 tones is
                                 #   12 intervals, so across exactly 2 octaves each step
                                 #   is exactly 2 semitones: the compressed mode lands on
                                 #   a true WHOLE-TONE SCALE, A2 B2 C#3 D#3 F3 G3 A3 B3
                                 #   C#4 D#4 F4 G4 A4, every interval 200.00 cents with
                                 #   no deviation from equal temperament. It falls out of
                                 #   the existing power law for free -- both axes are
                                 #   uniform in log, so an even span divides evenly. At 12
                                 #   the steps were 2.18 semitones and the chord was
                                 #   permanently a few cents sour with itself.
                                 #
                                 #   Only the COMPRESSED mode is tuned. Subwoofer mode is
                                 #   a straight x64 and stays untuned on purpose: exact
                                 #   transposition is the only thing it claims, and
                                 #   snapping it to a scale would break precisely that.
                                 #
                                 #   THE FILTERS. At BAND_Q each band is ~1.42 octaves
                                 #   wide against 0.355 octave spacing, so they already
                                 #   overlap 4x. More bands at this Q add redundant
                                 #   copies, not resolution.
                                 #
                                 #   AND PHYSICS STOPS THE OBVIOUS FIX. Sharper analysis
                                 #   needs higher Q, and ring time is ~Q/(pi*f): at 1 Hz
                                 #   Q=2.6 already rings 0.8 s, so doubling Q makes the
                                 #   bottom bands take 1.6 s to respond and smears every
                                 #   onset into a swell.
                                 #
                                 # So raising this number is not the way to more fidelity.
                                 # The loss is PHASE, discarded entirely -- which is why a
                                 # P-wave crack and a truck thud become the same twelve
                                 # tones in different proportions. Keeping phase means a
                                 # phase vocoder, not a wider filter bank.
OUT_HZ = 220.0                   # A3, an octave below concert A -- the centre of the
                                 # output range. Dropped from 440 on 2026-09-02 because
                                 # earthquakes read as rumble and 220-880 sat too bright
                                 # for that. Two consequences worth knowing: laptop
                                 # speakers roll off hard below ~200 Hz, so the lowest
                                 # bands may vanish on one; and the ear is less sensitive
                                 # down here, so a low band sounds quieter than its gain
                                 # says. Neither is compensated, because a per-band
                                 # loudness trim would misstate relative ground
                                 # amplitude -- which is the one thing this is faithful
                                 # about.
OUT_OCTAVES = 2.0                # total output span of the compressed mode
TRUE_MULT = 64.0                 # subwoofer mode: a straight x64, exactly six octaves
                                 # up, so 1-15 Hz lands at 64-960 Hz. No warp at all --
                                 # an octave in the ground is an octave in the ear. It
                                 # needs real bass response, which is the whole trade.
PREBUFFER_S = 10.0               # == the dropout tolerance, exactly
MAX_S = 60.0                     # bounded session; see the docstring
FLOOR_UV = 0.5                   # a quiet night, mapped to silence
CEIL_DB = 42.0                   # dynamic range above FLOOR_UV mapped to full scale
ENV_TAU = 0.12                   # envelope smoothing, s -- fast enough to hear an onset
BAND_Q = 2.6

INTRO = (
    "<p>Everything this station listens for happens between <b>1 and 15&nbsp;Hz</b>, one "
    "to three octaves <em>below</em> human hearing. So this is not a matter of turning "
    "the volume up &mdash; the sound has to be moved, and how you move it decides what "
    "you actually perceive.</p>"
    "<p>Twelve band-pass filters run across the live signal, and each one&rsquo;s "
    "loudness drives a single tone. What you hear is a chord whose balance is the shape "
    "of the ground&rsquo;s motion right now &mdash; mostly the neighbourhood: traffic "
    "on Route&nbsp;12, wind and thermal drift, the house&rsquo;s own machinery, and, a "
    "few times a week, the sharp arrival of an earthquake.</p>"
    "<p>What you will <em>not</em> hear is the ocean. The microseism &mdash; the "
    "ceaseless hum of distant surf that larger instruments record hundreds of "
    "kilometres inland &mdash; lives at 0.07&ndash;0.15&nbsp;Hz. That is not merely "
    "quieter than the lowest tone here; it is <em>below the bottom of this whole "
    "range</em>, and measured against a Bodega Bay wave buoy it also sits about "
    "100&times; under this geophone&rsquo;s noise floor. A 4.5&nbsp;Hz element is "
    "simply deaf to it.</p>"
)

CAVEAT = (
    "<p>This is a <b>sonification, not a recording</b>, and it is worth knowing exactly "
    "how. The frequencies are compressed, not transposed: 3.91 octaves of ground motion "
    "are squeezed into 2 octaves centred on A3, an octave below concert A, so a signal "
    "at twice the frequency "
    "does <em>not</em> arrive an octave higher. What survives faithfully is <b>timing and "
    "relative loudness</b> &mdash; nothing is sped up, so every swell and onset happens "
    "when it happens.</p>"
    "<p>It buffers for a few seconds before starting, then plays for up to a minute. "
    "Because playback runs at real speed, that head start is also the whole tolerance "
    "for a network hiccup: it never catches back up.</p>"
)


def markup():
    bands = _band_plan()
    return (
        '<div class="listen">'
        + mode_control() +
        '<div class="listen-controls">'
        '<button id="lsn-go" class="lsn-btn" type="button">Listen to the ground</button>'
        '<span id="lsn-state" class="lsn-state">ready</span>'
        '</div>'
        '<div id="lsn-bars" class="lsn-bars" aria-hidden="true">'
        + "".join(
            f'<div class="lsn-band"><div class="lsn-bar"><i id="lsn-b{i}"></i></div>'
            f'<span>{b["fin"]:.3g}</span></div>' for i, b in enumerate(bands))
        + '</div>'
        '<p class="lsn-legend">ground frequency, Hz &mdash; each bar is one band, '
        'and its height is that band&rsquo;s share of the sound</p>'
        '</div>'
    )


def _band_plan():
    """Band centres in the ground, and the two tones each one can drive.

    `fout` is the compressed mapping (2 octaves, 110-440, plays on anything). `foutT`
    is the faithful one: a straight multiply, so the 3.91 octaves of 1-15 Hz stay 3.91
    octaves. Only the OUTPUT frequencies differ -- the filter bank analysing the ground
    is identical -- which is why the page can switch between them mid-playback, and why
    the switch is an honest A/B rather than two different renderings.
    """
    import math
    pivot = math.sqrt(BAND_LO * BAND_HI)
    p = math.log(2 ** OUT_OCTAVES) / math.log(BAND_HI / BAND_LO)
    out = []
    for k in range(N_BANDS):
        fin = BAND_LO * (BAND_HI / BAND_LO) ** (k / (N_BANDS - 1))
        out.append({"fin": fin,
                    "fout": OUT_HZ * (fin / pivot) ** p,
                    "foutT": fin * TRUE_MULT})
    return out


def mode_control():
    """The compressed / subwoofer switch. One per page; the choice is remembered."""
    return (
        '<div class="lsn-mode" id="lsn-mode">'
        '<span class="lsn-mode-label">tuning</span>'
        '<button type="button" data-mode="c" class="on">Compressed</button>'
        '<button type="button" data-mode="t">Subwoofer</button>'
        '<span class="lsn-mode-note" id="lsn-mode-note"></span>'
        '</div>'
    )


CSS = """<style>
.listen{margin:0 0 1.25rem}
.listen-controls{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;margin-bottom:1.25rem}
.lsn-btn{font:inherit;font-weight:600;padding:.65rem 1.15rem;cursor:pointer;
  color:var(--ground);background:var(--copper);border:1px solid var(--copper);
  border-radius:2px}
.lsn-btn:hover{background:var(--copper-lit);border-color:var(--copper-lit)}
.lsn-btn[disabled]{opacity:.55;cursor:default;filter:none}
.lsn-state{font-family:var(--mono);font-size:.85rem;color:var(--ink-dim);
  letter-spacing:.04em;text-transform:none}
.lsn-bars{display:flex;align-items:flex-end;gap:.35rem;height:130px;margin:0 0 .4rem}
.lsn-band{flex:1;display:flex;flex-direction:column;align-items:center;gap:.3rem;height:100%}
.lsn-band>span{font-family:var(--mono);font-size:.62rem;color:var(--ink-dim)}
.lsn-bar{flex:1;width:100%;background:var(--rule);position:relative;border-radius:1px;
  overflow:hidden}
.lsn-bar>i{position:absolute;left:0;right:0;bottom:0;height:0%;
  background:var(--copper);transition:height .07s linear}
.lsn-legend{font-size:.8rem;color:var(--ink-dim);margin:0}
.lsn-mode{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin:0 0 1.1rem}
.lsn-mode-label{font-family:var(--mono);font-size:.7rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink-dim);margin-right:.15rem}
.lsn-mode button{font:inherit;font-size:.82rem;padding:.3rem .7rem;cursor:pointer;
  color:var(--ink-dim);background:transparent;border:1px solid var(--rule);border-radius:2px}
.lsn-mode button.on{color:var(--ground);background:var(--copper);border-color:var(--copper)}
.lsn-mode-note{font-size:.78rem;color:var(--ink-dim)}
/* the per-catch button on the Catches page */
.cx-play{display:inline-flex;align-items:center;gap:.5rem;font:inherit;font-size:.85rem;
  font-weight:600;padding:.4rem .8rem;margin:.1rem 0 .9rem;cursor:pointer;
  color:var(--copper);background:transparent;border:1px solid var(--copper);
  border-radius:2px}
.cx-play:hover{color:var(--ground);background:var(--copper-lit);border-color:var(--copper-lit)}
.cx-play[disabled]{opacity:.5;cursor:default;background:transparent;color:var(--ink-dim);
  border-color:var(--rule)}
.cx-note{font-family:var(--mono);font-size:.75rem;color:var(--ink-dim);margin-left:.6rem}
.cx-wave{position:relative;height:76px;margin:.1rem 0 1rem;display:none;
  border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
.cx-wave.on{display:block}
.cx-wave canvas{display:block;width:100%;height:100%}
.cx-wave .cx-head{position:absolute;top:0;bottom:0;width:2px;left:0;
  background:var(--copper);box-shadow:0 0 6px var(--copper);
  pointer-events:none;will-change:left}
.cx-wave .cx-mark{position:absolute;top:0;bottom:0;width:1px;
  background:var(--ink-dim);opacity:.55;pointer-events:none}
.cx-wave .cx-mark b{position:absolute;top:2px;left:4px;font:600 .62rem/1 var(--mono);
  color:var(--ink-dim);letter-spacing:.06em}
</style>"""


def script(live=True):
    """The engine, plus the glue for whichever page is asking.

    `live=True` gives the Listen page its poller; `live=False` gives the Catches page
    the engine alone, which its own buttons drive with a fixed clip.
    """
    cfg = {
        "bands": _band_plan(), "prebuffer": PREBUFFER_S, "maxS": MAX_S,
        "floorUv": FLOOR_UV, "ceilDb": CEIL_DB, "envTau": ENV_TAU, "q": BAND_Q,
    }
    js = "<script>const LSN=" + json.dumps(cfg) + ";\n" + _ENGINE + _MODE_GLUE
    if live:
        js += _LIVE_GLUE
    return js + "</script>"


# The engine. One player for the whole page: starting a second source stops the first,
# because two of these sounding at once is noise, not information.
_ENGINE = r"""
window.SeismoSynth=(function(){
  let ctx=null,nodes=[],master=null,filts=[],kEnv=0,dc=0;
  let buf=[],fs=100,playIdx=0,t0=0,consumed=0,timer=null,poller=null;
  let bars=[],say=()=>{},onEnd=()=>{},live=false,tEnd=0,maxS=LSN.maxS;
  let onProgress=()=>{},cancelled=false;
  let mode=(function(){try{return localStorage.getItem('seismoTune')||'c';}
                       catch(e){return 'c';}})();
  const foutFor=b=>mode==='t'?b.foutT:b.fout;

  // Band-pass biquads (RBJ) run in JS on the 100 sps ground samples. The ground never
  // enters the audio graph as audio -- it only ever moves gains, which is why a 100 sps
  // source and a 48 kHz context never have to meet.
  function mkBiquad(f0,q,sr){
    const w=2*Math.PI*f0/sr, cs=Math.cos(w), al=Math.sin(w)/(2*q); const a0=1+al;
    return {b0:al/a0,b1:0,b2:-al/a0,a1:-2*cs/a0,a2:(1-al)/a0,x1:0,x2:0,y1:0,y2:0};
  }
  function run1(s_,x){
    const y=s_.b0*x+s_.b1*s_.x1+s_.b2*s_.x2-s_.a1*s_.y1-s_.a2*s_.y2;
    s_.x2=s_.x1; s_.x1=x; s_.y2=s_.y1; s_.y1=y; return y;
  }
  // TWO biquads per band. A single 2nd-order band-pass leaves ~20 dB of bleed two
  // octaves out, so a pure tone lights every band; cascading takes that to ~41 dB for a
  // few multiplies per sample, which at 100 sps is free.
  function mkBand(f0,q,sr){ return {a:mkBiquad(f0,q,sr), b:mkBiquad(f0,q,sr), env:0}; }
  function run(f,x){ return run1(f.b, run1(f.a, x)); }

  function build(){
    ctx=new (window.AudioContext||window.webkitAudioContext)();
    master=ctx.createGain(); master.gain.value=0; master.connect(ctx.destination);
    nodes=LSN.bands.map(b=>{
      const o=ctx.createOscillator(), g=ctx.createGain();
      o.type='sine'; o.frequency.value=foutFor(b); g.gain.value=0;
      o.connect(g); g.connect(master); o.start(); return {o,g};
    });
    master.gain.setTargetAtTime(1/Math.sqrt(LSN.bands.length), ctx.currentTime, 0.25);
    filts=LSN.bands.map(b=>mkBand(b.fin,LSN.q,fs));
    kEnv=1-Math.exp(-1/(LSN.envTau*fs)); dc=0; playIdx=0; consumed=0;
  }

  async function pollOnce(){
    const d=await (await fetch('/live-data',{cache:'no-store'})).json();
    if(!d||!d.uv||!d.uv.length) return 0;
    fs=d.fs||100;
    const n=d.uv.length;
    if(!tEnd){
      // The first poll hands back the whole 30 s window, which would start us 30 s
      // behind live when only PREBUFFER_S of head start was asked for. Trim: that head
      // start IS the dropout tolerance, and anything beyond it is just listening
      // further into the past for no benefit.
      const keep=Math.min(n,Math.ceil(LSN.prebuffer*fs));
      buf=d.uv.slice(n-keep); tEnd=d.t_end; return keep;
    }
    const nNew=Math.max(0,Math.min(n,Math.round((d.t_end-tEnd)*fs)));
    if(nNew>0){ buf=buf.concat(d.uv.slice(n-nNew)); tEnd=d.t_end; }
    return nNew;
  }

  function tick(){
    const want=Math.floor((ctx.currentTime-t0)*fs);
    let n=want-consumed;
    if(n>0){
      if(playIdx+n>buf.length){
        n=buf.length-playIdx;
        if(n<=0){ say(live?'stream stalled — stopping':'done'); stop(); return; }
      }
      for(let i=0;i<n;i++){
        const raw=buf[playIdx++];
        dc+=(raw-dc)*0.0005;                     // slow DC/drift removal
        const x=raw-dc;
        for(let k=0;k<filts.length;k++){
          const f=filts[k], a=Math.abs(run(f,x));
          f.env+=(a-f.env)*kEnv;
        }
      }
      consumed=want;
    }
    const now=ctx.currentTime;
    for(let k=0;k<filts.length;k++){
      const db=20*Math.log10(Math.max(filts[k].env,1e-6)/LSN.floorUv);
      const u=Math.max(0,Math.min(1,db/LSN.ceilDb));
      nodes[k].g.gain.setTargetAtTime(u*u, now, 0.05);
      if(bars[k]) bars[k].style.height=(u*100).toFixed(1)+'%';
    }
    // WHERE THE SOUND ACTUALLY IS, which is behind where the analysis has got to.
    // Reporting raw playIdx put the playhead visibly ahead of the audio -- Charles
    // measured about half a second. Three things separate the two, and only the last
    // was ever in doubt:
    //
    //   ENV_TAU (120 ms)  the envelope follower responds ~tau after the sample that
    //                     moved it, so the tone swells late by that much
    //   0.05 s            the setTargetAtTime smoothing on each band's gain
    //   base + output     AudioContext scheduling, plus whatever the device chain adds.
    //                     outputLatency is only meaningful once the context is running,
    //                     so it is read every tick rather than once at build time -- it
    //                     also changes if the output device does.
    //
    // Anything the browser cannot see (an external DSP host inserting its own
    // processing) stays uncompensated, because nothing here can measure it.
    const lag = LSN.envTau + 0.05 + (ctx.baseLatency||0) + (ctx.outputLatency||0);
    const heard = playIdx - lag*fs;
    onProgress(buf.length ? Math.max(0, Math.min(1, heard/buf.length)) : 0);
    const left=maxS-(now-t0);
    if(left<=0){ stop(); return; }
    say((live?'playing — ':'')+Math.ceil(left)+' s left');
  }

  function stop(){
    cancelled=true;
    clearInterval(timer); clearInterval(poller); timer=poller=null;
    if(ctx){ master.gain.setTargetAtTime(0,ctx.currentTime,0.15);
             const c=ctx; setTimeout(()=>c.close(),600); ctx=null; }
    bars.forEach(b=>{if(b)b.style.height='0%';});
    onProgress(0); onProgress=()=>{};
    const cb=onEnd; onEnd=()=>{}; cb();
  }

  async function start(opts){
    stop();                                   // only one source may sound at a time
    cancelled=false;
    bars=opts.bars||[]; say=opts.say||(()=>{}); onEnd=opts.onEnd||(()=>{});
    onProgress=opts.onProgress||(()=>{});
    live=!!opts.live; buf=[]; tEnd=0;
    if(live){
      const first=await pollOnce();
      // Fail fast on a dead feed: otherwise the loop below spends 40 s reporting "0%"
      // against a station that is not there, which reads as a hung page.
      if(!first){ say('no live data from the station right now'); onEnd(); return false; }
      const need=LSN.prebuffer*fs; let guard=0;
      while(buf.length<need && guard++<40){
        await new Promise(r=>setTimeout(r,1000));
        // stop() during the wait must actually stop. Ten seconds of un-cancellable
        // buffering is a long time to have taken someone's button away.
        if(cancelled){ onEnd(); return false; }
        await pollOnce();
        say('buffering… '+Math.min(100,Math.round(100*buf.length/need))+'%');
      }
      if(cancelled){ onEnd(); return false; }
      if(buf.length<need*0.5){ say('not enough live data yet'); onEnd(); return false; }
      maxS=LSN.maxS;
    }else{
      buf=opts.clip.uv; fs=opts.clip.fs||100;
      maxS=Math.min(LSN.maxS, buf.length/fs);   // a clip is as long as it is
    }
    build();
    if(ctx.state==='suspended') await ctx.resume();
    t0=ctx.currentTime; consumed=0;
    timer=setInterval(tick,25);
    if(live) poller=setInterval(()=>pollOnce().catch(()=>{}),2000);
    return true;
  }
  // Switching retunes the live oscillators; it does NOT touch the filter bank, because
  // only the OUTPUT mapping differs. That is what makes it an honest A/B of the
  // compression rather than two unrelated renderings -- and why it can happen mid-note.
  function setMode(m){
    mode=(m==='t')?'t':'c';
    try{localStorage.setItem('seismoTune',mode);}catch(e){}
    if(ctx) LSN.bands.forEach((b,i)=>{
      if(nodes[i]) nodes[i].o.frequency.setTargetAtTime(foutFor(b),ctx.currentTime,0.04);
    });
    return mode;
  }
  return {start,stop,setMode,getMode:()=>mode,bandCount:LSN.bands.length};
})();
"""

_MODE_GLUE = r"""
(function(){
  const box=document.getElementById('lsn-mode');
  if(!box||!window.SeismoSynth) return;
  const note=document.getElementById('lsn-mode-note');
  const NOTES={
    c:'2 octaves, 110\u2013440\u202fHz \u2014 plays on anything, but a 4:1 ratio in the ground is heard as 2:1',
    t:'true pitch, 64\u2013960\u202fHz \u2014 no compression at all; needs real bass response'
  };
  function paint(m){
    [...box.querySelectorAll('button')].forEach(b=>b.classList.toggle('on',b.dataset.mode===m));
    if(note) note.textContent=NOTES[m];
  }
  box.addEventListener('click',e=>{
    const b=e.target.closest('button'); if(!b) return;
    paint(window.SeismoSynth.setMode(b.dataset.mode));
  });
  paint(window.SeismoSynth.getMode());
})();
"""

_LIVE_GLUE = r"""
(function(){
  const go=document.getElementById('lsn-go'), st=document.getElementById('lsn-state');
  if(!go) return;
  const bars=LSN.bands.map((_,i)=>document.getElementById('lsn-b'+i));
  const START='Listen to the ground', AGAIN='Listen again';
  let busy=false, played=false;
  // The button stops as well as starts, so it has to SAY which it will do. It used to
  // go disabled for the whole session, which left no way out of a 60 s listen.
  go.addEventListener('click',async()=>{
    // stop() runs onEnd synchronously, so set the text AFTER it, or the
    // countdown from the last tick is left standing next to a stopped player.
    if(busy){ window.SeismoSynth.stop(); st.textContent='stopped'; return; }
    busy=true; go.innerHTML='<span>&#9632;</span> Stop'; st.textContent='buffering…';
    const ok=await window.SeismoSynth.start({
      live:true, bars, say:s=>{st.textContent=s;},
      onEnd:()=>{ busy=false; played=true; go.textContent=AGAIN;
                  st.textContent='done'; }
    });
    if(!ok){ busy=false; go.textContent=played?AGAIN:START; }
  });
})();
"""

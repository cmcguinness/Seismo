# STATUS — Seismo

_Last updated: 2026-09-02 (UTC)_

**How to read this file:** the *Current system* section is the resume point; below it the
recent entries run newest-first; then the reference sections that are still true; then an
index into [`STATUS-ARCHIVE.md`](STATUS-ARCHIVE.md), where everything before 2026-08-20
lives verbatim. `BACKLOG.md` holds deferred work; `CLAUDE.md` maps the hosts and code.

## 🧭 CURRENT SYSTEM (as of 2026-09-02)

**Station.** LGT-4.5 vertical geophone in a printed case on the garage slab (Oakmont;
92 m from and 13 m above Route 12), Waveshare ADS1256 at PGA 64, Raspberry Pi 2B
(`seismo.local`, Ethernet via a Wi-Fi bridge). Since 2026-08-25 the ADC is owned by
`station/adsreader` (C: spidev + GPIO uAPI, DRDY as a kernel interrupt with hardware
timestamps); `recorder.py` writes 100 sps miniSEED day-files on an exact sample grid
(one sample tossed every ~2 min for the crystal's +85 ppm; timing ±7.5 ms), despikes,
runs the inline STA/LTA, streams records by UDP to pi5. Lost conversions: 3 in 1.8 M,
all counted. Noise floor 1–15 Hz ~0.8 µV RMS on a quiet night, ~3.5 µV afternoon.

**Calibration.** Reads ~3.2× quieter than the 28.8 V/(m/s) nameplate (five anchors vs
USGS NP.1835 1.6 km away, median 3.26×, fixed-path scatter ~1.4×). Vp 5.19 km/s
measured. **34 catalog-confirmed events, validated range 88.8 km** (M3.8 San Leandro);
biggest M4.2 Cloverdale (07-29); furthest recorded (but deliberately **not fitted** — now
enforced by `EXCLUDE_FROM_FIT`, not left to a filter a magnitude revision can flip) the
M4.8 off Petrolia at 319 km (08-29). Closest: the M1.8 at 2.8 km (08-29). Most recent and
the only one with a felt report: M2.6 Middletown, DYFI MMI II (09-02). Detection map:
`dashboard/catches/detection-range-map.png`, with its headline numbers in the `.json`
beside it so the prose cannot drift from the image.

**Instrument response is PROVISIONAL and is the project's biggest open number.**
`station/SS.OAKM1.xml` uses f0 = 4.5 Hz and zeta = 0.6, both guesses; only the 9.0 V/(m/s)
sensitivity is measured. Every magnitude rests on them. The inline calibration injector
(`doc/BOM-calibrator.md`, `calibrator/`, `analysis/calfinder.py`) exists to replace them.

**Spectral lines, all identified but one:** 41.0/40.6/37.65 Hz + 19.3 Hz + 20.0 Hz are the
heat-pump AC (weather-driven duty cycle, minute-tick edges); 40.0 Hz is the 60 Hz mains
alias; a ~0.1 µV tick on the 10 s block cadence combs every sub-Hz spectrum (divide by
the time-median PSD). **1.05 Hz is the one unexplained line.** The ocean microseism is
~100× below this element's floor — not reachable.

**Data plane (pi5, LAN only).** `udp_collector` owns the archive; `detector` re-runs
STA/LTA over it, dedupes (±3 s), scores every trigger with ratio ≥ 10 using the
gradient-boosting **trigger classifier** (`p_quake`; trained on the Mac from the
station's own catalog — 75 % precision / 86 % recall on the displayed range vs the
`hf_lf` rule's 2.4 %) and **pushes to ntfy at p ≥ 0.7** (one per 5 min); `seismo_server`
serves `/v1/*`. pi5 auto-pulls `main` every 2 min. Retrain: `harvest_events.py` →
`trigger_dataset.py` → `augment.py` → `trigger_train.py --aug` → push.

**Dashboards.** LAN copy `http://seismo.pi5.mcguinness.ai` (Live, Detections with
p(quake), History, Activity day×hour + weekly, Spectrum, Environment, Catches, Learn,
About). **Public copy https://seismo.mcguinness.ai** on apps02 — same image, fed
outbound-only from pi5 (files every minute, live ring every 3 s), no Detections page,
**nothing at the house reachable from the internet** (the Cloudflare Tunnel is gone).
Every dynamic image reload is double-buffered (the Safari half-drawn-drum fix).

**Pending / on order.** **Calibration injector parts (DigiKey, ~2026-09-09; USBasp
programmer 09-03)** — the box that replaces the guessed f0/zeta. Geophones for the
ESP32/ADS1220 field rig (`doc/field-seismograph.md`: hammer refraction on the lot and the
street). FDSN network code from ISC (station currently uses the self-assigned `SS`).
Weekly-view weighted median (BACKLOG, ~November).

## Open threads

1. **Calibration injector — parts arrive ~09-09.** Everything on the software side is
   built and tested: `calfinder.py` (0 false positives over 749 h), the firmware (compiles
   clean, 330 B), and `ringdown.py` (band bias fixed, `z_max` added). Remaining: build the
   board, `make flash`, acceptance test, then a firmware-enforced 48 h soak before the
   first burst. **f0 and zeta are still guesses until it runs**, and every magnitude rests
   on them.
2. ⚠️ **The −0.066 zeta residual at zeta 0.85 on real noise** that widening the fit band
   does not touch. If the element is that heavily damped, average hard and caveat the
   number. The injector settles it empirically.
3. Field rig firmware: log triggered windows to flash, tap-the-piezo milestone.
4. Retrain the classifier when the confirmed count grows; CNN at ~100 positives.
   Augmentation is in the retrain path now (`augment.py` → `trigger_train.py --aug`).
5. `seismo_dashboard.py` is 1,028+ lines — split the image/live-data routes out.
6. The 1.05 Hz line.
7. Network code cutover (unit `SEISMO_NETWORK`, pi5 config, epochs row) when ISC answers.
8. Serve `fdsnws-station` / `fdsnws-dataselect` (BACKLOG); then ask NCEDC. Do the
   ring-down first — the entry ticket to any archive is metadata you can defend.

---

# Recent entries (newest first)

## 🔓 THE REPO IS PUBLIC (2026-09-02)

github.com/cmcguinness/Seismo went public tonight so the 1835 comparison is reproducible
by the people it was sent to. History was rewritten first: the outreach plan, the 1835
site notes and the visitor analytics moved to a private sibling repo (`Seismo-private`),
and contact names came out of every file and message. `README.md` is the front door,
`LICENSE` is MIT. From here on, STATUS entries and commit messages are public writing.

## 👀 WHO IS VISITING: A DAILY DIGEST, NOT A LOG DUMP (2026-09-02)

**The NSMP data-centre manager replied the same afternoon**, warmly, offering to check
1835's metadata and pointing at the ANSS site-characteristics compilation (Schleicher et
al. 2021, sciencebase 6183f02cd34ec04fc9bf7f8f): 1835 has no measured Vs30, only proxies
(290-540 m/s, class C/D). `analysis/refstation_spectra.py` then showed the 1835/OAKM1
ratio is flat over 5-15 Hz (slope -0.06), so the 1.2x is our sensitivity, not the site:
`doc/refstation-spectra.png`. Next contact after the calibration injector has a result.

Now that the NP.1835 email is out, Charles wanted to know who reads the public dashboard.
Two obstacles first: the site is proxied through Cloudflare, so the nginx log on apps02
held Cloudflare's edge addresses, not visitors'; and the live view's 3 s poll was most of
the log. Fixed the first with `/home/dokku/seismo/nginx.conf.d/realip.conf` (Cloudflare's
published ranges + `real_ip_header CF-Connecting-IP`); real addresses from 18:52 UTC.

**The visitor digest** (code in the private sibling repo `Seismo-private`; cron: ingest
hourly, digest + report 14:00 UTC, DB-IP refresh monthly) tails the log into **Postgres** (Dokku
service `seismo-visitors`, like every other database on apps02; the host cron job reaches
it by container address, DSN in `/etc/seismo/visitors-db.dsn`), resolves each address
once (DB-IP lite city + ASN via python3-maxminddb), and classifies every (day, address):
**reader** = fetched a page AND rendered something (asset, /live-data poll, or own-site
referrer), or 20+ polls; **crawler** = never sent a browser-looking User-Agent that day;
**scanner** = the rest. Digest to the **`seismo-visitors`** ntfy topic: readers,
pageviews, scanners, crawlers, top pages, referrers, **US states** and countries,
networks (hosting hidden), and a higher-priority line when a visitor comes from a
research or agency network. Our own report at **https://seismo.mcguinness.ai/visitors/**
(basic auth, `access_log off`):
readers/scanners per day (30 d), a continent > country > state > city
tree of readers, pages, referrers, networks, what the scanners probed for. Lines before
the real-IP fix (18:53:30 UTC) are never ingested: Cloudflare's edges geolocate to San
Jose and would look like Bay Area readers.

Started with GoAccess and replaced it the same evening: everything actually wanted
(readers vs scanners, states, excluding pre-fix lines, history past the 7-day log
rotation) meant parsing the log ourselves anyway, and its panel stops at country.

Two things learned on the way: apps02 had never had ntfy credentials (the dashboard's
own dc_watch push there could not have worked), so pi5's `/etc/seismo/ntfy.env` was
copied over and the `seismo` ntfy user granted write-only on the new topic; and
**ntfy.mcguinness.ai is now behind Cloudflare** despite the reference doc, whose WAF
answers Python-urllib's User-Agent with `403 error code: 1010`. Any named agent passes.

Caveats: the organisation is only as good as the ASN database (a phone reads as a
carrier); federal traffic often exits a shared DOI block; 2026-09-01 and earlier show
Cloudflare as the network. Refresh the databases monthly (cron does, 3rd of the month).

## 🪞 THE CATCHES PAGE NOW SHOWS THE REFERENCE STATION, AND THE TABLE IS DATA (2026-09-02)

Prompted by the outreach plan (kept in the private sibling repo): the first move toward NCEDC is
an email to the USGS strong-motion group about NP.1835, and the thing to link is a page
that shows our record beside theirs. So the Catches page was restructured.

**`analysis/refstation_compare.py`** puts NP.1835 (response removed to velocity) and
OAKM1 (counts × the provisional 9.0 V/(m/s)) on the same axes in 5–15 Hz, over the
harvest's own P/S window, with the envelopes overlaid on a log panel. Nine featured
catches got figures (`dashboard/catches/ref-*.png`, ~60 KB each after pngquant); every
confirmed 100 sps event got a ratio (`refstation.json`). **The envelopes coincide** —
Middletown, the Santa Rosa M1.8, San Leandro, and even Petrolia at 319 km, where both
instruments show the same Pn and Sn bursts. Residual ratio over the 26 events the
reference sees clearly: **median 1.21×**, so the 3.2× correction is right to within the
site scatter (a few events sit at 2–3×, always the same way: 1835 louder). Two honesty
flags travel with each ratio: the reference at its own floor (RMS ≥ 2.5× or peak ≥ 6×
its pre-event level, absolute floor from `refstation.py`), and the amplitude epoch
(events before the 2026-08-07 rebuild are shown with † and never averaged).

**`analysis/catches_data.py`** writes `dashboard/catches/confirmed.json` from the same
`detection_map.calibrate()` filter the map uses, joined with the ratios. `catches.py`
reads it for a **summary table of all 35 events** (34 in the fit + Petrolia, flagged),
a **uniform stat strip** on each featured catch (magnitude, distance, depth, envelope
peak, envelope SNR, predicted P, sustain, low/high band, vs NP.1835), and a
**reference-station section** with the method and the headline residual. The prose
write-ups stay as commentary. Nothing numeric on the page is hand-typed any more.

Dropped on purpose: the harvest's `triggered` column. It is computed against whichever
copy of the events log was on the Mac at harvest time (the pi5 copy ends 08-30), and it
said "no" for Middletown, which alerted. Not a page-worthy number until the harvest
reads the canonical log.

Refresh after a new catch: `refstation_compare.py <origin> --harvest`, then
`catches_data.py`, then `pngquant --force --skip-if-larger --quality 70-90 --ext .png`
on the new figure. St. Helena (07-25, 60 sps) has a write-up but no row or figure.

## 🎯 THE CATCHES PASS: MEASURED P PICKS, ONE FRAME, AND A VELOCITY RESULT (2026-09-02)

Started as a cosmetic ask — make the playback waveform line up with the trace image
above it — and turned into the most useful measurement of the day.

**Why it could not be done cheaply.** The catch images were made ad hoc over weeks at
different widths (1400 and 1150 px) with different windows. A detector run over the old
set returned **four outright failures and three impossible answers** (the t=0 line placed
*after* the P line). Reverse-engineering geometry from pixels is not a foundation.

**So the renderer now emits it.** `quake_share.py` writes a `.geom.json` beside every PNG
(axes box + plotted window), and the axes literals are named rather than repeated.

**The picks are MEASURED.** `quake_share` is explicit that `--p` must be an onset picked
off the trace, never predicted from catalogue distance. `analysis/catch_picks.py` picks
all nine, `catch_picks.json` records them; taup supplies only a **search window** — where
to look, never the answer — and the residual is reported so the difference stays visible:
**median +1.24 s, spread 0.66 s**. Residuals near zero everywhere would have meant the
picker was echoing the prediction.

**Three wrong pickers first**, each caught by the one independently recorded number, the
+9.06 s the page already carries for Cloverdale:

- ✗ envelope walk-back on a **zero-phase** filter → 6.81 s. `sosfiltfilt` smears a loud
  transient *backwards* and the walk-back follows the precursor. (Same acausal trap
  `calfinder.py` hit from the other direction the same day.) Causal filter now.
- ✗ AIC alone → 5.51 s: the coarse trigger fired on cultural spikes at 4.2× and 4.8× the
  median floor, on a night whose noise p99 was already 3.75× median.
- ✗ "loudest in ±15 s" → four picks 5–9 s late by finding **S**, which at 88 km is 12 s
  behind P and far louder. ±4 s excludes S; taup is good to ~1–2 s locally.

**⭐ THE RESULT.** Over the 8 local events (<100 km) the measured picks show iasp91
running **systematically early**:

| model | median error | mean \|error\| |
|---|---|---|
| iasp91 (global) | **+0.94 s** | 1.02 s |
| station's own 5.19 km/s | **−0.14 s** | 0.62 s |

Petrolia at 319 km reverses it exactly as it should — taup −0.63 s, local model
−16.61 s, because the local model has no Pn. Nine independent picks now support keeping
**both** models and the crossover between them, which is what `eventcheck.py` does.

**The frame.** Every image spans `[pick−10, pick+40]`, anchored on its own measured P
rather than on origin — no origin-relative window frames both Santa Rosa (P at +2.2 s)
and Petrolia (+45.2 s). 50 s, inside the audio player's 60 s cap, so image and clip share
one window. All nine sidecars now report identical axes and identical 50.0 s spans.
Result: the playhead sits **0 px** off the figure's plot box on both edges.

⚠️ Images and clips are served with long cache headers (correct — they are static) but
they must AGREE: a cached clip beside a freshly rendered image is a misaligned playhead,
the exact bug being fixed. Both URLs now carry an mtime+size version tag.

## 🔊 SONIFICATION, REFINED BY EAR (2026-09-02, later)

Four rounds of Charles listening and correcting, each one a real defect:

- **12 → 13 bands.** 13 tones is 12 intervals, so across exactly 2 octaves each step is
  exactly 2 semitones: the compressed mode now lands on a **true whole-tone scale**,
  A2 B2 C♯3 D♯3 F3 G3 A3 B3 C♯4 D♯4 F4 G4 A4, every interval 200.00 cents. It falls out
  of the existing power law for free. At 12 the steps were 2.18 semitones and the chord
  sat permanently a few cents sour. (Worth knowing: the whole-tone scale *cannot* exist
  in just intonation — six major whole tones overshoot the octave, six minor ones fall
  short. It closes only under equal temperament.)
- **440 → 220 Hz centre**, because earthquakes are rumbly. Not compensated for the ear's
  reduced low-frequency sensitivity: a per-band loudness trim would misstate relative
  ground amplitude, which is the one thing this rendering is faithful about.
- **The playhead led the sound by ~0.5 s.** 175 ms of that was mine before the audio
  device was involved — the envelope follower's 120 ms τ plus 50 ms of gain smoothing —
  and `outputLatency` reports 0 until the context is running, so it is read every tick.
- **✗ Subwoofer mode was raising the pitch.** ×64 was chosen because six octaves was
  *tidy*, which is a property of the transform, not the result. The two mappings cross at
  3.03 Hz and nearly all our energy is above that, so ×64 put the Middletown clip's
  median energy at **333 Hz against compressed mode's 256** — with nothing below 64 Hz at
  all, so a subwoofer had nothing to reproduce. Now ×16: median at 83 Hz, bottom bands at
  16–30 Hz, which genuinely needs the sub.

## 🔊 SONIFICATION: /listen, AND A PLAY BUTTON ON EVERY CATCH (2026-09-02)

Charles's idea, and every parameter came from a constraint he set rather than a default
I picked. Live on both dashboards.

**`/listen`** — the ground, live. Twelve band-passes across 1–15 Hz run on the 100 sps
samples in JavaScript; each band's envelope drives one oscillator's gain. The ground
never enters the audio graph as audio, only moves gains, which is why a 100 sps source
and a 48 kHz context never have to meet. No server work: it runs on what `/live-data`
already serves.

**`/catches`** — nine of the ten featured events carry a play button, the same engine fed
a pre-rendered clip. Still 1:1 real time. A waveform strip is drawn from the clip's own
samples with a copper playhead and a P marker; drawing it in the browser rather than
overlaying the PNG means it cannot drift, and sidesteps the fact that the image and the
clip cover different windows. St Helena gets no button: it predates the owned archive.

**The mapping, and why it is a compression:**

- 1–15 Hz is **3.91 octaves**, one to three octaves *below* hearing. Not a filtering
  job — a transposition job.
- **A carrier cannot work.** Beating against 440 Hz shifts ADDITIVELY: 440 + [1,15] spans
  **0.045 octaves**, one note with a waver, at any carrier.
- Two tunings, switchable live and persisted: **Compressed** (110–440 Hz, 3.91 octaves
  squeezed into 2, plays on anything) and **Subwoofer** (×64, exactly six octaves up,
  64–960 Hz, *no compression at all*). Switching retunes only the oscillators, not the
  filter bank, so it works mid-playback and is an honest A/B — which makes the page's own
  caveat audible instead of something to take on trust.

**Four bugs worth remembering, three of them mine by construction:**

- ✗ **Dockerfile COPY is an explicit list.** `listen.py` was not on it, so the image built
  green, the container died on `import listen`, dokku kept the old one serving, and the
  only symptom was a 404. Nothing in the deploy output points at a missing COPY.
- ✗ **I invented CSS tokens.** `var(--accent-strong)` and `var(--bg)` do not exist here
  (`--copper` / `--ground` do). An undefined custom property resolves to *nothing* rather
  than erroring, so the playhead was invisible and both buttons unstyled — and this
  repeats a bug this project already fixed once. Every `var(--x)` is now checked against
  the defined properties.
- ✗ **The clip window was found by energy**, on the reasoning that an earthquake is the
  loudest thing near its origin. It is not: Geysers M3.2 came back with its "arrival" at
  +125.7 s and M2.8 at +188.3 s, both having found a louder truck. Anchored to the
  harvest's `tp_s` now.
- ✗ **The live button went disabled for the whole session**, so a 60 s listen could not be
  stopped. It toggles to "■ Stop", and `stop()` can now interrupt the buffering wait too.

⚠️ The page states plainly what it cannot hear: the ocean microseism at 0.07–0.15 Hz is
below the bottom of the displayed range *and* ~100× under this element's floor. An earlier
draft claimed we hear "the slow swell of distant surf"; Charles caught it.

## 🎚️ THE ZETA BIAS WAS THE FIT BAND; AND THE FIRMWARE COMPILES (2026-09-02)

Two findings from testing the injector's software path before the hardware lands, both
of which would otherwise have surfaced with a soldering iron in hand.

**`ringdown.py` could not represent zeta above 0.8 at all.** A damped oscillator rings at
w_d = w_0*sqrt(1 - zeta^2), so the fit's lower frequency bound of `0.6 * f_expect` was
*exactly* a ceiling of zeta = sqrt(1-0.36) = 0.80. Written as a bare `0.6` it did not look
like a limit on the quantity being measured. zeta 0.85 failed 11-12 times out of 12 at
**every** signal level including SNR 200 — more signal cannot rescue an excluded answer.
That matters because zeta is the unknown the injector exists to measure and the 0.6 in
`SS.OAKM1.xml` is a vendor guess. Now a `z_max` parameter, defaulting to 0.8 so tap
behaviour is unchanged (the bound earns its keep on taps, where a hard knock rings the
case); an injector drives the coil electrically and excites no case mode, so that path
can open the window safely.

**Then a systematic bias, and it was not noise.** A sweep showed zeta reading low, growing
with damping, and NOT improving with SNR. One experiment settled it: run the estimator on
a **noiseless** synthetic and the bias is still there, -0.002 at zeta 0.2 growing to
-0.159 at 0.9. That is also how two characterisations at different SNRs could disagree
about its *sign* — they were both looking at a noise-independent effect through noise.

The mechanism is in the fitted w_d, systematically high at large zeta (2.48 Hz against a
true 1.96 at zeta 0.90); since zeta = alpha/hypot(alpha, w_d), over-reading w_d under-reads
zeta. A heavily damped ring-down is **short and therefore broadband** — nearly a single
pulse, content from near-DC to tens of Hz — and band-passing to 0.2-20 Hz truncates both
tails, leaving something that looks more oscillatory and less decayed than the truth.

| zeta | 0.2–20 Hz (noiseless) | 0.01–49 Hz | real noise @SNR 50, 0.2–20 | real noise, 0.05–45 |
|---|---|---|---|---|
| 0.30 | −0.006 | −0.001 | −0.006 ±0.01 | **+0.001 ±0.01** |
| 0.60 | −0.047 | −0.005 | −0.046 ±0.04 | **−0.005 ±0.07** |
| 0.85 | −0.131 | −0.008 | −0.066 ±0.13 | −0.066 ±0.10 |
| 0.90 | −0.159 | −0.009 | | |

Default band is now **0.05–45 Hz**. It trades a little scatter for most of the bias, which
is right *for this instrument specifically*: **bias does not average away and scatter
does**, and the injector fires 12 releases a day forever. A week is ~84 releases, so 0.10
of scatter becomes ~0.01 of standard error while a 0.046 bias would have stayed 0.046
however long we waited. ⚠️ Still open: the −0.066 residual at zeta 0.85 on real noise that
widening does not touch. And do **not** narrow the band back to reject drift — de-trending
the short fit window is the right tool and does not distort the transient's spectrum.

**The firmware compiles.** `brew trust osx-cross/avr` cleared the way; avr-gcc 9.5.0 and
avrdude 8.2 are installed. First build failed for real: `held_long()` called `delay_ms_n()`
defined below it, so C took the implicit declaration then rejected the static definition.
Clean afterwards: **330 bytes of flash, 1 byte BSS** — 4 % of the ATtiny85. Added
`_Static_assert`s for what a compiler can check, one of which is a genuinely silent
failure: `burst()` computes `SPACING_MS - PULSE_MS` in `uint16_t`, so swapping those
constants wraps to ~65 s between pulses and the only symptom is calfinder quietly finding
nothing, months later. Verified the assertion fires by actually breaking it.

## 🎣 M2.6 MIDDLETOWN — 34th CATCH, FIRST FROM THE COLLAYOMI ZONE (2026-09-02)

03:49:01 UTC, 35.4 km due north, depth 4.2 km, **felt (DYFI MMI II)**. Peak 73 µV in
1–15 Hz, SNR ~46×, detector ratio 116, `p_quake` **0.999**, alert pushed at p=1.00.
Independently confirmed by eventcheck's empirical null at **p=0.008** — zero of 119
equivalent noise windows come close.

**Not The Geysers**, which is worth stating because 849 of the ~990 catalogued events we
see between 30 and 50 km are Geysers/Cobb induced seismicity in a narrow 335–350° band.
This arrived at bearing **1.3°**, 15.6 km ESE of the field, in the Collayomi fault zone —
tectonic, not steam-field — and it is the first one we have caught from there. Four
earlier Middletown events (M0.46–1.52) all went past unrecorded.

**The local velocity model beat the global one.** P broke out at **+7.07 s**. The station's
own 5.19 km/s relation predicted +7.18 (0.11 s off); iasp91 said +6.10, a full second
early. At local distances the crust here is genuinely slower than the world average.

**The far-field exclusion is now enforced in code.** The re-harvest gate blocked its own
publish: USGS revised Petrolia 4.84 → 4.74, its residual shifted, and it *qualified* as
confirmed — which would have moved the published validated range 88.8 → 318.6 km. The
exclusion described in STATUS as "deliberate" was never actually enforced; it held only
because a filter happened to reject it, and a routine magnitude revision undid that.
`EXCLUDE_FROM_FIT` now keys on origin time, the one field a revision cannot move. Petrolia
is still *drawn* via `FAR_CONFIRMED`, just not fitted. With that in place the gate passed:
**33 → 34 confirmed, reach unchanged at 88.8 km**.

Also: `detection_map.py` writes `detection-range-map.json` beside the PNG, and `catches.py`
reads it. That count went stale twice in one day — the prose said 32 while the map's own
legend said 33, then 33 after the harvest moved to 34. Anything derived from the
calibration is now read from it.

## 🔎 eventcheck COULD NOT SAY NO (2026-09-01/02)

Asked "did we see this?" about an M2.3 at 166 km — 1.9× beyond our reach — `eventcheck.py`
answered **LIKELY DETECTED, ratio 4.16**. It is not there: at the true arrivals the
envelope reads 0.99 µV (P) and 0.63 µV (S) against a 3.13 µV background, sustain 0.0 s.

Three faults, compounding:

- **It compared unequal windows.** Noise was peak-to-peak over 18 s, signal peak-to-peak
  over 44 s, and **peak-to-peak grows with window length** — so the ratio sat above 1
  whether or not an earthquake happened. On that event the noise window's own pp (21.0 µV)
  equalled the signal window's (20.5).
- **Constant-velocity travel times**, which have no Pn, so past ~150 km they run late —
  +4.8 s on P — sliding the box off the arrivals onto the coda.
- **No sustain guard**, the one that saved the Toms Place null test.

Then a second pass, because a fixed threshold could not survive daytime background: for
the M2.1 near Ukiah the 2–6 Hz p99 was 0.78 µV over a 170 s noise window and 2.70 µV over
270 s, purely because one burst fell outside the shorter one — and a "2.9× detection"
evaporated when the window grew. It now judges **non-parametrically**: slide the exact
two-box signal mask back through the pre-event noise and count how often background alone
matches it. Controls at both extremes: M1.8 at 2.8 km p=0.008, M4.8 Petrolia p=0.012,
M2.3 Challenge p=0.147, M1.78 Toms Place p=0.383, M2.1 Ukiah p=0.527.

**And the same class of bug existed in a third place.** The travel-time audit found
`trigger_dataset.py` — the *labeller* — still on `origin + dist_km/5.19 + 0.30`. No labels
change today (max error 2.38 s over the confirmed set against a 43 s window), but it is
latent: the error grows to 16 s at Petrolia's 318 km, and the day a far event becomes
confirmed that shift moves the window off the arrival entirely. It reads `tp_s` from the
harvest now. One travel-time authority remains.

## 🧪 NOISE AUGMENTATION: +0.09 TO +0.14 PR-AUC ON REAL ROWS (2026-09-01)

Positives are the bottleneck -- 33 events at ~5/week, set by seismicity inside 89 km.
Template matching was meant to add real ones and does not work here (its own entry
below). So: bury the events we have in real archive noise and manufacture the weak,
barely-triggering positives the catalogue supplies only a handful of.

`analysis/augment.py` -> 792 rows from 58 real ones. Measured on REAL rows only:

| | baseline | +aug |
|---|---|---|
| overall PR-AUC | 0.337 | **0.480** |
| displayed slice (ratio>=20) | 0.760 | **0.882** |
| deployable, ratio>=10 | 0.694 | **0.784** |
| deployable, ratio>=20 | 0.868 | **0.895** |

⚠️ With 33 independent events these intervals are wide. The gain is consistent across
all four slices, which helps, but this multiplies SAMPLE COUNT, not INFORMATION --
there are still 33 earthquakes in there, and it will not improve generalisation to
genuinely new sources.

**What had to be right, including two things that were not at first:**

- **Real noise, not synthetic.** From our own archive, across the day so the diurnal
  range is represented, and >=180 s from any catalogue event so an augmentation cannot
  quietly contain a second earthquake. Gaussian noise is the wrong distribution: this
  background is cultural, impulsive and non-stationary, and separating quakes from
  white noise is not the problem we have.

- **peak_ratio is transformed analytically, not re-measured.** ✗ *First attempt:*
  re-run `server/stalta.py` over the augmented window. It does not reproduce the
  detector and structurally cannot -- on pi5 the STA/LTA runs CONTINUOUSLY, so its 30 s
  LTA carries hours of history. Cold-started on a 150 s lead it reported peak_ratio 5.2
  where the log says 61.2, and 2149 where the log says 8535. Worse, many real positives
  sit barely over the threshold -- one is **4.07 against trig=4.0** -- so a slightly
  different LTA means they do not re-trigger at all, and **60% of events were lost**.
  ✓ *The physics gives it directly:* the CF is energy, so R = 1 + A²/σ², and adding
  independent noise at α times background gives **R' = 1 + (R−1)/(1+α²)**. Exact,
  monotone, starts from the real logged R, needs no detector state. 0/792 rows disagree.

- **Missingness is carried through.** ✗ `hf_lf` is absent from 25 of the 58 real
  positive rows (older `events.log` schema). Filling it in for augmented rows only
  would have made them identifiable -- and since every augmented row is a positive, the
  model could have used that as the label. Now 46% missing in aug against 43% real.

- **Rows below the trigger are dropped** -- 54% of attempts, rising with α
  (288/252/138/90/24 kept). The classifier only ever scores things that triggered.

- **Groups are inherited.** Augmented rows carry their source event's `origin`, which
  is what `trigger_train.py` groups positives on, so every derivative lands in the same
  CV fold. They are also removed from every test fold and from the holdout: a PR-AUC
  counting synthetic positives would be scoring the augmentation, not the classifier.

Sanity check worth keeping: aggregate `snr_env` RISES with α, which looks wrong until
you see it is survivorship -- at high α only loud events still clear the trigger. Per
source row it falls monotonically in 22/23 cases.

## 🧬 TEMPLATE MATCHING: BUILT, MEASURED, DOES NOT WORK HERE (2026-09-01)

Recommended as the best route to more positives, on the published 5–10× catalogue yield.
On our data it returns nothing, and the reason is physical rather than tuning, so the
negative is written into the module rather than left to be rediscovered.

The machinery is right: each template recovers its own source event at cc 0.97–1.00 over a
full day of archive. But every *other* catalogue event that day — including forty Geysers
events in the same field as 21 of the templates — sits at cc 0.20–0.33, exactly where
noise sits. Pairwise over all 33 templates: **max off-diagonal 0.390, median 0.180, zero
pairs above 0.4**. The most similar pairs are geographically unrelated (Kenwood with
Hidden Valley Lake), so even those are coincidence.

Template matching needs **repeating events** — the same patch of fault — not events from
the same region. Similarity survives co-location to about a quarter wavelength; at 43 km
our dominant frequency after attenuation is ~3–8 Hz, so the wavelength is 0.6–1.7 km and
the requirement is **150–400 m**. A geothermal field is seismicity spread through a volume
kilometres across. Two events both labelled "6 km NW of The Geysers" are routinely many
wavelengths apart — including the two M3.2s 109 seconds apart on 2026-08-12, which do not
correlate with each other either. The published yields come from aftershock sequences and
creeping-fault repeaters, where multiplets genuinely exist.

Kept, because it is exactly right for the case it was built for: an aftershock sequence on
a fault beneath us would produce real multiplets. A `similarity` subcommand now tests the
premise in seconds and gates any scan — if no two templates correlate, no unknown event
will correlate with one either, and a scan can only return noise dressed as detections.
Re-run it as the catalogue grows; the day a pair clears ~0.6, scanning is worth it.

## 🔧 CALIBRATION INJECTOR: BOM, BURST FINDER, FIRMWARE (2026-08-31)

**Why.** Everything downstream — the StationXML below, every magnitude, the whole
sensitivity claim — rests on f0 and zeta, and we do not know either. The plan is an
inline box between the Pi and the geophone that closes a PhotoMOS into the coil
**four times a day, forever**, so the archive accumulates transients whose *input is
known*. `ringdown.py` fits f0 and zeta from the release. Nothing has to be touched, so
nothing has to re-settle (the ~35 min settling tax after handling the rig).

**`doc/BOM-calibrator.md`** — all through-hole, D-series Neutrik in/out, `ATTINY85-20PU`
in a socket, `AQY212EH` PhotoMOS, LM4040 2.5 V reference, three CR2032s (one for the
micro, two in series for the injection leg). Notes worth keeping: the LED goes on
**MISO not MOSI** (MISO is driven by the ATtiny, so the load sits on a driver we
specify; on MOSI it hangs off the programmer's output, and USBasp clones vary); the
**factory fuses are already correct** (1 MHz via CKDIV8, BOD off, RSTDISBL clear), so
the right move is to read them and change nothing; and the CKDIV8/slow-SCK trap that
makes a healthy chip look dead (`-B 8`).

**`analysis/calfinder.py`** — finds the bursts again in the archive. It has to do two
jobs at once: **mask** them, or ~1500 spurious triggers a year walk into the classifier's
training set against ~33 real positives; and **feed** them to `ringdown.py`, since they
are the only signal in the archive whose input we know.

Detection is on **repeatability, not shape** — the three units of a burst are
near-identical waveforms — because f0 and zeta are precisely the unknowns, so no
template can be known in advance. Isolation ("exactly three, then silence") rejects
periodic machinery.

**The self-test was necessary and not sufficient.** It caught four defects that were
mine by construction: alignment grid-searched at 50 ms (81° of phase at 4.5 Hz);
masking the isolation test so chance noise correlation read as a fourth repeat;
unit 1 being both template and member, so it self-projected to 1.0 — a bias that
rejected bursts *for being well correlated*; and a 0.1 s envelope burying a well-damped
element's 20 ms spike below the trigger. But the two that mattered only appeared when
**real archive data** went through it:

  - **Narrowband oscillation.** 9 "bursts" in 5.6 h with no injector attached. A
    sustained wavetrain is self-similar at every lag near a multiple of its period, so
    searching ~40 lags for the best correlation always finds one. Every decoy I had
    written was impulsive; the whole class was untested. Fixed by using what we *design*
    rather than asking correlation to work harder: a unit is two steps `PULSE_S` apart
    and then **silence**, where oscillation fills the unit.
  - **A fading periodic source.** One survivor in 749 h, at `rho_out` 0.85 — its
    neighbour correlated at 0.85 — which slipped through only because the AND with
    amplitude let a source that was *running down* pass. Isolation is now two-tier.

**Measured false-positive rate: zero over 749 h of real archive.** Re-run that scan
whenever the gates are touched; that is now in the module docstring.

**A hardware requirement fell out of it.** The detection floor depends on damping
(SNR ≥ 14 at zeta 0.3, ≥ 40 at zeta 0.85) — and damping is the unknown, so the injector
must be sized for the worst case: `SNR_SPEC = 50`, now in the BOM beside the 249 kΩ. If
bursts come out weak the answer is a smaller resistor, **never** a lower `RHO_MIN`:
that threshold is the entire decoy rejection.

**`calibrator/calibrator.c` + `Makefile`** — fires the pattern after a firmware-enforced
`SOAK_H = 48` of silence, so the archive holds two clean diurnal cycles of "off" before
the first burst rather than that depending on remembering not to install it yet.
Timekeeping is deliberately bad (watchdog RC, drifts with temperature): the burst is
identified by shape, `calfinder` *measures* the spacing, and the drift usefully walks the
bursts through the diurnal cycle. **The firmware and `calfinder.py` are two halves of one
protocol and nothing at runtime would notice them drifting apart** — the bursts would
just stop being found, silently, months later — so the self-test parses `calibrator.c`
and fails on a mismatch.

⚠️ **Not yet compiled** — avr-gcc is not installed on the Mac (`brew tap osx-cross/avr &&
brew install avr-gcc`, then `cd calibrator && make`). Nothing else blocks on it.

## 📐 INSTRUMENT RESPONSE: THE DATA CANNOT GIVE IT, SO A DECLARED GUESS (2026-08-30)

Tried to fit the response from data — spectral ratio against USGS NP.1835, 1.6 km away
(`analysis/response_fit.py`). **It cannot be done with what we have, and the script
documents its own negative result** rather than being deleted: residual 0.298 (2×
scatter), f0 indistinguishable anywhere in 2.5–4.5 Hz, per-anchor zeta 0.39–0.70,
sensitivity spread 4.4×. Five anchors over a fixed path is not enough to separate
instrument from site.

So `analysis/make_stationxml.py` writes `station/SS.OAKM1.xml` from an **explicitly
declared guess** — f0 4.5 Hz, zeta 0.6, 9.0 V/(m/s) — as two stages (PolesZeros M/S→V,
Coefficients V→COUNTS). Two zeros at the origin and a conjugate pole pair, standard
moving-coil. It is honest about being provisional, and it is what the injector above
exists to replace.

Also fixed here: `COUNTS_PER_VOLT` was **2× wrong** — the ADS1256's full-scale range is
±2·VREF/PGA, not ±VREF/PGA.

## ⏱️ GPS CLOCK HOST IN SERVICE; THE STATION IS OFF POOL NTP (2026-08-30 16:20 UTC)

`pi3chrono` moved to its final position: antenna sited, **Ethernet only** (Wi-Fi radio
disabled — `nmcli radio wifi off` plus autoconnect off, so a clock server has one path and
one address). Serving the LAN via `allow 192.168.4.0/22`.

| | before | after |
|---|---|---|
| **station** (`seismo.local`) offset vs GPS | **+3.0 ms** | **746 ns** |
| clock host vs GPS | — | 50 ns, skew 0.022 ppm |

The station moved from `systemd-timesyncd` against the Debian pool — which had stretched
to a **34-minute poll**, leaving the Pi running free on an uncorrected crystal between
updates — to chrony against `pi3chrono.local` by name (mDNS; it is a DHCP lease), `prefer`,
`minpoll 4 maxpoll 6`. Pool entries stay as a fallback so the station degrades to stratum 2+
rather than to nothing if the clock host dies. **chrony slewed, it did not step** (3 ms is
far under `makestep`'s 1 s), and the recorder logged **dropped 0 / glitches 0 / resyncs 0**
across the switch. Epoch row added: `timing`, absolute timestamps only — rate and
amplitudes unaffected.

**But the station's accuracy is now limited by its network path, not by the clock.** Its
root delay to the clock host is **7.0 ms** and ping confirms it: RTT avg 7.2 ms, min 5.4,
max 9.9, mdev 1.6. That is not wired Ethernet — the station's `eth0` feeds the *wireless
bridge* installed on 2026-07-20 to keep a Wi-Fi radio away from the ADC
([[wifi-tx-corrupts-acquisition]]), so the path traverses Wi-Fi whatever the interface is
called. chrony's own error bound on the station is **±3.5 ms**, not the sub-µs the host
achieves.

So the earlier prediction of "tens of µs at the station over Ethernet" was wrong: that
would need real copper to the garage. What was actually bought is a much better-controlled
*offset* (3.0 ms → sub-µs at any instant) and a 16–64 s poll instead of 34 minutes, with an
uncertainty floor of a few ms set by the bridge. At 100 sps one sample is 10 ms, so ±3 ms
is under half a sample and this is comfortably good enough — it is simply not the
microsecond regime.

Also serving the Mac (`/etc/ntp.conf` -> `server pi3chrono.local`; sntp reports
+3.8 ms ± 4.6 ms over Wi-Fi). `chronyc clients` shows both.

## 🪪 SEED IDENTITY CUTOVER: XX.OAKMT.00.SHZ -> SS.OAKM1.00.EHZ (2026-08-30 15:39 UTC)

Decoupled from the ISC wait, which was never a blocker. James (ISC DCO) answered on
2026-08-05 that the ISC is happy to use FDSN-coded stations and there was no reason not to
have both; Charles replied the same day; the IR confirmation has not come in 25 days. But
**`SS` needs no assignment** — it is the FDSN code any single-station operator may use — so
nothing here ever depended on them. The IR entry is a directory record, not a permission.

**The band code was a real bug, not a rename.** FDSN sets it by sample rate: **E is
80–249 sps, S is 10–79**. `SHZ` was correct at 57/60 sps and stopped being correct at the
2026-07-25 move to 100 sps, so every file since carried a band code contradicting its own
sample rate. Charles had `EHZ` right on the ISC form; only the code was wrong, and it took
comparing the two to notice.

**Two hardcodes that would have broken silently:**

- `seismo_dashboard.py` built `SID` as `f"{NETWORK}.{STATION}.00.SHZ"` and the rail printed
  a literal `00.SHZ` — both would have kept saying SHZ while the data said EHZ.
- `reharvest.py` synced day-files by the literal `XX.OAKMT.00.SHZ.D.{day}.mseed` and
  `trigger_dataset.py` read them the same way, so the weekly job would have quietly stopped
  pulling new files and harvested a frozen archive **with no error**. Both now match on the
  **day**, not the SEED id.

**The archive keeps both identities on purpose.** Pre-cutover files stay `XX.OAKMT.00.SHZ`
because that is what was written; `epochs.py` carries an **`identity`** boundary — not
amplitude/noise/timing, since waveforms are byte-identical across the line. Do not let a
future comparison treat this as a data discontinuity. `udp_collector` names files from the
**record header**, so it followed the station on its own and the archive was never at risk.
Day 242 holds two part-files, one per identity; `load_archive` prefers the larger, so that
one day is partial in the harvest. Accepted rather than merged.

**Verified end to end:** station logs `recording SS.OAKM1.00.EHZ`; the collector filed
`SS.OAKM1.00.EHZ.D.2026.242.mseed` within a minute; the detector restarted on `d041663`
and is emitting scored events; `/v1/live` serves; both dashboards render `OAKM1` / `00.EHZ`.

**apps02 carried an undocumented override.** The public dashboard kept saying `OAKMT`
after everything else had switched, because its dokku app had explicit
`SEISMO_NETWORK=XX` / `SEISMO_STATION=OAKMT` config set at some point and never written
down — so the code defaults never applied there. `SEISMO_CHANNEL` was *not* set, which is
why the same page rendered `00.EHZ` beside `OAKMT` and gave the game away. Now set
explicitly on apps02 (`dokku config:set seismo SEISMO_NETWORK=SS SEISMO_STATION=OAKM1
SEISMO_CHANNEL=EHZ SEISMO_LOCATION=00`). **`deploy.sh public` does not touch dokku config**,
so any future identity change has to set it there by hand as well; pi5's dokku app has no
identity config at all and takes the code defaults.

**Still outstanding:** the ISC IR confirmation. Nothing depends on it — we are already
publishing under the identity Charles told James we would use.

## 🏷️ LABEL GUARD + A FROZEN HOLDOUT (2026-08-30, later)

Two things, both cheap now and expensive later.

**The `sustain >= 2.0` guard now applies to the LABEL.** It was added to
`detection_map.calibrate()` and to the harvest's `seen` this morning but never to
`trigger_dataset.py`, which is where it matters most — that is the training label. One
positive dropped, exactly the right one: the **Toms Place M3.4 at 348 km**, whose 8.8×
spike lasts 1.35 s where every genuine catch holds 3.4–7.9 s. Two trigger rows.

Removing a single mislabelled positive out of 33 measurably improved the model:

| | before | after |
|---|---|---|
| PR-AUC, ratio ≥ 10 | 0.637 | **0.694** |
| PR-AUC, ratio ≥ 20 | 0.769 | **0.868** |
| Toms Place spike | 0.894 | **0.005** |
| confirmed positives below the 0.7 alert threshold | 0/33 | **0/33** |

The four local events all went *up* (M1.8 0.998, M1.4 0.951, M1.5 0.987, M2.1 0.998). So
the label was doing real damage, and this is a better before/after than the morning's
retrain because only the label set changed — same features, same data, same
hyperparameters.

**A held-out set is now frozen: `HOLDOUT_AFTER = "2026-08-31"` in `trigger_train.py`.**
Everything after that date is reserved — never fitted, only scored. It excludes nothing
today, which is the point: it costs nothing to start and cannot be arranged retroactively.
Every model so far has seen every row in the archive, so no evaluation to date is
out-of-sample in the strict sense — the grouped CV is honest about leakage between folds
but not about how many times these rows have informed a choice of feature, threshold or
filter. **Move the date forward only by deliberately promoting the holdout into training
and choosing a new one; never to make a number look better.**

This is the first concrete step toward the rigorous train/test set. Still open for that:
positives are defined by a filter rather than by recorded provenance, and the ~28,000
negatives certainly contain real earthquakes below catalogue completeness (the harvest's
own `smallest SEEN` is M0.2) — irreducible label noise on the majority class without a
second station, and a ceiling on measured precision that is not the model's fault.

## 🧠 CLASSIFIER RETRAINED — the very-local blind spot is closed (2026-08-30)

Four confirmed local events in 48 hours exposed it, and the depth double-count in
`trigger_dataset.py` (fixed in `bdf7137`) explained it: counting depth twice does most
damage where depth is a large fraction of the distance, so the close events — the only
counter-examples that could teach the model that a nearby quake is broadband — were
labelled at the wrong time and effectively poisoned.

**⚠️ CORRECTED 2026-08-30 — the mechanism below was wrong.** The original claim here was
that the model had learned *"far away means earthquake"*. Tested properly against all 33
positives it does not hold: Spearman rho(p_quake, distance) is **+0.147 (p = 0.42)** for
the old model and **+0.144 (p = 0.43)** for the new one — no distance relationship in
either. The old model's five sub-threshold positives had a **median distance of 38 km**,
mid-range, not local. What actually separated them was that they were **weak, spiky and
short**: median snr_env 6.3 against 13.3 for all positives, kurtosis 8.1 against 3.7,
duration 10.8 s against 15.2 s, peak_ratio 23 against 33. That is an ordinary small-sample
failure — 19 positives left too few examples near the decision boundary — not a spatial
confound. The two-event comparison below is real but was generalised from n=2 and should
not be repeated as a finding.

**What prompted the retrain.** The M2.1 at The Geysers (43 km) and the M1.5 at Larkfield
(16 km) are near-identical triggers — STA/LTA 77 vs 82, peak 19.9 vs 21.7 µV — and the old
model scored them **0.994 vs 0.181**. That contrast is genuine; the explanation offered for
it was not.

**Retrain:** refreshed `events.pi5.log` from pi5, rebuilt the features on the corrected
labels, and refit. Positives **31 → 58** in the dataset, **19 → 33** in the deployable
`peak_ratio >= 10` slice. Also stamped the `trained` date instead of the hardcoded
`"2026-08-26"` literal — that string is what the detector prints at startup, so a stale
one makes a fresh model look like the old one in the log.

| event | dist | OLD p | NEW p |
|---|---|---|---|
| M1.8 Santa Rosa | 9.9 km | 0.988 | **0.996** |
| M1.4 aftershock | 9.0 km | **0.130** | **0.937** |
| M1.5 Larkfield | 15.7 km | **0.181** | **0.986** |
| M2.1 Geysers | 43.2 km | 0.994 | **0.991** |

Both events it got badly wrong now clear the 0.7 alert threshold, and the distant one did
not regress. The M1.8 was never scored at all in production (the window race, fixed in
`a12fe36`).

**A metric got worse and the model got better — read the numbers carefully.** PR-AUC on
the `ratio >= 20` slice fell **0.91 → 0.769**. That is not a regression: the old figure was
measured on a training set whose hard local positives were mislabelled or absent. Adding
genuinely difficult true positives lowers a measured PR-AUC while making the classifier
correct on exactly the cases that matter. The event-level table above is the real test,
and it is unambiguous. Do not "restore" the old number by dropping local events.

**FIXED, same day — see the entry below.** ~~A mislabelled positive is in the training set.~~ `trigger_dataset.py`'s positive filter
is `snr >= 3 and -1.2 < resid < 0.4 and lo_hi >= 1` — it never got the `sustain >= 2.0`
guard that was added to `detection_map.calibrate()` and to the harvest's `seen`. So the
Toms Place M3.4 at 348 km, which waveform inspection showed to be a **1.35 s cultural
spike**, is labelled `1` and the retrained model duly scores it **0.894** (the old model
said 0.003, which was arguably correct). The guard belongs in all three places. Not fixed
yet — it means another retrain, and that wants deciding rather than doing reflexively.

**Two further data-quality items noted, not fixed:**

- The M2.1 Geysers carries `label=0` in the feature set — it is a confirmed catalogue
  event, but it postdates the last harvest run, so it is training as a *negative*. The
  model scores it 0.991 anyway, so it is not fooled, but with 33 positives a mislabelled
  one is not free. The weekly re-harvest will absorb it.
- A 2026-08-12T06:15:46 trigger with **peak 110,187 µV** (110 mV) and `ratio 1.4 M` sits in
  the training data as cultural. That is a front-end artifact, not ground motion.
  `EXCLUDE` in `trigger_train.py` only covers the 07-31 → 08-03 fault window; this one is
  outside it and should be cut too.

## 🔁 WEEKLY RE-HARVEST, AUTO-PUBLISHING BEHIND GATES (2026-08-29)

Charles: "we need a workflow system that re-harvests events a week or so after the
event." Right instinct — USGS publishes small events as `automatic` within minutes and a
human reviews them days later, and everything here is computed from those parameters.
The M2.3 near Graton (2026-08-30, `nst 5`, `gap 217°`, depth pinned at −0.71 km) is the
case in point.

**`analysis/reharvest.py`**, weekly under launchd
(`ai.mcguinness.seismo-reharvest.plist`, Sundays 09:15; launchd runs a missed calendar
job on the next wake, so a sleeping Mac delays rather than skips).

**It runs on the Mac, not pi5**, though pi5 has obspy/numpy/sklearn and the archive
locally. Publishing needs GitHub write access and root on apps02; pi5 has neither by
deliberate design (`git push --dry-run` from `~/seismo-src` fails — read-only deploy key,
and its apps02 key is rsync-restricted). That posture is worth more than the convenience.

**Auto-publish, per Charles's explicit choice**, so the judgement a human would apply
lives in gates instead. Nothing publishes if, versus what is committed: rows fall >10%,
confirmed events fall >25% or double, the validated range moves more than 1.5×, the site
deficit moves >0.15 dex, or >15% of `seen` rows flip. On a block it keeps the candidate
at `analysis/reharvest-rejected.csv` and sends a high-priority ntfy instead.

**The gate is tested against the case that motivated it.** Injecting the 2026-08-29 Toms
Place spike (the 1.35 s cultural bang at 348 km) into a candidate CSV drives reach
88.8 → 348.2 km, and the gate blocks with *"validated range moved 88.8 -> 348.2 km
(3.92x)"*. That near-miss was caught by eye; now it is caught by code.

**First dry run found real churn in 30 days:** 8+ events revised (one depth 2.4 → 6.0 km,
several magnitudes), 5 events added late, and one **withdrawn** from the catalogue
entirely (M0.77 near Cobb, 2026-08-19). Calibration held at 32 confirmed / 88.8 km /
−0.244 dex, so it would have published.

Sends ntfy on publish, on a gate block, and on failure; silent when nothing moved.
`--dry-run` does everything except commit/push/deploy. Takes ~4 min.

**Two bugs the first *scheduled* run exposed** — both invisible to a hand-run:

- **launchd hands an agent a minimal PATH** (`/usr/bin:/bin:/usr/sbin:/sbin`), and both
  `direnv` and `git` are under `/opt/homebrew/bin` on this Mac. Every git operation would
  have failed and the job would have alerted instead of publishing, every Sunday, forever.
  The plist now sets PATH explicitly, and the script preflights `direnv`/`git`/`scp`
  before spending four minutes harvesting.
- **ntfy.mcguinness.ai is behind Cloudflare**, whose browser-integrity check 403s the
  literal User-Agent `Python-urllib/x.y` with `error code: 1010`. `curl` and
  `python-requests` pass; `urllib` does not. So the notifications — the entire point of a
  job that runs unattended — were silently failing. Fixed by sending a real User-Agent.
  **`server/detector.py` is unaffected**: it uses `requests`, which Cloudflare allows, so
  the earthquake alerts have been getting through all along (including Petrolia's).

The dirty-tree guard also fired correctly on that run, refusing to publish over
uncommitted edits.

**Not covered:** it does not retrain the classifier. `trigger_dataset.py`'s
double-counted depth means the deployed model was trained on mislabelled windows, and
that retrain wants a human looking at the result — see the entry below.

## 📐 STATION ELEVATION IN hypo_km, AND A DOUBLE-COUNTED DEPTH (2026-08-29)

The GPS box gave us a measured station elevation, and it exposed that every hypocentral
distance in the project put the station at sea level. Catalogue depths are referenced to
**mean sea level**, so a station 119 m *above* it is that much further from the
hypocentre — the two add, they do not cancel. `hypot(horizontal, depth)` was short by the
station height on every event.

`STA_ELEV_M = 119.0` (GPS MSL at the house, 2026-08-29, eph 4.6 m; the geophone is in the
garage a few metres off, and 5 m of error moves a 10 km hypocentral distance by 0.05 %)
now enters the vertical leg in all five places that computed one:

| file | was |
|---|---|
| `analysis/harvest_events.py` | `hypo_km()` — the harvest, and therefore the map |
| `dashboard/usgs_events.py` | `hypo_km()` — the live predicted-arrival markers on the drum |
| `analysis/quake_share.py` | the catch images' distance/S-expected line |
| `analysis/eventcheck.py` | the manual event checker |
| `analysis/trigger_dataset.py` | see below |

**Effect is real but small, and confined to close events**, which is where the vertical
leg is a meaningful fraction of the total: the 2026-08-29 M1.8 goes 9.79 → 9.91 km
(~23 ms of P travel time), St Helena 19.9 → 20.0 km. Petrolia at 318.6 km, San Leandro at
88.0 and Cloverdale at 45.8 are unmoved to the printed precision. Harvest `seen` stays 48
with **zero flips**; the map still reads 32 confirmed, site deficit −0.244 dex, furthest
88.7 → 88.8 km. Nothing published changes except the M1.8's "9.8 km" becoming 9.9.

**The bug it turned up.** `trigger_dataset.py` computed
`hypo = hypot(dist_km, depth_km)` — but `dist_km` out of the harvest is **already
hypocentral**, so depth was counted twice. For the M1.8 that turned 9.79 km into
13.57 km and put its predicted P arrival **0.73 s late**, mislabelling the window the
classifier trained on. Worst for deep, close events; negligible for distant shallow ones,
which is why it survived. Now just `hypo = float(r["dist_km"])`.

That matters more than the elevation fix: it is the labelling path for the trigger
classifier's training set. **The current model was trained through this bug** — it should
be retrained before the next confirmed-count milestone, and the very-local blind spot
seen on the M1.8's aftershock (p = 0.13) is exactly the regime the double-count distorted
most.

## 🕐 HARVEST: REAL TRAVEL TIMES, AND A NULL TEST THAT NEARLY DIED (2026-08-29)

`harvest_events.py` cut its measurement window at `dist / 5.19 km/s`. That velocity was
fitted to 18–90 km paths through shallow crust; past ~150 km the first arrival is **Pn**
refracted along the Moho at ~8 km/s. At 318 km the old estimate put P at **+61 s** when
iasp91 puts it at **+45.7 s** — the window opened 15 s *after* the wave arrived. `ts` was
computed and never used, so once S−P grew past the fixed 32 s box the S/Lg peak fell out
of the window entirely.

- `arrivals_s()` now returns (P, S) from **iasp91 via obspy.taup**, cached, falling back
  to the straight-line VP/VS below 15 km where taup has no useful ray and the constant
  velocity is right anyway. Both are written out as `tp_s` / `ts_s`.
- The signal is measured in **two tight boxes** — `[tP−2, tP+12]` and `[tS−4, tS+22]` —
  not one box spanning both. They merge into one box locally. Exposure stays ~40 s at
  every distance, so the false-positive rate does not grow with range.

**Why two boxes and not one long one.** One spanning box was tried first, and `seen` rose
65 → 88. That looked like a win and was not: at 348 km the box is 70 s long, and one
unrelated cultural spike inside it carries the peak. It promoted the **Toms Place M3.4 —
the only far-field NON-detection we own, the red X on the map** — to a 348 km detection,
which would have quadrupled the published validated range off a door slam. Waveform check
(`+100.9 s`, **8.8× the floor**, 6.8 s of a 71 s window above 3×, no onset at the
predicted P, nothing sustained at S): cultural.

**`sustain_s`, and the sharpest discriminator in the harvest.** Peak SNR is carried by a
single sample, so `seen` now also requires the 1 s envelope to hold above **half its peak
for ≥ 2.0 s** (`--sustain-seen`). Measured:

| event | dist | sustain |
|---|---|---|
| Toms Place M3.4 (cultural spike) | 348 km | **1.35 s** |
| Santa Rosa M1.8 | 9.8 km | 3.41 s |
| Petrolia M4.8 | 319 km | 4.82 s |
| St Helena M2.5 | 20 km | 4.90 s |
| San Leandro M3.8 | 88 km | 7.08 s |
| Cloverdale M4.2 | 46 km | 7.94 s |

Clean separation, and it is now also a guard on `calibrate()`'s confirmed set in
`detection_map.py` — that filter never used `seen`, so the guard had to be added in both
places or the map would have taken the spike anyway.

**Net effect on the published numbers: none.** Still **32 confirmed events, furthest
88.7 km**, site deficit −0.244 dex, rings within 1 km of the previous run. `seen` across
the harvest went 65 → 48 as the far-field spike detections dropped out; `triggered` 433 →
445 as correctly-placed boxes caught real triggers the old window missed. Petrolia is
untouched (peak 19.2 µV, resid −1.216, still excluded from the fit, still drawn).

**Noted, not changed:** `REF_PEAK_UV = 126.0` is the anchor for every residual, but the
current pipeline measures that same M2.5 St Helena at **47.8 µV** — the constant predates
the 1 s-smoothed-envelope definition. The rings are unaffected (an anchor offset cancels
between `predict_uv` and the fitted `resid_med`), but it does mean part of the advertised
"1.8× quieter than textbook" is measurement definition rather than site. Re-anchoring
would move every residual on the page and wants doing deliberately.

## 🌊 M4.8 OFF PETROLIA AT 319 km — RECORDED, AND THE MAP REBUILT (2026-08-29)

USGS **M4.8, 85 km W of Petrolia, 2026-08-29 02:41:11.61 UTC, 40.450/-125.272, 10 km** —
**318.6 km NW**, offshore of the Mendocino triple junction. Recorded, alerted, and now on
the Catches page. This is **3.6× the previous furthest catch** (88.7 km, San Leandro).

**Identified by the clock, not by amplitude.** iasp91 puts Pn at 02:41:56.7 and the
detector triggered at **02:41:57.0**; Sn at 02:42:32.1 and the envelope peaked at
**02:42:31.7**. Two independent arrivals inside half a second each, and a USGS catalogue
query returns **exactly one** event within 700 km in a nine-minute window. Peak 52 µV,
SNR ~27, energy above 2× the floor from +45 s to +356 s. `hf_lf` **0.40** (and 0.25 on
the follow-on) against 1.2–3.3 for every other trigger that evening; all the energy sits
below ~7 Hz, hugging the geophone's own 4.5 Hz corner. **It alerted**: p_quake 0.991,
ntfy push 91 s after P; the follow-on at 0.838 was correctly eaten by the 5-minute
hold-off. The alerting path works — the M1.8's silence really was the window race.

**Why it was never in the harvest:** `harvest_events.py` defaults to `--radius 300` and
this is at 318.6 km. Re-harvested at **`--radius 400`**, 2026-07-19 → 08-30, with the
current `events.log` pulled from pi5 (the local copy was from 07-27): **1883 windows**,
up from 1316.

**Recalibrated:** `detection_map.py` now reads **32 confirmed events** (was 28),
furthest **88.7 km**, site deficit −0.244 dex (1.8× quieter than textbook), corner
penalty 0.313 dex/M above M3, floor 3.0× noise.

**Petrolia is drawn on the map but NOT fitted**, as a green diamond beside the red X of
the Toms Place null. `calibrate()` rejects residuals below −1.2 dex as probable
mis-associations and this one reads **−1.216** — 16× below textbook, because at 319 km
what survives is low-frequency Lg, the band a 4.5 Hz geophone is built to reject.
Admitting it would also make it the n=1 anchor for the corner penalty in place of the
M4.2, reshaping every ring from one far-field point. The model already predicts it
anyway: M4.8 median reach 559 km, so 319 km is comfortably inside.

**A bug the regeneration exposed.** The map's null-test verdict was a *hardcoded
sentence* — "sits OUTSIDE even the best case" — never checked against the numbers. Under
the new calibration the M3.4's best case is 444 km and the event is at 348 km, i.e.
*inside* it, so the map had gone false on the public page. `null_verdict()` now computes
the wording from where the event actually lands: outside best case / between median and
best / inside median, each with the right conclusion. The honest reading today is that
the miss says the best-case ring is an upper bound, not that the model called it.

**Also corrected:** the M1.8 entry claimed the nearest previous catalogued event was
8.5 km. The harvest's `dist_km` is **hypocentral**, so that was not comparable to the
M1.8's 2.8 km epicentral. By epicentral distance the nearest before that night was
8.4 km (M1.31, Kenwood). And the M1.8 had an aftershock the station also caught — M1.38
at 04:13:48 UTC, same spot, predicted P 04:13:49.7 vs trigger 04:13:50.0, peak
43.6 µV — which the classifier scored only **0.13**. A very local quake is broadband and
impulsive, which is what cultural noise looks like; with 19 training positives that are
mostly further out, close events are the model's blind spot. Worth more positives.

## 🚨 M1.8 AT 2.8 km — RECORDED PERFECTLY, ALERT LOST TO A RACE (2026-08-29)

USGS **M1.8, 7 km ESE of Santa Rosa, 2026-08-29 00:42:16 UTC, 38.429/-122.633, 9.4 km
deep** — 2.75 km epicentral, **9.79 km hypocentral**, the closest event the station has
recorded (previous nearest catch: 2 km... check before claiming a record on Catches).

**The record is the best yet.** Trigger 00:42:18, dur 13.16 s, **STA/LTA 585**, peak
**196.7 µV** — both the maximum across the last 3000 triggers (~2 days); next-biggest
ratio in that window is 106. At the measured Vp 5.19 km/s, P is predicted at
**00:42:17.89**; first energy above 4x the pre-event noise arrives at **00:42:18.14**,
0.25 s late. Predicted S-P 1.38 s; envelope peaks 00:42:20.67, 2.5 s after onset.
1-15 Hz peak 106 µV over a 2.10 µV floor (SNR ~50). Energy concentrated 3-6 Hz
(**4550x** above background there, vs 91x at 15-25 Hz and 17x above 25 Hz), dominant
5.9 Hz, hf_lf 0.70. Textbook local quake shape.

**And it did not push.** The event went out with **no `p_quake`**, so no ntfy alert —
Charles heard about it from USGS. Re-scored offline against the same model, window and
feature code: **p_quake 0.988**, comfortably over the 0.7 alert threshold. The classifier
was never the problem; it never ran.

**Root cause (fixed).** `detector.realtime()` released a trigger as soon as
`now >= t_start + POST + 2` (PRE 5 s, POST 25 s, poll 60 s), but the archive arrives from
the station in ~10 s blocks with a few seconds of lag. This one was polled at 00:42:50
needing data through 00:42:43 that had not landed; `_window()` fell under its 95%
completeness bar, returned `None`, and the `w is not None` guard skipped scoring
**silently** — no log line, so nothing ever said why. Timing luck, not size:
**77 of 1120 triggers with ratio >= 10 (7%)** had been dropped this way, and the same
burst re-detected a poll later *does* get scored (07:10:19 unscored / 07:10:24 scored).

- hold raised to `POST + SCORE_HOLD_S` (`SEISMO_SCORE_HOLD_S`, default **15 s**), past
  the block cadence plus lag; alert latency goes from ~27 s to ~40 s after onset, which
  is nothing against the 60 s poll
- the incomplete-window skip now **logs** (`score skipped <start>: window incomplete`).
  An unscored trigger cannot raise an alert, so the reason has to be in the journal.

**On the Catches page** (2026-08-29): `catches/2026-08-29-m1.8-santa-rosa.png`, rendered
with `quake_share.py --usgs-near --spectrogram --expect-s`. It sorts to the top (CATCHES
self-sorts newest-first by filename). Its entry also required a qualifier in the page
INTRO: the page tells readers a quake "starts at low frequency and stays there", and at
2.8 km that is simply not true — there is no path to strip the highs, and the spectrogram
runs to ~24 Hz at onset. The rule is about distance, not about earthquakes.

**Still open:** `detection-range-map.png` and its caption still say "28 confirmed events".
This is the 29th. Refreshing it means re-running `harvest_events.py` then
`detection_map.py`; the text and the image have to move together.

## ♿ CONTRAST GATED AGAINST WCAG + THE DRUM'S FIRST PAINT (2026-08-28)

Charles: dark-mode prose was washed out. Measured from his screenshot: `#7e8c93` on
`#111419` = **5.4:1** — passes AA, fails AAA, and the text in question was four
paragraphs of drum instructions marked up as a *caption* (`text-muted small`).

Rather than nudge a hex, the palette is now **gated**: `dashboard/contrast_check.py`
parses the token blocks straight out of `seismo_dashboard.py` (no second copy to drift)
and asserts a ratio for every pair that actually meets on screen, in both themes:

| target | applies to |
|---|---|
| **7:1** (AAA) | anything paragraph-length — body, captions, rail labels |
| **4.5:1** (AA) | links, axis numbers, badge fills, button labels |
| **3:1** (1.4.11) | the live trace, canvas axes, the status lamp |

Run it before changing a colour. It exits non-zero on any failure.

Eight pairs failed on the first run; all fixed by moving tokens, not by relaxing targets:
`--ink-dim` → `#414a50` / `#9aa7ae` (was 5.2 / 5.3, now 7.9 / 7.5), light `--copper` →
`#8a4f1c`, light `--copper-lit` → `#6d3c12` (hover must get *darker* on a light ground —
it was getting lighter), `--plot-axis` → 3:1 in both themes (it was 1.6, i.e. invisible).
A live DOM audit over the rendered pages then caught what tokens can't: Bootstrap's
`.text-success` / `.text-danger` in the Seismology 101 tables are ~4:1 on both grounds —
below even AA — and its `.text-bg-danger` badge is 4.0:1. Both replaced with `--yes` /
`--no` / `.badge-hot` from the gated palette. The rendered pages now show **zero**
failures at the AAA threshold in dark and one link at 5.7:1 in light (links are held to
the AA 4.5 target, deliberately).

**The half-painted drum, actually fixed.** `BFCACHE_JS` has always swapped in a fully
decoded image on refresh and on bfcache restore, but the *first* load was a plain
`<img src>` — and PNGs decode top-down, so a transfer cut off by a container swap or a
dropped packet left the first rows drawn and blank paper below until the 60 s timer came
round. The drum and the History drum now ship as `data-src` with no `src`, so the same
atomic double-buffered swap protects the first paint; a truncated transfer takes the
error path and retries after 3 s instead of painting half a record. While unloaded the
element holds 16:9 of empty space rather than plate-white, so it reads as *not here yet*
rather than as a drum with no data on it.

## 🎨 DASHBOARD REDESIGN — the rack panel (2026-08-27)

The dashboard read as stock Bootstrap because it *was* stock Bootstrap: one accent hex
over the defaults. A first pass swapped tokens and typefaces and still looked templated —
the card grid and the navbar are what date it, not the palette. So the structure went too.

**The page is now an instrument front panel, not a document site.**

- **A fixed left rail replaces the navbar.** It carries the station identity (OAKMT set
  in Barlow Semi Condensed) and, on *every* page, live vitals: a status lamp, seconds
  behind, the 1–15 Hz rms reading, a 30 s sparkline, sps / gain / pp. The station does not
  stop while you read the glossary, and now the site does not pretend it does. Nav is
  grouped by how far back you are looking — Now / Recent / The record / The instrument /
  Background — which is the only thing that really separates these pages.
- **No cards.** `_card()` still exists (every page is built from it) but emits a section:
  a hairline, a copper tick, a title. Panels are separated by space and rules, not boxes.
- **The Live page opens with the instrument.** No title block: an oversized reading, then
  the trace edge to edge with no frame. The rail drops its own copy of that number there.
- **Palette: copper on blue-slate** — the coil and the rock — in both themes, with the
  light/dark toggle (OS-following until clicked) kept in the rail.
- **Type:** Barlow (drawn from Californian public signage, for a Californian fault
  station), Newsreader for the long prose at a 66 ch measure, DM Mono with tabular
  figures for every number.
- **Both canvases are now DPR-aware** — they were drawn at CSS pixels, so every live
  trace was soft on a retina screen. Also: CSS `text-transform:uppercase` turns the micro
  sign into a capital Mu, so "pp µV" was rendering as "PP MV" in the rail. Labels that
  contain units are no longer transformed.

**Known gap, unchanged:** the server-rendered PNGs (drum, spectrum, activity) are
matplotlib on white and cannot follow a client-side toggle, so in dark mode they print on
a paper plate and the frame carries the theme. Threading a `theme=` param through
`render.py` / `heli_render.py` / `activity.py` (and the `heli_service` pre-render cache)
is the real fix; deferred.

`dashboard/seismo_dashboard.py` is now ~1500 lines — past the 1000-line mark, worth
splitting the page handlers from the chrome before it grows again.

## 🧠 TRIGGER CLASSIFIER, STAGE 1 — trained on the Mac, not yet on pi5 (2026-08-26 19:00 UTC)

After Yeck et al. 2020 (`doc/yeck2020.pdf`: NEIC keeps STA/LTA and bolts small
classifiers onto its PICKS; the win was 25 % fewer false associations, not more
detections). Same shape as this station's STA/LTA → `hf_lf` rule, so: learn to believe
triggers less, from the station's own catalog.

- `analysis/trigger_dataset.py`: every pi5-detector trigger since 07-25 as a feature row
  (window −5…+25 s, 1–45 Hz: band-energy fractions, hf/lf, centroid, dominant Hz,
  envelope rise/decay/duration, kurtosis + the detector's own fields). Label 1 if within
  [−3, +40] s of a CONFIRMED catalog arrival (detection_map criteria), ambiguous
  (±180 s of any `seen` event) dropped. **20,947 rows: 31 quake, 20,916 cultural.**
- `analysis/trigger_train.py`: HistGradientBoosting, class-weighted, **grouped CV**
  (positives by catalog event, negatives by day). Amplitude-absolute features excluded
  (they straddle the 08-07 rebuild); the **07-31→08-03 fault window excluded** — its 180 s
  millivolt triggers were the model's favourite "quakes" until they were.
- **On everything: hopeless** (PR-AUC 0.06) — 20k near-threshold blips with M1.3–1.8
  Geysers events hiding in them. **On the displayed range it works:**

| slice | rule `hf_lf<1.4` | model (grouped CV, out-of-fold) |
|---|---|---|
| ratio ≥ 20 (2,795 trig, 14 quake) | precision **2.4 %**, recall 100 % (7 TP / 283 FP) | PR-AUC 0.84; p≥0.5 → **75 % / 86 %**; p≥0.7 → 85 % / 79 % |
| ratio ≥ 10 (6,976 trig, 19 quake) | — | PR-AUC 0.65; p≥0.5 → 50 % / 68 % |

  Top features: 1–3 Hz and 3–8 Hz energy fractions (the same physics as `hf_lf`, in
  two bands), then kurtosis and 8–15 Hz. **`analysis/models/trigger_gbm.joblib`** (133 KB;
  trained on ratio ≥ 10, scores nothing below it). 14–19 positives: treat the numbers
  as "about right", not as decimals. Stage 3 (CNN) waits for ~100 positives.
- By-product worth a look: the highest-p "cultural" triggers are quiet-night bursts at
  04–07 UTC (08-13 11:43/13:04/13:23/14:24, 08-19 09:23, 08-23 08:04) with hf_lf 0.5–0.7
  — possibly sub-catalog Geysers events, i.e. mislabelled negatives.

**Stage 2 — DEPLOYED 2026-08-26 18:58 UTC** (2bf614c). `server/trigger_features.py` is
the single definition of the feature vector (training imports it; parity-checked).
`server/detector.py` holds a new trigger until its +25 s window exists, scores it
(ratio ≥ 10 only), writes `p_quake` into events.log; the Detections page (LAN copy —
the public one has no detections page) shows it as a badge beside `character`. The
`hf_lf` rule stays. scikit-learn + joblib installed in pi5's collector venv; `deploy.sh
services` ships the model with the collector files — **training stays on the Mac**.
First scored trigger: 18:59:24 UTC, ratio 11.4, hf_lf 1.03 (the rule says seismic),
**p_quake 0.001**. That is the whole point.

⚠️ **Found while checking the page:** the dashboard was reading the STATION's trigger
log (`seismo-rsync.service` still copies `seismo.local:seismo/events.log` into
`seismo-data/`), not the pi5 detector's — two parallel STA/LTA logs, same thresholds,
only one scored. Fixed as host state on pi5, no code: `dokku storage:mount seismo
/home/charles/seismo-archive:/archive`, `SEISMO_EVENTS=/archive/events.log`
(the `seismo-server` API already used that log); `seismo-public-sync.sh` now ships the
archive log as the public `events.log`. The pi5 detector's log is the canonical
detections list everywhere now, as rev2 intended. The station's own log still feeds
its health/QC and stays in `seismo-data/events.log`.

**Alert (2026-08-26 19:43 UTC, 5d01664):** the detector pushes to ntfy (`seismo-alerts`,
same server/token as dc_watch, from `/etc/seismo/ntfy.env` root:charles 640 via
`EnvironmentFile` in the unit) when **p_quake ≥ 0.7** — title "Probable earthquake
p=…", body with time/ratio/peak, click-through to the History drum for that hour;
**at most one push per 5 min** so an aftershock cluster is one notification.
`detector.py --test-alert` sends a TEST push (sent once at 19:43 UTC). Near-duplicate
triggers (same burst re-detected across polls, start shifted 1–2 s; 6,995 pairs in the
log) are now deduped by ±3 s proximity in the detector and collapsed on the page.

Retrain when: the harvest CSV is refreshed with new confirmed events
(`harvest_events.py` → `trigger_dataset.py` → `trigger_train.py` → `deploy.sh services`).

## 🖥️ DASHBOARD, DAY TWO (2026-08-26 14:00–17:30 UTC)

All on both copies (`./deploy.sh public` + `./deploy.sh dashboard`), all pushed.

- **The torn drum, third time, correctly diagnosed at last** (68923c7). Charles hit it on
  a fresh load — in **Safari**, not Chrome. Server side was clean (nginx byte counts
  match every render, no restarts, Cloudflare delivers whole files), so the transfer
  is being cut between Cloudflare and the browser, and Safari paints a PNG
  progressively as bytes arrive. Fix: **every dynamic image reload is double-buffered**
  — fetch into an off-screen `Image`, swap the visible one only on `load`, keep the old
  one on error. Applies to the 60 s drum timer, the 30 min spectrum timer, the bfcache
  restore, tab-visible, and image-error paths (`BFCACHE_JS`, `window.seismoReload`).
  A bad transfer now costs staleness, never a broken picture. The two earlier fixes
  (render lock ece96b8, bfcache reload 9596650) were real but were not this.
- **About page is copy-aware** (31bfd54): `{serves}` placeholder — public copy says the
  Pi 5 pushes the charts, outbound only, to a cloud host; LAN copy says it serves the
  page. Also mentions the C reader.
- **"What does a real earthquake look like?"** (13160b5 → 42a6f5a). Charles's screenshot
  of the 2026-07-29 drum (`doc/20260729 Cloverdale M4-2.png`; web crop
  `dashboard/catches/drum-2026-07-29-cloverdale-m4.2.png`, 61 KB) sits under every drum
  (Live, History) inside a `<details>` whose summary is now a **full-width button:
  "Click here to see what a REAL earthquake looks like on this drum"**, and expanded in
  the Learn helicorder walkthrough. Shown at **50 % width, centred, captioned "a saved
  image … not live"** so nobody mistakes it for the live drum. Text: three rows each way
  (the clip is deliberate), ~80 s taper, felt in Santa Rosa as a jolt; the 03:45 blip is
  the M2.2 aftershock — what a felt-by-nobody quake looks like.
- **Weekly activity view unlocked** at 15:30 UTC (14.0 days since the 08-12 move).
  Monday-first is Python's ISO `weekday()`, kept on purpose: Saturday night bleeds into
  Sunday and the two should be adjacent rows. Exponentially-weighted median for this
  view is on the BACKLOG (797bf4f), revisit ~November.
- **Distance to Route 12: 92 m across open ground, and 13 m below the garage** (421 ft vs
  377 ft, ~8° slope) — from Charles's map. Fixes the traffic-envelope arithmetic (~4 s
  per pass), makes the open strip the hammer-refraction line, and frames the site as
  hillside flank vs valley fill for the site-response question. In memory.
- **Deploy note:** the pi5 `./deploy.sh dashboard` grep for "Application deployed"
  sometimes reports 0 while the deploy succeeded (its output differs); check
  `DEPLOYED_SHA` / `dokku apps:report` rather than trusting the count.

## 🖥️ DASHBOARD EVENING — catches, public trims, a render race (2026-08-26 03:30–06:30 UTC)

All on both copies (`./deploy.sh dashboard` + `./deploy.sh public`), all pushed.

- **Catches page** (`/catches`, commit 24d8429 → 2e81646): newest first. Seven confirmed
  events with quake_share images + spectrograms + facts, the refreshed detection map on
  top (28 confirmed events, validated to 89 km — see the entry below). The Wyoming
  non-detection was added and then dropped (08cbb5f): the map already carries the far
  edge. Content in `dashboard/catches.py`, images in `dashboard/catches/`.
- **Public copy has no Detections page** (2eb89f5): nav link gone, `/detections` 404s,
  the About paragraph loses its link. It is a raw trigger log, mostly cultural. pi5
  keeps it. The switch is `_PUBLIC_COPY` (= `SEISMO_HELI_BUILD=0`), same flag as the
  footer.
- **Seismology 101 → "Keep learning"** (2656db3, 35cdbf8, a610d64): three USGS pages on
  the Rodgers Creek fault first (traced through Santa Rosa 2016; the new lidar map;
  the Hayward–Rodgers Creek connection), then eight general explainers (USGS science
  of earthquakes, magnitude vs intensity, IRIS animations, Berkeley Seismo Lab, the
  Hayward fact sheet, USGS latest-quakes map, Putting Down Roots, ShakeAlert). All
  `target=_blank`. usgs.gov 403s curl but serves browsers — verify those with a
  browser-style fetch, not curl. Wikipedia's Rodgers Creek page just redirects to
  Hayward; Press Democrat / SF Chronicle explainers are paywalled — both skipped.
- **Thunder sentence** (fe08d12): the S–P and thunder gaps are now stated the same way
  round (5 s/mile vs 0.2 s/mile; a second of gap ≈ 7 km at this station's Vp/Vs).

### 🐛 A half-drawn helicorder — actually a HALF-DOWNLOADED one (9596650, 454662d)

Second occurrence the next morning made the real cause obvious: the image is cut
mid-row with the header intact — a PNG that stopped decoding partway. Navigating away
cancels the in-flight image download; "back" restores the page from the browser's
bfcache with the half-decoded bitmap still in the `<img>`; the drum's 60 s refresh
timer would eventually replace it. Fix: `BFCACHE_JS` in `_shell` re-requests the
dynamic renders (helicorder, history, spectrum, activity — never the static catch
images) on `pageshow` with `persisted`, on a tab becoming visible, and 2 s after an
image error. The render lock below was a real bug too, just not this one.

### 🐛 (and) two matplotlib renders at once (ece96b8)

Charles hit a drum with rows 04:30–06:00 blank under a "data to 06:06" header; refresh
fixed it. Not Cloudflare (`/helicorder.png` is `no-store`; "back" shows the browser's
bfcache copy of the page as first loaded). The drum is drawn by heli_service's
background thread while `/history.png`, `/spectrum.png`, `/activity.png` draw in request
threads, all via `plt.figure()` — pyplot's figure registry is not thread-safe, and
heli_service's lock guarded only the cache. Fix: `heli_render.MPL_LOCK` around every
render in the process (helicorder, history, spectrum, activity — the latter two via
thread-safe wrapper functions so an exception can never strand the lock), and the
figures moved to `Figure` + `FigureCanvasAgg` (no pyplot state; the obspy dayplot keeps
pyplot under the lock). Verified locally: six concurrent drum renders, byte-identical.

### 🔧 Public `/spectrum.png` was 503 since launch (4e727eb)

It Welches the miniSEED, which the public copy does not have. pi5's minute sync now
curls its own `/spectrum.png` (30-min server cache, O(1)) into `seismo-data/spectrum.png`
and ships it; the public route serves that file when `_PUBLIC_COPY`. All four rendered
images now 200 on both hosts.

### ⚠️ Deploy gotchas learned tonight
- `deploy.sh`'s rsync has no `--delete` (on purpose), so a static file removed from git
  lingers in the hosts' build contexts — delete it there by hand.
- Dokku skips `git:from-image` when the image TAG is unchanged, even if the image was
  rebuilt: a same-SHA redeploy is a no-op. Retag (`seismo-dash:<sha>-r2`) to force it.
- Cloudflare caches static PNGs for the `max-age` (1 day); a removed image keeps
  answering at the edge until it expires or is purged.

## 🎣 CATCHES PAGE + DETECTION MAP REFRESHED (2026-08-26 04:10 UTC)

Charles: a page highlighting the interesting earthquakes we've caught, with the
detection map. **/catches** on both copies. Content module `dashboard/catches.py`
(content.py style), static images in `dashboard/catches/` (quake_share.py renders,
shrunk to ~150 KB each with Pillow), two thin routes in the app.

Seven catches: M4.2 Cloverdale (07-29), M3.8 San Leandro (08-13, 88 km — USGS revised
it down from the M4.1 first reported; the page says so), M2.5 St Helena (07-25, the
first), M3.2 / M2.8 / M2.5 / M2.4 Geysers, plus the Wyoming M3.3 non-detection as the
other edge. Each: image with spectrogram, catalog line, three or four facts.

**The map was stale.** `detection_map.py` calibrates from `event_harvest.csv`, which
stopped on 07-30 (7 confirmed events, validated to 46 km). Re-harvested 07-25 → 08-26
against the local day-files (1,316 catalog events; the 08-02→06 fault gap is simply
absent): **28 confirmed events, validated range 89 km** (the San Leandro), site deficit
−0.24 dex (1.8×), corner penalty still the n=1 M4.2 number. `reports/detection-range-map.png`
and the page copy are the new render. Re-run both whenever the harvest is refreshed.

⚠️ `seismo_dashboard.py` is at **1,028 lines** — over the 1,000 guideline. The next
page should come with a split (routes for images/live-data into their own module is
the natural cut). Charles's call when.

## 🌐 PUBLIC DASHBOARD LIVE: https://seismo.apps02.mcguinness.ai (2026-08-26 02:20 UTC)

Charles: make the data more useful without hacking exposure. Principle: **the house
only pushes outward**; nothing on the internet can open a connection to the LAN.

- **Same image, second host.** `./deploy.sh public` rsyncs `dashboard/` + `epochs.py` to
  `root@apps02`, builds `seismo-dash:<sha>` there (apps02 is aarch64 like pi5), and
  `dokku git:from-image seismo`. Dokku app `seismo`, storage
  `/var/lib/dokku/data/storage/seismo:/data`, ports 80/443 → 5000, Let's Encrypt (a
  public host, so ACME works). Config: `SEISMO_HELI_BUILD=0`, no ntfy vars (dc_watch
  logs only — no duplicate alarms).
- **`SEISMO_HELI_BUILD=0`** (`heli_service.py`): the public copy does not own a miniSEED
  mirror and must only render what pi5 banked; render freshness keys off the envelope
  files' mtimes instead of the archive's.
- **Feed from pi5, two cadences.** `~/seismo-public-sync.sh` (cron, every minute,
  flock): `heli/ env/ events.log health.json dc_watch.json signatures.json` (272 MB once,
  KBs after). `seismo-public-live.service`: the 30 s live ring every 3 s over one
  persistent SSH master (~4 KB/s). Both through `~/.ssh/seismo_sync_ed25519`.
- **The key can only rsync.** On apps02 the user `seismo-sync`'s `authorized_keys` entry
  is `command="/usr/bin/rrsync /var/lib/dokku/data/storage/seismo",restrict` — it can
  write files into that directory and do nothing else; pi5 never accepts connections.
- **Verified in Chrome:** Live (2.6 s behind), History drum, Detections, Activity,
  Spectrum, Environment, Learn, About all render over HTTPS.

The activity heatmap is **traffic, not the household**: sharp weekday 06–07 onset,
loudest cells at the 16–18 commute, Saturday quiet until 09–10, Sunday quiet until 11
then loud all afternoon (wine-country return traffic on 12). Safe to publish.

⚠️ The pi5 dashboard is untouched; apps02 is a second consumer of the same files.
`./deploy.sh dashboard` and `./deploy.sh public` are separate steps — deploy both.

### 🔒 seismo.mcguinness.ai → apps02; the Cloudflare Tunnel into pi5 is gone (2026-08-26 03:21 UTC)

`seismo.mcguinness.ai` used to be a Cloudflare Tunnel (`cloudflared` on pi5, ingress →
pi5's nginx :80) — a standing path from the internet into the LAN. Charles re-pointed
the Cloudflare record to `CNAME apps02.mcguinness.ai` (proxied); apps02's cert now
carries both names; then on pi5 `cloudflared.service` was disabled and tunnel
`460bf18f…` deleted. **Nothing at home is reachable from the internet any more.** The
LAN copy stays at http://seismo.pi5.mcguinness.ai; the public one at
https://seismo.mcguinness.ai (and seismo.apps02.mcguinness.ai).

## ✅ C READER LIVE: the ADS1256 is owned by `station/adsreader` (2026-08-25 19:46 UTC)

Charles: "Let's build the C reader." ~1 hour, as he said it would be.

**What it is.** `station/adsreader/adsreader.c` (~300 lines, libc + kernel headers only)
owns the chip end to end — SDATAC/RESET, chip-ID check, WREG (buffer off, AIN0−AIN1,
PGA, DRATE), SELFCAL, SYNC/WAKEUP, RDATAC — over `/dev/spidev0.0` (`SPI_NO_CS`; the
Waveshare CS is GPIO22, driven by hand and held low for the session) and
`/dev/gpiochip0`. **DRDY is a kernel interrupt** (GPIO uAPI v2 edge events with
`EVENT_CLOCK_REALTIME` timestamps and a per-line seqno), not a sampled level. The loop
is poll → read 3 bytes → write a 16-byte record `{ts_ns, sample, lost, flags}` to
stdout. It takes SCHED_FIFO 50 + `mlockall` when the unit grants them (`LimitRTPRIO`,
`LimitMEMLOCK`). `station/creader.py` spawns it, grows the pipe to 1 MB (~17 min of
buffer), and presents `RdatacReader`'s interface. `recorder.py` with
`SEISMO_READER=c`: lost conversions are **filled** (held value, `filled` counter,
`qc.log` "filled") instead of cutting the block; block start = kernel timestamp of
its first emitted sample (a timestamp queue rides alongside the despiker's lookahead);
`ClockAnchor` idle. The pigpio path is untouched (`SEISMO_READER=pigpio`).

**Standalone (recorder stopped, 62 s):** 6,171 samples, **1 lost — counted**, 0 flagged,
100.009 sps from the timestamps. The passive pigpio monitor running alongside reported
2 misses in the same minute: the sampler drops edges the kernel does not.

**Integrated, first 10 min:** `rate_est 100.0087` (the crystal), lag 0.4–0.9 ms,
**0 dropped, 0 filled, 0 glitches** — the old path logged 5 drops and 29 glitches in the
three minutes before the restart. Day-file after the cutover: **one contiguous 600 s
trace, zero gaps** (before: 185 traces in 30 min, 18.3 ms median gap). Raw DC identical
(323.9k counts). Noise: event-robust 1–15 Hz RMS 3.51 → 3.40 µV, band ratios 0.9–1.2 in
a busy afternoon; the quiet-night comparison is below — **floor unchanged**. pi5 collector still
receiving (archive mtime live). Epoch row added (`timing`, `glitch`).

⚠️ Nothing else may open the ADC while the service runs — `adc_diag.py`, `capture_raw.py`
etc. must `systemctl stop seismo-recorder` first (that was already true, but pigpiod
running no longer means the chip is free). Acceptance test for any future change:
`/tmp/drdy_meas.py`-style passive DRDY intervals → the 20 ms bin must read 0 and
agree with `lost`.

### 🌙 Quiet-night comparison: floor unchanged, one instrumental line halved (2026-08-26 12:10 UTC)

`analysis/night_compare.py 237 238` — 07:00–12:00 UTC (00:00–05:00 PDT), last pigpio
night vs first C-reader night. Yardstick from two ordinary pigpio nights (236 vs 237):
bands 0.88–1.01, robust RMS 0.89 → 0.78 µV, a ~23 Hz line wandering ×2.8.

| band | before | after | ratio |
|---|---|---|---|
| 1–3 Hz | 0.604 | 0.604 µV | 1.00 |
| 3–8 | 0.438 | 0.440 | 1.00 |
| 8–15 | 0.535 | 0.579 | 1.08 |
| 15–30 | 0.512 | 0.498 | 0.97 |
| 30–45 | 0.729 | 0.473 | **0.65** |

Robust 1–15 Hz RMS 0.78 → 0.85 µV (×1.09; night-to-night scatter is ×0.88–1.14).
**The quake band is untouched.** The 1.05 Hz intrinsic line is identical (2.83 µV/√Hz
both nights). What changed is above 30 Hz — and this turned out to be the HOUSE, not the station
(see the next entry): the **41.3 Hz line lost half its amplitude** (0.87 → 0.38 µV/√Hz, power ×0.19) and the **40.0 Hz line (the 60 Hz mains
alias) doubled** (0.32 → 0.61) — net 30–45 Hz down 35 %. A weak 19.3 Hz feature (×1.6
over floor, 0.19 µV/√Hz) is within the nightly-wander class. So the pigpio loop's
timing was a contributor to the 41 Hz line; the mains alias is now sharper because
the sample grid is exact. Neither matters below 30 Hz.

**⚠️ The sub-Hz comb did NOT go away — the fragment-gap explanation was wrong.** With
zero gaps in the archive, jday 238 still shows lines at 0.1 / 0.2 / 0.4 Hz (×7 / ×71 /
×14 over neighbours at 0.0033 Hz resolution), same as 237. Folding the quiet night on
the UTC 10 s grid shows a real periodic signal, **~0.1 µV peak-to-peak**, locked to the
block cadence on both nights — a tick from the recorder's 10 s block work (SD flush,
health.json, UDP burst) coupling into the front end at the 0.05 µV level. It only
looks large because the sub-Hz per-bin floor is tiny. Irrelevant to anything in band
(0.1 µV vs a 0.8 µV floor), and the rule for sub-Hz work is unchanged: divide out the
time-median PSD (`microseism_relative.py`). The 18 ms gaps were real and are gone;
they were not the comb's cause. Corrected in memory as well.

### 🏠 The 41 Hz "instrumental" line is the heat-pump AC compressor (2026-08-26 14:40 UTC)

Charles asked about a noise burst 08:31–09:18 UTC with edges on minute boundaries.
Pure tones at **41.0 / 40.6 / 37.65 Hz and 19.3 Hz**, nothing below 15 Hz, plateaus that
change at minute+~8 s (08:31:08 on, 09:07:12 step, 09:18:10 off, 09:22:58 on). The same
hour on ten nights shows 10–30 min runs with 10–15 min gaps every night; tracking the
41 Hz line-to-neighbour power ratio per minute over a full day: **on ~65 % of all
minutes, every hour, 100 % at 21–22 PDT**. A compressor on a hot August day. Charles: gas
water heater, **heat-pump AC** — outdoor unit on the ground by the garage, ground-coupled
into the slab. The minute-aligned edges are the thermostat's 1-min evaluation tick.

Consequences: the 41 Hz line is not hardware and never was; its "halving" in the
night comparison above was a cooler night; the 19.3 Hz feature is the same machine.
The 20 Hz line is HVAC too: Charles asked if it was 60/3. Not an alias — a 120 Hz
fold would sit at 100 − 2·f₄₀ and track the mains drift; measured hour by hour it does
not (r = +0.2). Per minute it is on 19 % of the day, almost only while the compressor
runs (P = 0.26 vs 0.04) and only 17–20 PDT, at 19.95–20.05 Hz: an evening high
fan/blower stage at ~1,200 rpm. **No unexplained lines remain except 1.05 Hz.** Any future 30–45 Hz
comparison must be done with the AC state known (the 41 Hz ratio is the state).

### 🕰️ Then the grid: toss one reading every ~123 s (2026-08-25 20:52 UTC)

Charles: "At some point we have to toss a reading, no?" Yes — and the first C-reader
version did not. Each block was timed from its own first sample: correct per record,
but any reader that stitches records into one trace assumes exactly 100 sps, and the
crystal runs 81 ppm fast. Measured on the day-file: **−280 ms after 61 min, −6.6 s/day**
of timing walk in a stitched trace.

Now `recorder.py` keeps ONE continuous grid at exactly 100 sps from the first emitted
sample. Every sample takes the next slot; when the chip's true time runs more than
¾ period ahead of its slot the sample is **tossed** (`tossed` counter, `qc.log`
"tossed"); more than ¾ period behind, one held sample is **padded**. A >1 s step
(NTP) re-anchors and counts a `resync`. Records abut exactly, a stitched day-long
trace keeps true time, and the timing error is bounded at ±7.5 ms forever. Charles's
arithmetic: 81 ppm × 100 sps = one surplus sample per 12,300 → every **123 s**; measured
122.6 s (the first one comes at half that, since the grid starts at zero offset).

⚠️ First cut used ½ period and oscillated: a correction moves the offset by a whole
period, so from −5.0 it landed at +5.01 and a few µs of jitter produced
toss/pad/toss inside one block. ¾ period lands at ±2.5 ms with 5 ms of margin.

`rate_est` in health.json is now the CRYSTAL rate (conversions per NTP-second, tossed
ones included), i.e. the thing the grid corrects — 100.0075–100.0087 so far, wandering
with temperature. `clock_err_ms` is the grid offset at the block boundary (±5 ms).

**Time reference.** The Pi runs systemd-timesyncd against `2.debian.pool.ntp.org`
(stratum 2, offset +6.5 ms, jitter 4.9 ms, Pi crystal correction +3.4 ppm). Absolute
time is therefore good to ~5–10 ms — half a sample — and the RATE against it is good to
well under 1 ppm on 10-min averages, which is what the 100.008 figure is measured
against. GPS-PPS (µs) or chrony (~1 ms) would be upgrades; neither changes anything at
100 sps.

## 🔍 RECORDER: the 18 ms block gap is 0.2 % of samples lost SILENTLY (2026-08-25)

Follow-up to the sub-Hz comb. Health counters (86,993 blocks since restart):
`rate_est 99.8173`, `glitches 170,280` (~2 per block, not "once per 100 s"),
`dropped 28,770`, `stalls 10,885`, `resyncs 1`, `clock_err_ms 0.00` on every log line.

**Passive DRDY measurement** (second pigpio client, falling-edge ticks, 60 s, recorder
untouched): **5,988 edges/60 s**; 5,975 intervals in a 9.994–10.001 ms core with mean
**9.99911 ms = 100.009 sps** (~90 ppm fast — the same crystal error the 60 sps epoch
measured), and **12 intervals of exactly 20.000 ms**. Nothing in between.

So: the ADS1256 converts at 100.009 sps. About **0.2 % of conversions produce no DRDY
edge that pigpio sees** — when the read is late, the chip's unread-data DRDY pulse
before the next update is sub-µs, under pigpio's 5 µs sampling — and the reader's
edge counter therefore cannot count them as `dropped`. The sample is simply gone.
`ClockAnchor` measured samples-per-wall-second honestly and got 99.82, so **block
start times are right** (P arrivals still land on prediction) but each 1000-sample
block is declared at 100 sps over 9.99 s when it really spans 10.018 s: an 18 ms
stretch inside every block, then an 18 ms gap, hence the comb.

Two compounding bugs in the discipline:
- `err = 0.0 if glitch_in_block else anchor.update(...)` — with ~2 zero-frames per
  block the update is skipped essentially always. `rate_est` is frozen at whatever it
  last saw; the "clock err 0.00" in the log is the skip, not a measurement.
- Missed conversions are invisible to `dropped`, so the "honest gap" path never fires
  for them.

**Fix (not done — Charles's call):** `_on_edge` already receives pigpio's `tick`; derive
the count from the tick delta (`round(Δtick / 10 000 µs) − 1`) instead of the edge
counter, so every lost conversion is known. Then, rather than cutting the block (would
fragment to ~5 s), **insert one interpolated sample per lost conversion** and count it
in a `filled` QC counter — a 1-in-500 interpolated point is a far smaller lie than a
0.2 % time-stretch plus a comb. With the index honest, `rate_est` converges to
100.009, blocks become contiguous, and the comb disappears. Also stop skipping
`anchor.update()` on glitch blocks — the 10 ms `outlier` guard already handles stalls.
Root cause underneath all of it is that the per-sample Python loop (pigpio socket
round-trips + despiker + STA/LTA + UDP) is marginal at 100 sps on a Pi 2B.

## 🌊 BODEGA BUOY vs SUB-Hz CHANNEL: the ocean is ~100x below our floor (2026-08-25)

Charles: correlate the sub-Hz channel with NDBC 46013 (Bodega Bay, ~35 km W). The
secondary microseism sits at TWICE the swell frequency with amplitude ~Hs², so the
buoy's WVHT/DPD predict where and how loud it should be. Three passes, 14 days
(08-12 → 08-25), 1,304 fifteen-minute intervals, buoy Hs 0.9–2.2 m, DPD 4–18 s:

1. **Band RMS** (`analysis/buoy_join.py`, on `subhz_reduce.py`'s CSV): the 0.12–0.5 Hz
   band lives in a **0.557–0.608 µV slot (p5–p95, ±5 %)** for the whole fortnight,
   through three swell peaks. Spearman vs Hs +0.11, vs APD +0.20, lag scan flat from
   −6 h to +12 h — a confound's signature (pressure scores the same), not a signal.
2. **Spectrogram** (`analysis/microseism_specgram.py`): dominated by a **comb of fixed
   lines at 0.05, 0.1, 0.2, 0.25, 0.5, 1.0 Hz …** bright enough to hide anything. See
   the trap below.
3. **Relative spectrogram** (`analysis/microseism_relative.py`, each interval ÷ the
   night-median PSD, which removes the comb exactly): white noise below 0.5 Hz. Ridge
   tracker vs 2/DPD rho +0.03; excess at the buoy-predicted frequency vs Hs² rho −0.01.

**Null, and it is the expected null.** HOPS records the summer 0.1–0.3 Hz microseism
at ~0.34 µm/s (table above). Our 0.58 µV floor at 0.2 Hz, through the element's f²
roll-off below 4.5 Hz ((0.2/4.5)² × 9 V/(m/s) = 0.018 V/(m/s)), is **~33 µm/s
equivalent — two orders of magnitude short.** A winter storm reaches maybe 5–10 µm/s;
still 3–7× under. The microseism is not reachable with this element in any season; it
needs a broadband or a low-corner sensor, not a better floor.

Plots (gitignored): `analysis/buoy_microseism.png`, `microseism_specgram.png`,
`microseism_relative.png`. Buoy file cached at `analysis/data/ndbc_46013.txt`
(realtime2 feed = last 45 days only; the NDBC historical archive has the rest).

### ⚠️ TRAP: the archive's 10 s fragments put a comb on every sub-Hz spectrum

A day-file is **~9,760 traces of 9.99 s with a 28 ms gap between each** (2.8 samples
at 100 sps; p5–p95 20–38 ms). `merge(fill_value="interpolate")` turns that into a
periodic 10.02 s structure → spectral lines at 0.0998 Hz and every harmonic (plus 0.05
Hz), 2–3 dex above the floor. Any sub-Hz PSD, ridge finder or band RMS that does not
divide out or notch the comb is measuring the recorder, not the ground. Divide by the
time-median PSD (as `microseism_relative.py` does) or restrict bands to fall between
lines. Separately: 28 ms lost per 10 s block is a 0.28 % timing slip that the recorder
is resolving by re-anchoring — worth a look at whether the block length or the
nominal 100 sps is the thing that is wrong.

## 📏 M2.4 GEYSERS 2026-08-25 00:22 UTC — fifth calibration anchor, 4.49× (2026-08-25)

Detected cleanly (`eventcheck.py` ratio 4.6, P onset on the predicted +9.0 s — a sixth
confirmation of `onset = dist/5.19 + 0.30`). Plot: `analysis/2026-08-24-geysers-m2.4.png`.

Against NP.1835 in 5–15 Hz: reference RMS 1.02 µm/s, OAKMT 0.23 → **4.49× (peak 4.39×)**.
Same 45 km path as the M2.8 (3.26×) and M3.2 (3.15×) Geysers anchors, so this is the
first fixed-path repeat — and it moved by 1.4×. That is the "~2× site scatter" caveat
made concrete, not an epoch shift: the San Leandro doublet (08-13T16:07, post-move)
gave 2.99×, so the 08-12 move does not split the anchors before/after.

Five anchors, one epoch: **median 3.26×, implied 8.82 V/(m/s)**. `PROVISIONAL_FACTOR`
stays 3.20 — the change is inside the noise. Added to `refstation.py` `ANCHORS`.

⚠️ `--all`'s MEAN (3.25×) still includes the rejected 0.88× Glen Ellen row; the median
is the number to quote.


---

# Reference (still true)

## Board jumper cheat-sheet (this board shipped with jumpers OFF)

- **Left yellow block** = the **AD input sensor-interface pinheader** (item 3 in the Waveshare manual: `VCC AGND AD7…AD0 D0–D3 P22–P25`), NOT jumpers and NOT SPI routing. It carries the SAME nets as the screw terminals. **Zero shunts fitted is correct** — it's a header for plugging in Waveshare sensor modules. (An earlier note here wrongly called it "SPI/GPIO routing, fully jumpered".)
- **Reference is an on-board `LM285-2.5`**, not the VREF jumper. The jumper only selects the LM285's bias source, so **v_ref = 2.5 V in every jumper position** — the hardcoded `2.5` in `recorder.py` / `live_server.py` / `render.py` is valid regardless of VCC/VREF selector position.
- **Waveshare's documented default is VCC→5V and VREF→5V** (manual §2.1). That makes our 5V failures a real fault on this board's 5V path, not a misconfiguration: it hard-locked the Pi once, and on 2026-07-23 (VCC→5V, all demo shunts removed) it produced a DC offset of −32% of full scale and ~1500× the normal RMS. Reverted to VCC→3V3.
- **`JMP_AGND`** (AINCOM ↔ AGND): jumpered — required for single-ended reads.
- **Right block top:** VCC selector (`5V/VCC/3V3`) = analog AVDD; VREF selector (`5V/VREF/3V3`). **Both on 3V3** (works). ADS1256 wants AVDD=5 V for best noise floor, but jumpering "to 5 V" **hard-locked the Pi even on a 2.5 A supply** → almost certainly a 3-pin cap shorting 5 V↔3V3. Revisit carefully, Pi OFF, pins verified.
- **Right block bottom:** the demo-sensor block (pot `ADJ`, photoresistor `LDR`). **It IS jumpered** (verified on the board 2026-07-23 — an earlier note here wrongly said "not jumpered"). Observed: the top four shunts sit **vertically** (`VCC→3V3`, `VREF→3V3`, `DAC1→LEDB`, `DAC0→LEDA`); the bottom two sit **horizontally** (`AD1—AD0`, `LDR—ADJ`). We use the **screw terminals** (`AD7…AD0 AGND VCC GND DAC1 DAC0`) for signal.
  - The above is **observed fact, verified visually on the board by Charles** (2026-07-23). Treat it as ground truth; do not re-derive it from the silkscreen legend or from photos.
  - Open question (does **not** cast doubt on the observation): the silkscreen legend would read `AD1—AD0` as bridging the differential pair, yet the front end demonstrably works (235 µV taps, real ground motion recorded). So the header's physical pin-to-net mapping is not what the printed legend implies. Resolve by buzzing out nets with a meter when convenient — it is a mapping question, not a fault.
  - Light sensitivity was tested and is **negative**: lights on vs off gave RMS 1.59 µV in both cases with near-identical spectra (`analysis/lights.png`), so the LDR is not coupling into the signal.


## Decisions & deferred

- **Accelerometer: not for v1.** The geophone is the sensitive weak-motion sensor; a MEMS accel is strong-motion class and adds nothing to detection sensitivity. If ever added (horizontal components / big-local-quake capture), use the **ADXL355** (~25 µg/√Hz, 20-bit — what OpenEEW / the Raspberry Shake strong-motion units use), **not** the ADXL345 (~300 µg/√Hz, consumer-grade, useless here). 6 free ADS1256 channels available. Add-on, not a gap.
- **Ferrules, not tinned ends, in screw terminals** — see the cable note above.
- **5 V AVDD jumper deferred** — currently on 3V3 (works); see jumper cheat-sheet for the lock-up caution before revisiting.
- **miniSEED via `simplemseed`, NOT ObsPy, on the Pi.** ObsPy (scipy + matplotlib) OOM-wedged the 1 GB Pi 2B for an hour during install and is overkill for an acquisition daemon. `simplemseed` is pure-Python (numpy-only), installs in seconds, stays lean. ObsPy-based analysis (helicorder, response) belongs on the Mac, reading the Pi's files. If ObsPy is ever needed on the Pi, add a swapfile first (`CONF_SWAPSIZE=2048`) or it OOMs.
- **miniSEED specifics (v1):** int32 uncompressed (STEIM2 later), 512-byte records chunked at 100 samples, integer sample rate declared via explicit `sampRateFactor`/`sampRateMult` (simplemseed's auto rate-calc is broken). Rate is measured at startup (~56–57 sps, SYNC-limited) and each block is wall-clock anchored → accurate absolute time, ≤3 ms/block cosmetic overlap. Exact 60.000 sps would need ADS1256 RDATAC mode — deferred.
- **Passwordless SSH** from the Mac to `seismo.local` is set up (Claude can drive the Pi directly).


---

# Archive index — older entries, verbatim in `STATUS-ARCHIVE.md`

Newest first. Each is a section header there; the dates are in the headers.

- [📅 ACTIVITY HEATMAP: day x hour, and it is a portrait of PEOPLE (2026-08-15, LIVE)](STATUS-ARCHIVE.md#activity-heatmap-day-x-hour-and-it-is-a-portrait-of-people-2026-08-15-live)
- [🎣 A FADED SECTION IS NOT A BLIND SECTION — measured (2026-08-14)](STATUS-ARCHIVE.md#a-faded-section-is-not-a-blind-section-measured-2026-08-14)
- [🔧 DESPIKER: the bracket tolerance was stricter than the outlier bar (2026-08-14, LIVE)](STATUS-ARCHIVE.md#despiker-the-bracket-tolerance-was-stricter-than-the-outlier-bar-2026-08-14-live)
- [✅ DETECTOR FIXED: band-limited trigger + `hf_lf` classifier (2026-08-14, LIVE)](STATUS-ARCHIVE.md#detector-fixed-band-limited-trigger-hf_lf-classifier-2026-08-14-live)
- [🗑️ LABELLED GROUND TRUTH: the trash-can run, 2026-08-13 20:16–20:19 PDT](STATUS-ARCHIVE.md#labelled-ground-truth-the-trash-can-run-2026-08-13-20162019-pdt)
- [⛔ TELESEISMS ARE STRUCTURALLY IMPOSSIBLE HERE — settled with evidence (2026-08-13)](STATUS-ARCHIVE.md#teleseisms-are-structurally-impossible-here-settled-with-evidence-2026-08-13)
- [✅ PROVISIONAL CALIBRATION ADOPTED: 3.2x low, ~9 V/(m/s) (2026-08-13)](STATUS-ARCHIVE.md#provisional-calibration-adopted-32x-low-9-vms-2026-08-13)
- [🧭 EPOCH TABLE — `analysis/epochs.py` (2026-08-13)](STATUS-ARCHIVE.md#epoch-table-analysisepochspy-2026-08-13)
- [🎯 ABSOLUTE CALIBRATION MEASURED — ~3.6x low, against a station 1.64 km away (2026-08-13)](STATUS-ARCHIVE.md#absolute-calibration-measured-36x-low-against-a-station-164-km-away-2026-08-13)
- [📐 SAMPLING BIAS: the amplitude model is an ALONG-STRIKE model (2026-08-13)](STATUS-ARCHIVE.md#sampling-bias-the-amplitude-model-is-an-along-strike-model-2026-08-13)
- [🌟 M4.1 SAN LEANDRO — biggest signal yet, and it validates the amplitude model (2026-08-13)](STATUS-ARCHIVE.md#m41-san-leandro-biggest-signal-yet-and-it-validates-the-amplitude-model-2026-08-13)
- [🏆 INSTRUMENT-LIMITED FROM 1 TO 28 Hz — and the 20 Hz line is NOT the floor (2026-08-13)](STATUS-ARCHIVE.md#instrument-limited-from-1-to-28-hz-and-the-20-hz-line-is-not-the-floor-2026-08-13)
- [🎯 ARRIVAL PREDICTION: one real bug, and the velocity model is fine (2026-08-12)](STATUS-ARCHIVE.md#arrival-prediction-one-real-bug-and-the-velocity-model-is-fine-2026-08-12)
- [📏 AMPLITUDE MODEL: exclude the pre-epoch event (2026-08-12)](STATUS-ARCHIVE.md#amplitude-model-exclude-the-pre-epoch-event-2026-08-12)
- [✅ DESPIKER v3 — local noise scale, CENTRED window (2026-08-12)](STATUS-ARCHIVE.md#despiker-v3-local-noise-scale-centred-window-2026-08-12)
- [🚫 LAWN EQUIPMENT IS INVISIBLE TO THE STATION — no signature added (2026-08-12)](STATUS-ARCHIVE.md#lawn-equipment-is-invisible-to-the-station-no-signature-added-2026-08-12)
- [🔧 DESPIKER now judges against a rolling MEDIAN (2026-08-12)](STATUS-ARCHIVE.md#despiker-now-judges-against-a-rolling-median-2026-08-12)
- [🖥️ DASHBOARD "gaps" were masked samples, not missing data (2026-08-12)](STATUS-ARCHIVE.md#dashboard-gaps-were-masked-samples-not-missing-data-2026-08-12)
- [🏠 GARAGE INSTALL — the ~20 Hz mount resonance is 4.4x DOWN (2026-08-12)](STATUS-ARCHIVE.md#garage-install-the-20-hz-mount-resonance-is-44x-down-2026-08-12)
- [🔧 ZERO-FRAME FILL FIXED — it was manufacturing unrejectable width-2 spikes (2026-08-12)](STATUS-ARCHIVE.md#zero-frame-fill-fixed-it-was-manufacturing-unrejectable-width-2-spikes-2026-08-12)
- [⛔ SCHED_FIFO does NOT reduce the glitch rate — tested and refuted (2026-08-12)](STATUS-ARCHIVE.md#sched_fifo-does-not-reduce-the-glitch-rate-tested-and-refuted-2026-08-12)
- [🏆 BEST NOISE FLOOR YET — and 1–5 Hz is now at the ELECTRONICS limit (2026-08-12)](STATUS-ARCHIVE.md#best-noise-floor-yet-and-15-hz-is-now-at-the-electronics-limit-2026-08-12)
- [✅ ENCLOSURE CLOSED + 5 V VIA GPIO — the power path is proven (2026-08-12)](STATUS-ARCHIVE.md#enclosure-closed-5-v-via-gpio-the-power-path-is-proven-2026-08-12)
- [✅ ROOT CAUSE: the glitch/stall rate is the 60→100 sps SWITCH, not any hardware (2026-08-12)](STATUS-ARCHIVE.md#root-cause-the-glitchstall-rate-is-the-60100-sps-switch-not-any-hardware-2026-08-12)
- [🔧 DESPIKER threshold 200,000 → 50,000 counts (2026-08-12)](STATUS-ARCHIVE.md#despiker-threshold-200000-50000-counts-2026-08-12)
- [🌟 M2.8 THE GEYSERS DETECTED — and the catalog doublet resolved (2026-08-11)](STATUS-ARCHIVE.md#m28-the-geysers-detected-and-the-catalog-doublet-resolved-2026-08-11)
- [📐 CALIBRATION: split the problem before spending events on it (2026-08-12)](STATUS-ARCHIVE.md#calibration-split-the-problem-before-spending-events-on-it-2026-08-12)
- [✅ REBUILT FRONT END CHECKS OUT ON THE BENCH (2026-08-07)](STATUS-ARCHIVE.md#rebuilt-front-end-checks-out-on-the-bench-2026-08-07)
- [✅ FAULT FIXED 2026-08-03 — it was a STRAY SHIELD STRAND, not a bias resistor](STATUS-ARCHIVE.md#fault-fixed-2026-08-03-it-was-a-stray-shield-strand-not-a-bias-resistor)
- [✅ V1 ELECTRONICS NOISE FLOOR MEASURED (2026-08-03) — and it bounds rev-2](STATUS-ARCHIVE.md#v1-electronics-noise-floor-measured-2026-08-03-and-it-bounds-rev-2)
- [🛑 SHUNT DAMPING — CLOSED, no resistor, not deferred (2026-08-10)](STATUS-ARCHIVE.md#shunt-damping-closed-no-resistor-not-deferred-2026-08-10)
- [⛔ FIRST Pi BASE PRINT WAS SCRAP — and why (2026-08-09)](STATUS-ARCHIVE.md#first-pi-base-print-was-scrap-and-why-2026-08-09)
- [✅ GEOPHONE CASE COMPLETE — printed and assembled (2026-08-08)](STATUS-ARCHIVE.md#geophone-case-complete-printed-and-assembled-2026-08-08)
- [🧰 Pi + front-end CASE — modelled, coupon validated (2026-08-08)](STATUS-ARCHIVE.md#pi-front-end-case-modelled-coupon-validated-2026-08-08)
- [📦 Pi + front-end ENCLOSURE — decisions and parts ordered (2026-08-04)](STATUS-ARCHIVE.md#pi-front-end-enclosure-decisions-and-parts-ordered-2026-08-04)
- [🛰️ FDSN network identity: `SS` is available WITHOUT asking (2026-08-03)](STATUS-ARCHIVE.md#fdsn-network-identity-ss-is-available-without-asking-2026-08-03)
- [🔴 (HISTORICAL — RESOLVED, see above) STATION FAULTED 2026-07-31 16:41 PDT](STATUS-ARCHIVE.md#historical-resolved-see-above-station-faulted-2026-07-31-1641-pdt)
- [✅ COUPLING TEST DONE (2026-07-31 13:40 PDT) — tile→slab changed nothing measurable](STATUS-ARCHIVE.md#coupling-test-done-2026-07-31-1340-pdt-tileslab-changed-nothing-measurable)
- [🌟 M4.2 CLOVERDALE — biggest event yet, plus 4 more the same day (2026-07-29)](STATUS-ARCHIVE.md#m42-cloverdale-biggest-event-yet-plus-4-more-the-same-day-2026-07-29)
- [🚗 Traffic direction — a road patch gives the symmetry-breaker (2026-07-27)](STATUS-ARCHIVE.md#traffic-direction-a-road-patch-gives-the-symmetry-breaker-2026-07-27)
- [🎯 FOUR confirmed earthquakes — and a detector that finds them (2026-07-27)](STATUS-ARCHIVE.md#four-confirmed-earthquakes-and-a-detector-that-finds-them-2026-07-27)
- [🎉 SECOND CONFIRMED EARTHQUAKE — M2.5, The Geysers (2026-07-27)](STATUS-ARCHIVE.md#second-confirmed-earthquake-m25-the-geysers-2026-07-27)
- [🎉 FIRST CONFIRMED EARTHQUAKE — M2.5, 3 km E of St. Helena (2026-07-25)](STATUS-ARCHIVE.md#first-confirmed-earthquake-m25-3-km-e-of-st-helena-2026-07-25)
- [✅ Environmental node LIVE in the garage (2026-07-25)](STATUS-ARCHIVE.md#environmental-node-live-in-the-garage-2026-07-25)
- [✅ 24 h UDP loss probe COMPLETE — sets rev-2 redundancy at N=2 (2026-07-25)](STATUS-ARCHIVE.md#24-h-udp-loss-probe-complete-sets-rev-2-redundancy-at-n2-2026-07-25)
- [📏 Instrument characterization from the M2.5 (2026-07-25)](STATUS-ARCHIVE.md#instrument-characterization-from-the-m25-2026-07-25)
- [✅ SWITCHED TO 100 sps — new epoch (2026-07-25)](STATUS-ARCHIVE.md#switched-to-100-sps-new-epoch-2026-07-25)
- [✅ UDP streaming — Phase-1 step 1 LIVE (2026-07-26)](STATUS-ARCHIVE.md#udp-streaming-phase-1-step-1-live-2026-07-26)
- [🌙 Overnight soak (started 2026-07-26 ~03:30 UTC)](STATUS-ARCHIVE.md#overnight-soak-started-2026-07-26-0330-utc)
- [✅ Galvanic Ethernet isolator INSTALLED and it LOWERED the noise floor (2026-07-23)](STATUS-ARCHIVE.md#galvanic-ethernet-isolator-installed-and-it-lowered-the-noise-floor-2026-07-23)
- [⚠️ NEW EPOCH 2026-07-24 ~02:15 UTC — demo jumpers removed from AD0/AD1](STATUS-ARCHIVE.md#new-epoch-2026-07-24-0215-utc-demo-jumpers-removed-from-ad0ad1)
- [🐛 SOLVED 2026-07-24 — the "faux detection" population was a `peak_uv` bug](STATUS-ARCHIVE.md#solved-2026-07-24-the-faux-detection-population-was-a-peak_uv-bug)
- [🚗 Site ambient is TRAFFIC-limited, not electronics-limited (2026-07-24)](STATUS-ARCHIVE.md#site-ambient-is-traffic-limited-not-electronics-limited-2026-07-24)
- [🚗 Traffic training pipeline started (2026-07-24)](STATUS-ARCHIVE.md#traffic-training-pipeline-started-2026-07-24)
- [Plan (agreed 2026-07-23)](STATUS-ARCHIVE.md#plan-agreed-2026-07-23)
- [Where we are](STATUS-ARCHIVE.md#where-we-are)
- [Milestone map (bring-up order — specification.md §6)](STATUS-ARCHIVE.md#milestone-map-bring-up-order-specificationmd-6)
- [Hardware as-built](STATUS-ARCHIVE.md#hardware-as-built)
- [Software as-built (on the Pi, `~/seismo`)](STATUS-ARCHIVE.md#software-as-built-on-the-pi-seismo)
- [Analog front-end (AS-BUILT + validated 2026-07-19)](STATUS-ARCHIVE.md#analog-front-end-as-built-validated-2026-07-19)
- [Enclosure](STATUS-ARCHIVE.md#enclosure)

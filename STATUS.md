# STATUS — Seismo

_Last updated: 2026-08-27 (UTC)_

**How to read this file:** the *Current system* section is the resume point; below it the
recent entries run newest-first; then the reference sections that are still true; then an
index into [`STATUS-ARCHIVE.md`](STATUS-ARCHIVE.md), where everything before 2026-08-20
lives verbatim. `BACKLOG.md` holds deferred work; `CLAUDE.md` maps the hosts and code.

## 🧭 CURRENT SYSTEM (as of 2026-08-26)

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
measured. 28 catalog-confirmed events, validated range 89 km (M3.8 San Leandro);
biggest M4.2 Cloverdale (07-29). Detection map: `reports/detection-range-map.png`.

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
`trigger_dataset.py` → `trigger_train.py` → push.

**Dashboards.** LAN copy `http://seismo.pi5.mcguinness.ai` (Live, Detections with
p(quake), History, Activity day×hour + weekly, Spectrum, Environment, Catches, Learn,
About). **Public copy https://seismo.mcguinness.ai** on apps02 — same image, fed
outbound-only from pi5 (files every minute, live ring every 3 s), no Detections page,
**nothing at the house reachable from the internet** (the Cloudflare Tunnel is gone).
Every dynamic image reload is double-buffered (the Safari half-drawn-drum fix).

**Pending / on order.** Uputronics GPS HAT for a dedicated Pi 3B+ LAN stratum-1 (seismo
Pi syncs by chrony; no PPS on the 2B). Geophones for the ESP32/ADS1220 field rig
(`doc/field-seismograph.md`: hammer refraction on the lot and the street). FDSN network
code from ISC (placeholder `XX`). Weekly-view weighted median (BACKLOG, ~November).

## Open threads

1. GPS clock host when the HAT arrives (memory + `doc/`); then chrony on seismo.local.
2. Field rig firmware: log triggered windows to flash, tap-the-piezo milestone.
3. Retrain the classifier when the confirmed count grows; CNN at ~100 positives.
4. `seismo_dashboard.py` is 1,028+ lines — split the image/live-data routes out.
5. The 1.05 Hz line.
6. Network code cutover (unit `SEISMO_NETWORK`, pi5 config, epochs row) when ISC answers.

---

# Recent entries (newest first)

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

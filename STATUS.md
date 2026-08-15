# STATUS — Seismo

_Last updated: 2026-08-14 (UTC)_

## 📅 ACTIVITY HEATMAP: day x hour, and it is a portrait of PEOPLE (2026-08-15, LIVE)

Charles: a weekly day-by-hour heatmap of noise levels, to paint a portrait of
environmental activity. `dashboard/activity.py` + `/activity`, built from the
helicorder interval files `heli_build` already writes — `env` per 15 min is a robust
noise level, so the whole grid is a few hundred medians and no miniSEED is decoded
(scan 0.14 s over 1,267 files, render 0.40 s; cached 10 min).

**LOCAL time, not UTC** — the entire point. Indexed by UTC the morning rush lands in
the middle of the night.

What it shows, over the four settled days so far: a **4x swing** between 04:00 and
mid-afternoon, quiet from midnight, lifting at 05:00, loud through the working day,
falling away after dark. Which is also the operational fact — the same earthquake at
4 AM competes with four times less noise, and that is why the overnight detection
threshold is ~M1.4 against the daytime figure.

### ⛔ The first render was a picture of our own hardware, not the neighbourhood

Straight `env` on an absolute µV scale over the last 7 days produced a chart whose
dominant feature was the **2026-08-12 enclosure/siting change** — everything before it
uniformly dark, everything after uniformly light, the diurnal pattern squeezed into two
shades. It looked exactly like "the neighbourhood went silent on Wednesday".

Three fixes, each a smaller lie than the last:

1. **The colour scale is computed from the CURRENT configuration only** (p1–p99 of the
   post-boundary cells), so today's hours get the full ramp instead of two shades.
2. **Pre-boundary cells are drawn FLAT GREY, not on the ramp.** Fading them at 45 %
   was tried first and was worse — a dimmed navy and a mid blue land on the same grey,
   so half the chart became a mid-tone smear that still invited comparison.
3. **The boundary itself is drawn as a staircase**, which is what it geometrically is:
   time runs left-to-right within a row then down, so a change at 08:24 cuts across
   that row at hour 8.

**The weekday view refuses to draw itself.** Collapsing onto Mon–Sun is the better
portrait, but with 3 days in the current epoch the cells are single samples and the
"pattern" is which weekday fell on which side of a hardware change. `/activity` shows
a countdown card instead (needs 14 days; fills itself in ~26 August).

### 🔗 epochs.py is now imported by the dashboard, and NOT duplicated

`analysis/epochs.py` is the one register of configuration changes, and this is the
first consumer outside `analysis/`. It is **copied into the build context by
`deploy.sh`** (`rsync analysis/epochs.py -> seismo-dashboard/`, `COPY` in the
Dockerfile, drift-checked by `deploy.sh status`) rather than forked into `dashboard/`,
because a second epoch table that silently disagrees with the first is worse than no
table at all. `activity.py` degrades to "no marks" if the import fails.

⚠️ `dashboard/seismo_dashboard.py` is now **1,391 lines**, past the 1,000-line
guideline. The chart code went into its own module, but the page/route bodies keep
accreting there. Worth splitting the LEARN/ABOUT prose blocks into a `content.py`
before the next page lands.

## 🎣 A FADED SECTION IS NOT A BLIND SECTION — measured (2026-08-14)

Charles: when a section is faded as local activity, are we blind to any seismic signal
in those seconds, or can it be fished out? Measured with `analysis/cultural_recovery.py`
— the real M2.8 Geysers waveform (44.6 km) superposed, scaled, onto the labelled
trash-can run and onto a quiet control from the same night.

**The fading is cosmetic — nothing is removed from the archive.** The cost is
sensitivity, and it depends entirely on which band you look in:

| band | quiet control | inside the cans | penalty | M units lost |
|---|---|---|---|---|
| **1–8 Hz** | M0.92 | M1.76 | 7.0× | **0.84** |
| **2–5 Hz** | M1.02 | M1.67 | **4.5×** | **0.65** |
| 1–15 Hz | M1.14 | M2.13 | 9.9× | 0.99 |
| 15–30 Hz | M1.33 | M2.33 | 10.0× | 1.00 |

Criterion is SNR 3 on the peak envelope, matching `detection_map.py`. Cultural noise is
HF-dominated, so **the band a quake lives in is the band the episode damages least** —
2–5 Hz costs 0.65 magnitude units against 1.00 broadband. During an episode this is a
less sensitive station, not a deaf one; roughly its own busy-daytime floor.

**The live classifier also survives the episode**, which was not obvious. The cans own
the amplitude so the quake never gets its own trigger — but it adds energy only to the
1–8 Hz denominator, so it drags the composite event's `hf_lf` down:

| | peak ratio | `hf_lf` | label |
|---|---|---|---|
| cans alone | 307 | 1.95 | cultural |
| cans + M2.3 | 319 | 1.49 | cultural |
| **cans + M2.5** | 325 | **1.37** | **QUAKE** |
| cans + M2.8 | 390 | 1.30 | QUAKE |

**Crossover ~M2.4–2.5 at 45 km**: a buried event that size re-labels the episode hiding
it. `peak_ratio` is useless here (307 → 390 for a whole M2.8); `hf_lf` is the channel
that carries the information.

⚠️ **Below the crossover the event stays filed as cultural.** It is in the archive and
recoverable by hand in 1–8 Hz, but nothing flags it — the real cost of the faded columns
is lost *attention*, not lost data.

⚠️ **The template window matters more than anything else in this measurement.** Cut
loose, the template measures the ROOM: hf_lf is 1.22 over the 25 s event, 1.92 over 60 s
including the ambient tail, and 6.69 over pre-event ambient alone. A 60 s template can
never fall below the 1.4 cut no matter how large it is scaled — the first version of
this experiment used one and produced a confident, meaningless "still cultural at M4.3".

**The clean escape is FS7.** NP.1835, 1.64 km away, already used for calibration: real
ground motion appears at both stations, a wheelie bin appears at one. That is a
coincidence test, it does not degrade during an episode, and `refstation.py` already
pulls the data per event.

## 🔧 DESPIKER: the bracket tolerance was stricter than the outlier bar (2026-08-14, LIVE)

Charles spotted an obvious bad-data spike on the drum at ~05:46 UTC. It is real and it
is in the archive: **2026-08-14T05:46:40.56, one sample, −6,062,080 counts** (−59 mV)
against a 324,101 baseline. As 24-bit two's complement that is `0xA37800` — **low byte
zero**, the same one-byte-late SPI read as the other known garbage frames.

It is not in `qc.log` as a spike, a `zero_frame` or a `dropped`. The despiker judged it
and **kept** it. Reproduced offline against the archived samples:

```
ref = 324,101   scale (MAD) = 109.7   bar = 8σ = 878   tolerance = TOL·σ = 439
05:46:40.55     +492    bracket BEFORE  <- 4.5σ, exceeds the 439 tolerance
05:46:40.56     -6,386,181              <- centre, 55,000σ
05:46:40.57     -116    bracket AFTER
```

Run length 1 passes `MAX_RUN`; then the isolation test requires both bracketing samples
to be quiet, and the preceding sample was the noisiest in the 51-sample window — an
ordinary 4.5σ noise sample. "Brackets aren't quiet → not isolated → keep." A 55,000σ
frame survived because its neighbour was 0.5σ too lively.

**Root cause is that `TOL=4.0` was stricter than `NSIGMA=8.0` for no stated reason.**
A bracket between 4σ and 8σ is not an outlier by the despiker's own definition, yet it
vetoed rejection. `MIN_SCALE=100` makes it worse on quiet nights — σ pins near the floor
(109.7 here), tolerance collapses to ~440 counts, and ordinary noise clears it. So the
failure is biased toward the quietest nights, when a spike is most visible on the drum.

**Fix: `TOL` 4.0 → 8.0**, i.e. a bracket disqualifies a run only if it is *itself* an
outlier. `MAX_RUN` is untouched and remains what protects real ground motion.

| | TOL=4 (was) | **TOL=6** | **TOL=8 (deployed)** |
|---|---|---|---|
| 05:46:40 spike | **MISSED** | CAUGHT | **CAUGHT** |
| day 223 held | 6.7/h | 7.6/h | 8.7/h |
| day 224 held | 5.1/h | 6.7/h | 9.0/h |
| day 226 held | 1.2/h | 1.2/h | 2.2/h |
| 1–15 Hz floor | unchanged | unchanged | unchanged (9.59→9.52, 3.85→3.82 µV) |
| 4 confirmed quakes | 0 samples altered | 0 | **0 samples altered** |

8 over 6 because 6 is arbitrary and 8 is the consistency argument; the extra ~2 held
samples/h is 0.003 % of samples and moves no band metric. Cost: a **second** synthetic
case now holds one sample — 18 Hz, 400,000 ct, STEP onset — joining the 12 Hz one
already accepted. Both preserve **100 % of the peak** and both are physically impossible
onsets at 3.7 mV.

Archive scan, days 223–226 (`>100σ`, width-1, neighbours not outliers): **9 survivors in
78 h**. Seven predate the v3 deploy on 08-12 and the current code rejects them on replay;
of the two genuine post-v3 survivors this bracket veto is one, and the other (day 224
00:55, 13,472 ct) fell **below the 8σ bar** in a loud window — not the same bug.

Deployed to `seismo.local` 07:52 UTC, recorder restarted and healthy (backup
`station/rdatac.py.bak-tol4`). Regression row added to `analysis/despiker_v2.py`, which
MISSES at 4.0 and CATCHES at 8.0. ⚠️ **The spike stays in the day-file** — this is a
forward fix only, nothing rewrites the archive, so 05:46:40 will keep appearing on any
drum that renders day 226.

## ✅ DETECTOR FIXED: band-limited trigger + `hf_lf` classifier (2026-08-14, LIVE)

The trash-can run (below) exposed it: the CF was high-passed at 3 Hz and **never
low-passed**, so it integrated to Nyquist — handing the decision to the 15–45 Hz band
where only cultural noise lives. Two changes, in `stalta.py` (station + server):

1. **4-pole Butterworth low-pass at 15 Hz on the CF.** Marginal M2.8 goes 4.0 → 10.7.
2. **`hf_lf` on every event** — `sqrt(E>15Hz / E[1-8Hz])` accumulated over the window,
   from six biquads on the RAW input. Reported, never enforced.

Validated by `analysis/stalta_band.py`, replaying days 223–226 at the **production**
`SEISMO_HP=3.0` — it reproduces the live `events.log` ratios exactly (loudest cultural
256.7 in both), which is what makes the rest of the table trustworthy.

| window | kind | ratio (old→new) | `hf_lf` |
|---|---|---|---|
| M2.8 Geysers 45 km | quake | 4.0 → **10.7** | 0.98 |
| M2.0 Glen Ellen 9.7 km | quake | 168 → 415 | 0.74 |
| M3.2 Geysers ×2 | quake | 71/113 → 296/396 | 0.39 / 0.19 |
| M4.1 San Leandro 88 km | quake | 1384 → 1953 | **0.09** |
| footsteps | cultural | 38 → 87 | **3.26** |
| two cans rolling | cultural | 244 → **307** | 1.95 |
| third can rolling | cultural | 159 → 18 | 5.26 |
| doors closing/locking | cultural | 75 → 118 | 1.97 |

**Band-limiting alone does NOT separate** — rolling cans are genuine 1–15 Hz ground
motion three metres away and still hit 307, above every quake but the two loudest.
`hf_lf` is what separates: quakes **0.09–0.98**, cultural **1.95–5.26**. A cut at
**1.4** splits all nine labelled cases and rejects **80–95 %** of daily triggers
(17.9–37.7/h → 1.4–10.6/h).

⚠️ The margin is only ~2× on n=9, so `CULTURAL_HF_LF` **labels, it does not delete**.
A mislabelled quake still in the log is recoverable; a deleted one is not. The class
most likely to be misfiled is a *very close* quake, which keeps its high frequencies —
the M2.0 at 9.7 km is already the highest-`hf_lf` quake in the set.

Deployed to `seismo.local` 03:40 UTC (backups `stalta.py.bak-nolowpass`,
`recorder.py.bak-prehflf`). **Event counts are not comparable across this line** —
`analysis/epochs.py` gains a `detection` aspect for exactly this.

**Also closed:** `station/recorder.py` and `station/rdatac.py` in the repo were STALE —
the despiker v3 work had been edited in place on the Pi and never synced back. The Pi's
versions are now committed. Deploying the repo copies would have silently reverted it.

### Helicorder now shades local activity (2026-08-14, LIVE)

Charles: a loud row is ambiguous — a door slam and an earthquake look identical on a
drum. The same discriminant runs per pixel column in `heli_build` (`hf` array in each
interval npz) and `heli_render` draws high-frequency-and-loud columns **faded to 50 %
alpha in their own row colour**, underneath the true trace (separate LineCollection at
lower zorder, so a genuine arrival in the same seconds still draws over it at full
strength). Legend explains it.

### How to read a helicorder — as HTML, not baked into the image (2026-08-14, LIVE)

Charles showed the UI to a friend, who asked whether the four trace colours were four
simultaneous data feeds. They are not — they cycle every fourth row so the eye can
follow one line — and no in-image legend was ever going to fix that, because **the image
is where the confusion comes from**. So the explanation is now real HTML text.

- `HELI_HOWTO`, a four-paragraph block under the drum on **/** and **/history**: rows are
  15 min oldest-first, the colours carry no meaning, faded = local (with the reason:
  distance strips >15 Hz), triangles = USGS predicted arrivals.
- A full section in **/learn**, `#how-to-read-the-helicorder`: where the drum layout
  comes from (a real paper drum), UTC vs local, what an earthquake / ordinary noise / a
  door slam each look like, why pitch separates near from far, what the faded halo and
  the solid core each mean, both honest limits (fading is a positive ID not an
  exhaustive one; the core is a band, not the quake), and what the fading costs
  (~0.8 magnitude units, from `analysis/cultural_recovery.py`).
- `_card()` gained `card_id`, and `learn()` slugs each header, so any section is
  deep-linkable. The older "Reading the views on the front page" card now links across
  instead of half-repeating it.

Verified in a browser against a local instance (both pages, plus the anchor jump).

### Faded halo + full-colour seismic core (2026-08-14, LIVE)

Charles: "I'm looking for a UI where the seismic signal is in full colour, but the
extent that the environmental exceeds that is painted at a=.5, so you can see the true
seismic signal THROUGH the environmental noise." Doable, and now shipped — the data was
already being computed.

`heli_build._band_energies` filters a 1–8 Hz copy of the window to get `E_lo` for the
`hf` ratio, and now also returns that WAVEFORM. Each interval stores `lo_mins`/`lo_maxs`
— the same min/max envelope as `mins`/`maxs`, on the same counts scale — so the renderer
nests one inside the other: on a cultural column it draws the **total excursion faded**
and the **1–8 Hz core at full colour on top**. No extra filter pass, ~8 KB per interval.

What you see on the trash-can run: a pale halo with a solid dark trace running through
it, and the core is *thin* — which is the honest picture, since the cans put 4.2 µV into
1–8 Hz against 23.5 in 15–30. During the M4.1 the core would fill the whole excursion.

⚠️ **The core is not "the earthquake"** — it is the motion in the band a quake would
occupy, noise included. It is a band decomposition, not a separation.

Non-cultural columns are unchanged (single full-colour trace). Older intervals lack the
arrays and fall back to fading the whole column; `_is_complete` now requires `lo_mins`,
so the live 4 h window self-heals exactly as it did for `hf`. Legend swatch is a faded
thick bar with a solid thin one through it — a side-by-side pair read as two separate
things rather than one nested in the other. `analysis/heli_core_{after,zoom}.png`.

⚠️ **Grey was tried first and replaced 2026-08-14** — Charles: "the grey is distracting."
Recolouring OVERWROTE the trace, so a shaded burst lost its row colour and broke the
drum's one reliable visual rule (row colour tells you which row you are reading).
Fading annotates without taking anything away, and keeps the four-colour row cycle
intact through a loud minute. `CULTURAL_COLOR` is gone; `CULTURAL_ALPHA = 0.5` replaces
it, and the legend swatch is now a full-strength/faded PAIR because the thing being
explained is opacity and a lone faded stub gives the eye nothing to compare against.
Before/after over the same 4 h (including the trash-can run):
`analysis/heli_alpha_{before,after}.png`.

Both directions verified on real data: the labelled trash-can run is the most heavily
shaded interval of the night (161 columns); the **M4.1 is 7.2× its row's median
excursion — loud enough to pass the loudness test — and 0 of its 110 columns shade**,
because its `hf` is 0.10.

Only columns that are *both* high-frequency *and* loud relative to their own row shade:
the noise floor is itself HF-dominated (median `hf` 1.7–3.8 on a quiet night), so
shading on ratio alone would tint the whole drum. `_is_complete` now also requires the
`hf` array, so the live 4 h window self-heals; older intervals render unshaded, which
is honest — they genuinely do not carry the ratio.

USGS magnitude labels moved to the **left** of their caret. The caret marks predicted
arrival, so the label was previously drawn exactly where the burst lands and got
overwritten; the lead-in is quiet by construction. Flips right near the left edge.

## 🗑️ LABELLED GROUND TRUTH: the trash-can run, 2026-08-13 20:16–20:19 PDT

Charles narrated eight steps; **all eight resolve individually** in the record
(03:16:10–03:19:11 UTC day 226). `analysis/2026-08-13-trashcans{,-zoom}.png`, rows
appended to `analysis/annotations.csv`. Peak envelope during the run: **292 µV, 43×
the 6.4 µV pre-event floor** (1–45 Hz).

| PDT | narrated step | signature | peak µV |
|---|---|---|---|
| 20:16:12–20 | 1–2 house door → garage → side door | 12 impulses, 0.57 s apart = **105 steps/min** | 85 |
| 20:16:33.6 | side door shuts | impulse, f_cent 24 Hz | 104 |
| 20:16:41–48 | 3 walk to street | pulse train | 121 |
| 20:16:52–20:17:38 | 4 **two cans wheeled in** | 46 s broadband 5–45 Hz wall | **292** |
| 20:17:38–20:18:11 | 5 walk back out | near-floor, empty-handed | — |
| 20:18:11–28 | 6 **third (small) can** | 17 s, same texture, weaker | 216 |
| 20:18:35–52 | 7 re-enter, close+lock side door | 3 impulses; 20:18:47 is the run's biggest | **280** |
| 20:19:08.9 | 8 house door closed | impulse, end of episode | 82 |

### The useful result: cultural noise is HIGH-frequency, quakes are LOW

Band RMS (µV), same window lengths:

| source | 1–8 Hz | 8–15 | 15–30 | 30–45 | **HF/LF** |
|---|---|---|---|---|---|
| M4.1 San Leandro, 88 km | 89.6 | 17.3 | 5.0 | 3.0 | **0.06** |
| M2.8 Geysers, 45 km | 25.4 | 19.9 | 15.2 | 19.4 | **0.97** |
| door slam, 3 m | 3.9 | 35.5 | 14.8 | 6.5 | **4.12** |
| cans rolling, ~3 m | 4.2 | 9.7 | 23.5 | 23.5 | **7.84** |
| footsteps | 6.2 | 7.7 | 6.4 | 6.4 | 1.45 |

Path attenuation low-passes a real quake; a source three metres away keeps its high
frequencies. **A `>15 Hz / 1–8 Hz` ratio separates rolling cans from the M4.1 by 130×**
and from the M2.8 by 8×. Footsteps (1.45) are the one ambiguous class, and they are
also the weakest.

### ⛔ And the detector fired eight times on it

`events.log` for this run: peak_ratio **256.7, 182.5, 164.2, 76.3**, 31.7, 12.4, 11.1,
9.6. The **confirmed M2.8 reached 3.7.** The STA/LTA is amplitude-only, so a man with a
wheelie bin outranks a real earthquake by ~70×. In the 1–15 Hz band the cans peak at
59 µV against the M4.1's 503 and the M2.8's 159 — i.e. **just band-limiting the trigger
to 1–15 Hz already inverts the ranking.** That is the fix to make before touching the
threshold, and it supersedes "review the STA/LTA threshold" in the backlog.

## ⛔ TELESEISMS ARE STRUCTURALLY IMPOSSIBLE HERE — settled with evidence (2026-08-13)

M5.5, 69 km SSW of Chirilagua, El Salvador, 2026-08-13 00:30:04 UTC, depth 56.8 km.
**4,438 km / 39.9°**, teleseismic P predicted 00:37:32Z (iasp91).

Not detected — and neither we nor **BK.HOPS**, a real broadband 60 km north, shows
anything in the band we can hear (0.7–2 Hz: P window quieter than pre-event at both).
So it is not an instrument-quality problem. HOPS DID record it, but only here:

| band (Hz) | HOPS pre-event | P window | surface waves |
|---|---|---|---|
| **0.02–0.05** | 2.1 | **6.6** | **36.5 nm/s** |
| **0.05–0.1** | 9.6 | **17.6** | **40.3** |
| 0.1–0.3 | 339 | 338 | 329 (microseism swamps) |
| 0.3–1.0 | 190 | 172 | 197 |
| 0.7–2.0 | 35 | 31 | 36 |

The whole signal is 20–50 s period surface waves. Nothing survives above 0.1 Hz at
4,400 km — path attenuation removes it.

**Below its corner a geophone falls as f².** At 0.03 Hz that is `(0.03/4.5)² = 4.4e-5`
— **~22,000× down, −87 dB**. Those 36 nm/s would appear as 0.0016 nm/s at our output
against a ~50 nm/s floor: short by ~30,000×. **No siting, electronics or averaging
changes this.** It is the instrument's defining trade, not a defect.

**Answer for next time a headline quake lands:** if it is more than ~1,000 km away we
will not see it, however large, because the surviving energy is below 0.1 Hz. What we
DO see is local — the M4.1 at 88 km was 93× baseline. Do not spend time checking
distant events; check the catalogue inside ~150 km.

## ✅ PROVISIONAL CALIBRATION ADOPTED: 3.2x low, ~9 V/(m/s) (2026-08-13)

Charles: the superposition still calibrates (both stations feel the same ground, so the
RATIO is valid however many quakes caused it — correct, and I had wrongly excluded it),
and one M4.1 is enough for a provisional number. Both right.

| anchor | ratio |
|---|---|
| M2.8 Geysers | 3.26× |
| M3.2 Geysers | 3.15× |
| M2.99+M2.82 San Leandro (doublet) | 2.99× |
| M4.1 San Leandro | 4.46× |

**n=4, median 3.21×, spread 2.99–4.46, all in one amplitude epoch.**
`PROVISIONAL_FACTOR = 3.20`, `EFFECTIVE_SENS = 9.0 V/(m/s)`. **1 µV = ~111 nm/s**, not
35. Adopted rather than kept in reserve: the nominal 28.8 is measurably wrong by 3×, so
using it is the less accurate choice.

Uncertainty is site response, not statistics — 1.64 km apart, ~2× band differences are
ordinary. Treat as "3×, maybe 2.5–4.5". It still does not say WHERE the loss is; the
bench injection remains the only thing that separates a deaf element from a lossy front
end, and now it knows what answer to expect.

### ⛔ "What can we see that FS7 cannot?" — nothing, honestly

| band | FS7 | OAKMT (×3.2) |
|---|---|---|
| 0.5–2 Hz | 0.342 | 0.058 µm/s |
| 2–5 Hz | 0.126 | 0.053 |
| **5–15 Hz** | **0.088** | 0.106 |
| **15–30 Hz** | **0.110** | 0.168 |

The apparent win below 5 Hz is an ARTIFACT: the geophone is 5× down at 2 Hz and 20× at
1 Hz, so applying only the flat-band correction makes it look quiet exactly where it is
deaf. Corrected for roll-off, 0.058 becomes 0.3–1.2 µm/s — comparable or worse.

**Above 5 Hz, where the comparison is fair, FS7 beats us by 1.2–1.5×.** It is a
professional instrument 1.64 km away. What this station offers is continuous ownership
of one specific place, not better hardware.

⚠️ `REF_MIN_RMS` cut 0.5 → 0.12 µm/s: the old guard was set from a single window and
assumed FS7 was far noisier than it is (it reaches 0.086 µm/s on a quiet night).

## 🧭 EPOCH TABLE — `analysis/epochs.py` (2026-08-13)

Charles: "we have to be careful about any data that precedes the current placement and
hardware." Correct, and it had already cost three wrong answers in two days:

- The M2.5 St Helena sat in the amplitude `CALIBRATION` as a 5.6× outlier until someone
  noticed it predated the 60 → 100 sps switch by twelve hours.
- The 2026-08-03 "V1 electronics floor" was used to conclude *siting is closed, we are
  measuring our own amplifier* — and published to the About page — when three changes
  had landed after it was measured.
- The ~20 Hz table implied three configurations when there were two.

`analysis/epochs.py` now holds every boundary with a tag for WHAT it invalidates —
`amplitude`, `noise`, `timing`, `glitch` — so a comparison is blocked only when it
matters. Approximate times (STATUS recorded a date but no clock) are flagged, and a
comparison straddling one is unsafe rather than merely suspect.

Run against today's work it reproduces both failures and clears the good case:

- the five amplitude anchors are **all in one epoch** — the calibration set is valid;
- the V1 electronics floor is separated from now by **1 amplitude and 4 noise
  boundaries**, which is exactly why reading below it was impossible.

`refstation.py --all` uses it: it computes the calibration factor across anchors and
**refuses to average** across an amplitude boundary, printing them separately instead.
Current output — 3 anchors, one epoch, **mean 3.63× / median 3.26× low, implied
8.82 V/(m/s)** against 28.8 nominal.

⚠️ The table is only as good as its dates. Add a row the same day a change is made;
a boundary nobody recorded is worse than no table, because the checks will pass.

## 🎯 ABSOLUTE CALIBRATION MEASURED — ~3.6x low, against a station 1.64 km away (2026-08-13)

Charles noticed the USGS event page lists PGA/PGV per contributing station, and one of
them is **NP.1835 "Santa Rosa Fire Station 7"** — a USGS National Strong-Motion Project
accelerometer **1.64 km from OAKMT**, with continuous waveforms and full response served
by NCEDC. That is a better reference than this project could have hoped for: same basin,
same events, no dependence on catalogue magnitudes.

`analysis/refstation.py` removes its response to velocity, band-passes both stations to
**5–15 Hz** — safely above the 4.5 Hz corner, where 28.8 V/(m/s) is flat and no response
model is needed on our side — and takes the ratio.

| event | reference RMS | OAKMT (nominal) | ratio | implied V/(m/s) |
|---|---|---|---|---|
| M4.1 San Leandro | 6.09 µm/s | 1.36 | **4.46×** | 6.45 |
| M3.2 Geysers | 2.20 | 0.70 | **3.15×** | 9.15 |
| M2.8 Geysers | 2.16 | 0.66 | **3.26×** | 8.82 |
| ~~M2.0 Glen Ellen~~ | 0.14 | 0.16 | ~~0.88×~~ | REJECTED |

**OAKMT reads ~3.6× low; implied sensitivity ~8 V/(m/s) against 28.8 nominal.**

- **This supersedes the "7.5×-low" figure**, which came from magnitude inversion in a
  band straddling the corner. Measured properly above the corner against a real
  reference, the shortfall is ~3.6×, not 7.5×.
- **Glen Ellen rejected on principle, not convenience:** 0.14 µm/s is below what a
  strong-motion accelerometer resolves, so the reference was measuring itself. It is
  also the event where 1.64 km of separation matters most. `REF_MIN_RMS` now rejects
  any window where the reference is under 0.5 µm/s RMS.
- **What it does NOT tell us:** whether the loss is a deaf element or a lossy front end.
  Only the bench injection separates those, and it is still the top open item.
- **Site response is the main uncertainty.** 1.64 km is close but not co-sited; at
  5–15 Hz local conditions can differ ~2× on their own. Three events is enough for a
  factor, not for a coefficient — more anchors will tighten it, and the method is now a
  one-line script per event.

## 📐 SAMPLING BIAS: the amplitude model is an ALONG-STRIKE model (2026-08-13)

Charles asked whether being on the Hayward–Rodgers Creek system with San Leandro
affects transmission, then made the sharper point: the data will be dominated by quakes
on that fault family. Measured over the USGS catalogue, M≥1.5 within 100 km, two years
(n=3268):

| angle from strike (325/145) | events |
|---|---|
| 0–15° | 1862 |
| 15–30° | 1196 |
| 30–45° | 82 |
| 45–60° | 50 |
| 60–75° | 32 |
| 75–90° | 46 |

**94 % within 30° of strike, against 33 % if azimuth were uniform.** The Geysers
geothermal field with Cobb and Anderson Springs supplies ~1980 of them up the NNW arm;
San Ramon adds 319 down the SSE arm. This will not improve with time — the seismicity
is geometrically constrained.

- **Azimuth is a THIRD axis of extrapolation** beside magnitude (the M1.2) and distance
  (Byron). The single off-strike anchor, Sebastopol at 76°, came in at **0.51×** — the
  model OVER-predicted by 2×, the direction that produces false "likely" marks.
- **No correction applied**: one point cannot justify one, and today already produced
  two retractions from over-reading thin data. Instead every cached event now records
  `az_deg` and `off_strike_deg`, so the question becomes answerable as anchors
  accumulate. Off-strike events deserve suspicion meanwhile.
- **Fault-zone guided waves are NOT evidenced.** The M4.1 at 87.7 km, 7° off strike,
  landed at 1.02× a model fitted mostly on the NNW arm — no along-strike enhancement.
  If the azimuthal pattern is real at all, ordinary strike-slip radiation pattern is a
  simpler explanation than a waveguide.
- Harmless in practice for now: the model is fitted on along-strike events and used
  mostly to predict along-strike events, so any azimuthal term is already absorbed for
  the geometry that dominates.

## 🌟 M4.1 SAN LEANDRO — biggest signal yet, and it validates the amplitude model (2026-08-13)

USGS M4.1, 15:30:04 UTC, 87.7 km hypocentral. `analysis/2026-08-13-san-leandro-m4.1.png`.

| | |
|---|---|
| peak (2–15 Hz, 0.5 s) | **504 µV = 93× baseline** |
| P onset | **+16.0 s** (predicted +17.2, Vp 5.19) |
| shaking duration | 66 s to ambient |

- **Travel-time relation holds to 1.2 s at 87.7 km**, nearly double the 45.7 km it was
  calibrated over.
- **Amplitude model predicted 493.9 µV against 504 observed — 1.02×.** Adding it as a
  sixth anchor barely moves the fit (B 1.58 → 1.58, C 1.67 → 1.66) and leaves the worst
  residual at 1.95×. That is the strongest evidence yet that the model is sound, and it
  doubles the fitted distance range to 9.7–87.7 km.
- `CAL_MAX_KM` 60 → **90**, the measured limit of validity.

### ⛔ RETRACTED: the Byron "detection" was noise

Earlier the same day an M2.0 at 105 km (Byron) was called a detection at 46.3 µV, and
used to argue the fit under-predicts at range — which is why `CAL_MAX_KM` had just been
cut to 60. The M4.1 kills that:

- The model is **1.02× correct at 87.7 km**, so at 105 km an M2.0 really should give
  ~3 µV. Byron would require the model to be **16× wrong at 105 km while 2 % right at
  88 km**.
- The Byron burst was only **2.0× the pre-event MAXIMUM** in a busy 08:00 local
  background, and the half-second alignment with the predicted S was coincidence.
- Row left commented in `CALIBRATION` so it is not re-added.

**Same failure mode as the "31 Hz lawn line":** a feature picked out of noisy data
because it appeared where it was expected. Timing agreement alone is not detection when
the amplitude disagrees with a validated model by an order of magnitude.

## 🏆 INSTRUMENT-LIMITED FROM 1 TO 28 Hz — and the 20 Hz line is NOT the floor (2026-08-13)

Overnight, 600 s to 03:53 UTC, garage on cement.

| band (µV) | overnight | garage daytime | V1 elec floor |
|---|---|---|---|
| 0.02–0.12 | 0.32 | 0.27 | — |
| **1–5** | **0.54** | 0.75 | — |
| 1–15 | **1.50** | 3.47 | 1.18 |
| 10–15 | 1.06 | 2.83 | — |
| **15–28** | **1.08** | 1.84 | **1.08** |
| 19–21 | 0.32 | 0.61 | — |

⚠️ **RETRACTED the same night.** This entry originally decomposed the floor against
the 2026-08-03 electronics measurement (1.18 µV over 1–15 Hz, 1.08 over 15–28) and
concluded "the site contributes 0.02 µV, siting is closed, we are measuring our own
amplifier." Two hours later, at 02:00 PDT, the station read **0.80 µV over 1–15 Hz and
0.51 over 15–28** — 32 % and 53 % BELOW that electronics floor.

Reading below a floor measured with the sensor DISCONNECTED is impossible unless the
electronics themselves changed. **The 2026-08-03 electronics floor is obsolete** — the
front-end rebuild (08-07), the Mean Well supply replacing micro-USB, and the move off
Wi-Fi all landed after it, and any of them could be responsible.

| band | 03:53 UTC | 09:04 UTC (02:00 PDT) | elec floor 08-03 |
|---|---|---|---|
| 1–5 | 0.54 | **0.52** | — |
| 1–15 | 1.50 | **0.80** | 1.18 |
| 10–15 | 1.06 | **0.35** | — |
| 15–28 | 1.08 | **0.51** | 1.08 |
| 19–21 | 0.32 | **0.15** | — |

**So we do NOT know how much headroom remains in siting.** That claim required a
current electronics floor and there isn't one. What is certain: the deep-night floor is
the best ever recorded, and **re-measuring the electronics floor is now a prerequisite
for interpreting any of these numbers** — one more reason the bench injection is the
top open item.

**Lesson:** an "instrument floor" is only a floor until the instrument changes. Three
things changed after 08-03 and the reference was never re-taken.

Detection at The Geysers overnight: **~M1.4 marginal, ~M1.65 trigger** (vs M2.3/M2.6
before 2026-08-12).

### ⛔ The ~20 Hz resonance is NOT the plastic tile, and NOT the floor

Charles suspected the move from plastic floor tile to cement killed it. It did not.
High-resolution spectra (0.012 Hz bins):

⚠️ Two corrections to the first version of this entry. The tile hypothesis was NOT
newly ruled out here — the 07-31 coupling test already recorded that the pair survived
tile→slab at the same frequencies. And there has never been a 3-point-case-on-tile
configuration: the geophone left the tile on 07-31, and the printed case arrived 08-08.
The two changes were sequential, never a controlled A/B.

There are only ever TWO configuration changes in the whole archive: the floor
(tile → garage floor, 07-31) and the mount (flat/cup → printed 3-point case, 08-08).
"Garage slab" and "garage cement" are the same surface — the garage floor — so the last
two rows are the SAME configuration measured twice, three weeks and a relocation apart.
That is a reproducibility check, not a third data point.

| window | mount | surface | mode 1 | mode 2 | f₂/f₁ |
|---|---|---|---|---|---|
| 07-26 | pre-case (flat / cup) | **plastic tile** | 19.995 | 40.894 | 2.045 |
| 08-11 | printed 3-point case | garage floor | 19.983 | 41.016 | 2.053 |
| now | printed 3-point case | garage floor (moved) | 19.983 | 40.906 | 2.047 |

- **Constant to 0.06 % across BOTH the floor change and the mount change**, and
  reproducible to 0.000 Hz across a relocation on the same floor.
  Charles proposed the flat bottom → 3-point contact as the cause; it is not. Changing
  contact geometry changes coupling stiffness and changing the floor changes what it
  couples to; neither moved the frequency. The companion mode tracks at a fixed 2.05x
  throughout — NOT 2.000x, so it is not harmonic distortion either.
- **It travels with the ELEMENT.** Leading suspect: a parasitic transverse/rocking mode
  of the moving mass inside the geophone, which is a property of its own suspension and
  independent of what it sits on.
- **Harmless:** 19.98 Hz is above the 1–15 Hz working band and sits at 0.32 µV overnight,
  below the electronics floor.
- **Test to settle it**, next time the element is out of the case: tap it on foam at
  several tilt angles. A transverse mode's coupling into the vertical output varies
  strongly with tilt while 4.5 Hz does not; if the frequency also holds off the floor
  entirely, that is conclusive.
  Related: [[one-hz-instrumental-line]], [[coupling-test-negative]].

## 🎯 ARRIVAL PREDICTION: one real bug, and the velocity model is fine (2026-08-12)

Charles: "I feel like the prediction of arrival logic is off." Two separate things.

**REAL BUG.** `eventcheck.py` documents the measured relation as
`onset = dist/5.19 + 0.30 s` and then computed `tP = hypo / VP`, **dropping the
intercept**. Every P marker was drawn 0.30 s EARLY, so every arrival looked slightly
late on every plot ever produced. Fixed; `T0_INTERCEPT` is now named and applied.

**THE VELOCITY MODEL IS NOT THE PROBLEM.** STA/LTA onset picks against origin times:

| event | hypo km | residual | STA/LTA |
|---|---|---|---|
| M2.0 Glen Ellen | 9.7 | **+0.05** | 753 |
| M2.8 Geysers | 44.6 | +0.38 | 12.5 |
| M3.2 #1 | 43.4 | +0.50 | 17.2 |
| M3.2 #2 | 43.3 | +1.16 | 26.9 |
| M2.3 Sebastopol | 22.5 | +1.38 | 10.9 |

All positive, and the size tracks **signal quality, not distance**. The cleanest event
(SNR 753) lands at +0.05 s; the weakest is worst. That is STA/LTA's late-picking bias
— the ratio needs energy to accumulate. M3.2 #2 is extra-late because it sits inside
#1's coda, which inflates its LTA.

⚠️ **Do not use ARRIVAL times as origin times.** `usgs_events.__main__` prints
`e['arrival']`; feeding those to the picker as origins produced −8 s residuals and a
brief panic that the velocity model was broken.

## 📏 AMPLITUDE MODEL: exclude the pre-epoch event (2026-08-12)

Adding the M2.3 Sebastopol (22.5 km, 34.7 µV, detected at 5.3× baseline in a busy
midday background) exposed the M2.5 St Helena as a **5.6x outlier** — and physically
incoherent with the rest: an M2.5 at 18.4 km cannot read **8x** an M2.0 at 9.7 km.

It was recorded **2026-07-25 11:31 UTC, before the switch to 100 sps that evening at
23:45 UTC** — a different acquisition epoch, so not comparable. Excluded (row left
commented in `CALIBRATION` so nobody re-adds it).

| fit | B | worst residual |
|---|---|---|
| 2 events | 4.18 | predicted 5904 µV where 171 was observed (34x) |
| 6 events incl. pre-epoch | 2.01 | 5.6x |
| **5 same-epoch events** | **1.58** | **1.95x** |

B=1.58 is close to plain geometric spreading. **This is the epoch discipline that
`signatures.json` already preaches, applied to amplitudes.**

## ✅ DESPIKER v3 — local noise scale, CENTRED window (2026-08-12)

Third design in one day. The first two shipped and both were wrong; this one was
validated before deploying, and `analysis/despiker_v2.py` holds the exact class plus
the harness that justifies it.

| design | verdict |
|---|---|
| fixed `jump`, "does the NEXT sample return?" | misses every 2–3 sample burst → false EVENT at 19:37:30, ratio 25.7 |
| fixed `jump` lowered to 10,000 | held 3.2 % of ALL samples, 1–5 Hz 1.18 → 3.96 µV, ate 188 samples of the M2.8 |
| median reference, TRAILING window | held 8–13 samples inside synthetic 5/12 Hz events, −21 % peak |
| **local scale, CENTRED window** | **deployed** |

**The discriminator is the local noise scale**, so during real motion the bar rises
with the signal and the rule stops firing — which a fixed threshold can never do.

**The trap that cost two attempts: the scale window must be CENTRED, not trailing.**
A trailing window is blind at event onset, exactly where a quake most resembles a
glitch. Both failures were "validated" offline with a centred window and then shipped
with a trailing one — the same class of error as validating a different algorithm than
you deploy.

Deployed parameters: `NSIGMA=8`, `MAX_RUN=3`, `HALF=25`, `TOL=4`, `MIN_SCALE=100 ct`.
Physics behind MAX_RUN: the 4.5 Hz element plus the ADS1256's ~25 Hz output bandwidth
make a 10–30 ms depart-and-return impossible for ground motion. A quake rings.

**Validation** (`python analysis/despiker_v2.py`):

- **39/40 synthetic events** (2–18 Hz × 2,000–400,000 counts × sharp/ramped onset,
  injected into 60 s of real ambient): **0 held, ≥95 % peak preserved**.
- The 40th — 12 Hz, 400,000 ct, STEP onset — holds **1 sample and preserves 100 % of
  the peak**. A 3.7 mV event with an impossible onset. Accepted knowingly.
- **Both known artifacts caught**, including the width-2 pair at 16:39:01 that no
  previous version could reject at any threshold.
- **0 samples altered inside all four confirmed earthquakes** (M2.8 @44.6 km,
  M2.0 @9.7 km, two M3.2 @43 km).
- Day 223: 6.7 held/h, 1–15 Hz **9.59 → 9.52 µV**, 1–5 Hz unchanged at 1.18.
  Day 224: 6.2 held/h, 1–15 Hz 4.02 → 4.00, 1–5 Hz unchanged at 0.68.

**Costs, both accepted:**
- **0.25 s latency** (was 10 ms). Free here: block times come from the sample INDEX
  via ClockAnchor, not from wall clock at emission.
- **26 samples lost per restart** while the window warms up. Timing self-corrects,
  because ClockAnchor hard-anchors at the first block boundary before that block's
  start time is computed.

⚠️ `flush()` had a real bug found by the harness: it re-emitted `half`+1 already-judged
samples into the final block at shutdown. It now returns only the samples after the
last centre. `recorder.py` loops over the list instead of appending one value.

Backups on the Pi: `rdatac.py.bak-v2median`, `recorder.py.bak-v2flush`.

## 🚫 LAWN EQUIPMENT IS INVISIBLE TO THE STATION — no signature added (2026-08-12)

Lawn service worked the property 17:42–~18:10 UTC, a rare labelled cultural-noise
window. Median per-10 s band RMS, before (17:30–17:42) vs during (17:45–18:05):

| band (Hz) | before | during | ratio |
|---|---|---|---|
| 0.5–2 | 0.49 | 0.48 | 0.99 |
| 2–5 | 0.68 | 0.64 | 0.94 |
| 5–15 | 3.64 | 3.63 | 1.00 |
| 15–28 | 1.74 | 1.91 | 1.10 |
| 28–45 | 1.74 | 1.35 | **0.77** |

**Nothing in the working band moved.** A Geysers event arriving mid-mow would be as
detectable as at any other time. Operationally this is the good outcome.

**A "31 Hz line" was claimed and then withdrawn.** A Welch ratio at nperseg=2048 showed
~2.5–2.7x at 31.0/31.5/35.3/43.9/49.2 Hz, and it was nearly added to
`dashboard/signatures.json`. Scored the way `sources.py` actually scores (30 s windows,
nperseg=512, band 30–32.5, shoulder 1.5–4.0):

| window | n | ASD med | peak/shoulder med | max |
|---|---|---|---|---|
| lawn | 40 | 0.454 | 1.34 | 2.17 |
| control: just before | 44 | 0.339 | 1.41 | 2.24 |
| control: quiet mid-morning | 80 | 0.377 | 1.44 | 2.62 |
| **control: overnight** | 120 | **0.779** | 1.54 | **4.08** |

Peak/shoulder of 1.34 is not a line (the 20 Hz signature demands 4.0), the CONTROLS are
stronger than the lawn window, and no threshold separates them. The 2.68x was a
**multiple-comparisons artifact** — the largest of ~1000 bin ratios, which is ~2.5x from
noise alone, reported as if it were a finding. The band table in the same output already
said otherwise (28–45 Hz went DOWN).

- **Rule going forward: score a candidate signature with `sources.py`'s own parameters
  and against CONTROLS before it goes in the file.** A spectral ratio between two
  windows is a hypothesis generator, not evidence.
- For a real lawn signature: equipment much closer, ≥2 separate days (the file's own
  `provisional` rule), and ideally the anti-alias RC fitted first so >50 Hz content is
  not folding back into the band being examined.

## 🔧 DESPIKER now judges against a rolling MEDIAN (2026-08-12)

A 64 mV artifact at 16:39:01 UTC survived the despiker at jump=50,000:

```
16:39:01.45      322,800   normal
16:39:01.46      263,404   PARTIALLY corrupted -- 59,396 counts off baseline
16:39:01.47   -6,586,368   -64 mV
16:39:01.48      323,101   normal
```

Judging `.47` used `prev = .46`, so `d_after = |323,101 - 263,404| = 59,697` — over the
50,000 threshold, the "returns to baseline" test failed, and the spike was KEPT.
**One corrupted sample poisoned the reference used to judge the next.**

Fix: the isolation test now compares against the **median of the last 5 validated
samples** (`Despiker._hist`), not the single previous one. Same test, same threshold,
robust reference. Re-run of `analysis/despike_sweep.py` on day 223:

| jump | held/h NEW | held/h old | 1–15 Hz | 1–5 Hz | holds in the M2.8 |
|---|---|---|---|---|---|
| 200,000 | 5.9 | 0.0 | 9.59 | 1.18 | none |
| **50,000 (live)** | **83.4** | 58.4 | **9.56** | 1.18 | **none** |
| 20,000 | 986 | 1207 | 9.59 | 1.25 | 3 |

Strictly better at the deployed threshold: 44 % more artifacts caught, 1–15 Hz floor
slightly *lower*, 1–5 Hz unchanged, earthquake untouched. The 5.9/h it catches at
200,000 (where the old logic caught none) are the poisoned-reference cases.

- `_hist` is a `deque(maxlen=5)` of EMITTED samples; `prev` is retained because
  `recorder.py` fills zero-frames from it.
- Patched 2026-08-12 16:55 UTC; backup `station/rdatac.py.bak-prevref`.
- **Below 20,000 still degrades** exactly as before. 50,000 remains the floor.

## 🖥️ DASHBOARD "gaps" were masked samples, not missing data (2026-08-12)

The pi5 drum showed ~1-pixel dropouts that looked like outages. The archive was
continuous through every one of them.

Cause: `server/store.py` called `st.merge(method=1)` with **no `fill_value`**, which
returns a MASKED array at every gap — and this archive has a **20–80 ms gap at EVERY
10 s block boundary**, because the recorder cuts a block on each dropped sample
(~100/hour). Those masked samples reached the browser and each one killed a pixel.

- Fix: `_bridge_short_gaps()` interpolates gaps **shorter than 1 s** and leaves longer
  ones masked; the JSON now serializes still-masked samples as **null** rather than
  dropping or zeroing them.
- Blanket `fill_value="interpolate"` was rejected: it would draw a straight line across
  a REAL outage, e.g. the 265 s the station was unplugged for the garage move.
- ⚠️ **Every analysis script must `merge(..., fill_value=...)` or handle masks.** This
  bit twice in one day — the dashboard, and an interactive analysis that silently read
  only the first contiguous chunk. See [[analysis-window-traps]].

## 🏠 GARAGE INSTALL — the ~20 Hz mount resonance is 4.4x DOWN (2026-08-12)

Installed 15:24 UTC (08:24 PDT), settled 300 s window to 16:01 UTC.

| band (µV) | **garage settled** | indoor floor 08-12 | garage historical |
|---|---|---|---|
| 0.02–0.12 | **0.27** | 0.36 | 0.85 |
| 1–5 | 0.75 | 0.67 | — |
| 1–15 | 3.47 | 2.89 | 2.74 |
| 10–15 | 2.83 | 2.98 | — |
| 15–28 | **1.84** | 4.22 | 5.69 |
| 19–21 | **0.61** | 2.67 | — |

- **19–21 Hz down 4.4x, 15–28 Hz down 3.1x vs historical garage.** This is the ~20 Hz
  line STATUS attributes to a MOUNT RESONANCE — the one that survived tile→slab, the
  room change and the front-end rebuild. First thing that has ever moved it. It held
  through settling, so it is not a first-minutes artifact.
- Sub-Hz 0.27 µV is also the best ever, 3.1x below historical garage.
- 1–5 Hz 0.75 µV ≈ the electronics floor again (predicted 0.63) — instrument-limited
  in the quake band here too.
- **1–15 Hz is the one band UP** (3.47 vs 2.74). Measured 09:00 on a weekday; the
  historical figure's time of day is not recorded. Wait for the overnight soak before
  reading anything into it.

## 🔧 ZERO-FRAME FILL FIXED — it was manufacturing unrejectable width-2 spikes (2026-08-12)

A 12.9 mV "event" (peak_ratio 55.4) at 15:28:13 UTC was NOT mechanical — no ringdown,
and a 4.5 Hz element cannot start and stop in 10 ms. Sample level:

```
15:28:13.15      322,308     normal
15:28:13.16   -1,328,192     garbage frame
15:28:13.17   -1,328,192     ZERO frame, filled with the garbage
15:28:13.18      322,160     normal
```

`recorder.py` set `last_good` from the RAW frame, so a garbage frame became the fill
value for the next zero-frame. One bad read became **two identical samples** — and the
despiker only rejects ISOLATED samples, so the pair was unrejectable at any threshold.

- **Fix: fill from `despiker.prev`** (already passed the isolation test) instead of
  `last_good`. This stops the propagation AND lets the despiker reject the original
  garbage frame, because its lookahead is now back at baseline (`d_after == 0`).
- **Four false events in `events.log` share the STA/LTA's delta-function signature**
  (duration 3.68–3.69 s, ratio 54.7–55.4): 08-08 04:20 (39,008 µV), 08-10 23:40
  (13,380), 08-12 13:48 (10,592), 08-12 15:28 (12,932). All would have been caught.
- Patched 2026-08-12 15:36 UTC; backup `station/recorder.py.bak-zerofill`.

## ⛔ SCHED_FIFO does NOT reduce the glitch rate — tested and refuted (2026-08-12)

Recorder and pigpiod both ran `SCHED_OTHER` prio 0. Hypothesis: the read is late because
of scheduling latency, so real-time priority should cut the collision rate.

| | zero_frame | dropped |
|---|---|---|
| SCHED_OTHER, 2 h baseline | **585/hr** | 104/hr |
| SCHED_FIFO prio 20, 21 min | **641/hr** | 106/hr |

641 ± 43 vs 585 ± 17 — indistinguishable. **The collision is intrinsic to the DRDY→read
window at 100 sps, not scheduling.** Reconciles with 07-26: the 5x spike then was real
CPU contention (STEIM2 encoding), and RT priority only helps when something competes.

- Override left in place at `/etc/systemd/system/seismo-recorder.service.d/rtprio.conf`
  as insurance under load; measured no harm. Delete the file to revert.
- **DO NOT re-litigate the glitch rate.** 60 sps is worse overall (31 % more in-band
  noise), faster SPI is worse (+7.4 %), redundant reads are impossible in RDATAC
  (releasing CS aborts the stream, 3737/3737 all-zero) and would inject noise in legacy
  mode. The answer is the mitigation now in place: detect, hold, don't propagate, keep
  it away from the detector.
- The byte-level cause is still open. The one garbage frame examined (`0xEBB800`, low
  byte zero) is consistent with a one-byte-late read, but a single sample is an anecdote
  and miniSEED discards the raw bytes. Settling it needs `RdatacReader.read()` to log the
  actual 3 bytes on deviant frames — best done alongside the bench injection, where a
  known clean sine makes every bad frame unambiguous.

## 🏆 BEST NOISE FLOOR YET — and 1–5 Hz is now at the ELECTRONICS limit (2026-08-12)

Station assembled into the printed case, then measured on the bench and again on the
floor. Median of per-10 s band RMS, gain 64, 300 s windows, each **after 35 min
undisturbed** ([[settling-time-after-handling]]).

| band (µV) | bench 18:40 | bench 23:01 | **FLOOR 23:53** | garage ambient | V1 elec floor |
|---|---|---|---|---|---|
| 0.02–0.12 | 0.31 | 0.33 | **0.36** | 0.80–0.90 | — |
| **1–5** | 1.44 | 1.16 | **0.67** | — | — |
| 1–15 | 14.23 | 7.80 | **2.89** | 2.74 | 1.18 |
| 10–15 | 13.64 | 7.25 | **2.98** | — | — |
| 15–28 | 17.04 | 8.53 | **4.22** | 5.69 | 1.08 |
| 19–21 | 4.70 | 3.23 | **2.67** | — | — |

- **1–5 Hz at 0.67 µV is the headline, and it is the FLOOR, not a site number.** The V1
  electronics floor of 1.18 µV was measured over 1–15 Hz; white noise scales as
  √bandwidth, so the same electronics in a 4 Hz-wide band predicts
  `1.18 × √(4/14) = 0.63 µV`. Measured 0.67. **In the quake band this station is no
  longer limited by its site — it is limited by its own front end.** Further coupling
  work in 1–5 Hz cannot buy much; the bench injection (below) is the lever that can.
- **⚠️ DO NOT compare noise numbers across sessions.** At 18:40 the bench read 15–28 Hz
  at 17.04 µV and it looked like the new enclosure had cost HF performance. By 23:01,
  with **nothing touched**, it was 8.53. It was the room. This is the third time this
  trap has been walked into (see the "+10 % in band" figure at the RDATAC entry) — A/B
  in ONE session or don't claim a delta.
- Broadband RMS 10.33 µV on the floor vs 31.5 µV on the bench; pp 211 µV.

## ✅ ENCLOSURE CLOSED + 5 V VIA GPIO — the power path is proven (2026-08-12)

Mean Well GST25A05 → panel barrel jack → **GPIO pins 2+4 (5 V), 6+14 (GND)**, doubled
Dupont jumpers, 2 A slow-blow inline. See `doc/power-wiring.md`.

- **`throttled=0x0` continuously over 14 h.** The Pi 2B's undervoltage detector never
  fired once — a stronger result than a meter reading, since it watches continuously.
  The doubled-jumper termination carries it with margin. [[power-5v-usb-extension-gotcha]]
  is satisfied: the DC side is short and fat, the AC side is the long run.
- **Operating point unchanged by the rebuild.** DC 325,756–326,395 counts @ g64 vs
  330,808 on 08-07 — **1.3–1.5 %**. The standing offset is bias current through the coil,
  so its presence again proves the DC path is continuous end to end.
- Cover-on cost nothing: DC 3.039 mV open vs 3.032 mV closed.
- **Boot fault during assembly was the SD CARD**, not the wiring — solid green ACT, no
  network. Reseating fixed it. Solid RED on a Pi 2B means the rail is *good* (that LED
  drops out below ~4.63 V), so red-solid + green-solid = power fine, card not read.
- **The Pi moved to `eth0` 192.168.4.62** (was 192.168.4.47 on Wi-Fi). Ethernet also
  retires [[wifi-tx-corrupts-acquisition]]. ⚠️ `server/README.md` and the pi5 Dokku
  config still point the live-feed proxy at **.47**.

## ✅ ROOT CAUSE: the glitch/stall rate is the 60→100 sps SWITCH, not any hardware (2026-08-12)

`zero_frame` glitches run ~550/hour and `dropped` ~110/hour, and this looked alarming
after the rebuild. It is neither new nor caused by anything physical. Counting the whole
`qc.log` by day:

```
2026-07-23    161      2026-07-26  19511   <- 25x step
2026-07-24    487      2026-07-27  13538
2026-07-25    568      ...
                       2026-08-11  13489   <- identical rate today
```

Hourly across the transition it is a **cliff, not a ramp**: ~18–20/hr through
07-25T22, 163 at T23, ~550/hr from T04 onward. STATUS puts the first 100 sps interval
at **2026-07-25T23:45Z**. That is the cliff.

- Per-sample glitch probability went **1-in-12,000 → 1-in-650** (~18×). Mechanism is the
  one `rdatac.read()` already documents: a frame landing in the ADS1256's register-update
  window clocks out zeros, and at 100 sps there is less slack between conversions for the
  read to land in. Same physics as "a higher rate injects proportionally more bursts into
  shorter windows".
- The 07-26 T01–T03 spike to ~2900/hr on top of the new baseline was the UDP streaming +
  detector-to-pi5 work going live. **CPU load modulates the rate; the sample rate causes it.**
- **`stalls` is a misleading name** — it is `ClockAnchor.outliers`, i.e. block boundaries
  where the wall-clock read is >10 ms off prediction. `update()` is skipped entirely on any
  block containing a glitch, so stalls count scheduling latency on the *remaining* blocks.
- **Impact is small by design and confirmed negligible**: a zero frame HOLDS the previous
  sample (gapless, no needle), 0.15 % of samples, `resyncs` 0 over 14 h. The 0.67 µV
  1–5 Hz floor was measured with all of this present.
- Not worth "fixing": 60 sps is rejected (100 sps measured ~31 % *lower* noise in band),
  and faster SPI is known to be worse. Leave it.

## 🔧 DESPIKER threshold 200,000 → 50,000 counts (2026-08-12)

Helicorder speckle prompted a full-day threshold sweep (`analysis/despike_sweep.py`,
day 223, 23.4 h, contains the confirmed M2.8):

| jump (ct) | ~µV | held/h | 1–15 Hz | 1–5 Hz | holds inside the M2.8 |
|---|---|---|---|---|---|
| 200,000 (was) | 1863 | 0 | 9.59 | 1.18 | none |
| **50,000 (now)** | **466** | **58** | **9.57** | **1.18** | **none** |
| 20,000 | 186 | 1207 | 9.82 | 1.30 | 5 |
| 10,000 | 93 | 11424 | 12.67 | 3.96 | 188 |

- **50k is the last free threshold.** Below ~25k the ISOLATION test stops discriminating:
  ordinary HF ambient routinely spikes for one sample and returns, so real samples get
  held and the injected step discontinuities push the band RMS **UP**, not down.
- Hard bound: the largest sample-to-sample jump *inside* that M2.8 is **22,512 counts
  (210 µV)**. Any threshold above that cannot truncate it.
- **The helicorder speckle at 100–200 µV is NOT removable this way** — it is the HF tail
  of ordinary noise, not discrete garbage frames (correlation with the ADC's own QC
  counters is at chance: 24–29 % vs a 22 % baseline). Band-pass the drum for display, or
  fit the input anti-alias RC. Do not chase it with the despiker.
- Blind spot worth knowing: the despiker can only ever reject **isolated single samples**.
  ~12 % of observed excursions are two samples wide and survive at any threshold.
- Patched on the Pi 2026-08-12 08:03 PDT; backup at `station/rdatac.py.bak-jump200k`.

## 🌟 M2.8 THE GEYSERS DETECTED — and the catalog doublet resolved (2026-08-11)

USGS listed two events at the same spot 17 s apart: **M3.0 at 21:34:57** and **M2.8 at
21:35:14** (38.826°N, ~122.80°W, ~45 km NNW). The station recorded **one** arrival.

| solution | predicted P onset | observed | residual |
|---|---|---|---|
| **M2.8, origin 21:35:14** | 21:35:22.9 | **21:35:23.0** | **+0.1 s** |
| M3.0, origin 21:34:57 | 21:35:05.9 | — | no arrival |

- Envelope (2–15 Hz, 0.5 s windows): baseline 10.5 µV → **peak 69.3 µV = 6.6×**, coda back
  to ambient in **~16 s**. An M3.0 at the same range would be ~2× larger and cannot have
  been missed, so the two catalog entries are almost certainly one earthquake with two
  solutions — and the 21:35:14 one has the better origin time.
- Plots: `analysis/2026-08-11-geysers-m2.8.png` (onset on the P marker) and
  `analysis/2026-08-11-geysers-m3.0.png` (17 s late). `*.png` is gitignored in `analysis/`.
- **⚠️ THE DETECTOR MISSED IT.** STA/LTA peaked ~2.5–3.7 against `trig 4.0`. A confirmed,
  catalogued M2.8 producing 6.6× baseline did not fire. That is a trigger-sensitivity gap,
  not an instrument limit — the signal is unmistakable in the data.
- Scale check: 69 µV here vs 1406 µV peak from the M2.5 at 18.4 km. Consistent falloff;
  nowhere near the detection limit for Geysers events at this range.

## 📐 CALIBRATION: split the problem before spending events on it (2026-08-12)

On "can catalog earthquakes calibrate the station?" — yes, but only for half of it, and
the other half is exactly measurable on the bench first.

- **Electronics half — bench injection, exact, an afternoon.** Two resistors:
  `source → 100 kΩ (0.1 %) → node → 187 Ω → XLR pin 2`, `10.0 Ω (0.1 %)` node-to-return,
  `187 Ω → pin 3`. Ratio **10001:1**, so 1.000 Vrms in = **100.0 µVrms out**; the two
  187 Ω legs put **374 Ω** between the pins so the DC bias lands where the coil puts it
  (verify ~326,000 counts before trusting anything). Source must be **DC-coupled and
  floating** — battery-powered DDS module, or the Waveshare's own DAC8552. **Not** a
  headphone output (AC-coupled, dead below ~20 Hz). Sweep 0.5–30 Hz at 100 µV plus a
  linearity ladder at 5 Hz. Expect **10,738 counts** per 100 µV at gain 64.
- **Sensor + site half — regress against a reference station**, not against catalog
  magnitudes. Pull the same events from a nearby NC/NCEDC station, remove its response to
  m/s, band-pass identically, regress our counts against its velocity: the slope IS
  counts-per-m/s, and path/radiation cancel between two stations at similar range.
  ~15–20 events for ±20–30 %. The ML-residual route needs 2× the events for worse scatter
  (catalog ML ±0.2–0.3 = 1.5–2× in amplitude; ML is a *horizontal* metric).
- **Do the bench injection FIRST.** Calibrating against events while an unknown factor
  sits in the electronics measures the two together and attributes the result to the
  ground. It also either explains the open ~7.5×-low discrepancy outright or hands the
  earthquake data a much sharper question.

## ✅ REBUILT FRONT END CHECKS OUT ON THE BENCH (2026-08-07)

Interface board rewired (same circuit), geophone in its printed case, XLR panel connector
and cable in the chain for the first time. Read from the ADC side, on the bench, ~3 min
after power-up (i.e. **not settled** — see [[settling-time-after-handling]]):

| check | known-good 2026-08-03 | now | Δ |
|---|---|---|---|
| AIN0 / AIN1 single-ended, **gain 1** | 1.528 / 1.524 V | 1.516 / 1.513 V | −0.8 % |
| DC counts @ gain 64 | 336,304 | 330,110 | −1.8 % |
| DIFF @ gain 64 | 3.026 mV | 3.074 mV | +1.6 % |

The standing differential offset is bias current through the coil, so its presence proves
the DC path is continuous **through both new connector pairs** with no added series
resistance worth measuring. Landing within 2 % of the pre-rebuild operating point is the
confirmation.

**Noise** (gain 64, median of per-10 s band RMS — comparable to every other table here).
Three captures: two unsettled 120 s runs bracketing a `JMP_AGND` remove/replace, then a
300 s run after **35 min undisturbed**.

| band (µV) | on, unsettled | off, unsettled | **ON, SETTLED** | garage ambient | V1 elec floor |
|---|---|---|---|---|---|
| DC counts @ g64 | 330,110 | 330,741 | **330,808** | — | — |
| 0.02–0.12 Hz | 0.88 | 4.30 | **0.54** | 0.80–0.90 | — |
| 1–5 Hz | 2.02 | 2.21 | **1.64** | — | — |
| 1–15 Hz | 15.97 | 18.02 | **11.07** | 2.74 | 1.18 |
| 10–15 Hz | 17.33 | 18.67 | **11.07** | — | — |
| 15–28 Hz | 35.31 | 39.26 | **10.12** | 5.69 | 1.08 |
| 19–21 Hz | 7.99 | 9.09 | **3.08** | — | — |

- **Settling is worth 3.5× at 15–28 Hz and 8× sub-Hz.** Reconfirms
  [[settling-time-after-handling]] — do not read a noise number within 35 min of a touch.
- **The residual 1–15 Hz excess is still all the 10–15 Hz hump**; 1–5 Hz is 1.64 µV, *below*
  the garage number. Benchtop mechanical noise, not electronics. Re-measure on the slab.
- Figure: `analysis/bench_rebuild_2026-08-07.png` (settled trace + both spectra).

### `JMP_AGND` on vs off: no effect on the signal path (2026-08-07)

Pulled and replaced while measuring. **DC operating point identical across all three runs
(0.2 % spread)** — expected, since AINCOM is only a mux input node and the common mode is
set by the 100 k pull-up / 100 k pull-down against the board rails. The ~10 % apparent rise
with the jumper out was settling, not grounding: it lifted *every* band uniformly including
the 19–21 and 40–42 Hz mechanical lines, and the settled run came in far below both.

**Keep the jumper fitted.** It buys nothing measurable to remove, and without it the
single-ended BIAS check — the one 10-second reading that localizes a lost DC path — reads
both legs at an arbitrary −0.38 V and is useless. Refitted, they read 1.515 / 1.514 V.

**The 19.95 / 41 Hz line pair is still present on the bench** (7.99 µV at 19–21, 9.71 µV at
40–42) — different room, rebuilt board, new cable. Combined with the negative coupling test,
that points at the **instrument**, not any structure.

### ⚠️ adc_diag's BIAS check RAILS at any gain above 1 — and reads as a real voltage

At gain 64 the single-ended FSR is ±78.125 mV, so the ~1.5 V bias legs peg and print as
"+0.078 V" — which looks exactly like the floating-pair signature this project has already
chased once. **Always run the BIAS check with `SEISMO_GAIN=1`.** `adc_diag.py` now prints
the correct FSR (it previously mislabelled it ±VREF/gain) and appends `<-- RAILED` when a
leg is within 1 % of full scale.

**Open, pre-existing:** gain 1 and gain 64 disagree by ~2× on the differential offset
(7.78 vs 3.07 mV today; 6.31 vs 3.03 mV on 08-03). Predates the rebuild — a scaling bug in
the gain-1 path, not a hardware change. Trust gain 64; it is what the recorder runs.

## ✅ FAULT FIXED 2026-08-03 — it was a STRAY SHIELD STRAND, not a bias resistor

**Root cause: a single whisker of the cable's shield braid making intermittent contact
with a coil wire.** Charles found and cleared it on the bench. Everything below in the
"faulted" section is retained for the diagnostic trail, but **its hypothesis was wrong** —
it blamed a bias-resistor leg or a cold-flowed ferrule, and the real failure was a loose
braid strand. Different failure, different prevention: **terminate the shield properly**
(comb the braid, twist to one pigtail, sleeve/heat-shrink right up to its landing) rather
than trusting ferrules to fix it. The shield lands at the board end only, right next to
the input terminals — that is the one place in this build where a stray strand can reach
a signal leg. Carry this into the rev-2 layout and the case wiring.

**Confirmed restored** (bench, geophone attached, `adc_diag.py` + `capture_raw.py`):

| | faulted | after fix |
|---|---|---|
| AIN0 / AIN1 (single-ended) | −1.224 / −1.225 V | **+1.528 / +1.524 V** |
| DIFF @ gain 64 | −78.125 mV (railed) | **+3.026 mV** |
| DC, raw counts @ gain 64 | −2,174,268 | **+336,304** (baseline ~334,000 — **0.7 %**) |

Landing within 0.7 % of the pre-fault operating point is the strong confirmation: nothing
else drifted.

### Diagnostic lessons from this session (worth more than the fix)

- **`adc_diag.py`'s BIAS check is single-ended vs AINCOM**, so it is only meaningful with
  `JMP_AGND` fitted. With the geophone connected, healthy is ~1.5 V on both legs; **both
  legs equal but at an arbitrary/negative potential means the pair is FLOATING**, because
  the coil ties them together. That one reading localises the fault to the DC path.
- **The rev-1 topology is a series divider** — `V+ –100k– AIN0 – coil – AIN1 –100k– GND`,
  shield to GND, no damping shunt fitted. It is NOT a common-node bias. Consequence:
  **a single open 100 k floats BOTH legs**, because there is only one DC path. (I argued
  the opposite from the rev-2 schematic during this session and was wrong — `doc/rev2-frontend.md`
  describes the *replacement* board, not what is built.)
- **The design's own arithmetic checks out:** 3.3 V / 200 kΩ = 16.5 µA through the coil,
  × 375 Ω = **6.2 mV** standing differential offset. Measured at gain 1: **+6.308 mV**.
- **`adc_diag.py` prints full-scale as ±VREF/gain; the ADS1256's FSR is ±2·VREF/gain.**
  Its gain-64 "±39.1 mV" is half the true ±78.125 mV. Convert via raw counts, not its mV.
- **Do not diagnose off "seems better" after reseating a connection.** A reseat that
  changed nothing measurable read as an improvement; the ADC said otherwise.

## ✅ V1 ELECTRONICS NOISE FLOOR MEASURED (2026-08-03) — and it bounds rev-2

The **shorted-input floor test** that `BACKLOG.md` puts in the rev-2 critical path is
**done**, on the bench, geophone disconnected, cable terminated at its far end. Settled,
RDATAC, 100 sps, gain 64 — same statistic as everything else in this file (median of
per-10 s band RMS, µV), so the columns are directly comparable.

| band | 0 Ω short | 330 Ω source | garage ambient (100 sps epoch) |
|---|---|---|---|
| 1–15 Hz | 1.176 | **1.179** | 2.74 |
| 3–15 Hz | 0.968 | 1.023 | 2.62 |
| 15–28 Hz | 1.077 | 1.240 | 5.69 |

- **The old "~1.17 µV electronics floor" was right after all.** It sits in the DEAD column
  because it was measured through the demo-jumper network; the clean re-measurement lands
  on **1.176 µV**. The figure is now re-established on valid hardware.
- **Source impedance costs nothing in the quake band.** 1.179 vs 1.176 µV is noise. The
  penalty is HF-weighted (+15 % at 15–28 Hz), consistent with switched-cap sampling noise,
  and above the band of interest. **BACKLOG item 2 (input RC + charge reservoir) is worth
  ~0 % in 1–15 Hz** — an earlier +4.6 % reading was an unsettled measurement, not physics.
- **Electronics are ~10 % of the in-band noise.** Noise adds in quadrature: at 2.74 µV
  ambient, site alone is √(2.74² − 1.18²) = 2.47 µV. Removing the front end *entirely*
  buys 2.74 → 2.47. **Buffer-on and 5 V AVDD cannot beat that ceiling.**
- Caveat: measured in the bench's EM environment, not the garage's. Re-run once in place.

### 🔀 DECISION (2026-08-03): rebuild V1 ruggedly; do NOT chase rev-2's noise features

The failure was **mechanical**, and the measurements say the circuit is not the problem.
So: **same topology, same values, better mechanics** — rigid mounting instead of a rat's
nest, shield combed/twisted/sleeved to its landing, strain relief both ends, XLR panel
connector for a real service disconnect. This also keeps the archive comparable, because
the epoch change becomes mechanical only rather than mechanical *and* electrical.

- **Still carry over: the input anti-alias RC.** That one is *correctness*, not noise — at
  100 sps, 60 Hz mains aliases to 40 Hz, and no digital filtering afterwards can undo it.
- **DEFER the LC Tech ADS1256_V1.1 swap.** Its whole draw was enabling buffer-on at 5 V
  AVDD, and that payoff is now measured as small. It is also the riskiest item on the list
  (unmetered P1→ADC R/C network, new epoch, unfamiliar board).
- **Shunt damping is the last step, and it is a real tradeoff, not a default.** No shunt is
  fitted today. Size it by *measurement* (tap the element, take the log decrement of the
  ring-down, solve for the difference to target), not from the datasheet. And note a shunt
  damps by loading the coil, i.e. **it costs sensitivity** — with absolute calibration
  already ~7.5× low and the project explicitly sensitivity-first, deliberate under-damping
  is defensible. Do it last, in the garage, against a stable baseline.

## 🛑 SHUNT DAMPING — CLOSED, no resistor, not deferred (2026-08-10)

**Decision: the socket stays empty. Permanently.** Not "pending a measurement" — decided.

Charles: *"I just don't see the long term value... who's going to care, really?"* Nobody.
The station detects local earthquakes and does it well (9 confirmed events, an M4.2 at
45 km). A shunt makes the response flatter and **costs sensitivity to do it**, on a
station that is explicitly sensitivity-first and already reads ~7.5× low.

The arithmetic that should have ended this on day one:
- Ringing is the only practical argument for damping, and it lasts **under a second**
  even at ζ = 0.2, against event codas of **20–80 s**. It cannot affect STA/LTA,
  duration, or anything measured here.
- The resonance peak an undamped element gives you (×1.75 at ζ = 0.3) is **free gain**
  at 4.5 Hz for a detection instrument, not a defect.
- A shunt that adds meaningful damping costs 3.6–27 % of signal, in the wrong direction.

### What the attempt did establish, which is worth keeping

- **The tap test on a table measures the TABLE.** Stacked ring-downs peaked at 7.71 Hz
  with the table clear and 6.39 Hz with a lamp on it — added mass lowering the frequency
  proves it is a structural mode, not the element. Ambient peaks there too, so noise
  measured on that table is also contaminated. Any future attempt must be on the slab, or
  must excite the element **electrically** through its own coil (the Waveshare's DAC8532
  is on the same terminal block — the hardware exists).
- **`analysis/ringdown.py` works and is validated**, bounding the fit near the element,
  fitting every tap, and refusing to report unless ≥3 agree. If damping is ever needed
  it is ready.
- **The two-point method measures `k = G²/(2Mω₀)` and hence G** — the quantity behind the
  7.5×-low calibration. That is the only reason to revisit this, and it is a curiosity,
  not a need.

**⚠️ For future sessions: do not reopen this.** It consumed most of a session to reach
"do nothing", and the answer was derivable from the first paragraph above without a
single measurement.

## ⛔ FIRST Pi BASE PRINT WAS SCRAP — and why (2026-08-09)

Printed, then found unusable. Two independent defects, both mine, both avoidable.

**1. The cavity was sized to the PCB rectangle.** `pi_len` 85 with 12 mm margins, and no
connector, mating plug or bend radius modelled anywhere. An RJ45 plug plus boot is ~33 mm
before the cable can even begin to turn, against 12 mm of clearance. Charles had directed
me explicitly to oversize well past what I thought I needed; I applied "generous" to a
rectangle that does not describe the object.

**2. The board was MIRRORED.** `chassis.py` carries a comment saying the ports are on the
−X short edge. The mechanical drawing (confirmed on a photo) puts the 58 × 49 hole
rectangle 3.5 mm from one short edge and 23.5 mm from the other, with the connectors on
the 23.5 mm edge — so the offset three lines above that comment implies the opposite. I
built the layout off the comment. "Ports +X with GPIO −Y" is a *reflection* of the real
board, not a rotation, and its symptom is that the locating pins land in the two holes
occupied by the Waveshare standoffs.

### The fix (Charles's layout call)

**Cotter pins toward the MIDDLE of the case, round support post out at the −Y edge** —
swapping what gen-1 had. That turns the Pi 180° so its cables emerge into open space.

| | gen-1 | now |
|---|---|---|
| connector faces → wall | ~9 mm (**overhung the case**) | **54 mm** |
| headroom above the Pi | — | 46 mm (cable can rise and loop) |
| microSD edge | 12 mm | 20 mm |
| case | 115 × 156 | 168 × 165 |

### What actually prevents a repeat

- **Hole positions are stated in BOARD coordinates from the drawing** and mapped through
  `pi_map()`, which applies a **rotation**. The mirrored combination is no longer
  expressible. Every hand-signed offset is gone — every error here was a sign.
- **Clearance is asserted from the CONNECTOR FACE.** The board is not symmetric about the
  pins: their midpoint is 10 mm toward the non-port edge, so the faces sit 55.5 mm away,
  not 42.5. Sizing from the PCB edge is what did it.
- Asserts also cover: pins and post on opposite long edges, pins toward the middle, post
  never under a standoff nut, and a minimum at the microSD edge.
- **`from dimensions import *` silently skips leading-underscore names** — hit twice in one
  day. Shared values must not start with `_`.

**No microSD access slot** (Charles, 2026-08-09): patches go over the air, so the card is
effectively never swapped. Card protrudes ~3 mm into 20 mm of clearance; access is by
lifting the cover.

## ✅ GEOPHONE CASE COMPLETE — printed and assembled (2026-08-08)

Gen-1 geophone enclosure is **done**: body + lid printed, XLR fitted, element in its
cup, assembled. It has been carrying the bench measurements all week (the 08-07 settled
run was taken through it), so it is not just built — it is in service.

That closes the sensor end. Everything remaining before the station goes back in the
garage is the Pi/front-end case below.

## 🧰 Pi + front-end CASE — modelled, coupon validated (2026-08-08)

**`parts/pi_case.py` — 168 × 164 × 93 mm, ~454 g PLA.** Minimal tier (Charles's call):
base + lid + handle, three panel jacks, boards on standoffs. No gasket, vents, inserts or
labels. Plan + elevation: `parts/pi_case.png`.

### ✅ Coupon results (2026-08-08) — both open connector questions closed

`parts/panel_coupon.py`, 80 × 106 × 3 mm, ~27 g, printed and fitted against the real parts:

- **Barrel jack → the rung labelled `12`.** `barrel_bore_dia = 12.0`, no longer provisional.
- **RJ45 coupler mounts fine in the D-series cutout**, so **Ethernet and XLR are the same
  cutout** — the pattern already validated by `xlr_coupon.py` covers both.

The ladder-of-candidate-bores approach is worth reusing: it answers "what size is this
thread" for ~27 g *including* print shrinkage, which a caliper reading does not.

### Design rules this case is built on

- **SIZE IS DERIVED from a bay table**, not chosen, so a corrected component dimension
  rescales the case instead of forcing a redesign.
- **Generous margins are deliberate** (Charles, forcefully, 2026-08-07): do not design a
  box so tight that everything must be perfect or it is scrap. 12 mm wall clearance,
  20 mm between rows, and a NAMED `iso_allow = 10 mm` on the isolator bay.
- **The unvalidated dimension never goes in the expensive part** — *while it is still
  unvalidated*. The barrel bore briefly lived on a removable 48 × 48 × 3 plate for exactly
  that reason. The coupon then validated it at 12 mm on this printer and filament, so the
  risk was gone and **the plate was deleted rather than carried as dead weight** (it cost a
  part, four screws and a 34 mm opening). The case takes a plain bore. The lesson is the
  pattern, not the plate: isolate a guess until it is settled, then remove the scaffolding.
- **Connectors ride ABOVE the boards**, so no floor is reserved behind them. The XLR's
  32 mm body intrudes at its own height, costing Z (180 mm available) instead of Y (which
  was fighting the bed). The tall upper cavity is where the coiled patch cable lives.
  This also made the old `panel_band` parameter dead — removed.
- **Interface board stands ON EDGE** (Charles's suggestion) in two slotted uprights, slot =
  board + 1.4 mm so it takes ~1.4–2.6 mm stock. Honest accounting: this did NOT shrink the
  box (the row's depth is set by the isolator), but it puts the screw terminals sideways
  and reachable, shortens the runs to the XLR, and drops the board's footprint 50 × 35 →
  50 × 22. It cost 10 mm of height.
- **The bed check includes a 5 mm brim allowance.** "Fits the bed" and "prints on the bed"
  are different claims; at 176 mm the case had 4 mm to spare and nowhere to put a skirt.

### Asserts that caught real defects while modelling

Worth keeping because each was invisible to a manifold/volume check:

- Asserting connector positions against the **corner radius** rather than the cavity
  half-width caught the barrel flange AND then the XLR pad sitting where a flange cannot
  seat and a nut has nothing square to pull against.
- The barrel plate's own assert caught its M3 circle at ±17.5 falling **inside** the 34 mm
  opening — four screws into thin air. Plate resized 44 → 48 mm.
- An assert written `... or True` could never fail; replaced with the check that matters.
- Every bore is **point-in-solid scanned** with a control point in solid material, per the
  `geophone_case` lesson that watertight + plausible volume hides a plug.

### Layouts tried and rejected (do not retry)

- Interface board packed against the −X wall beside the Pi: collides unless the Pi is
  offset, and offsetting the Pi drives its end into the +X wall where the 5 V jack wants
  to be.
- 5 V plate on the −Y wall: must clear the 36 mm Pi stack vertically, breaks through the
  ceiling, implies a ~107 mm box.

### 🔌 Isolator moved OUT of the case (2026-08-08) — the 08-04 decision was self-contradictory

STATUS 2026-08-04 said "isolator INSIDE, on the Pi side, with the panel jack on the network
side — **isolation barrier at the enclosure boundary**". Those cannot both hold: an isolator
inside puts the *barrier* inside, so the **unisolated** segment (panel jack → isolator, and
6 in is the shortest patch cable Charles has) runs through the case past the front end,
carrying exactly the common-mode currents the isolator exists to block into the enclosure
volume. Charles caught this.

**It now lives at the NETWORK TAP**, with isolated cable running the whole way down to the
box — better than merely "outside the case", because the long run cannot pick up
common-mode along its length either. Isolate at the source, not the destination.

**The case got much smaller as a result: 168 × 164 → 130 × 143 mm, ~454 → ~348 g**, with
50 mm and 36 mm now spare on the bed. Knock-on changes:

- The 5 V plate moved from the +Y wall to the **+X side wall**. Three pads side by side
  needed 166 mm of flat wall, which would have forced a 196 mm case on a 180 mm bed; +Y now
  carries XLR + Ethernet only, and +X has room that only exists because the isolator left.
- **The Pi is deliberately OFF-CENTRE in X** (`pi_cx` derived, not 0). The 5 V jack pokes
  `barrel_body_depth` into the cavity from +X, and centring the Pi would pay that clearance
  on both sides — worth ~30 mm of case width for nothing.
- `cav_x` is now **derived from the connector wall** as well as the component packing, so
  "the jacks do not fit side by side" is caught by arithmetic instead of by an assert
  firing late.

### Still open

- **Lid + handle** — not modelled yet. Reuses the geophone case's handle.
- Connector intrusion depths were going to set `panel_band`; that parameter no longer
  exists, so this is now only a sanity check that no body is deeper than the 158 mm cavity.

## 📦 Pi + front-end ENCLOSURE — decisions and parts ordered (2026-08-04)

Design pass for the case holding the Pi 2B + Waveshare + front-end board. Gen-1 geophone
case is **printed and assembled-tested** (body + lid; handle prints clean, the 24 mm bridge
at the top of the trapezoidal opening came out with no sag). Everything fits: geophone into
cup, XLR into case, M3 screws through both.

- **Front end shares the Pi's case — do NOT give it its own.** `BACKLOG.md`'s
  digitize-at-the-sensor analysis: the geophone run is *differential* across a low 375 Ω
  source and is fine over a cable; the vulnerable nodes are the **high-impedance,
  single-ended** bias network and ADC input. A separate front-end case puts exactly those
  nodes on a connector and cable. Get serviceability from a **removable sub-plate** inside
  the shared case instead, so rev-1 → rev-2 swaps never touch the enclosure.
- **⚠️ NEVER panel-mount micro-USB for Pi power.** The 5 V USB side already browns out when
  extended ([[power-5v-usb-extension-gotcha]]) — dropped sample rate, square-wave plateaus.
  A feedthrough adds two more contact pairs to the rail that is already marginal. Instead:
  **panel-mount barrel jack → short heavy run → Pi GPIO 5 V/GND pins.** Tradeoff: the GPIO
  feed bypasses the Pi's input protection.
- **Keep the PSU external and extend the AC side, never the 5 V side.** A switcher inside
  the box is also an EMI source next to a µV front end.
- **Ethernet: D-type panel coupler**, because it reuses the D-series bore + ±(10, 11.5) mm
  hole pattern already validated by `parts/xlr_coupon.py`. Unshielded is *preferable* here —
  the case is PLA with nothing to bond to, and a shielded coupler would risk a second ground
  path against the single-point-ground doctrine.
- **Galvanic Ethernet isolator goes INSIDE, on the Pi side**, with the panel jack on the
  network side — isolation barrier at the enclosure boundary. It measured a real **1.6×**
  improvement in the signal band; preserve it deliberately.
- **Print a fit coupon for every new panel connector before committing to a case print.**
  That is why the XLR fit first try.

### Parts ordered 2026-08-04

| item | part | notes |
|---|---|---|
| PSU | **Mean Well GST25A05-P1J** | 5 V 4 A, 20 W, IEC C14 in, 5.5 × 2.1 barrel out, **80 mV published ripple**, ~$13–25 |
| AC cords | C13→NEMA 5-15, **25 ft** (under-house) + **6 ft** (bench) | AC side is the side you extend |
| DC jack | **RuiLing 5.5 × 2.1 panel mount, 3-pin, hex nut** | flange Ø14.0, thread length 11.8 mm, receptacle Ø6.3. **Pin 5 = +, pin 2 = −, pin 3 = switch contact, leave unconnected.** Thread OD still to be measured — that is the panel hole |
| Ethernet | D-type Cat6 female/female feedthrough, 2-pk | verify flange + hole spacing against the validated D pattern |
| screws | #6 × ½″ 18-8 stainless **pan head** sheet-metal (variety pack) | pan/button head deliberately: the 3 feet ARE the ground contact, so a rounded head gives near-point 3-point contact. `pilot_6 = 2.7` |

**Rejected:** a $135 linear supply. At ~10 % of in-band noise from the whole front end, the
payoff is bounded; buy ripple performance later only if the floor test says to. Thread-forming
plastic screws (Plastite / Delta PT) are genuinely better in PLA but not worth re-specifying
gen-1 pilots for — revisit with heat-set inserts at gen 2.

**Cosmetic:** the engraved `GEOPHONE` will be wax-filled (Stockmar beeswax **sticks** — a
0.9–1.3 mm marker nib cannot enter the letter strokes, so pack wax in and scrape flush
rather than trying to paint into the groove). Gen 2 should instead raise the text and do a
filament change, now that an AMS lite is on order.

## 🛰️ FDSN network identity: `SS` is available WITHOUT asking (2026-08-03)

`BACKLOG.md` said the only routes were "register an FDSN network code" or "be a Raspberry
Shake". There is a third and it is the easy one: **`SS` ("Single Station") may be used by
any operator running a single station, with no application to FDSN** — "a generic network
code for any operator that wishes to produce data in FDSN formats, but is not otherwise
associated with a network."

- ✅ **ISC replied 2026-08-07 (James) and the registration is proceeding under IR** —
  Charles confirmed "yes, register under IR" the same day. The ISC explicitly stated it is
  **happy to use stations with FDSN network codes in its operations, and there is no reason
  not to have it in both**. So IR and `SS` are *complementary*, exactly as assumed: IR is the
  ISC's own registry (it reserves the station code against collision), `SS` is the FDSN
  network code used in miniSEED headers. Registering under IR is what makes `SS.<code>` safe
  to publish.
- Submission was filed ~2026-07-27 and auto-acknowledged; the human reply took 11 days.
- 🔤 **The registered code is `OAKM1`, NOT `OAKMT`** (Charles, 2026-08-07) — chosen so a
  future second station can be `OAKM2`. The cutover is therefore **two fields, not one**:
  `XX.OAKMT` → `SS.OAKM1`. The station code is embedded in every **day-file name**, so this
  is a bigger change than the network flip alone.
- **Still outstanding:** James's confirmation that `OAKM1` is actually registered. The
  cutover waits on that email, not on the 08-07 reply.
- **Station codes are not globally unique in FDSN** — the unique key is
  network·station·location·channel. Under `SS` specifically, uniqueness *within* `SS` is
  the requirement, which is exactly what registering buys.
- Cutover: flip `SEISMO_NETWORK` `XX` → `SS` once the registry confirms `OAKMT`. It rewrites
  miniSEED headers, so it is a **metadata** discontinuity (not an instrument epoch), and
  anything globbing the archive by station code needs to know about both. Do it once.
- 🚫 **Do NOT schedule this around epoch boundaries.** Charles, 2026-08-08: the archive to
  date "went nowhere to nobody" — it is equipment testing and tuning, nothing downstream
  depends on it being continuous, and it never will. Just flip it when the registration
  lands. (An earlier note here argued for timing the flip to coincide with the front-end
  rebuild so the epoch changed once; that was protecting data with no consumer.) The same
  goes for the bench data now in the archive and the shadowed `AM.OAKMT` day-201 file —
  neither needs recording, renaming or backfilling.
- What *does* still matter is code that stays correct ACROSS the change, because a stale
  `XX.OAKMT` glob fails **silently** and yields a plausible wrong answer. That is
  correctness, not archive preservation, and it is already done.

#### Cutover checklist — audited 2026-08-07

**Already parameterized** (just set the env): `station/recorder.py`, `server/store.py`,
`dashboard/seismo_dashboard.py`, `dashboard/heli_render.py` — all read `SEISMO_STATION`
(default `OAKMT`).

**Hardcoded, will break:**
- `server/detector.py:41` — `NET, STA, LOC, CHAN = "XX", "OAKMT", "00", "SHZ"`; the pi5
  detector will not see the renamed files at all.
- `station/seismo-recorder.service:16` — `Environment=SEISMO_STATION=OAKMT` (+ network).
- `station/motd-50-seismo.sh` — cosmetic.

**⚠️ Silent failures — FIXED 2026-08-07.** `analysis/ppsd.py` globbed `XX.OAKMT*.mseed`
and `analysis/coupling_test.py` / `analysis/break_1641.py` built
`XX.OAKMT.00.SHZ.D.{julian}.mseed` by hand. These would not have errored after the flip —
they would quietly stop matching new files, so a mixed-epoch analysis would run on
pre-cutover data only and look healthy. Same class as the `max(st, key=npts)` trap.

### ✅ CUTOVER PREP DONE (2026-08-07) — the flip is now config-only

All code is SEED-id agnostic. **No source change is required at cutover**; it is env vars
plus a restart.

- **`analysis/helicorder.py` gained `day_path(julian)`** — resolves a day-file by globbing
  `*.D.{julian}.mseed`, i.e. on the date (stable) rather than the SEED prefix (changes).
  Refuses to guess when a day has two SEED ids, which is the cutover day itself.
  `coupling_test.py` and `break_1641.py` now use it.
- **`analysis/ppsd.py`** globs `*.D.*.mseed`; its state/PNG names follow `SEISMO_STATION`.
- **`server/detector.py`** no longer hardcodes `NET, STA, LOC, CHAN` — reads the same four
  env vars as `recorder.py` / `store.py`. **Deployed to pi5 and restarted**; behavior is
  identical today because the defaults are still `XX`/`OAKMT`.
- **`analysis/detection_map.py`** figure labels follow `SEISMO_STATION` so the map stops
  saying OAKMT after the flip.
- **No change needed in `server/udp_collector.py`** — it derives day-file names from the
  *record headers* (`_dayfile()`), so it follows the station automatically.

#### 🔎 Found while testing: a shadowed `AM.OAKMT` day-file — and it is REAL DATA

`day_path("2026.201")` immediately errored on **two** files for that day. Characterised
2026-08-07: they are **complementary halves of 2026-07-20, not duplicates.**

| file | covers (UTC) | span | samples | sps |
|---|---|---|---|---|
| `AM.OAKMT...201` | 05:31:18 → 16:24:43 | 10.9 h | 2,197,176 | 55 + 57 |
| `XX.OAKMT...201` | 16:24:48 → 24:00:00 | 7.6 h | 1,510,763 | 57 |

The 5.4 s seam is the recorder restart at the `AM` → `XX` rename (AM is Raspberry Shake's
registered code — see the warning in `recorder.py`). So the AM file is the **first 10.9 h
of day 201, 59 % of that day's samples**, and every prefix-hardcoding analysis has silently
dropped it. The exact failure mode this cutover prep guards against, already realised once.

**Impact is bounded:** day 201 is the 55/57 sps epoch (100 sps did not start until day
206), so current-epoch work was never affected. What was short-changed is early-archive
noise/PPSD work, which lost more than half of that day.

**Also found: 2 KB of corruption in the XX day-201 file** — 16 consecutive 128-byte
non-SEED records at bytes 2,902,016–2,904,063. obspy skips them with a warning, so ~16
records are lost from that day; not a correctness threat, but it only shows up on a real
read.

#### 🐍 obspy import failure — cause found, and the manifest was the real bug

`import obspy` failed while `obspy/` sat on `sys.path`: the install was **half-present**
(dist-info there, package directory gone). `uv pip install --reinstall obspy` fixed it.
Root cause is that **`pyproject.toml` declared no dependencies at all**, so the whole
analysis stack was an undeclared local install free to drift. `numpy` / `scipy` / `obspy` /
`matplotlib` are now declared.

⚠️ **Do NOT run `uv sync` in this repo.** The build123d / ocp-vscode CAD stack shares this
`.venv` and is deliberately undeclared (dev tooling, per `CLAUDE.md`); `uv sync` prunes
anything undeclared and would delete it. `[tool.uv] package = false` is set so nothing
tries to build the repo as a package. Install with
`uv pip install --python .venv/bin/python <pkg>`.

#### Cutover runbook — run when James confirms `OAKM1` is registered

1. **Station** (`seismo.local`), `/etc/systemd/system/seismo-recorder.service`:
   `SEISMO_NETWORK=XX` → `SS`, `SEISMO_STATION=OAKMT` → `OAKM1`.
   `sudo systemctl daemon-reload && sudo systemctl restart seismo-recorder`
2. **pi5** — add `Environment=SEISMO_NETWORK=SS` + `SEISMO_STATION=OAKM1` to *both*
   `seismo-detector.service` and `seismo-server.service`; `daemon-reload` + restart each.
   The collector needs nothing.
3. **Dashboard** (dokku on pi5): `dokku config:set seismo SEISMO_NETWORK=SS SEISMO_STATION=OAKM1`
   (it currently sets neither, so both fall through to the `OAKMT` defaults).
4. **Verify:** a new `SS.OAKM1.00.SHZ.D.2026.<jjj>.mseed` appears in `~/seismo-archive/`,
   `/v1/health` still fresh, detector still writing events.
5. **Do NOT rename historical files.** The archive legitimately spans `AM` → `XX` → `SS`;
   `day_path()` handles that, and rewriting history would falsify the record.
- Refs: <https://docs.fdsn.org/projects/source-identifiers/en/v1.0/network-codes.html>,
  <https://www.fdsn.org/networks/detail/SS/>

## 🔴 (HISTORICAL — RESOLVED, see above) STATION FAULTED 2026-07-31 16:41 PDT

**Recorder stopped AND `systemctl disable`d at 22:35 PDT** so it does not come back on a
power cycle during the repair. The Pi itself is still up and reachable (`seismo.local`);
run `sudo shutdown -h now` on it before touching the wiring. To bring the station back
after the fix:

```
sudo systemctl enable --now seismo-recorder     # re-enable + start
journalctl -u seismo-recorder -f                # expect DC near mid-scale, 5-min std ~700
```

Data through 2026-08-01T05:35Z is synced to `analysis/data/`. **Everything from 16:41 PDT
onward is instrument noise, not ground** — exclude it from any archive analysis, and
ignore the ~200 false `EVENT` entries it wrote to `events.log` in that window.

At **23:41 UTC / 16:41 PDT** the trace slammed to negative full scale for a few seconds
and then parked at **≈ −2.2M counts (≈ −20 mV input-referred)**, where it still sits.
Broadband noise went up **20–200×** (5-min std ~700 → 15k–140k counts) and the STA/LTA
detector has been firing continuously ever since — the `EVENT` lines in the journal from
16:41 onward are **all false**. The recorder itself is healthy (no restart, 8 d uptime,
clock error ±0–14 ms, rate 99.84 sps).

- **It is not the tile→slab move.** The move was at 13:40 PDT; it produced a 2-min
  handling transient and then the DC returned to its normal ~+334k with std ~700, and
  stayed clean for three hours. The break is a separate, later event with nobody at the
  rig.
- **Signature:** big negative DC offset + broadband, non-sinusoidal, 1/f-ish noise 100×
  the floor from 0.01 Hz to ~20 Hz, **no mains lines** (see `analysis/break_1641.png`).
  That is what a **lost DC path on one input leg** looks like — a bias resistor leg or a
  screw-terminal/ferrule that let go, leaving the input high-impedance and drifting.
  A move-loosened connection that finally opened three hours later fits the timing.
- **Ruled out — it is not the ADC's state.** A recorder restart does a hard pin reset plus
  `cal_self()` (`adc_common.py:143-146`): every register rewritten, offset recalibrated.
  Done at 22:33 PDT and the offset came back **identical** (−2,174,268 counts, std 22,614).
  A **reboot is therefore pointless** — it adds only kernel/pigpiod state, and nothing in
  software can hold a −20 mV offset on an analog input.
- **⚠️ WRONG WHEN WRITTEN — there was no XLR to unplug.** This said "unplug the XLR at the
  case", but the gen-1 case was never assembled and no connector existed in the chain: the
  geophone was hardwired, salvaged XLR *cable* soldered at the element end and tinned into
  the ADC screw terminals at the other. There was no disconnect point at all, which is why
  the XLR panel connector is worth fitting — it turns this diagnosis into a 10-second
  unplug-and-meter. (Kept as a caution: check what is physically built before writing a
  repair step against it.)
- **Then, Pi off:** reseat/verify the two 100 kΩ bias resistors and both signal legs in the
  ADC screw terminals and at the perfboard, then confirm DC returns to ~mid-scale before
  trusting anything.

## ✅ COUPLING TEST DONE (2026-07-31 13:40 PDT) — tile→slab changed nothing measurable

Geophone taken off the garage's plastic interlocking tile and set directly on the
concrete slab. Valid post-move data is the **2.8 h window 13:45–16:40 PDT** (settling +
the fault above), compared against matched clock windows on the tile.
`analysis/coupling_test.py` → `analysis/coupling_test.png`.

| band (median 5-min RMS) | Jul 30 14:20–16:35 tile | Jul 31 11:00–13:15 tile | **Jul 31 14:20–16:35 SLAB** |
|---|---|---|---|
| 0.02–0.12 Hz | 0.83 µV | 0.80 µV | **0.90 µV** |
| 1–15 Hz | 4.47 µV | 4.32 µV | **4.03 µV** |
| 18–22 Hz | 5.80 µV | 1.22 µV | **1.96 µV** |
| 38–44 Hz | 2.68 µV | 1.07 µV | **2.56 µV** |

- **The 19.95 / 41 Hz line pair survived the move at the same frequencies** (19.93–20.00
  and 40.9–41.2 Hz on both sides). The hollow-tile-resonance hypothesis in `BACKLOG.md`
  is therefore **not supported** — those lines are something else (instrument or another
  structure). Their *amplitude* swings 5× with time of day on the tile alone, so
  amplitude comparisons across windows prove nothing; frequency is the robust part.
- **No sensitivity was recovered.** The 1–15 Hz ambient floor is unchanged (4.0 vs 4.3–4.5
  µV), so the 7.5×-low absolute calibration is **not** coupling loss through the tile.
  That candidate is closed; shunt loading / element sensitivity / site response remain.
- **Two analysis traps found and fixed while doing this** (both now documented in the
  script): day-files are fragmented into ~10 s blocks with 2–3 sample gaps, so
  "longest gapless segment" silently analysed **1 minute** of a 2 h window — bridge the
  gaps by interpolation instead. And a single 82 µV transient at 14:44 made the post-move
  1–15 Hz band look **3.8× worse** under mean-averaged Welch; median-averaged Welch plus a
  median-of-5-min-RMS statistic show the floor was flat. **`spectrum.py` and anything else
  using `max(st, key=npts)` inherits the first bug.**

## 🌟 M4.2 CLOVERDALE — biggest event yet, plus 4 more the same day (2026-07-29)

**USGS: M4.2, 2026-07-29 02:40:06 UTC, 38.777°N 122.936°W, depth 5.9 km — 45.3 km
epicentral / 45.7 km hypocentral, azimuth NW.** Recorded cleanly and unmistakably.
Figures: `reports/2026-07-29-m4.2-cloverdale.png` (shareable),
`reports/2026-07-29-m4.2-cloverdale-look.png` (coda + onset zoom).

| metric | this event | previous best |
|---|---|---|
| detector `peak_ratio` | **8535** | 645 (M2.5 St Helena) |
| harvester SNR | **186** | 35.4 |
| peak (1–15 Hz) | **1406 µV** | 126 µV |
| coda duration (1–15 Hz back to ambient) | **~80 s** | ~25 s |

- **Not remotely clipped.** Raw counts spanned 196,219–491,394 against ±8,388,607 FS —
  the whole event used **~3.5 % of full scale**. Headroom is ~600× the observed peak, so
  gain 64 is in no danger for events of this class; a same-distance M6 would be the first
  to threaten it.
- **Sub-Hz band carried real signal for the first time:** band excess over the 120 s
  pre-event window was **0.5–1 Hz ×50 · 1–5 Hz ×306 · 5–15 Hz ×46 · 15–45 Hz ×5.5** —
  low-band-dominated, the earthquake signature, and by a wider margin than any prior event.
- **Four MORE confirmed events on the same day** (harvester, all three legs):
  M2.2 03:48:38 (aftershock), M1.9 10:48:54 (aftershock), M1.5 13 km NNW of Angwin at
  **28.8 km**, M2.3 20:11:44 (aftershock). That takes the archive from 4 confirmed events
  to **9**, and **M1.9 at 45.9 km is the new smallest-confirmed** (was M2.4 at 43 km).

### 📐 Vp is now MEASURED, not assumed: 5.19 km/s (this was a real error)

The M4.2's first arrival came in at **+9.06 s**, ~1.4 s later than the Vp = 6.0 km/s
prediction of +7.6 s. Ruled out a clock error using our own data — a clock offset is
*constant* with distance, a velocity error *scales* with it:

| event | dist | onset | delay vs Vp 6.0 |
|---|---|---|---|
| M2.5 St Helena | 18.4 km | 3.86 s | +0.79 s |
| M2.5 Geysers | 41.1 km | 8.15 s | +1.30 s |
| **M4.2 Cloverdale** | 45.7 km | 9.06 s | +1.44 s |
| M2.2 aftershock | 45.6 km | 8.90 s | +1.29 s |
| M2.3 aftershock | 45.6 km | 9.38 s | +1.77 s |

The delay scales with distance. Least-squares over the five: **onset = dist / 5.19 km/s
+ 0.30 s**, residuals ≤ 0.3 s over 18–46 km. The +0.30 s intercept is the envelope
detector's own lag (5× threshold on a 0.3 s smoother), not a clock offset — a
pure-clock fit needs +1.32 s with 0.32 s of unexplained spread. **The station clock is
fine; Vp = 6.0 was too fast for these shallow NW paths.** `VP` is now **5.19** (and
`VS` 3.00, keeping Vp/Vs ≈ 1.73) in `eventcheck.py` and `harvest_events.py`; window
placement shifts by ~1.4 s at 45 km, so residuals from earlier harvester runs are not
byte-comparable with new ones. Onset picks: `analysis/` ad-hoc run, method above.

### ⚠️ Peak amplitude under-reads at large magnitude — do not use it as a magnitude proxy

The M4.2's residual is **−0.633**, clearly outside the **−0.16 … −0.31** band the five
M1.5–M2.5 events sit in (and the earlier four M2.4–2.8 events' −0.318 … −0.412). Same
day, same azimuth, same distance for three of them, so this is **not** site or path — it
is **magnitude-dependent**: at M4.2 the source corner frequency drops toward ~1–2 Hz,
where the 4.5 Hz geophone response is falling steeply, so a growing share of the energy
lands below the 1–15 Hz metric. The residual leg still *accepts* it (−1.2 < −0.633 <
0.4), which is the filter working. But the ML-anchored `predict_uv` is only calibrated
in the M1.5–M2.8 range; inverting our peak to a magnitude would read **~1.7× low at
M4.2** and worse above it.

## 🚗 Traffic direction — a road patch gives the symmetry-breaker (2026-07-27)

Charles found the physical source of the "pop" on northbound transits: **broken/patched
pavement on Highway 12, in the NORTHBOUND LANE ONLY** (southbound is smooth). Photo +
measured geometry from satellite:

- **closest approach 336.96 ft** (102.7 m) — and it is essentially the perpendicular foot
- **patch 481.82 ft** (146.9 m), which puts it **344 ft (105 m) along the road** to the NW
  of the closest-approach point

**Why this matters.** A single vertical channel cannot give bearing — that is geometry,
not a sensitivity problem. But a *fixed impulsive source at a known location* breaks the
transit symmetry. Northbound vehicles pass closest approach, THEN hit the patch;
southbound never touch it.

**Falsifiable prediction (UNTESTED):**
- northbound → discrete pop **+4.3 to +6.7 s AFTER** the transit envelope peak (344 ft at
  35–55 mph)
- southbound → **no pop at all**

**⚠️ My first test of this was invalid — do not trust it.** I scored 75 "isolated passes"
overnight and got 7/7 impulses *before* the peak, none after. Three reasons that result
means nothing:
1. It assumes the 5–15 Hz envelope peak is closest approach, and I never verified that.
   Earlier analysis found night events here are **sharp ~1 s features**, not the 8–10 s
   swells a car at 102 m must produce — so the detector may be locking onto impulses, not
   transits, in which case "offset from the peak" measures nothing.
2. Only 7 of 75 candidates carried an impulse (9 %). If every northbound vehicle hits the
   patch and traffic splits evenly, that should be nearer 50 %.
3. The impulses found were 3–7 µV — small for a car striking broken pavement.

**What settles it, cheaply:** watch ONE northbound vehicle pass at a quiet hour and note
the second. That single labelled pass validates the whole chain at once — whether a
transit swell is visible at all, its shape, whether a pop follows, and at what delay.
Everything downstream rests on that unverified assumption.

**Superseded:** the earlier ask for ~20 labelled passes. With a known mechanism, a known
lane and a predicted delay, a handful suffices — and one is enough to validate the
detector.

## 🎯 FOUR confirmed earthquakes — and a detector that finds them (2026-07-27)

The catalogue-driven harvester (`analysis/harvest_events.py`) now identifies every real
event in the archive and rejects the noise, using three independent legs:

| origin (UTC) | M | dist | az | SNR | residual | lo/hi |
|---|---|---|---|---|---|---|
| 2026-07-25 11:31:41 | 2.5 | 18.4 km | ENE | 35.4 | −0.380 | 1.63 |
| 2026-07-27 06:29:25 | 2.5 | 41.1 km | NNW | 12.9 | −0.391 | 6.05 |
| **2026-07-27 15:29:01** | **2.8** | 38.1 km | NNW | 8.8 | −0.412 | 6.88 |
| **2026-07-27 21:35:39** | **2.4** | 43.4 km | NNW | 3.2 | −0.318 | 3.34 |

The last two were **found by the harvester**, not by the STA/LTA or by anyone watching.

**Why three legs and not a threshold.** Over 350 catalogued windows:
- **SNR ≥ 5 alone gives 7** — three of them physically impossible (M0.6 at 249 km,
  M0.7 at 500 km). With 350 windows some simply contain a passing truck.
- **Residual alone** (log₁₀ observed/predicted, scaled from the ML attenuation) is
  remarkable — all four real events fall in **−0.318 … −0.412**, a 0.09 spread across
  18–43 km and 2.5× in magnitude, while false positives sit at **+1.36 … +3.64**. But it
  cannot confirm marginal events: at SNR ~1 the "observed" is noise, and if the
  prediction happens to be a few times that, the residual looks fine by accident.
- **Shape** (1–5 Hz excess ÷ 15–45 Hz excess) is the independent third leg: earthquakes
  are low-band dominated (1.6–6.9), cultural sources are not (0.28–0.45).

Together: **`snr ≥ 3 AND −1.2 < resid < 0.4 AND lo/hi ≥ 1`** → exactly the four real
events, no false positives.

**The constant −0.4 offset is an anchor artefact**, not physics: `REF_PEAK_UV = 126` is a
raw peak from the original STATUS note, while the harvester measures a 1 s smoothed
envelope peak. Setting the anchor near 50 µV centres the residuals on zero.

**Detection threshold, measured rather than scaled:** smallest confirmed is **M2.4 at
43 km**, found at SNR 3.2 on a busy weekday afternoon. All four detections are 18–43 km
and NNW/ENE — nothing yet from the SE, where the Vallejo M2.2 at 54 km was *not* seen
(ray path crosses the Napa–Sonoma marshes; hypothesis recorded, needs months of data).

## 🎉 SECOND CONFIRMED EARTHQUAKE — M2.5, The Geysers (2026-07-27)

**USGS: M2.5, 2026-07-27 06:29:25.4 UTC, 38.798°N 122.781°W, depth 3.5 km — 41.1 km
hypocentral**, more than twice the distance of the first. Detected automatically:
`events.log` 06:29:33, ratio 61.2, peak 55.7 µV, 22.9 s.

**This one was a PREDICTION, which makes it a better validation than the first.**
Scaling the M2.5 at 18.8 km (126 µV) by the California ML attenuation gives 48 µV at
41.1 km; observed 55.7 µV — **16%**. Predicted P at +6.9 s, detector fired at +7.6 s.

**Band signature is unambiguous** (S window vs 120 s pre-event):
`1–5 Hz ×9.4 · 5–15 Hz ×5.6 · 15–45 Hz ×1.4` — all bands up, **low bands most**.
Contrast the 07:20:55 vehicle the same night: 5–15 Hz ×9 with 1–5 Hz *flat*. The two
classes separate cleanly on this alone. Figure: `analysis/geysers_m2.5.png`.

### 🔭 The Geysers is a permanent calibration source — use it as the benchmark

**235 catalogued events in 8 days (~29/day)**, median M0.9, at a fixed 40–50 km. Only
~2/week exceed ~15 µV, but the catalogue supplies origin times, so events far below the
STA/LTA threshold can still be **examined at known times** rather than detected blind:

| class | predicted peak |
|---|---|
| M2.5 @ 41 km | 51 µV (observed 55.7) |
| M2.2 @ 49 km | 19 µV |
| M1.8 @ 45 km | ~9 µV — SNR ~2 on a quiet night, invisible to STA/LTA, findable by cut-and-look |

**This is the instrument metric the project has lacked.** "Noise floor in µV" is
site-contaminated and hard to interpret; **"how many Geysers events can we see"** is
objective, mission-relevant, and directly comparable across hardware changes. Count
before lifting the tile, count after — that is the experiment.

## 🎉 FIRST CONFIRMED EARTHQUAKE — M2.5, 3 km E of St. Helena (2026-07-25)

The station caught its first confirmed local earthquake — the reason it exists.
USGS: **M2.5, 2026-07-25 11:31:41.760 UTC, 38.507°N 122.435°W, depth 6.2 km**
(~19 km hypocentral from Oakmont, on the Maacama/Rodgers Creek system).

- **STA/LTA triggered 11:31:45 UTC** — 4 s after origin. **peak_ratio 645**
  (threshold 4.0; every prior trigger was a false positive under 60), **peak
  ~110–125 µV** vs ~1 µV ambient (**SNR ~100×**), 24 s duration.
- **Waveform (1–15 Hz):** flat noise → sharp **first arrival (P) at 11:31:45.7**
  (jump to ~117 µV, matching the catalog-predicted P) → peak ~126 µV → coda to noise
  by ~11:32:12. Textbook local event.
- **Single-station limit (honesty note):** the **S is buried** — for a close event
  P and S are only ~2.4 s apart and merge into one burst, so S sits in the coda, not
  separately pickable. There is **no independent single-station S–P or distance**;
  the ~19 km is the catalog's. An earlier graphic drew an emergent "P" near the noise
  floor (a +2 s candidate implies an impossible ~10 km/s P velocity) plus an "S–P →
  distance confirms the catalog" annotation — that was **circular** and has been
  removed. What confirms it's a quake is the *network* (BK.CMB, CE.68327 saw it), not
  our single station.
- **This is the calibration reference** the detector/character work was missing
  (`dashboard/CHARACTER.md`: "no confirmed event yet to calibrate against"). Now
  there is ground truth: known M, known distance, clean recording.
- Recorder healthy throughout; the concurrent 24 h UDP probe did **not** perturb
  acquisition. Day-file: `data/XX.OAKMT.00.SHZ.D.2026.206.mseed` (event ~11:31:41 UTC).
- **Shareable image tool:** `analysis/quake_share.py` — parameterized per event (pass
  the catalog facts; measures peak/SNR, marks only phases you can actually pick, and
  renders a labeled hero PNG; it does NOT predict arrivals from the catalog distance —
  predict-then-confirm is circular). This event: `--origin 2026-07-25T11:31:41.760
  --mag 2.5 --event-lat 38.507 --event-lon -122.435 --depth-km 6.2 --p 3.97` (P = the
  measured first arrival; S not pickable). Output: `reports/2026-07-25-m2.5-st-helena.png`.

## ✅ Environmental node LIVE in the garage (2026-07-25)

The CLUE→Pi 4 environmental node (pressure / tilt / temp / humidity, 1 Hz, UTC-stamped
on receipt) is **installed in the garage near the station and logging**. Code in
`env_node/`; `env-logger` systemd service on **pi4env.local**, daily CSVs at
`pi4env:~/env-data/env-YYYY-MM-DD.csv` (schema `utc,clue_mono_s,temp_C,press_hPa,
humid_pct,ax_ms2,ay_ms2,az_ms2`).

- **Hardening from bring-up:** the host log filter now requires all fields numeric
  (drops CircuitPython reboot-banner lines on replug — was writing junk rows); CLUE
  backlight off (board mounted **face down**, sensors up in air).
- **`temp_C` is board self-heat, not ambient — use DELTAS only.** BMP280 is on the CLUE
  PCB and reads conducted self-heat (~constant offset); no case geometry fixes the
  absolute value (backlight-off/face-down/air-exposed all landed ~30–32 °C). Fine for
  the thermal-settling correlation, which wants swings, not absolutes. See
  `env_node/README.md`.
- **Mirror + dashboard DONE (2026-07-25):** the host `seismo-rsync.service` on pi5 now
  also pulls `pi4env.local:~/env-data/` → `~/seismo-data/env/` (= `/data/env` in the
  container) every minute (pi5→pi4env SSH key authorized, host key trusted). The
  dashboard has an **`/env` page** (nav "Environment") — current pressure / temp /
  humidity / tilt tiles + accel + freshness, self-refresh every 15 s off `/env-data`
  (JSON). `temp_C` tile is captioned "read changes, not the absolute". Deployed +
  verified live.
- **Open thread:** the actual question — **does pressure or tilt explain the
  0.02–0.12 Hz undulation?** (needs a day+ of undisturbed garage data first).

## ✅ 24 h UDP loss probe COMPLETE — sets rev-2 redundancy at N=2 (2026-07-25)

Sized the **rev-2 UDP streaming** redundancy (see `doc/rev2-data-plane.md §5`). 24 h,
**864,000 pkts** (10 pps × 512 B) over the real Ethernet-bridge→WiFi path, station→pi5.

- **Result: 0.0073 % loss** (63 of 864k), **0 reorder, 0 dup**. 16 loss events,
  **sporadic across the whole day** (midday, afternoon, evening, *and* 3 am) — random
  interference, **no time-of-day pattern** (the early-7 h "evening peak" guess did not hold).
- **Worst fade 1.4 s** (14 pkts @ 10 pps). Burst histogram (pkts): 1×7, 2×2, 3, 4, 7×2, 8, 9, 14.
- **Decision: fixed N = 2.** At the natural record cadence (~1.75 s/datagram, 100 samples
  @ 57 sps) a 1.4 s fade drops ≤1 datagram, so "send current + previous record" recovers
  **100 % of the observed loss inline** — MTU-safe (~1 KB). Rarer/longer fades → file-backfill
  (would have fired ~16×/day). **No adaptive-N machinery needed.** (Faster batching, e.g.
  0.5 s/datagram, would want N≈4.)
- **Spot test (pre-flight):** 3600 pkts at 512 B & 1400 B, 50 & 5 pps → 0 loss, jitter
  p99 ≤ 41 ms; packet size didn't matter.
- Probe processes finished; `/tmp` scratch (scripts, jsonl, pids) cleaned off both hosts.

## 📏 Instrument characterization from the M2.5 (2026-07-25)

**Absolute amplitude cal reads ~7.5× LOW.** Cross-checked our recorded peak against
**CE.68327** (Kinemetrics EpiSensor, *calibrated*, 19.6 km ≈ our 18.8 km, same vertical
component, same 1–15 Hz band, response-removed from NCEDC metadata):
- CE peak ground velocity **30.6 µm/s** vs ours (nominal 28.8 V/m/s) **4.06 µm/s** →
  **~7.5× deficit**. We're if anything slightly *closer*, so that's a floor on the error.
- **We under-report → over-stated sensitivity.** Likely: the **shunt damping resistor loads
  the 375 Ω coil** (28.8 V/m/s is the *open-circuit* figure; loaded effective sensitivity is
  lower, up to ~3×) and/or the **element sensitivity ≠ datasheet** (mislabeled-listing risk).
  Some fraction is **site response** (CE's site vs our garage slab) — the unquantified
  confound, so 7.5× is the *net* under-scaling, an upper bound on pure instrument error.
- **Effective sensitivity ≈ 28.8 / 7.5 ≈ 3.8 V/(m/s)** as a first empirical anchor.
- **Relative** measurements (our own records over time) UNAFFECTED — internal scale is
  consistent. Only **absolute** ground-motion numbers are ~7.5× low.
- Firm up: also compare CE horizontals + other neighbors, repeat on future quakes, and
  bench-measure the damping-loaded sensitivity to split instrument-vs-site.

## ✅ SWITCHED TO 100 sps — new epoch (2026-07-25)

The station now records **100 sps** (RDATAC, `SEISMO_DRATE=100`/`SEISMO_RATE=100`).
The earlier "switch-or-not maybe" was settled by a back-to-back noise measurement on
the current garage hardware (`rdatac_noise_test.py`, 90 s/case, baseline), which
**reversed the old bring-up call** that 100 sps was noisier:

| median per-10 s band RMS (µV) | 60 sps | 100 sps |
| --- | --- | --- |
| **1–15 Hz** (quake band) | 3.99 | **2.74** (~31 % lower) |
| **3–15 Hz** (detector band) | 3.86 | **2.62** (~32 % lower) |
| 15–28 Hz | 2.57 | 5.69 (60 sps was attenuating near its 30 Hz Nyquist) |
| achieved fs | 60.006 | 99.910 |
| glitches / 90 s | 0 | 5 |

- **Why lower in-band:** higher Nyquist spreads the converter's noise over a wider
  band (lower in-band density) and less HF energy aliases down into the quake band.
- **Read ceiling was a myth** for RDATAC: it sustains 99.91 sps with 5 glitches/90 s.
  The old "~92 sps ceiling" was the legacy per-sample-SYNC path, not RDATAC.
- **Only cost:** 60 Hz mains no longer falls on a sinc notch — it aliases to 40 Hz,
  above the quake band; digital notch in post if a spectrum needs it.
- **Cutover:** live recorder healthy at `rate_est 100.0, dropped 0`; today's 60 sps
  day-file preserved as `*.206.mseed.60sps-epoch`, fresh clean 100 sps `206.mseed`
  started. Dashboard verified live — spectrum Nyquist now reaches 50 Hz. Config
  reasoning updated in `station/waveshare_config.py` + `seismo-recorder.service`.
- **Old 5-min feasibility probe** (for the record): 99.9 sps, ~0.025 % drops,
  ~0.07 % held-sample glitches — corroborated by the above.

## ✅ UDP streaming — Phase-1 step 1 LIVE (2026-07-26)

The station now **streams each miniSEED record to the pi5 over UDP** and the pi5 builds
an **owned archive** from it — the first piece of the rev-2 data plane
(`doc/rev2-data-plane.md`, design pass resolved 2026-07-25). Runs **alongside** the
existing rsync mirror; nothing retired.

- **Station:** `station/udp_publisher.py` — a fail-open publisher thread. The writer
  hands each packed record to it; a paced daemon (record-period paced so the N=2 copies
  are spaced in time) sends `MAGIC|ver|n_records|seq + N×512B` datagrams. `publish()`
  is `put_nowait` drop-on-full → **never blocks or touches the ADC loop.** Enabled by
  `SEISMO_UDP_HOST` in the unit (→ 192.168.5.30:48317, N=2). `health.json` now carries
  `udp_sent`/`udp_dropped`.
- **pi5:** `server/udp_collector.py` + `seismo-collector` systemd service (own venv,
  simplemseed) → `~/seismo-archive/`. Dedups by record start-time (N=2 sends each twice),
  restart-safe (rebuilds the seen-set by scanning the day-file). No firewall on pi5.
- **Verified byte-faithful:** over the streaming window **90/90 in-window records
  arrived, all byte-identical** to the recorder's local day-file — 0 mismatched, 0
  fabricated, `udp_dropped=0`. Records are int32 for now (STEIM2 fill-model is the
  follow-on that lets N=2 also cover the worst 1.4 s fade inline, §14.0).
### ✅ UDP heartbeat + backfill — Phase-1 step 2 LIVE (2026-07-26)

The stream now has its reliability layer.

- **Heartbeat (sec 6):** `station/udp_publisher.py` `Heartbeat` sends a 1 s station→pi5
  JSON pulse on port 48318 — health counters + `hi_seq` (highest data seq, bounds tail
  loss). The collector writes it atomically to `~/seismo-archive/station_health.json`
  (the eventual replacement for the health.json rsync; feeds `/v1/health` in Phase 2).
  Fires regardless of data flow, so its *absence* is the liveness signal.
- **Backfill (sec 14.4):** the collector, on startup and hourly, `ssh`+`rsync`s the
  station's recent local day-files and merges any records missing from the archive
  (dedup by start-time; thread-safe under a lock shared with live ingest). Lazy,
  pi5-initiated, rare-catastrophe recovery — not per-packet plumbing.
- **Verified:** startup backfill healed **+2033** then **+31** records (exactly the
  gaps from the deploy restarts); live stream **`seq_gaps=0`**, `udp_dropped=0`; the
  only ever-residual is the current restart window, which the next cycle converges.
### ⛔ STEIM2 fill-model — tried, worked, then REVERTED (2026-07-26)

**Superseded — see "STEIM2 reverted on the station" below.** The recorder briefly wrote
STEIM2 (encoding 11, `encodeSteim2FrameBlock`, ~210–250 samples/record, ~20 MB/day,
lossless, byte-faithful, dashboard rendered it) — but the pure-Python encoder cost
~211 ms/block on the Pi 2B and starved the read loop (drops ~7×). **Rolled back to int32;
STEIM2 dropped for good in the acquisition/archive path** (int32 miniSEED is valid
FDSN/SeedLink anyway — compression, if ever wanted, is a pi5 *serving-layer* job). The
brief STEIM2 records that landed in the day-files before the revert stay readable (mixed
int32/STEIM2, per-record, lossless).

**Phase 1 is complete** (100 sps · UDP stream · N=2 redundancy · heartbeat · backfill ·
STEIM2).

### ✅ Phase 2 step 1: detector → pi5 (2026-07-26)

STA/LTA detection now also runs on the **pi5**, over the owned archive (`server/detector.py`
+ `stalta.py`, `seismo-detector` service → `<archive>/events.log`). It reuses the exact
`StaLta`, so results match, and it adds the thing the station couldn't do: **retroactive
re-detection** — `detector.py --day 2026.207 --trig 6 ...` re-runs over the whole archive
with tuned thresholds (the surface for killing the false positives).

- **Additive:** the station's inline detector is **still running** (removal is the next
  sub-step, and per house rule needs an explicit go-ahead — it's a working feature).
- **Parity verified:** 10/11 of the station's day-207 events reproduced with identical
  duration/ratio/peak. The 2 diffs are the station re-priming its LTA at today's recorder
  restarts — it actually *missed* a ratio-9 event the continuous pi5 detector caught.
- **Key fix:** feed one StaLta continuously across the frequent small drop-gaps (reset
  only on a real >60 s outage) — matching the station's stream-based behavior. Per-segment
  re-priming had suppressed all but one event.

### ✅ Phase 2 step 2a: /v1 server over the owned archive (2026-07-26)

`seismo-server` (pi5, port 8351) now serves the OWNED data plane via `store.py` — env
swapped to `SEISMO_DATA=~/seismo-archive`, events = the pi5 detector's `events.log`,
health = the heartbeat's `station_health.json`. Verified: `/`, `/v1/health` (rate 100,
`udp_dropped=0`, archive age <1 s), `/v1/events` (pi5 detections), `/v1/live` (fresh ring,
age ~5 s). `/v1/waveform` returns the documented 503 until obspy is added (apt
`python3-obspy` at the dashboard cutover). **Additive** — the dashboard still reads the
mirror; nothing retired.

### ⛔ STEIM2 reverted on the station — Pi 2B too weak to encode (2026-07-26)

STEIM2 fill-encoding worked and was byte-faithful, **but its pure-Python encoder cost
~211 ms/10 s block on the Pi 2B**, and that GIL-holding burst starved the RDATAC read loop:
**drops jumped ~0.05/s (int32) → ~0.35/s (~30k/day).** That trades the *one job* for
archive elegance — wrong on a sensitivity-first box. **Station is back on int32** (drops
confirmed back to ~0.05/s, ~7× lower).

**DECISION (2026-07-26): int32 stays; STEIM2 is not pursued** — not a C encoder, not a
pi5 re-encode. The working config is kept: 44 MB/day is trivial on the disk, and backfill
already heals the rare fade N=2 misses. Thread closed. (`doc/rev2-data-plane.md §14.0`.)

### ⚠️ The ~20 Hz line is a MOUNT RESONANCE — the station is on plastic tile (2026-07-26)

Charles mentioned the garage floor is **inherited plastic interlocking tile**, not bare
slab. Re-measured at 0.012 Hz resolution, the ~20 Hz peak sits at **19.885–20.007 Hz**
across washer spin, dryer, dead quiet, midday and afternoon — a 0.6 % spread — and the
41 Hz peak is **2.03–2.07× it in every case**. Fixed frequency + a 2:1 mode pair is a
**structural resonance the appliances excite**, not a shaft rate they generate. The
"~1195 RPM" reading is **retracted** (`analysis/SOURCES.md`, `dashboard/signatures.json`).

- It dissolves the coincidence that two different machines produced identical lines.
- **New candidate for the 7.5× amplitude deficit:** coupling loss through a compliant
  layer, which is not among the causes STATUS currently lists. Free to test.
- **Fix + test are in `BACKLOG.md` (first item).** Hardware touch → new epoch.
- The live badge's recall is only **59 %** against "an appliance is running" (80/136
  30 s windows over the confirmed 21:16–22:24 laundry period), with regularly
  alternating misses. Charles caught this: the badge was empty while his dryer ran, and
  I had "confirmed" that empty state by reading the detector's own feature to conclude
  nothing was running — circular. The signature detects *excitation*, not the appliance.

### ✅ Live source badge (2026-07-26)

The live page now labels what it can recognise. `dashboard/sources.py` scores the
live ring against `dashboard/signatures.json` (signatures as versioned DATA); a badge
appears in the "Live · last 30 s" header with the detail underneath.

- **Free to run:** `render._live_welch()` memoizes the raw Welch on `t_end`, so the
  display spectrum and the matcher share one FFT per ring update (~3 s) instead of one
  each per 300 ms poll.
- **Soft label**, same doctrine as the character badge: informational, never filters.
  Provisional signatures render light/bordered with a `?`; only `status: active` (seen
  on ≥2 separate days) would render solid.
- **Two guards in the matcher:** epoch (a signature is skipped unless `derived_at_sps`
  matches and `valid_from` has passed — both verified to reject) and an absolute
  `min_asd` floor alongside the peak/shoulder shape term, because the standing 41 Hz
  and 20 Hz lines score ×10 over their own continuum with nothing running.
- **Scored offline against real windows before deploy:** 8/8 true positives (5 washer +
  3 dryer), 7/8 controls correctly negative. The one hit is 2026-07-26T02:00Z, already
  flagged as plausibly an unlabelled real run.
- **Verified in-browser** by intercepting `/live-data` so the real render path runs.
  Nothing was running at deploy time, so the empty state is also confirmed correct
  (19.82 Hz sat at 0.85 µV/√Hz — standing-line level).

### ✅ ADS1256 reset no longer needs the RESET pin (2026-07-26)

The chip is now recovered over SPI — `SDATAC, SDATAC, RESET(0xFE)` with CS cycled
between each (`adc_common._soft_reset`), replacing the RESET-pin pulse.
`CHIP_HARD_RESET_ON_START = False`; the pin is opt-in via `SEISMO_RESET_PIN=1`.
`rdatac.stop()` uses the same sequence.

- **Why:** a bare ADS1256 breakout (LC Tech ADS1256_V1.1, under evaluation) brings out
  only SCLK/DIN/DOUT/CS/DRDY/PDWN — RESET stays on the die. The old recovery would
  simply not exist there, and "chip wedged in RDATAC" bricks every later startup.
- **Proven on the Waveshare** (`station/reset_test.py`, run with the recorder stopped):
  **4/4 rounds genuinely wedged** — reproducing the real *"Received wrong chip ID"* —
  and **4/4 recovered by software alone**, RESET pin untouched.
- **Test-design trap worth remembering:** the first version wedged and re-opened in ONE
  interpreter and "passed" 3/3 on `CS pin already used. Must be exclusive!` — that is
  PiPyADC's class-level GPIO bookkeeping, not a wedged chip. Every phase now runs in
  its own process, which is the only way the hardware is actually asked anything.
- Recorder restarted clean: `rate_est 100.0, clock_err 0.0 ms, dropped 0, udp_dropped 0`.

### 🔎 Alternative ADC board under evaluation — LC Tech ADS1256_V1.1

Bare breakout, considered because the Waveshare's demo-sensor block cost us the whole
pre-2026-07-24 archive and its 5 V AVDD path is faulty. From the board photos:
**ADS1256IDB + 7.680 MHz crystal** (so `CLKIN_FREQUENCY` is unchanged), **ADR03B** 2.5 V
XFET reference (better than the Waveshare's LM285-2.5), **AMS1117-3.3** → 5 V in / 3.3 V
digital, an inductor + 22 µF tantalums on the supplies, and no demo circuitry.

- **The draw:** it is 5 V-only, so AVDD = 5 V and the *buffered* common-mode range is
  0–3 V. A mid-supply bias is 2.5 V, which fits — that is exactly the ✓ row of
  `doc/rev2-frontend.md` §"Open decision", i.e. **buffer-on**, the biggest remaining
  noise lever, currently blocked on the Waveshare's 5 V fault.
- **Must meter before use:** there is an R/C network between header P1 and the ADC
  (~16 resistors, many marked `1000` = 100 Ω, plus C12–C20). Series-R + cap to AGND is
  helpful; a divider to ground would attenuate the signal and load the 385 Ω coil.
  This is the demo-jumper lesson — do not trust the silkscreen, ring it out.
- No RESET on the header (hence the work above). Four unpopulated pads sit next to U3 —
  check whether one is ADS1256 pin 6.
- Swapping the live station starts a **new epoch**. Bench it first.

### ✅ `/history` — browse any past 4 h window (2026-07-26)

The dashboard has a **History** page: `/history?datetime=YYYYmmDDHHMM` renders a drum
for that 4 h window, off the **same interval envelopes the live drum uses** — one npz
load per row, no miniSEED parse, no obspy on the request path.

- **Retention flipped.** `heli_build` used to prune envelopes older than the 4 h live
  window; it now prunes only what predates `SEISMO_EPOCH_START` (default
  `2026-07-25T23:45Z`, the first 100 sps interval). ~20 KB/interval → **~2 MB/day**
  against 87 GB free. `heli_build.py --backfill` is the one-shot that fills the range
  (ran it: 65 intervals; the dir now holds the whole epoch, 1.6 MB).
- **Picker is constrained by what's on disk**, not by epoch-start..now: `_available()`
  reads only the npz *filenames* and offers an hour when its opening hour holds data,
  so 2026-07-25 offers only hour 23 and a not-yet-backfilled range simply can't be
  selected. Changing the date repopulates the hour list client-side and rewrites the
  canonical URL live (shown on the page for copying).
- **Blank rows are real.** A historical window always draws all 16 rows, missing
  intervals included, so the row→time mapping can't silently shift.
- **Scope = current epoch only, on purpose.** Pre-2026-07-25 is 57/60 sps through a
  different front end; offering it behind the same picker would invite exactly the
  like-for-like comparison that isn't valid. The page says so.
- **Operational note:** the live builder only ever builds the last 4 h, so if the
  dashboard is down >4 h a hole appears in the envelope set. `--backfill` heals it.

---

## 🌙 Overnight soak (started 2026-07-26 ~03:30 UTC)

Everything runs; the old rsync path is untouched. **Morning review checklist:**
- **Station acquisition:** `dropped`/`glitches` over a clean restart-free night (int32
  baseline; expect low). `cat seismo.local:~/seismo/health.json`.
- **Link loss:** collector `seq_gaps` + station `udp_dropped` — real WiFi-bridge loss over
  a full day (the honest N=2 stress number). `journalctl -u seismo-collector` on pi5.
- **Backfill:** archive completeness vs the station local file (should self-heal to ~0 gap).
- **Detector:** review `/v1/events` — note the strong 03:14 events (ratio 13.7, **182 µV**;
  ratio 10.8, 157 µV). Real, or cultural? This is the retune surface (`detector.py --day`).
- **Then Phase 2 step 2b — dashboard → `/v1/*`:** add apt `python3-obspy` on pi5 (for
  `/v1/waveform`), point the dashboard at `/v1`, then retire the station's inline detector
  + rsync mirror + live-pull. At that cutover also update the About page (2 edits, both
  currently still accurate): the "rsync-mirrored miniSEED" footer (`seismo_dashboard.py`
  line ~100) → served from `/v1`, and optionally the "Pi 5 renders/serves" line to note it
  now also stores+serves the archive. **STEIM2 is decided/closed — do NOT reopen it.**

## ✅ Galvanic Ethernet isolator INSTALLED and it LOWERED the noise floor (2026-07-23)

Measured, undisturbed, all late-night (comparable cultural noise):

| config | 1–15 Hz RMS | 3–15 Hz | 0.02–0.12 Hz | count range |
|---|---|---|---|---|
| baseline, no isolator (06:00–06:14) | 1.15 µV | 0.88 | 0.96 | 2,857 |
| isolator in, original orientation | 0.74 | 0.61 | 1.16 | 3,392 |
| isolator in, **reversed** (07:13–07:16) | **0.68** | **0.48** | **0.59** | **1,236** |

**~1.6× better in the signal band, ~1.8× in 3–15 Hz, and the DC bias is *more*
stable than without it.** Both orientations agree (it's a symmetric passive part,
so no one-sided shield bond). Keep it installed.

### The trap: this rig needs ~35 min to settle after being HANDLED
The install looked catastrophic for the first 35 minutes — 1–15 Hz hit 14–68 µV
with the DC bias wandering ±10,000 counts — and I (Claude) misread that transient
as a steady state and told Charles to remove the thing that was helping. **Don't
judge this front end for at least 40 minutes after touching it.** Evidence it's
handling, not the device: the initial install took ~35 min to settle, but the
reinstall took ~3 min and the reversal ~2 min. Mechanism is charge injected into a
high-impedance node — the common-mode path is the 2× 100 kΩ bias legs (the
*differential* path is already 375 Ω through the coil, so a shunt won't speed it up).

Diagnostics that separate "electrical fault" from "ground motion" in one number:
- **DC bias stability** (mean counts/minute). No earthquake moves the ADC's
  operating point; a wandering bias is always electrical.
- **Settling time.** A 4.5 Hz geophone rings out in *seconds* even undamped, so a
  minutes-long decay is an electrical node, not mechanics.
- Undervoltage was checked and ruled out: `throttled=0x0`, `in0_lcrit_alarm=0`,
  stable 57.0 sps, no stuck ADC codes. (Note: power is still **micro-USB** — the
  GPIO-header feed is still only a BACKLOG plan.)

**`events.log` is polluted for 06:15–07:13 UTC 2026-07-23** — the STA/LTA fired
every 10–20 s (peaks ~380 µV) through the unsettled period. Annotate/exclude that
window; those detections are not real.

## ⚠️ NEW EPOCH 2026-07-24 ~02:15 UTC — demo jumpers removed from AD0/AD1

**The entire archive before this timestamp was recorded with the Waveshare demo-sensor
jumpers fitted on the differential pair** (the block STATUS.md wrongly recorded as
"not jumpered"). Removing them moved the DC operating point from **0.27 % of FS to
3.96 %** — ~310,000 counts — and that shift **persisted** after VCC was reverted from
5V to 3V3, so it tracks the jumpers, not the supply fault. The input network was
electrically different for every measurement taken before this point.

The split is **analog vs digital**, NOT absolute vs relative. An earlier draft of this
note claimed relative A/B results survived because the network was constant across them.
**That is wrong** and has been retracted: if the parasitic network dominated the noise
budget, every ratio measured through it is compressed toward 1 by an unknown factor — a
real 5× isolator improvement would read as 1.6×. "Constant" is not "transparent", and we
cannot bound the distortion.

- **DEAD — anything measured through the analog front end.** Every noise figure, absolute
  *and* relative: the "electronics floor ~1.17 µV / 41 nm/s"; the **gain-64 / DRATE-60
  selection** from the noise sweep (the optimum may differ now); the **isolator's 1.6×**;
  **RDATAC's "+2.2 % in band"** cost; all **PPSD**; the **~1.002 Hz line** attribution.
  All of it needs re-measuring post-epoch.
- **INTACT — nothing to do with the input network.** The clock work (60.0054 sps,
  ClockAnchor, ±1–3 ms residual); continuity (RDATAC 0 gaps vs 41.2 s/hour legacy); the
  all-zero-frame glitch filter; all software, dashboard and infrastructure.
- **Unaffected qualitatively:** it recorded real ground motion — waveforms, the diurnal
  cultural pattern, the Berkeley M2.1 non-detection.
- **RE-TEST the ~1.002 Hz instrumental line.** It was never attributed, and a trimpot +
  photoresistor on the differential pair were never on the suspect list because this doc
  said the block was unpopulated. If the line is gone post-epoch, that was the cause.
- **First job once settled:** re-measure the noise floor and compare against the historical
  ~1.5 µV ambient / 1.17 µV floor. That quantifies what the old network was doing.

## 🐛 SOLVED 2026-07-24 — the "faux detection" population was a `peak_uv` bug

The long-standing mystery where detections clustered implausibly tightly (204–219 µV,
hour after hour) was **not a physical phenomenon**. `stalta.py` computed
`amp = abs(x) * uv_per_count` from the **raw** count, which carries the front end's DC
operating point — so whenever real signal was smaller than the offset, the reported peak
*was* the offset. Proof: DC sat at 0.27 % of FS = **211 µV** and the cluster was 204–219;
after the epoch change moved DC to 3.96 % = **3094 µV**, the cluster moved with it to
3106–3130. Fixed to use the high-passed `hp`. **Triggering was always correct** (the CF
already used `hp`); only the reported amplitude was wrong — so every `peak_uv` in
`events.log` before 2026-07-24 is garbage, but the detection times are fine.

Charles spotted the thread that led here by eye: pre-epoch noise was **one-sided**
(positive spikes, no negative). Measured: beyond 8σ, **+50 / −0** pre-epoch vs +25/−28
post-epoch; beyond 5σ, 20.6× asymmetric vs 1.02×. Ground motion is symmetric, so that was
a **rectifying nonlinearity** in the signal path — most likely ADS1256 input ESD-diode
conduction (datasheet: keep inputs within −100 mV of AGND and +100 mV of AVDD). It vanished
with the demo jumpers. This is further evidence the pre-epoch archive is not trustworthy.

## 🚗 Site ambient is TRAFFIC-limited, not electronics-limited (2026-07-24)

Charles correlated Highway 12 traffic (~300 ft / ~90 m from the station) with the live
waveform, consistent over dozens of cars: quiet gaps bottom out at **< ~1.5 µV RMS**, and
each passing vehicle drives it well above that. Vehicle-induced Rayleigh waves at 90 m are
a textbook dominant cultural source, broadband ~few Hz–tens of Hz, overlapping the
local-quake band.

**Consequences (do not re-litigate the noise floor without these):**
- The ~1.5 µV quiet floor is **site ambient, not the electronics floor**. Every raw-RMS
  figure taken here (1.17 µV historical, 2.4 µV tonight) is contaminated with real ground
  motion, so it is an *upper bound* on electronics noise, never a measurement of it.
- The **shorted-input floor test** (rev2-frontend.md) is the only clean separator of
  site-ambient vs electronics, and traffic proves the site term is large. Prioritise it.
- Daytime at this site is **cultural-noise-limited**. Pushing the electronics below
  ~1.5 µV only helps in the deep-night quiet window and the microseism band — it is not a
  bug to chase. The RS1D Sleeman self-noise benchmarks are vault instrument noise; our
  working floor is the site.
- Traffic is a **free, repeatable, on-demand test source**: after any front-end change,
  confirm the chain still responds by watching a car, without waiting for a quake.

## 🚗 Traffic training pipeline started (2026-07-24)

Goal: a car-counter trained on observed counts. Charles logs discrete intervals with
`analysis/collect_traffic.py` — a stopwatch CLI: START beep → type `z` (north) / `/`
(south) per vehicle → STOP beep at `--interval` (30s default) → RETURN → appends
`start_utc,end_utc,total,north,south` (creates the CSV with a header). Then
`analysis/traffic_features.py`
joins each interval to the archive and reduces it to features (`rms_uv`, `peak_uv`,
sub-band RMS 1-5/5-15/15-28 Hz, `n_bumps`, coverage) → `<labels>.features.csv`. All
features high-passed (DC/epoch-robust). Offline, no API, no Pi changes — decided over a
live endpoint because labels are interval-based, so windowed archive reduction is the
right tool. `labels.example.csv` is a template.

- **The 5-15 Hz band is the standout discriminator** on real data: ~0.5 µV quiet night
  vs 5-8 µV during the commute (~10-16×), matching the by-eye traffic correlation.
- **`n_bumps` is provisional/weak** — it thresholds against each interval's own median, so
  it misfires on quiet windows and undercounts sustained traffic. Needs a fixed threshold
  from a quiet-epoch baseline (unavailable while traffic-limited). Let real labels decide
  if it survives.
- **Collect each label run within ONE epoch** (no hardware changes mid-session) or the
  transfer function shifts under the features.
- Next: Charles collects real counts → train (start simple: does band RMS regress on
  cars/interval?). A live 1 Hz `/traffic` display is a possible later slice, not needed
  for training.
- **One-off event annotations:** `analysis/log_event.py "label" [--at HH:MM] [--dur s]`
  appends to `analysis/annotations.csv` (`t_start_utc,t_end_utc,label,note`) — known
  discrete events (street sweeper, garbage truck, helicopter) as high-confidence labels.
- **First individually-resolved vehicle (2026-07-24):** a street sweeper at 18:40 UTC and
  its return pass ~18:42 both show clearly — 1–15 Hz RMS 5.6/4.5 µV vs 2.8 quiet (2.0×/
  1.6×), pass 1 a smooth transit swell, pass 2 sharper. Confirms the reframe: heavy/slow
  vehicles resolve cleanly where aggregate car counts washed out. This is the shape of the
  real target (heavy-vehicle detection), and a local microquake would look similar.

## Plan (agreed 2026-07-23)

**Hands off the hardware until the weekend.** Let the current configuration run a
couple of days to get a feel for it, THEN tackle the 5 V AVDD fault (which unblocks
buffer-on, the biggest remaining noise lever -- see `doc/rev2-frontend.md`).

Current configuration = RDATAC **100 sps** epoch (2026-07-25; was 60 sps, see the
switch note above) gapless, galvanic isolator in (reversed), gain 64, garage slab,
**no shunt damping fitted**. (PPSD/template work that started on the `rdatac-60sps`
epoch now has a `rdatac-100sps` successor epoch.) What two
undisturbed days buys, all passive:
- The **spike-rate test** that settles whether the 1-3 min spikes were electrical
  (BACKLOG "Suppress faux (cultural) detections") -- watch the 20:00-23:00 local
  window that ran 130-180/h.
- A meaningful **PPSD** (`analysis/ppsd.py`, epoch `rdatac-60sps`) -- it was
  pointless before because the archive mixed configurations.
- A baseline for the **QC counters** (`health.json`: dropped/glitches/spikes/stalls).
- A chance at a real local event.

Every touch of the rig costs ~35 min of settling and may start a new epoch, so if
something does get changed, write down the time.

## Where we are

**The full analog + digital signal chain is now VALIDATED end to end** (2026-07-19).
Geophone → perfboard front-end (differential + mid-supply bias) → ADS1256 →
SPI → pigpio → PiPyADC → Python → **live browser waveform**. Measured: both
inputs biased at 1.503 V, ~10 µV pp idle noise floor, and a tap kicks the
differential channel to ~235 µV (25× over floor) — clean, responsive motion on
screen. The mechanical base (geophone pocket + Pi 2B mount + cotter retention)
is printed and fits; the geophone is soldered to its XLR cable and validated.

**Station code now lives in the repo** under `station/` (was Pi-only before):
`waveshare_config.py` (our owned board config), `adc_diag.py` (bias/rate/tap
check), `live_view.py` (real-time browser strip-chart on :8347). Deployed to
`seismo.local:~/seismo/station/`; passwordless SSH from the Mac is set up.

**RDATAC CONTINUOUS SAMPLING — DEPLOYED (2026-07-23 08:56 UTC).** The recorder now
free-runs the ADS1256 in read-data-continuous mode (`station/rdatac.py`,
`SEISMO_RDATAC=1` in the unit). Measured: **0 gaps** vs **41.2 s lost per hour** on
the legacy per-sample-SYNC path, exactly **60 sps** declared and achieved (was a
load-dependent 54-57), and DRDY jitter of **1 us** instead of a ~68 ms discontinuity
at every 10 s block boundary.
- The crystal is not a clock: DRDY measures **60.0054 sps** against NTP time, i.e.
  ~90 ppm fast, so timestamping from sample count alone would drift 7.8 s/day.
  `ClockAnchor` predicts from a running anchor and slews a fraction of the error per
  block (cumulative rate estimate + 0.2 gain), holding residual clock error to
  **+/-1-3 ms**. Two independent methods agree on 60.0054.
- **NEW EPOCH.** Declared rate changed 57 -> 60, so files are not mergeable with the
  old archive. The 57 sps day-file was set aside as `*.mseed.57sps-epoch`; PPSD/
  template work starts from this epoch (`analysis/ppsd.py` epoch `rdatac-60sps`).
- A stuck chip (an RDATAC session that died without SDATAC) used to fail every later
  startup with "Received wrong chip ID" -- `adc_common._pin_reset()` now pulses the
  RESET pin before construction, so any tool recovers regardless of how the previous
  process exited.
- **NOISE COST: ~2% in band, ~20% at 15-28 Hz** -- measured BACK-TO-BACK in one
  session (`station/rdatac_noise_test.py`, 150 s per case, median of per-10 s band RMS):

  | case | 1-15 Hz | 3-15 Hz | 15-28 Hz |
  |---|---|---|---|
  | legacy | 0.7425 | 0.4859 | 0.2769 |
  | RDATAC 976 kHz | 0.7590 (+2.2%) | 0.5071 | 0.3334 (+20%) |
  | RDATAC 1.95 MHz | 0.7974 (+7.4%) | 0.5202 | 0.3491 |

  An earlier "+10% in band" figure was WRONG -- it compared windows 40 min apart with
  different ambient noise. Always A/B in the same session.
  The excess is injected HF (digital) noise, and it sits ABOVE the 1-15 Hz working
  band that every analysis path already low-passes -- so it is close to free.
  **Faster SPI is worse** (+7.4%), refuting "shorter burst = less coupling": faster
  edges couple more than the shorter duration saves. Keep 976 kHz.
  **CS cannot be toggled per read** in RDATAC -- releasing it aborts the stream
  (3737/3737 samples came back all-zero), so "CS held low" is not an adjustable
  suspect. Oversampling doesn't help either: per-sample noise scales with DRATE
  bandwidth (that IS what DRATE does), and RDATAC needs one SPI read per conversion,
  so a higher rate injects proportionally more bursts into shorter windows.
- **Glitch filter (needed):** roughly once per 100 s a read lands in the chip's
  register-update window and clocks out `0x000000`. Unfiltered that wrote a 200 uV
  single-sample needle -- enough to trip the STA/LTA and to make the drum look hairy
  (Charles spotted it as "hairy-er"). `rdatac.read()` now returns None for an all-zero
  frame or a late read (DRDY already high), the recorder holds the previous value, and
  the contaminated block's clock update is SKIPPED (the stall makes that boundary's
  wall-clock reading ~one sample period late, which would otherwise slew a fake error
  into the next boundary). Verified: 0 zero-samples, 0 needles, 0 gaps over 379 s.

**The continuous recorder is DONE and validated** (2026-07-19): `recorder.py`
writes gapless miniSEED day-files (`XX.OAKMT.00.SHZ`, int32, ~57 sps, absolute
UTC) that read back clean, with real ambient motion in them (~1.7 µV RMS /
~57 nm/s, above the 41 nm/s electronics floor). So the station **records**.

**DEPLOYED as a systemd service** (`seismo-recorder.service`, 2026-07-19):
enabled (auto-starts on boot), `Restart=always`, clean SIGTERM shutdown. The
station now records 24/7 to `~/seismo/data/*.mseed` unattended.

**Public dashboard — DEPLOYED** (2026-07-20): heavy work runs OFF the 1 GB Pi 2B on
LAN hardware. **Pi 2B = acquire** (recorder + STA/LTA, owns the ADC), **Pi 5 (16 GB,
Dokku) = render/serve**, **Jetson = future ML** (backlog). Live at **https://seismo.mcguinness.ai** (PUBLIC, via Cloudflare Tunnel) — also
`http://seismo.pi5.mcguinness.ai` on the LAN.
- **Public exposure = Cloudflare Tunnel** (`cloudflared` on pi5, systemd service).
  mcguinness.ai is on Cloudflare, so: `cloudflared tunnel login` (interactive, done)
  → `cloudflared tunnel create seismo` → `cloudflared tunnel route dns --overwrite-dns
  seismo seismo.mcguinness.ai` → `/etc/cloudflared/config.yml` (ingress
  `seismo.mcguinness.ai → http://localhost:80`, tunnel id + creds) → `cloudflared
  service install`. Also `dokku domains:add seismo seismo.mcguinness.ai` so nginx
  serves that Host. Outbound-only (no port-forward, home IP hidden), TLS by
  Cloudflare. NO Let's Encrypt (the tunnel handles TLS; Dokku host is LAN-only).
- **Pipeline:** host-level `seismo-rsync.timer` on pi5 mirrors
  `seismo.local:~/seismo/{data,events.log}` → `~/seismo-data/` every minute. Dokku
  app `seismo` (`dashboard/`: FastHTML + ObsPy, Dockerfile) renders helicorder/
  spectrum from the mirror and **proxies** the Pi's live feed (`192.168.4.47:8347`)
  so the acquisition box stays private. pi5→Pi2B SSH set up (pi5 key on seismo).
- **Deploy recipe** (pi5, all `dokku` as user charles; `docker` needs sudo):
  `sudo docker build -t seismo-dash ~/seismo-dashboard` →
  `dokku apps:create seismo` · `dokku storage:mount seismo /home/charles/seismo-data:/data`
  · `dokku config:set --no-restart seismo SEISMO_LIVE_URL=http://192.168.4.47:8347/data SEISMO_PLACE=...`
  · `dokku git:from-image seismo seismo-dash:latest` · `dokku ports:set seismo http:80:5000`.
  (To UPDATE: `sudo docker build` then `dokku ps:rebuild seismo` — `git:from-image`
  with the same tag reports "no changes" and skips.) Note: obspy compiles from source
  (no aarch64 py3.12 wheel) → the Dockerfile needs `build-essential`.
- **Helicorder v2 — DEPLOYED (2026-07-21):** precomputed-envelope drum, off the
  request path. `heli_build.py` reduces each 15-min interval to a fixed-width
  (min,max) envelope npz (`/data/heli`); `heli_render.py` stacks them into a
  1920×1080 drum with NO obspy; `heli_service.py` (daemon thread in the app)
  rebuilds+re-renders only on data change. Request cost is now O(1) served bytes,
  independent of viewers. High-pass 1 Hz kills tilt/drift. Design: `dashboard/
  HELICORDER.md`. Verified live on real 8 h data — scaling defaults look good.
- **Spectrum — still on-demand (SLOW): ~24–37 s per render on the pi5** (re-parses
  the whole day-file + Welch every hit — the same flaw the helicorder used to have).
  Moved OFF the home page onto a dedicated `/spectrum` info page (2026-07-21) so it
  no longer blocks the home load. TODO: give it the same background pre-render
  treatment as the helicorder (see BACKLOG "Helicorder v2").
- **Note:** the "does the 2B need a RAM upgrade" question is moot — it just acquires.

**Detection character badge** (2026-07-22): the detections table now labels each
trigger's waveform *shape* — `impulsive` / `sustained` / `near-threshold` — from
envelope kurtosis + duration-above-25%-of-peak + peak/median SNR, scored on the same
−8/+22 s slice the sparkline already loads (14 ms/event, no extra I/O). Soft label only:
never filters, and NOT an earthquake classifier (a very local quake is impulsive too,
and there's no confirmed event yet to calibrate against). Thresholds measured from 127
real triggers; the backlog's HF/spectral-flatness idea was tested and **refuted** —
see `dashboard/CHARACTER.md`. The sparkline/character fill also moved **off the request
path** into a background thread (it was a ~90 s cold-start hang on the public page).

**Detections moved to `/detections`** (2026-07-23): the table is off the home page and
onto its own nav entry. Every trigger so far is a false positive, so it wasn't worth the
front-page real estate — and the home request no longer kicks off any sparkline/character
work at all (that background fill now only runs when someone opens `/detections`).

**Event detection** (2026-07-20): the recorder runs a streaming **STA/LTA** trigger
(`stalta.py`) inline — 1-pole high-pass (**3 Hz corner since 2026-07-22**, was 1 Hz:
rejects microseism *and* the sub-Hz tilt/settling that was mistriggering faux
high-ratio events — the old gentle 1 Hz pole passed 0.3–0.5 Hz nearly intact) →
energy CF → STA/LTA with the LTA frozen during events. Detections → journal (`EVENT …`), `~/seismo/
events.log` (permanent JSONL), and `/dev/shm/seismo_events.json` (recent, for the
viewer). Tunable via `SEISMO_TRIG`/`STA`/`LTA`/`HP` (default trig 4.0). Feeds the
planned APRS alerts + helicorder event annotation. Wrapped so it can never break
acquisition.

**Real-time viewer** (2026-07-20): the recorder mirrors a rolling 30 s window to
shared memory (`/dev/shm/seismo_live.npz`) from a dedicated publisher thread (no
ADC contention, isolated from the sampling loop). `live_server.py` (its own
`seismo-live.service`, always-on, ADC-free) serves a scrolling waveform at
**http://seismo.local:8347** — real-time viewing that coexists with recording.
(This is why `live_view.py` alone can't run now: the recorder owns the ADC.)
The ring carries `t_end` (UTC epoch of its newest sample, stamped by the station —
the pi5 mirror's mtime is only its own copy time), so the dashboard's strip-chart
draws a **scrolling UTC time axis**: 1 s minor ticks, labels + gridlines every 10 s
(2026-07-22). Falls back to no axis if a ring predates `t_end`.

**Helicorder DONE** (2026-07-19): `analysis/helicorder.py` on the Mac pulls the
Pi's miniSEED (rsync) and renders a classic ObsPy dayplot drum — full loop
closed (geophone → 24/7 recorder → miniSEED → drum). ObsPy lives in a Mac-only
`analysis/.venv`, never on the Pi.

Remaining / refinements: (1) **tune the shunt damping** resistor against a
recorded impulse; (2) **data-continuity** — steady-state recording showed some
small gaps (jitter in the wall-clock-per-block timing, worsened by SSH load
during setup); watch it, and the RDATAC continuous-mode upgrade would remove it;
(3) minor: simplemseed writes a slightly inconsistent word-order flag (ObsPy
warns but reads fine) and int32 (STEIM2 compression later). Case walls/lid
deferred by choice. Crimp ferrules still inbound for permanent termination.

**Deferred work → see `BACKLOG.md`** — notably the **Rev-2 geophone→ADC front-end**
(revisit the input buffer for the noise floor, add an input anti-alias RC /
switched-cap reservoir, cleaner analog supply), plus STEIM2, RDATAC timing, and
the enclosure walls/lid.

### Operating the service (the recorder OWNS the ADC while running)
- Status / live log: `systemctl status seismo-recorder` · `journalctl -u seismo-recorder -f`
- **Before any manual ADC tool** (`live_view.py`, `adc_diag.py`, `noise_compare.py`, `recorder.py`): `sudo systemctl stop seismo-recorder` first, else the ADC is busy (chip-ID error). `sudo systemctl start seismo-recorder` when done.
- Unit lives at `/etc/systemd/system/seismo-recorder.service` (source of truth: `station/seismo-recorder.service`). Config via `Environment=` lines (station/gain/drate).

## Milestone map (bring-up order — specification.md §6)

- [x] **Phase 0** — Pi prepped (OS, SPI, pigpio, PiPyADC)
- [x] **Phase 1** — ADC reads a known source (AA cell → 1.29 V on AIN0)
- [x] **Phase 2a** — geophone connected, twitches on taps (life-check)
- [x] **Enclosure v1** — geophone pocket (`geophone_base.py`, seats solid) + combined Pi/geophone base (`chassis.py`, Pi 2B mount + cotter-pin retention), both printed and fitting
- [x] **ADC-end wiring** — perfboard front-end built + **validated** (bias 1.503 V, 10 µV floor, tap → 235 µV). 2× 100 kΩ bias to VCC/AGND, geophone on a detachable connector, empty shunt socket across AIN0/AIN1.
- [x] **Phase 2b** — differential/biased front-end ✓, live view ✓ (`live_view.py`), gain 64 + **DRATE_60** chosen from a noise sweep (`noise_compare.py`): electronics floor ~1.17 µV RMS / ~41 nm/s, mains-notched, sustainable timing
- [x] **Phase 4a** — **continuous recorder** (`recorder.py`): geophone → gapless miniSEED day-files via simplemseed, validated read-back
- [ ] **Phase 3** — shunt damping resistor (empirical tune to ~0.7 critical) — socket is wired, just needs a value (tune against a recorded impulse)
- [x] **Phase 4b** — recorder deployed as a **systemd service** (`seismo-recorder.service`, enabled/auto-start, 24/7)
- [x] **Phase 4c** — helicorder drum view (`analysis/helicorder.py`, Mac-side ObsPy dayplot vs the Pi's miniSEED)
- [~] **Phase 5** — record a real event; cross-check vs USGS / nearby Raspberry Shake.
  **Capability demonstrated 2026-07-24:** first correlation of readings to an external
  physical event — Hwy 12 traffic (~90 m), repeatable over dozens of cars. This closes the
  forward link world→ground→sensor→screen and proves the station resolves a weak, near,
  impulsive source — the same geometry as a local microquake. Still need an actual
  catalogued earthquake to tick the box, but the chain is now validated end to end against
  a known source, not just self-consistent.

## Hardware as-built

- **Sensor:** LGT-4.5 bare 1" element. Coil **385 Ω** measured. **25.4 mm ⌀ × 36 mm, 74 g.** Bottom = flat rim + central recess. Top = offset green board, two solder pins (one `+`, one marked; **red wire = +, white = −** on our cable).
- **ADC:** Waveshare High-Precision AD/DA (ADS1256).
- **Pi:** Raspberry Pi **2B** (32-bit), Bookworm Lite 32-bit, `seismo.local`, USB Wi-Fi dongle. PSU 5 V / 2.5 A.
- **Station:** `XX.OAKMT.00.SHZ` — vertical, 4.5 Hz. Location **38.451817°N, −122.621049°W** (Oakmont, Santa Rosa; measured at the sensor). Used by `analysis/eventcheck.py` for distance/travel-times.
- **Cable:** salvaged **XLR** (shielded twisted pair), ~1 m, coiled slack. red=+/white=−, braid=shield. **Soldered to the geophone + validated** (ohms + movement). Ends tinned for test insertion; **re-terminate with crimp ferrules** for the permanent build — tinned strands cold-flow/loosen under screw terminals. Shield → AGND at the board end only.

## Software as-built (on the Pi, `~/seismo`)

- venv `~/seismo/venv` (`--system-site-packages` → sees apt `python3-pigpio`).
- PiPyADC cloned + `pip install ./PiPyADC`. pigpio backend (fine on Pi 2B; the Pi-5 lgpio issue does NOT apply).
- `pigpiod` enabled at boot. Run demo: `cd ~/seismo/PiPyADC/examples/waveshare_board && source ~/seismo/venv/bin/activate && python waveshare_example.py`
- **Shim:** installed PiPyADC lacks context-manager support; patched the example `with ADS1256(...) as ads:` → `for ads in [ADS1256(...)]:`. Temporary — replace with our own sampler.

## Analog front-end (AS-BUILT + validated 2026-07-19)

Built on a **perfboard** (the ADS1256 screw strip was too cramped for 2 resistors
+ 3 wires + a bare shield without shorts). Three connectors on the board:
geophone-in (detachable), ADC-out (AIN0/AIN1/VCC/AGND), shunt socket.

- **Differential** read: geophone across **AIN0 (+) / AIN1 (−)**. Floating bipolar
  source, so it needs a common-mode bias regardless; differential also rejects hum
  (pairs with the shielded twisted pair).
- **Bias:** two **100 kΩ** resistors — R1 AIN0→VCC, R2 AIN1→AGND — pull the coil to
  mid-supply. Measured 1.503 V on both legs (≈AVDD/2; a hair low from unbuffered
  input bias current through the 100 k legs — harmless, symmetric). 100 k keeps the
  bias network invisible to the geophone (~200 kΩ across a 385 Ω coil), so damping
  stays independent of bias.
- **Input buffer OFF** (`status=0x00`). With AVDD on the 3V3 jumper the *buffered*
  common-mode range is only 0–1.3 V, but our bias sits at ~1.5 V — buffer on
  mangled the reads (chased this as a phantom wiring fault first). Buffer off gives
  the full 0–AVDD range; we don't need its high Zin (source is ~385 Ω).
- **Shunt (damping) resistor across AIN0/AIN1** goes in a **2-pin socket on the
  perfboard** (moved off the ADC screw terminals) — swappable by hand. Empty for
  now; tune empirically (~3–13 kΩ; clean single overshoot on the sampler).
- **Shield → AGND at the board end only** (floating at the geophone) — no ground loop.
- Coil is ~pure **385 Ω** in-band (measured; X_L ≈ 5 Ω @ 4.5 Hz negligible) — resistive network.
- **Sample rate:** DRDY-paced read sustains **~92 sps** at DRATE_100 on the Pi 2B
  (per-sample SYNC overhead nips just under the 100 nominal). Fine for viewing;
  the recorder will need a decide-the-rate strategy (accept ~92, or run DRATE_500
  and decimate to a clean 100).

## Enclosure

- `parts/geophone_base.py`: 25.8 mm bore (25.4 + 0.4), 36 mm deep, flat coupling floor, wire-exit notch. **31.8 mm ⌀ × 40 mm.** Prints flat-base-down, no supports.
- **Boss removed (ink test, 2026-07-17):** a 2 mm centering boss bottomed out in the geophone's shallow ~1 mm bottom recess and lifted it — ink transferred only at the center. Removed; flat floor now, glove-fit bore centers it. **Reprinted + re-inked: full rim contact, seats solid. ✓**
- **Mount = museum putty** on the flanks (NOT under the element — a compliant layer under a vertical geophone would low-pass the signal). No printed clamp.
- `parts/chassis.py`: combined base — geophone pocket (+X, port-free DSI end) + Raspberry Pi 2B mount. **~148 × 68 mm** (fits A1 Mini). Pi held by 2 locating pins in the free GPIO-side holes + 1 flat support post between the USB-side standoff nuts; pins stand proud with a transverse **cotter-pin hole** (1.5 mm, axis ⊥ the GPIO header for wire access; solid wire / improvised cotter) that retains the board. (Pi mount hole lightly filed to accept the 2.6 mm pin — future reprints could shave `pin_dia` ~0.1 mm to avoid that.) **Layout confirmed against the real Pi 2B:** GPIO/pins on −Y long edge; power/HDMI/nuts/HAT-terminals on +Y; USB/Ethernet/dongle on −X short edge; geophone on +X. **Printed and fits — Pi, geophone, and cotter all good.**
- Still to model (Pi/ADC side): **walls** (power-connector cutout on +Y, Wi-Fi **dongle slot** on −X) + a **lid**. Single combined case, flat base, no leveling feet. Consider a plate slot between Pi and pocket to break the vibration path.
- **Gen-1 geophone case (2026-07-28) — DESIGN DONE AND VALIDATED, printing scheduled 2026-07-29.**
  **Resume here:** slice `stl/geophone_case.stl` floor-down and `stl/geophone_case_lid.stl` flat — 0.28 mm layers, 4 walls, 6 top/bottom, 40% gyroid, **no supports**, brim if adhesion is marginal (~200 g, 7–9 h body, <1 h lid). Assemble in this order: (1) XLR into its seat, 2 × M3 × 10 countersunk + nuts, **before the geophone** or there is no hand room; (2) twisted 26 AWG to pins 2/3, pin 1 to nothing, ~60 mm service loop hot-glued to the wall; (3) geophone into the pocket on putty, standing 2 mm proud of the rim; (4) lid on 4 sheet-metal screws, 3 more as feet. Nothing is unresolved — both the geometry and the print orientation are validated on coupons.
  **Still the bigger lever, and independent of the case:** cut the plastic floor tile out from under the station and re-measure on bare concrete (`BACKLOG.md`, "⚠️ COUPLING"). New epoch, ~35 min to settle. `parts/geophone_case.py` + `parts/geophone_case_lid.py`. A deliberately crude POC whose only jobs are *pick it up and set it down* and *put the XLR on the case so the cable unplugs*. **116 × 116 × 79 mm** (74 body + 5 lid, plus ~4 mm of foot screw) rounded square, PLA, no seals, no ballast, no inserts. 30 mm of headroom over the element for terminals, wire and slack. Lid engraved "GEOPHONE". Element stands **2 mm proud of the cup rim** (cup 34 vs element 36) — flush meant any real variation put the rim high, and a hold-down pad cannot drop into the bore alongside the element (0.2 mm radial), so the element has to come up. Two **tall clamp bosses** (top 6 mm above the element) flank the cup as anchors; **no clamp fitted in gen 1** — the element is vertical under 1 g so the rim contact is never in tension at seismic amplitudes and gravity is already the preload. Any future hold-down must be COMPLIANT (silicone O-ring or extension spring over the bosses, with a printed saddle clear of the terminal pins); not paracord, which creeps and silently loses preload, and not rigid PLA, which at ~560 N/mm swings ±80 N on print tolerance alone. Three screw heads as feet (three-point contact; also lets the floor print flat on the bed instead of bridging over printed feet; ~1.4° of tilt per turn, which is the only leveling it has and enough). **No vents** — no heat source inside and the cavity's lowest acoustic mode is ~1.5 kHz, 30× above Nyquist, so they bought nothing and cost a convection path over the element. **XLR mount — VALIDATED on the printed coupon, 2026-07-28, twice.** Flat first (geometry: connector passes the bore, flange seats, panel and nut landing good), then **reprinted standing on edge in the case's wall orientation** — the flat print had put the bore axis vertical, so it never tested the overhang the real wall has. Vertical print at case layer height: bore, screw holes and pad underside all print clean, connector still passes. **No supports needed anywhere.** Connector passes the bore, flange seats in the recess, panel thickness and nut landing all good; the case carries the same geometry, so it is ready to print.
- **XLR mount detail.** Connector: 22 mm shell but the shank carries four slots/ribs (three centring + one release-lever) → **24 mm bore**, the published cutout, which is oversized precisely so those clear rather than engage; 23 mm fouls them and the connector will not pass; flange **30 × 25 × ~2 mm**; two countersunk holes 30 mm centre-to-centre on a diagonal. Offsets are the published D-series pattern — **±(10, 11.5) mm** from the bore centre, larger offset on the flange's 30 mm axis — spanning 30.5 mm, which reproduces the measurement. Panel screw holes **3.4 mm (M3)**: the measured 5 mm is the countersink's outer diameter — the standard flange takes countersunk M3 — and at a 24 mm bore a 5 mm hole leaves only 0.74 mm of web to the bore, vs 1.54 mm at 3.4. **The flange seats in a recess in a raised pad on the OUTSIDE wall**: pad 38 × 38 standing 1.5 mm proud, flange footprint recessed 2.0 mm into it → flange flush, **2.5 mm of panel** under it (inside the connector's 1–3 mm range). The recess is structural, not cosmetic — it carries the latch's lateral and torsional load in shear through plastic so the two screws only clamp. Nothing on the inside face: the case is a rounded square so that wall is already flat, and an inside pocket cannot restrain a flange bearing on the outside. Flange runs **30 mm axis vertical** (`xlr_flange_axis = "V"`) — a free choice of how to mount it, not a property of the connector, picked because it puts the screws 23 mm apart vertically instead of 20 against a hanging cable. `parts/xlr_coupon.py` is a 56 × 56 × 4.5 mm fit test (~10 min) reproducing the wall cross-section exactly; it carries all four sign combinations of the hole pattern so handedness never has to be established (two holes take screws, two hide under the flange). **Fasteners: 7 × #6 × ½″ sheet-metal (4 lid, 3 feet) + 2 × M3 × 10 countersunk + nuts for the XLR** (grip is just 4.5 mm; flat head seats in the flange countersink, no washer needed). Fit the connector before the geophone goes in.
- **Internal wiring (gen-1 case).** 26 AWG fine-stranded, silicone jacket, **twisted ~5 turns/inch** — the loop area between the two conductors is the magnetic-pickup antenna and any EMF induced there is in series with the 375 Ω coil, i.e. indistinguishable from signal. Not solid core (fatigues, and stiff enough to preload the element in its pocket). `+` → XLR **pin 2**, other → **pin 3**, **pin 1 unconnected** so the cable shield stays grounded at the Pi end only. **~60 mm service loop**, coiled along the wall and tacked with hot glue so nothing bears on the element — the pocket is 36 mm deep, so the lead must be long enough to lift the element fully clear and rest it on the rim rather than soldering down a hole. **No in-line JST/connector** — a tin crimp is a thermoelectric junction worth ~µV/°C against a ~1.6 µV noise floor, with two per conductor, drifting straight into the sub-Hz band where the thermal problem already lives; and it buys nothing, since the XLR *is* the service disconnect and swapping the element is two solder joints. If a disconnect is ever genuinely needed, gold contacts, not JST.
- **Servicing: the XLR belongs to the CASE, not the sensor, and never comes out.** It cannot be withdrawn with wires attached anyway — 22 mm shell in a 24 mm bore is 1.0 mm of annular gap and a twisted 26 AWG pair is ~2.4 mm across. Both service operations are therefore the same two joints at the ELEMENT end: swapping the geophone leaves the connector in place, and swapping the case (gen 2) also leaves it, because gen 2 takes the outdoor TOP-series connector, not this one. So the XLR solder cups are soldered exactly once — make them neat and heat-shrink them; keep the element-end joints tidy and accessible. Views: `doc/geophone_case*.svg`.
- The sealed/outdoor version is **gen-2**, specced separately in `doc/BOM-geophone-case.md`.

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

## Open threads (pick next session)

1. **Wire the ADC end** — differential + bias network + shunt in the screw terminals.
2. **Fast sampler** — read AD0/AD1 differentially at 100–200 sps, log + plot. ← software gate
3. **Tune the damping shunt** against the observed ring.
4. **Model the case walls + lid** (power cutout on +Y, dongle slot on −X; the Pi/geophone base is done) — mechanical, non-blocking.
5. Resolve the **5 V AVDD** jumper safely (noise floor).
6. Station software (miniSEED/helicorder) — `will127534/RaspberryPi-seismograph` is thin/stale; reassess.

# Source catalog — what shakes XX.OAKMT.00.SHZ

Identified sources, with the numbers that tell them apart. Windows are logged in
`annotations.csv` (via `log_event.py`); fingerprints are reproduced with
`source_signature.py`:

```
source_signature.py <day-file> --label "washing machine spin"
source_signature.py <day-file> --start 19:10:29 --end 19:10:41
```

All figures are 100 sps epoch (from 2026-07-25T23:39Z) unless noted.

## The two discriminators

**1. Where the energy sits.** Frequencies above ~15 Hz do not survive propagation —
anelastic attenuation strips them within a few km. So:

- energy in **1–15 Hz, all bands up together** → a real seismic source at distance
- energy **only in 15–45 Hz, quake band flat** → something mechanical within metres,
  coupling into the slab rather than arriving as a wave

**2. Whether there is a spectral line.** Rotating machinery puts a narrow peak at
its shaft rate; impacts, vehicles and earthquakes are broadband.

> **Trap:** this station carries *standing* lines — a persistent one near **41 Hz**
> and a weaker one near **20 Hz** — that score 10× over their local continuum in
> dead quiet. A continuum ratio alone will call them machinery. A line only belongs
> to the source if its **amplitude grows against a quiet reference window**.
> `source_signature.py` checks this; the earlier ~1.002 Hz instrumental line is the
> same genus of artifact (see STATUS.md).

## Catalog

| source | 1–5 Hz | 5–15 Hz | 15–45 Hz | line | verdict |
|---|---|---|---|---|---|
| **M2.5 St Helena, 19 km** (2026-07-25 11:31:44, 60 sps epoch) | **×17.7** | **×20.7** | ×11.7 | none | all bands up, low bands most — *the* earthquake reference |
| **garage appliance** — washer (5 bursts) *and* dryer, 2026-07-26 20:25–21:37 | ×1.0 | ×1.1 | ×2.6 | **19.3–20.0 Hz, ×12 over quiet** | detects the appliance; **cannot** say which |
| **street sweeper** (2026-07-24 18:40) | ×2.1 | ×1.6 | ×4.6 | none | vehicle, close but outside |
| **unidentified near-field** (2026-07-26 19:10:29, 13 s) | ×1.5 | ×1.0 | **×5.3** | none | impact/vehicle at metres — see below |
| **"garbage cans in"** (2026-07-26 03:12) | ×1.4 | ×2.2 | ×1.5 | 41 Hz **standing, not the source** | window is contaminated — see below |

### ⚠️ The ~20 Hz line is a MOUNT RESONANCE, not a machine (corrected 2026-07-26)

Everything below about a "~1200 RPM shaft rate" is **retracted**. Measured at 0.012 Hz
resolution, the peak sits at **19.885–20.007 Hz** across washer spin, "dryer", dead
quiet, midday and afternoon — a 0.6 % spread — and the 41 Hz peak is **2.03–2.07× it in
every case**. A spin cycle ramping through speeds would sweep far more than that. Fixed
frequency plus a 2:1 mode pair is a **structural resonance**, which the appliances
*excite* rather than create. That is also why two different machines produced identical
lines: they were never machine rates.

**Prime suspect: the geophone is not on the slab.** The garage has inherited plastic
interlocking tile — compliant, hollow, and exactly the panel geometry that resonates in
the tens of Hz with a harmonic pair.

**Three confirmed sources ring it: washer, dryer, A/C.** Charles caught the
"Laundry suspected" pill twice — once with only the dryer running, once with *only the
A/C* running. Renamed to "Household activity".

**Mode ratio (41 Hz / 20 Hz) is a PARTIAL fingerprint:**

| source | ratio |
|---|---|
| washer spin | **0.12–0.27** |
| clothes dryer (confirmed on *and* off) | 1.04–1.08 |
| air conditioning (confirmed) | 1.10–1.55 |
| garbage cans | 1.47 |

It separates the washer from everything else with a wide clean gap, but does **not**
separate dryer / A-C / cans from each other. Likely reflects the drive spectrum rather
than source location: energy concentrated near 20 Hz excites mode 1 selectively, while
broadband sources ring both modes. Note this feature is a property of the FLOOR — it
disappears when the tile does.

**It is a household-activity detector, not a laundry one.** Sampling 30 s windows
each minute across 2026-07-26/27:

| window (local) | excited |
|---|---|
| 14:16–15:26, laundry confirmed running | 59 % |
| 15:30–17:00, **after the dryer stopped** | **79 %** |
| 17:00–19:00 | 63 % |
| 19:00–20:00 | 58 % |
| 23:00–05:00 deep night | **2 %** |

Excitation *rose* after the dryer stopped and runs 58–79 % through the afternoon and
evening against 2 % overnight. Anything moving in the house rings the floor. (The 2 %
overnight also shows the rule is not merely firing on noise.)

**Recall is 59 %, not ~100 %.** Over the confirmed 21:16–22:24 laundry period only
80/136 thirty-second windows match, and the misses alternate regularly (ON 300 s / off
330 / ON 510 / off 330 …). It detects *excitation of the resonance*, not the appliance.

### (superseded) Garage appliance (~20 Hz line)

Five bursts on 2026-07-26, 139–475 s each, gaps shortening 664 → 424 → 183 → 164 s.

- **Energy is 15–45 Hz only.** The quake band does not move (1–5 Hz ×1.0, 5–15 Hz
  ×1.1). On the live strip-chart this reads as a raised, hairy trace with the
  `rms(1–15 Hz)` HUD figure barely changed — 7.41 µV total vs 2.18 µV in-band.
- **A narrow line at 19.4–20.0 Hz**, 5.0–8.8 µV/√Hz, ×12–26 over the local continuum
  *and* ×12 over the same frequency in the gaps between bursts. That is **1163–1198
  RPM** read as a shaft rate — a textbook ~1200 RPM final spin.
- **~41 Hz is NOT its second harmonic.** 41 Hz sits at 1.11–1.19 µV/√Hz during a
  spin and 0.74–1.37 in quiet: unchanged. It is a standing line.

#### The dryer falsified the "washer" label within the hour

Charles reported the clothes dryer running at 21:16–21:37 UTC. It produces the
**same line at 19.92–20.02 Hz**, ASD 4.2–7.6 µV/√Hz, at the same strength:

| | line ~20 Hz | 15–45 Hz broadband (line excluded) | line/broadband |
|---|---|---|---|
| washer, 5 windows | 4.8–9.5 | 0.31–0.37 | 14–28 |
| dryer, 4 windows | 4.2–7.6 | 0.27–0.34 | 16–22 |

Complete overlap on every feature tried. The original entry was written as
`washer-spin` with "a dryer would look the same" as a *hypothetical caveat*; one
hour later it was a measurement. The signature is now `garage-appliance-20hz` and
claims only what it can support.

This is the workflow working, not failing — a signature made a falsifiable claim
and got falsified by the next observation.

**Untried angle for separating them:** duty-cycle shape. The washer ran in bursts
of 139–475 s with gaps shortening 664 → 424 → 183 → 164 s; the dryer runs longer
and steadier. That is a time-domain feature, not a spectral one, and it needs a
second observation of each before it means anything.

### A/C: two-stage shutdown, and a start transient (2026-07-27)

Charles called out A/C transitions live; all three were witnessed and land on steps in
the record. 15–45 Hz 1 s envelope:

| time (UTC) | envelope | event |
|---|---|---|
| …–05:16:48 | 3.8 | compressor + blower |
| **05:16:48** | → 2.2 | **compressor stops** (recovered from the record; Charles hadn't noted it) |
| **05:17:50** | → 0.7 | **blower stops** — Charles's reported time, landing on the sample |
| 05:19–05:25 | 0.7–1.0 | confirmed quiet, household seated, detector correctly silent |
| **05:29:47** | → 3.8 | **restart**, compressor and blower together |

**The two-stage shutdown REPEATS with a fixed ~60 s lag** — confirmed on a second
witnessed stop, so it is a mechanical property of the unit (blower post-purge pulling
the remaining cooling off the coil), not a coincidence:

| run | compressor off | blower off | lag |
|---|---|---|---|
| 1 | 05:16:48 | 05:17:50 | **62 s** |
| 2 | 05:38:46 | 05:39:45 | **59 s** |
| 3 | 06:03:48 | 06:04:47 | **59 s** |

**Three repeatable amplitude levels** (15–45 Hz RMS), consistent across all runs:
both running **3.8–4.5 µV** · blower only **2.2–2.5 µV** · off **0.8–0.9 µV**. A
three-state machine with a fixed ~60 s dwell in the middle on the way down — no
spectral information required.

⚠️ **The start transient is NOT confirmed.** It rests on ONE observation (05:29:47,
23 µV vs ~3 µV). A test was designed around Charles reporting "blower just kicked on"
at 05:55 — if blower-only produced no jolt, the transient would be compressor inrush.
The start showed ratio 0.6 (no transient), but run 3's two-stage stop proves the
COMPRESSOR WAS RUNNING, so the premise was false and the test proved nothing. The
ratio-0.6 reading was the contaminated-baseline artifact already flagged (a 20 µV
excursion sat in the 20 s before the edge). Needs a genuinely blower-only cycle, or
simply more starts.

Run 2 envelope: 4.38 → 2.56 → 0.83 µV. Charles reported "10:40" for run 2, 15 s after
the measured edge — what a rounded human report should look like.

**This is the strongest A/C fingerprint we have.** Washer and dryer stop in one step; a
high→medium→low decay with a repeatable ~60 s dwell needs no spectral information, and
like the start transient it is a property of the MACHINE, not the floor — so it survives
the move onto slab.

**The start carries a transient; the stop does not.** At 05:29:47 the raw trace hits
**+23/−21 µV** against ~±3 µV in the preceding ten seconds — ~7× — broadband, largest in
15–45 Hz, riding exactly on the step. The blower stop shows only a clean step down.
Consistent with motor inrush / the unit rocking on its mounts at engagement. Verified
on BOTH witnessed stops: peak within ±2 s of the edge is *lower* than the peak in the
preceding 20 s (8.6 vs 11.1 µV; 12.9 vs 15.9), against 23 µV vs ~3 µV at the start.
Charles independently called this by eye — "no transient that I see on blower stop,
just less noise".

Charles spotted these by eye on the helicorder first ("littered through it").

**Why this matters more than the mode ratio:** it is discrete, timestamped, large, and
repeats every cycle — so it can auto-generate dozens of labelled events a day instead of
needing a human to call each source out. And unlike the mode ratio it is **not a property
of the tile**, so it should survive the move onto slab.

**A/C mode ratio repeats across runs:** 1.10–1.55 (run 1), 1.00–1.44 (run 2).

### The 19:10 event — near-field, but not the washer

2026-07-26T19:10:29 UTC, 12.8 s, STA/LTA 14.9, peak 84.8 µV. 15–45 Hz jumps ×5.3
while 5–15 Hz is flat (×0.99), so it is within metres. But there is **no line**
(strongest peak ×3.2 over continuum, broadband), so it is not rotating machinery
and specifically **not the washing machine**. Impact-like: rise 0.52 s, peak +2.2 s,
decay 0.31 s. USGS lists no event within 300 km in that ten-minute window.

Best remaining guesses: garage door, a vehicle in the driveway, something set down
hard. Unresolved — kept labelled `unidentified near-field` rather than guessed.

### The 03:12 window is contaminated

Logged as "garbage cans in", but the signature shows a strong **41 Hz standing line
at 8.04 µV/√Hz** (6× its usual level) *and* a 20 Hz line at 5.85. Something else was
running. Do **not** use this window as a clean single-source training label until
it is re-observed.

## How to add a source

1. Note it while it happens: `log_event.py "label" --at HH:MM:SS --end HH:MM:SS`
   (or `--dur`). Times are UTC unless you pass `--offset-hours -7`.
2. Wait for the archive to catch up, then `source_signature.py <day-file> --label "…"`.
3. If the line verdict says "LINE from this source", record the frequency and the
   implied RPM — that is the identity. If it says "standing line", the peak belongs
   to the instrument, not the source.
4. Add a row above.

## Heat-pump AC (identified 2026-08-26)

Pure tones at **41.0 / 40.6 / 37.65 Hz** (compressor, two speeds) and **19.3 Hz** (fan),
nothing below 15 Hz; on ~65 % of minutes on a hot day, 10–30 min cycles overnight,
on/off edges ~8–10 s after a minute boundary (the thermostat's 1-min tick). The
**20.0 Hz** line is the same machine's evening high stage. Outdoor unit on the ground
by the garage, ground-coupled into the slab. These were the "41 Hz / 19.95 Hz
instrumental lines" — they are not instrumental. Track per minute with the 41 Hz
line-to-neighbour power ratio. 40.0 Hz is the 60 Hz mains alias; 1.05 Hz remains the
one unexplained line.

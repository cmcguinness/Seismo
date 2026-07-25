# reports — cataloged station examples

Curated, share-worthy examples of what the station has recorded. Images are
generated from the archive by [`analysis/quake_share.py`](../analysis/quake_share.py)
(see its docstring) and can be regenerated any time from the miniSEED day-files.

**Naming:** report images use **descriptive** names. The tool's default output
name is `eq_*.png`, which is gitignored (scratch outputs) — so a curated example
kept here gets a descriptive name and is committed.

## Earthquakes

### 2026-07-25 — M2.5, 3 km E of St. Helena, CA · **first confirmed event**

![M2.5 St. Helena](2026-07-25-m2.5-st-helena.png)

- **USGS:** M2.5, 2026-07-25 11:31:41.760 UTC, 38.507°N 122.435°W, depth 6.2 km —
  ~19 km from Oakmont, on the Maacama/Rodgers Creek system. (Magnitude, location,
  depth, origin time are the catalog's, not ours.)
- **What we measured:** a clean impulsive local event — sharp **first arrival (P) at
  +3.97 s** (11:31:45.73), matching the catalog-predicted P time (~+3.3 s) within our
  clock + velocity-model slop; **peak ~117 µV** against a ~1.4 µV noise floor
  (**SNR ~85×**), ~25 s coda. STA/LTA fired with ratio 645 (every prior trigger a
  false positive under 60).
- **What we can NOT do from one trace:** the **S** is buried — for a close event P
  and S are only ~2.4 s apart and merge into one burst, so S sits in the coda, not
  separately pickable. Therefore **no independent single-station S–P or distance** —
  the ~19 km is the catalog's. (Earlier drafts drew a P near the noise floor and an
  "S–P → distance confirms the catalog" annotation; that was circular and is gone.
  A candidate spike at +2 s implies a ~10 km/s P velocity — too fast for a direct P —
  so it's noise, not the P.)
- **What actually confirms it's an earthquake:** other stations saw it. Nearby
  professionals recorded it too — **BK.CMB** (broadband, ~185 km) and **CE.68327**
  Santa Rosa (Kinemetrics EpiSensor strong-motion) — and their multi-station picks
  are what locate and confirm the event. A single geophone detects; a network confirms.
- Regenerate:
  ```
  analysis/.venv/bin/python analysis/quake_share.py \
    --mseed <XX.OAKMT.00.SHZ.D.2026.206.mseed> \
    --usgs-near 2026-07-25T11:31:45 \
    --p 3.97 --expect-s --spectrogram --out reports/2026-07-25-m2.5-st-helena.png
  # --usgs-near <time> (~the trigger time) auto-fills mag/place/lat/lon/depth/origin from
  # the USGS catalog -- no event id, no site lookup. A no-match => probably cultural noise.
    # envelope is on by default; --spectrogram stacks the time-frequency panel below (one image)
  ```

## Non-detections (the envelope's other edge)

### 2026-07-25 — M3.3, Little America, WY (~1140 km) · **not detected**

![M3.3 Wyoming not detected](2026-07-25-wyoming-m3.3-not-detected.png)

- A distant (~1140 km) M3.3. In the geophone band there is **no arrival** at the
  predicted regional times — Pn(pred) +142 s and Lg(pred) +326 s both sit at ~1×
  the pre-event noise (1-15 Hz: Pn 1.1×, Lg 1.4×; 1-5 Hz: 1.0×/1.0×). The two
  bright bursts near +205 s and +290 s are **local cultural noise**: impulsive,
  broadband to 25 Hz, and unaligned with either predicted phase. A source 1140 km
  away cannot deliver 15-25 Hz energy (high frequencies attenuate first), so
  broadband-impulsive is the signature of something local, not teleseismic.
- This is the useful counter-example to the St. Helena hit: it pins down the
  station's **local-only detection envelope**. Kept here so the two plots sit on the
  **same spectrogram colour ruler** (see below) and can be compared directly.

## Spectrogram standard

Every spectrogram in this repo is drawn by [`analysis/specgram.py`](../analysis/specgram.py)
so they share one absolute colour scale (magma, fixed **−25 .. +25 dB**, 1.5 s window /
0.2 s hop, 0–25 Hz, high-passed full-band µV). The fixed axis is the point: the same
colour is the same absolute power in every figure, so a real event and a non-detection
lie on one ruler. Don't hand-roll spectrograms elsewhere — import `specgram.draw()`.

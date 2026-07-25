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

- **USGS:** M2.5, 2026-07-25 11:31:41 UTC, 38.507°N 122.435°W, depth 6.2 km —
  ~19 km hypocentral from Oakmont, on the Maacama/Rodgers Creek system.
- Clean impulsive local event: emergent **P +2.3 s**, sharp **S +4.73 s**
  (**S–P ≈ 2.4 s → ~19 km**, matching the catalog), **peak ~117 µV**, **SNR ~90×**.
- STA/LTA fired at 11:31:45 with ratio 645 (every prior trigger a false positive
  under 60).
- Independently confirmed by nearby professional stations: **BK.CMB** (broadband,
  185 km, S–P 22 s) and **CE.68327** Santa Rosa (strong-motion, S–P 3 s) — the S–P
  ratios track the distance ratios, same event seen three ways.
- Regenerate:
  ```
  analysis/.venv/bin/python analysis/quake_share.py \
    --mseed <XX.OAKMT.00.SHZ.D.2026.206.mseed> \
    --origin 2026-07-25T11:31:41 --mag 2.5 \
    --place "3 km E of St. Helena, California" \
    --event-lat 38.507 --event-lon -122.435 --depth-km 6.2 \
    --p 2.3 --s 4.73 --out reports/2026-07-25-m2.5-st-helena.png
  ```

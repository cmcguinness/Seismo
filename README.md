# Seismo — a DIY seismic station on the Rodgers Creek fault

A single-channel, sensitivity-first seismometer in a garage in Oakmont, Santa Rosa,
California, recording continuously since 2026-07-20 as station **SS.OAKM1.00.EHZ**.
Live at **https://seismo.mcguinness.ai**. The whole thing, hardware to dashboard, was
built by one person working with Claude Code; that is part of the story, not a footnote.

## What it is

- **Sensor:** a 4.5 Hz vertical geophone (LGT-4.5 class, 375 Ω coil), shunt-damped, on
  the slab.
- **Digitizer:** a TI ADS1256 24-bit ADC (Waveshare AD/DA board) on a Raspberry Pi 2B,
  100 sps, PGA 64, with the ADC's data-ready line handled as a kernel interrupt so every
  sample carries a hardware timestamp (`station/adsreader/`, C).
- **Recorder:** miniSEED day-files on an exact 100 sps grid, despiking, an inline
  STA/LTA trigger, and a UDP stream to a second Pi (`station/recorder.py`).
- **Server (Pi 5, LAN):** archive, re-detection, a gradient-boosting trigger classifier
  that scores every trigger before it becomes a push notification, and a JSON API
  (`server/`).
- **Dashboard:** the LAN and public copies are the same image; the public one is fed
  outbound-only by the house (`dashboard/`, Dokku).
- **Analysis (Mac, obspy):** calibration against the USGS strong-motion station NP.1835
  1.64 km away, detection-range fits against the NCEDC catalogue, classifier training,
  spectral work (`analysis/`).
- **Enclosures:** build123d CAD, printed (`parts/`).

## What it has done so far

As of 2026-09-02: 34 catalogue-confirmed earthquakes inside a validated detection range
of 88.8 km for M2, plus an M4.8 off Petrolia at 319 km, verified by arrival time. Every
confirmed event is shown beside NP.1835's record, in ground velocity on the same axes,
at https://seismo.mcguinness.ai/catches.

The comparison against 1835 is the calibration: after one empirical sensitivity factor
the two stations agree to ~1.2x, and `analysis/refstation_spectra.py` shows that ratio is
flat over 5-15 Hz (`doc/refstation-spectra.png`), so the residual is a constant, not a
site effect. The geophone's f0 and damping are still nominal; an inline calibration
injector (`calibrator/`, `doc/BOM-calibrator.md`) is being built to measure them.

## Reproducing the 1835 comparison

```
cd analysis && uv venv && uv pip install -r requirements.txt
# day-files for the events you want go in analysis/data/ (not in the repo)
.venv/bin/python refstation_compare.py --harvest     # per-event ratios -> dashboard/catches/refstation.json
.venv/bin/python refstation_spectra.py               # the ratio vs frequency
```

NP.1835 waveforms and response come from NCEDC's FDSN service at run time. The station
metadata is `station/SS.OAKM1.xml` (`SS` is self-assigned pending a network code).

## Reading the repo

`STATUS.md` is the running log, newest first, with the current-system summary at the
top; `STATUS-ARCHIVE.md` holds everything before 2026-08-20. `BACKLOG.md` is deferred
work. `specification.md` is the original design and the alternatives rejected.
`CLAUDE.md` is the working brief for the AI side of the collaboration and doubles as
the best map of where the code runs.

MIT licensed. Not a professional instrument; treat every number here as a hobbyist's,
checked against a professional station where it could be.

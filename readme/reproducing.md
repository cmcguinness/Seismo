# Reproducing the results

Everything below runs on a laptop against a copy of the station's miniSEED archive. The
archive is not in the repository. Day-files are rsynced from the station (or the Pi 5 archive) into
`analysis/data/` (gitignored); each script says what it needs.

## Setup

```
cd analysis && uv venv && uv pip install -r requirements.txt
```

The station metadata is `station/SS.OAKM1.xml` (`SS` is self-assigned pending a network
code). NP.1835 waveforms and instrument response are fetched from NCEDC's FDSN service at
run time.

## The comparison against NP.1835

The check that matters most. The professional strong-motion accelerometer 1.64 km away
is corrected to ground velocity with its published response; our trace is converted with
the provisional sensitivity of 9.0 V/(m/s), itself measured against this reference; both
are band-passed to 5-15 Hz, above the geophone's 4.5 Hz corner so no response model is
needed on our side. Method and honesty flags are in the docstring of
`analysis/refstation_compare.py`.

```
.venv/bin/python refstation_compare.py --harvest     # per-event ratios -> dashboard/catches/refstation.json
.venv/bin/python refstation_compare.py 2026-07-29T... # side-by-side figures for named events
.venv/bin/python refstation_spectra.py               # the ratio as a function of frequency
```

`refstation_spectra.py` writes `doc/refstation-spectra.png` and `.json`: the stacked
amplitude ratio has a log-log slope near zero over 5-15 Hz, so the residual is a constant
sensitivity factor, not a site effect. Below the geophone corner the ratio is
uncorrected and not claimed.

## The event set and the detection range

```
.venv/bin/python harvest_events.py --days 30 --radius 300   # every catalogued event the archive covers
.venv/bin/python detection_map.py                           # range rings by magnitude -> reports/
```

The harvest cuts the archive at the predicted P and S arrivals for every catalogued
event, whether or not the station triggered, so non-detections are data too. Rows carry
the hardware epoch (`analysis/epochs.py`) so a fit can be restricted to comparable data.
`detection_map.py`'s docstring lists every number on the map and where it comes from,
including the ones that are extrapolation.

## Retraining the trigger classifier

```
.venv/bin/python trigger_dataset.py     # features for every trigger in the pi5 log
.venv/bin/python augment.py             # bury real events in real archive noise (train-only rows)
.venv/bin/python trigger_train.py --aug # grouped cross-validation, then fit -> analysis/models/
```

The features are defined once, in `server/trigger_features.py`, and shared with the
detector on the Pi 5. Every reported metric is computed on real rows; the augmented rows
exist only to supply the weak positives the catalogue is too slow to provide. The
calibration bursts are masked out of the training set by `analysis/calfinder.py`.

## Looking at one event

```
.venv/bin/python eventcheck.py --origin 2026-07-29T... --lat 38.8 --lon -122.9 --mag 4.2 --label Cloverdale
```

Pulls the day-file, computes the epicentral distance and predicted arrivals, and plots
the record with them marked.

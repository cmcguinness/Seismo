# Architecture

This is not just a seismometer; it is a software system that delivers a finished web
page and raw data to downstream users. Three hosts, one repository:

1. **The seismometer itself**, built from a geophone and a Raspberry Pi 2B. Its only job
   is to collect the real-time stream of readings. It consists of two boxes joined by an
   XLR cable: the geophone is isolated by distance from the other electronics to give the
   lowest possible noise floor.
2. **A Raspberry Pi 5**, elsewhere on the home network, which receives the real-time
   stream from the Pi 2B and does the ingest and processing. It is the official raw data
   source.
3. **A public-facing website** on a cloud server, which gives public access to the data
   and the tools built on it.

This differs from the Shake, which puts the geophone and the Pi in a single box and has
that Pi both collect the readings and process them. My initial design mimicked that, but
I discovered that the busier the Pi gets, the more electrical noise it generates, and
the ADC hears it. So acquisition was stripped down to the bare minimum and everything
else moved to another machine. Nothing at the house is reachable from the internet; the
public site is fed outbound-only.

`CLAUDE.md` at the repo root has the host-by-host table with the deploy paths, and is
kept current because the AI side of the project works from it — see
[How this was built](#how-this-was-built) below.

## Station

- **Sensor:** a 4.5 Hz vertical geophone (LGT-4.5 class, 375 Ω coil) on the garage
  slab, in a 3D-printed case (`parts/`, build123d; `doc/BOM-geophone-case.md`).
- **Digitizer:** a TI ADS1256 24-bit ADC (Waveshare AD/DA board) on a Raspberry Pi 2B,
  100 sps, PGA 64, with the ADC's data-ready line handled as a kernel interrupt so every
  sample carries a hardware timestamp (`station/adsreader/`, C).
- **Recorder:** miniSEED day-files on an exact 100 sps grid, despiking, an inline
  STA/LTA trigger, and a UDP stream to the Pi 5 (`station/recorder.py`).
- **Time:** a dedicated stratum-1 clock host on the LAN (a Raspberry Pi 3B+ with a
  Uputronics GPS/RTC HAT, PPS-disciplined chrony, holding to tens of nanoseconds of
  GPS). The station syncs to it over Ethernet with chrony; its error bound is a few
  milliseconds, and every sample is stamped from the kernel interrupt rather than from
  a polling loop. Arrival-time comparisons with the USGS station next door rest on this.
- **Front end:** the analogue path between coil and ADC is in `doc/rev2-frontend.md`;
  the shunt-damping reasoning is `doc/shunt-damping.md`; power is `doc/power-wiring.md`.

## Data engine

- **Server (Pi 5, LAN):** builds the archive from the UDP stream (`server/udp_collector.py`),
  re-detects over it and scores every trigger with a gradient-boosting classifier
  before it becomes a push notification (`server/detector.py`), and serves a JSON API
  (`server/seismo_server.py`). Design notes in `doc/rev2-data-plane.md`.

### The trigger classifier

An STA/LTA trigger fires on anything that gets suddenly louder, which in a residential
garage is mostly cars, doors, footsteps and the heat pump. The station logs roughly
20,000 near-threshold blips a month with a handful of real M1.3–1.8 earthquakes hiding
among them. The question "was that an earthquake?" is a classification problem, so it
is handled as one.

- **What it scores.** Every trigger gets `p_quake`, a probability. At ≥ 0.7 it becomes
  an ntfy push to a phone. Below a peak-to-noise ratio of 10 it is not scored at all —
  that mass of blips is where a model learns to predict blips.
- **The features are deliberately amplitude-*relative*** — band-power fractions across
  1–45 Hz, spectral centroid and dominant frequency, envelope rise and decay times,
  duration, kurtosis, high/low band ratio: seventeen in all, defined once in
  `server/trigger_features.py` and imported by both the trainer and the detector so the
  deployed model cannot drift from what it was fitted on. Absolute amplitudes are
  computed and kept for inspection but never fed to the model, because the front end was
  rebuilt on 2026-08-07 and an amplitude feature would teach it the hardware's history
  instead of the ground's.
- **Judged by grouped cross-validation**, positives grouped by catalogue event so an
  aftershock cannot vouch for its own mainshock, and negatives grouped by day. It is
  scored against the rule it replaced (`hf_lf < 1.4`), because "better than what we
  already had" is the only comparison that means anything.
- **The hard part is that earthquakes are rare.** There are 33 real positives against
  thousands of cultural negatives, and that number is set by how often the ground
  actually moves within reach — about five a week. `analysis/augment.py` buries known
  events in progressively more real archive noise to manufacture the weak, marginal
  positives the catalogue supplies only a handful of. It multiplies the sample count,
  not the information: there are still 33 independent earthquakes in there afterwards.
  Augmented rows are **train-only**, and every reported metric is computed on real ones.
- **A held-out set was frozen on 2026-08-30**, reserving every trigger after
  2026-08-31. Every model before then had seen every row in the archive, so no earlier
  evaluation can honestly call itself out-of-sample: the grouped CV is honest about
  leakage between folds, but not about the many times those same rows informed a choice
  of feature or threshold. Reserved triggers are never fitted, only scored. It cost nothing to start — there was no data
  after it yet — and it is the one thing that cannot be arranged retroactively.

Training runs on the Mac (`analysis/harvest_events.py` → `trigger_dataset.py` →
`augment.py` → `trigger_train.py`); the fitted model is shipped to the Pi 5 by
`deploy.sh`. Neither Pi ever trains anything.

## Public website

- **Dashboard:** the LAN and public copies are the same Docker image (`dashboard/`,
  Dokku); the public one is fed by rsync and a live ring from the house.

## Other tools

- **Analysis (Mac, obspy):** calibration against USGS NP.1835, detection-range fits
  against the NCEDC catalogue, classifier training, spectral work (`analysis/`). See
  [reproducing.md](reproducing.md).
- **Calibration injector:** an ATtiny85 box inline on the geophone cable that fires a
  known current burst four times a day, so the geophone's natural frequency and damping
  can be measured rather than assumed (`calibrator/`, `doc/BOM-calibrator.md`).

## How this was built

Most of the code here was written with **Claude Code**, with me directing rather than
typing. That is worth stating plainly in an architecture document, because it shaped the
architecture.

What it changed:

- **The documentation is load-bearing, not decorative.** `CLAUDE.md`, `STATUS.md` and
  the `doc/` notes carry what a session needs before it can do anything useful: which
  host owns the ADC, why the 41 Hz line is the heat pump and not a fault, which numbers
  are still guesses. Each session starts with no memory of the last, so anything not
  written down does not exist. That turns documentation from a courtesy to posterity —
  paid for now, repaid much later, and therefore permanently deferred — into a working
  input that has to be current today. A change in incentive rather than in discipline,
  and it is why about a third of the non-blank Python lines here are comments or
  docstrings.
- **Long comments explaining *why*.** Several files here open with paragraphs about the
  decision behind them and the alternative that was rejected. That is deliberate. The
  reasoning is the part that is expensive to reconstruct and cheap to lose, whether the
  reader is an AI session or me in six months.
- **More things got measured.** Writing a throwaway script to answer "is that real?" is
  cheap enough now that the answer is usually measured rather than assumed. Template
  matching is in the repo *because it does not work here* — the measurement is the
  result, and it was worth keeping.

What it did not change:

- **The hardware.** Soldering, siting, shielding, and everything the ADC hears is mine.
  Nothing about an AI helps when the noise floor moves because the geophone was touched
  forty minutes ago.
- **What is true.** Every claim on the public site is checked against the USGS station
  1.64 km away or against the catalogue. An AI is a confident writer, and confident
  prose about an instrument that has not been calibrated is precisely the failure mode
  this project is trying to avoid. `f0` and damping are still labelled as **guesses**
  in `station/SS.OAKM1.xml` because they are, and the calibration injector exists to
  replace them with measurements.

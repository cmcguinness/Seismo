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
kept current because the AI side of the project works from it.

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

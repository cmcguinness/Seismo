# Seismo: DIY seismic station

This repository holds the design and implementation of a small seismometer station and its accompanying support software.  You can see it in operation at **https://seismo.mcguinness.ai**. 

The repo is more than just the software, however: it includes the hardware design, the models for the 3d printed cases, and a sense of the evolution of the project from initial, vague goals to actual implementation.

At its current state, it is a single-channel, sensitivity-first seismometer in my garage in Oakmont, Santa Rosa, California, recording continuously since 2026-07-20 as station **SS.OAKM1.00.EHZ**.

### Why?

The origin of the project was my noticing that a chandelier in our house, which is hanging on about 10 feet of chain, was very sensitive to ground motion.  If my wife yelled out "was that an earthquake?" and I was unsure, I'd go look at the chandelier to see if it was moving.  I joked that I should attach permanent magnets to the chandelier and then wrap it in a giant coil to turn it into a geophone.  My wife did not approve whatsoever of the idea.  Next I thought about using Computer Vision to read its movements.  However, research proved it would not be a good device for that either.  But at that point the idea of a home seismometer was planted in my brain.

The natural approach to building a home device is to buy an off-the-shelf [Raspberry Shake](https://raspberryshake.org) box. That's a great option.  But I learn by building things, not just having, so I decided to do so using the Shake as a design inspiration: clearly a Raspberry Pi, A/D board, and a small geophone would work and, in the famous ignorance of a programmer, "how hard could that be."

Before the era of agentic programming, or in my case, Claude Code, the answer would have been very hard.  With AI's help, it became merely hard.  That difference is what made this happen instead of being put on the backlog.  That is part of the story here and what makes this interesting.

### Caveats and Truths

I am not a professional geologist; I am a professional software engineer, with a graduate degree in AI. I'm also an amateur hardware engineer; much of this project was spent with a soldering iron in hand.

To "get it right", I've done a few things.  One is to try to reference successful designs, like the Shake.  I did not copy their design, but I also didn't do something completely different.  Because there is a USGS seismometer (in the casual sense) located about a mile from my house, I have a great benchmark for my device.  And, indeed, the professional device successfully validates the readings my device gives off. 

So I am confident that the design is good.  But, of course, I am not a professional geologist...



## Architecture

This is not just a seismometer, it's a software system to deliver the finished web page and raw data to downstream users.  The components of the system are:

1. The Seismometer itself, which is built using a geophone and a Raspberry Pi 2.  Its only job is to collect the realtime stream of readings.  It consists of two boxes separated by an XLR cable.  The Geophone is isolated by distance from other electronics to give the lowest possible noise floor.
2. A Raspberry Pi 5, elsewhere on the home network, which extracts the realtime data from the Pi 2 and does the initial ingest and processing of the data.  It becomes the official raw data source.
3. A public facing website on a server in the cloud that provides the public access to the data as well as various tools.

This differs from the Shake in that they have a single box with the geophone and Pi, and the Pi not just collects readings but does initial ingestion and processing (which I use a separate computer for).  My initial design tried to mimic that, but I discovered that the busier the Pi gets the more noise it generates.

### Station

- **Sensor:** a 4.5 Hz vertical geophone (LGT-4.5 class, 375 Ω coil) on the slab.
- **Digitizer:** a TI ADS1256 24-bit ADC (Waveshare AD/DA board) on a Raspberry Pi 2B,
  100 sps, PGA 64, with the ADC's data-ready line handled as a kernel interrupt so every
  sample carries a hardware timestamp (`station/adsreader/`, C).
- **Recorder:** miniSEED day-files on an exact 100 sps grid, despiking, an inline
  STA/LTA trigger, and a UDP stream to a second Pi (`station/recorder.py`).
  
### Data Engine

- **Server (Pi 5, LAN):** archive, re-detection, a gradient-boosting trigger classifier (AI)
  that scores every trigger before it becomes a push notification, and a JSON API
  (`server/`).

### Public Website
- **Dashboard:** the LAN and public copies are the same image; the public one is fed
  outbound-only by the house (`dashboard/`, Dokku).
  
### Other tools
- **Analysis (Mac, obspy):** calibration against the USGS strong-motion station NP.1835
  1.64 km away, detection-range fits against the NCEDC catalogue, classifier training,
  spectral work (`analysis/`).


## What it has done so far

As of 2026-09-02: 34 catalogue-confirmed earthquakes inside a validated detection range of 88.8 km for M2, plus an M4.8 off Petrolia at 319 km, verified by arrival time. Every confirmed event is shown beside NP.1835's record, in ground velocity on the same axes, at https://seismo.mcguinness.ai/catches.

The comparison against 1835 is the calibration: after one empirical sensitivity factor the two stations agree to ~1.2x, and `analysis/refstation_spectra.py` shows that ratio is flat over 5-15 Hz (`doc/refstation-spectra.png`), so the residual is a constant, not a site effect. The geophone's f0 and damping are still nominal; an inline calibration injector (`calibrator/`, `doc/BOM-calibrator.md`) is being built to measure them.

## Reproducing the 1835 comparison

```
cd analysis && uv venv && uv pip install -r requirements.txt
# day-files for the events you want go in analysis/data/ (not in the repo)
.venv/bin/python refstation_compare.py --harvest     # per-event ratios -> dashboard/catches/refstation.json
.venv/bin/python refstation_spectra.py               # the ratio vs frequency
```

NP.1835 waveforms and response come from NCEDC's FDSN service at run time. The station metadata is `station/SS.OAKM1.xml` (`SS` is self-assigned pending a network code).

## Reading the repo

`STATUS.md` is the running log, newest first, with the current-system summary at the top; `STATUS-ARCHIVE.md` holds everything before 2026-08-20. `BACKLOG.md` is deferred work. `specification.md` is the original design and the alternatives rejected. `CLAUDE.md` is the working brief for the AI side of the collaboration and doubles as the best map of where the code runs.

MIT licensed. Not a professional instrument; treat every number here as a hobbyist's, checked against a professional station where it could be.

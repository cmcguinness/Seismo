# Seismo: a DIY seismic station

A single-channel, sensitivity-first seismometer in a garage in Oakmont, Santa Rosa,
California, on the Rodgers Creek / Maacama fault system. Recording continuously since
2026-07-20 as station **SS.OAKM1.00.EHZ**. Live at **https://seismo.mcguinness.ai**.

![The assembled station](doc/station.jpg)

It started with a chandelier that swung when the ground did, and the thought that a
Raspberry Pi, a 24-bit ADC and a 4.5 Hz geophone could do the same job more honestly.
It is checked against a USGS National Strong Motion Project accelerometer 1.64 km away,
and after one empirical sensitivity factor the two agree to about 1.2x, flat across
5-15 Hz. The story, the design and the recipe for checking that claim are in the
documents below.

## The system in three boxes

1. **The station** (Raspberry Pi 2B, garage): geophone, ADS1256 digitizer, miniSEED
   day-files at 100 sps. It does nothing but acquire; a busy Pi is a noisy Pi.
2. **The data engine** (Raspberry Pi 5, house LAN): the owned archive, re-detection, a
   gradient-boosting classifier that scores every trigger, a JSON API.
3. **The public website** (cloud VPS): the dashboard, fed outbound-only from the house.

## Read on

- [The story](readme/story.md): why, how, and what a hobbyist can and cannot claim.
- [Architecture](readme/architecture.md): the three hosts, why they are three, and how
  this differs from a Raspberry Shake.
- [Reproducing the results](readme/reproducing.md): the comparison against NP.1835,
  the detection-range fit, and retraining the trigger classifier.
- [Catches](https://seismo.mcguinness.ai/catches): every confirmed earthquake beside
  the professional station's record, on the same axes.

## Navigating the repo

`STATUS.md` is the running log, newest first, with the current-system summary at the
top; `STATUS-ARCHIVE.md` holds everything before 2026-08-20. `BACKLOG.md` is deferred
work. `specification.md` is the original design and the alternatives rejected.
`CLAUDE.md` is the working brief for the AI side of the collaboration and doubles as the
best map of where the code runs.

MIT licensed. Not a professional instrument; treat every number here as a hobbyist's,
checked against a professional station where it could be.

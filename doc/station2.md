# Station #2 — a clone, burned in at home, then handed off

**Decided 2026-09-25.** Build a second station as an exact clone of OAKM1, run it at
Oakmont first, and hand it to the grandkids in Portola Valley around **end of October to
Thanksgiving 2026**. This is the "cheaper station" direction of
[`Seismo-private/doc/amateur-network-brief.md`](../../Seismo-private/doc/amateur-network-brief.md)
— additive, not load-bearing. Nothing about OAKM1 depends on it.

---

## Why a second station at all

**Two stations 122.6 km apart turn a range-finder into a locator.** Today every catch is a
radius from S−P, with direction taken on the USGS catalogue's word. Two radii intersect.
That is the largest capability jump available to this project, and it is the real argument
— the hand-off is the occasion, not the reason.

**And the pair is well placed.** OAKM1 on Rodgers Creek; theirs 3.7 km off the San Andreas
trace, with Hayward at 41.8 km and Calaveras at 76.6 km sitting roughly between. Most
regional events would fall inside both stations' range at once.

| from the grandkids' house (37.38559, −122.26691) | |
|---|---|
| San Andreas trace | **3.7 km** |
| Hayward fault, mid-segment | 41.8 km |
| Loma Prieta 1989 epicentre | 51.5 km |
| Calaveras, Gilroy end | 76.6 km |
| OAKM1 | 122.6 km |
| The Geysers | 161.8 km |

**What it will and will not hear, stated now so nobody is disappointed later.** Hayward and
Calaveras at 42–77 km are well inside a 98 km validated range, so it will catch plenty. The
fault 3.7 km away will be nearly silent — the Peninsula segment ruptured in 1906 and has
been close to aseismic since. *The noisy fault is the far one and the quiet one is under the
house*, which is the whole of earthquake hazard in one sentence and a better thing to show a
child than a busy drum.

---

## Why a clone, and not the better design

`amateur-network-brief.md` describes a nicer station: geophone → ADC → RP2040 → optical TX,
battery, no radio, fibre to an ESP32 bridge. **It is better and it is not what goes to
Portola Valley.**

**The hard part of this project is not the sensor — it is that the site cannot be visited.**
Remote hobby deployments die of small things: an SD card, a router, a power cut that does
not come back cleanly, with nobody on site to diagnose and a two-hour drive to reach it.
That risk should pick the hardware, and it picks the stack whose every failure mode has
already happened in our own garage: the Wi-Fi TX corruption, the front-end fault of
2026-07-31, the 35-minute settling, the ADS1256 glitch classes. A novel board at the one
site we cannot reach doubles the unknowns exactly where they cost most.

**Identical also buys a clean comparison.** Same response, same processing, so any
difference between Oakmont and Portola Valley is the *ground* rather than the gear.

**The tradeoff, recorded rather than hidden:** at 42–77 km a **2 Hz** element would suit the
sources better than 4.5 Hz. It would also destroy the like-for-like comparison and introduce
a part we have never characterised. Not worth it for v1; revisit if the station stays.

---

## The home phase has three jobs, not one

Running it at Oakmont first is not a rehearsal — two of the three payoffs only exist there.

1. **Prove the data plane and the second identity.** Two station codes through
   `udp_collector`, `detector`, the dashboard and `epochs.py`. The dashboard currently
   renders ONE identity from env (`SID`); multi-station is the largest software item here.
2. **Measure instrument-to-instrument scatter — and settle the 3.2×.** Two identical
   instruments on the same slab recording the same earthquakes is the cleanest available
   test of the calibration question ([the datasheet section of
   `/calibration`](../dashboard/content.py)): if both read ~3.2× low against NP.1835 it is
   NOT that unit — it is the site, the response model, or something systematic about these
   elements. If they disagree, it is unit variation after all. **This discriminator does not
   exist today and it comes free with hardware being built anyway.**
3. **Burn in the hardware**, so nothing unproven travels to a house we cannot reach. A month
   minimum; the window allows more.

⚠️ **A co-located twin validates plumbing and instruments, NOT geometry.** Two sensors metres
apart have no baseline; locating cannot be tested until the station moves.

---

## Long-lead items — start these, everything else can wait

| item | latency | note |
|---|---|---|
| **ISC station code** | ~3 weeks | OAKM1: requested 2026-09-02, registered 2026-09-24, and that needed a chased follow-up and survived a change of officer. Send it in October, not November. |
| ~~**Geophone**~~ | **none — in hand** | Charles has **two spare 4.5 Hz verticals** (2026-09-25). Station #2 needs one. Still confirm the actual Hz on the unit used: the listing mislabels "LGT-20D 4.5 Hz" and "20D" is a family name, not a frequency. |
| **ADS1256 board** | days | Waveshare High-Precision AD/DA, $43.95 from PiShop.us. NOT a bare "ADS1256 breakout" — different pinout. |
| **Calibration injector** | project | Already priority one. **It should work before this station leaves the garage**: a remote station nobody can visit is the worst possible place for a guessed f0 and zeta, because nobody can go and measure it later. |

---

## The two spare geophones, and what they collide with

**They are almost certainly the pair bought for the field rig** (`doc/field-seismograph.md`,
ordered 2026-08-26 — hammer refraction, walkaway, MASW-lite → Vs30). Station #2 needs one of
them, which leaves one. **Refraction can be walked with a single geophone; MASW cannot.** So
spending one here quietly downgrades the field rig from "a pair" to "one and a plan". That is
a real trade, it is cheap to reverse ($36 and a boat), and it should be a decision rather
than something noticed in November.

**A second channel on the SAME board is electrically nearly free, and is not the same test.**
The Waveshare board carries an 8-channel ADS1256 — 4 differential pairs — and we use one
(AIN0/AIN1). A second geophone on AIN2/AIN3 needs only its own bias network. It would isolate
the *element* beautifully, since everything downstream is literally shared.

But it is **not** free in software: `station/adsreader/adsreader.c` runs **RDATAC**,
continuous-read on a fixed channel, which is exactly what gives us the hardware-timestamped
DRDY discipline. Two channels means MUX switching with a SYNC and settling time per sample,
which is a rewrite of the hot path and puts the timing property at risk to answer a
calibration question. **Not worth it** — station #2 gives the same comparison with its own
board and its own Pi, at the cost of hardware we are building anyway and no risk to the
instrument that works.

---

## Open questions, not yet decided

- **Data path.** pi5 ingests over the LAN today; Portola Valley arrives over the internet.
  Needs buffering across outages and a way out through their router — outbound-only, to keep
  the "nothing at the house is reachable from the internet" property at both ends.
- **Whose infrastructure?** Simplest is a dumb station shipping to our data plane, with all
  the smarts staying here. That matches the existing shape (station → pi5 → apps02) and means
  nothing at their house needs maintaining beyond power and a network.
- **Whose page?** A second station wants somewhere to appear. Same dashboard with a station
  switch, or their own.
- **Compute.** A spare Pi, or buy one. The Pi 2B works but is the oldest thing in the stack.
- **Which spare geophone**, and does the field rig keep the other or get a replacement ordered
  now (it is the only item left with boat latency).
- **Siting.** Unknown — garage, crawl space, closet. Coupling matters more than anything else
  we could spend money on, and it is the one thing that must be got right on the day.

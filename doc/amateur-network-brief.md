# An amateur seismic network — is it worth doing, and what would it be?

**Status: a brief, not a plan.** Written 2026-09-24 to answer one question Charles asked —
*could I get an FDSN network code that I set up but anyone can join, around an open-source
cheap-but-decent design?* — and to replace assumptions about FDSN's requirements with the
actual text. Nothing here is committed to. The calibration injector remains priority one;
see `STATUS.md`.

---

## 1. The sensor decision comes first, and it decides everything else

The idea as posed used **accelerometers**. That choice is not a detail — it determines
what the network can be. Measured against this station's own catalogue:

```
geophone floor    0.25 µm/s RMS, 1–15 Hz   (median floor_uv 2.24 µV ÷ 9 V/(m/s))
ADXL355 floor    37.70 µm/s RMS, same band (25 µg/√Hz, datasheet, ±2 g)
penalty            151×  (44 dB)
```

Applying that penalty to the 60 confirmed events and re-testing the `seen` bar (snr ≥ 5):

| sensor | events clearing snr ≥ 5 |
|---|---|
| LGT-4.5 geophone (today) | 39 / 39 |
| **ADXL355 at 25 µg/√Hz** | **0 / 39** |
| ADXL355 best case, 10 µg/√Hz | 1 / 39 |
| a MEMS 10× better than ADXL355 | 3 / 39 |
| a MEMS 100× better (no cheap part exists) | 27 / 39 |

The largest signal in fourteen months — the M3.34 at 13.3 km, felt in the house — lands at
**snr ≈ 3** on an ADXL355, below this station's own bar.

**Boundary of that claim.** It is computed in the 1–15 Hz detection band, where converting
acceleration to velocity divides by *f* and so penalises MEMS hardest; it is the fair
comparison *for this station's detection goal*, not a verdict on accelerometers. It assumes
sensor self-noise dominates, which flatters MEMS — a cheap station in a house has a worse
ground floor too. It varies nothing else: one band, one bar, one catalogue, datasheet noise
rather than a measured unit.

**The trap.** The sensor that makes a community network easy is the sensor that makes it
deaf. Every hard thing about this station — unmeasured f0 and ζ, the damping resistor, the
per-unit ring-down — *does not exist* for a MEMS part: factory-calibrated, digital,
uniform, nothing to measure. That is an enormous operational win for stations nobody can
visit. It costs 151×.

So there are two different projects wearing one name:

- **A felt-shaking network (accelerometers).** Density is the product. Answers real
  questions — site response, ground-motion variability street to street — that *need* many
  stations and tolerate poor ones. Never catches an M1.8 at 3 km.
- **A microearthquake network (geophones).** Catches what makes the hobby fun. Every unit
  needs its response measured, which is why nobody has built one.

## 2. What FDSN actually requires (verified 2026-09-24, not assumed)

- **Codes are assigned by the FDSN** "to uniquely identify the owner and operator
  responsible for the data collected by a network."
- **Length is 1–8 characters**, not the old two. The scarcity argument against handing a
  code to a small operator is much weaker than it used to be. Temporary deployments are
  "strongly encouraged" to append a 4-digit start year.
- **Permanent networks** are expected to "operate continuously for the foreseeable future",
  keep "a relatively stable set of stations and instruments", and **"distribute data in the
  FDSN SEED format"**.
- **`SS` is reserved** "for any institution running a Single Station", and such a station
  "should be registered with the International Registry of Seismograph Stations" — which
  OAKM1 now is, as of 2026-09-24.
- **Requesting requires an fdsn.org login**, and the site states only those "associated with
  an existing network" as originators or PIs may submit. That is a chicken-and-egg for a
  brand-new operator and the form itself is behind the login, so **the real first step is an
  email to FDSN asking how a new operator applies** — not filling anything in. Treat the
  application specifics below the bullet above as unknown until that reply arrives.

**The obligation nobody mentions up front: a network code makes you the data centre.**
"Distribute data in FDSN SEED format" means running `fdsnws-station` and
`fdsnws-dataselect` continuously, for other people's data, indefinitely. That is the real
cost, not the paperwork.

## 3. The precedent is exact, and worth reading closely

**AM — Raspberry Shake.** Operator: Raspberry Shake, S.A., Panama. Started 2016. Permanent.
DOI `10.7914/SN/AM`. Described as a citizen-scientist network of "professional
seismologists, hobbyists, educators and students", stations operated by a distributed
community, and it runs **its own FDSN web services** at `data.raspberryshake.org/fdsnws/`.

So FDSN has already accepted the model: *one accountable operator, many volunteer station
hosts, one code.* The idea is not unprecedented. But note what AM is — a company, with
staff, hosting, and standardised hardware it sells. The durability question ("who runs this
in ten years") is answered there by a balance sheet. For an individual it has to be
answered some other way: a foundation, a club, a university partner, or an explicit
succession plan. That question, not the technology, is the hard part of the application.

## 4. What would actually be novel

Raspberry Shake solved *cheap station*, well enough that AM exists and gets cited. There is
no gap there and no reason to re-solve it.

The unsolved thing is **cheap station with a response you can defend**. Every amateur
network today ships stations whose f0 and ζ are nameplate guesses, which is exactly why the
data is treated as detection-only. The inline calibration injector being built here
(`doc/BOM-calibrator.md`, `calibrator/`, `analysis/calfinder.py`, `analysis/ringdown.py`)
fires a known current burst four times a day so each unit measures its own response *in
situ*, forever, with no site visit.

That is the contribution worth open-sourcing. A network of stations with guessed responses
is a directory; a network of stations that ring themselves down every six hours is a
dataset. **It also happens to be the one piece of this that is already being built for
other reasons.**

## 5. If it were done, the order

Deliberately staged so each step is useful alone and none of it is wasted if the next never
happens.

1. **Reference design published** — BOM, build guide, firmware, the injector. The repo is
   already public. Costs nothing beyond writing. *Test: does one other person build one?*
2. **Station #2, operated here** — the grandkids' station, already a stated goal. Proves the
   two-station data plane: two station codes, two metadata sets, one archive, one dashboard.
   This is what turns "my station" into "a network" architecturally.
3. **`fdsnws-station` + `fdsnws-dataselect`** (already `BACKLOG` B5). Required by FDSN for a
   permanent code, and independently useful — our own analysis stops needing bespoke
   archive-reading glue.
4. **Apply for the code** covering the stations actually operated here. A real network of
   two or three, with working web services, is a far more credible application than an
   aspiration with one station.
5. **Only then open it to others**, with per-station metadata review as the price of entry.

**Gate rule: apply when there is a second *operator*, not a second station.** The question
FDSN will press on is durability, and "someone else runs one and keeps it running" is the
only evidence that answers it.

## 6. How this fails

Named in advance so it is recognisable while it is happening, rather than in hindsight.

- **Nobody joins.** By far the most likely outcome, and the one every project like this
  meets. Step 1 exists to find this out for the price of a weekend.
- **Metadata rot.** Volunteer stations with wrong coordinates, wrong orientation, or a
  response nobody measured. This is what makes amateur data unusable, and the injector is
  the only reason to think it is tractable here.
- **The operational tail.** Running web services for other people's data, forever, alone.
- **It eats the instrument.** The station is a learning project; a network is an
  organisation. Different work, and only one of them is why any of this started.

## 7. Not investigated

The honest boundary of this brief. Not looked at: what FDSN's actual application form asks;
whether an individual has ever been assigned a permanent code; the cost of hosting an
archive for *n* stations; whether NCEDC or EarthScope would ingest a small network's data
and on what terms; any MEMS part other than the ADXL355; hybrid geophone + MEMS designs,
which is what this station is becoming anyway and may be the real reference design; and
whether an existing amateur effort already occupies this niche beyond Raspberry Shake.

---

**Sources** (fetched 2026-09-24):
[FDSN network codes](https://docs.fdsn.org/projects/source-identifiers/en/latest/network-codes.html) ·
[FDSN network code request](https://www.fdsn.org/networks/request/) ·
[FDSN network AM](https://www.fdsn.org/networks/detail/AM/)

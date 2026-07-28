# BOM — sealed geophone case (outdoor-capable) — **GEN 2**

> **This is not the next thing being built.** Gen-1 is a crude indoor POC
> (`parts/geophone_case.py` + `parts/geophone_case_lid.py`, 2026-07-28) whose only
> jobs are easy pick-up/set-down and an XLR on the case. Its entire BOM is: PLA,
> **7 × #6 × ½″ sheet-metal screws** (4 lid, 3 feet), **2 × M3 × 10 countersunk
> machine screws + 2 × M3 nuts** (XLR flange — the Neutrik D flange is
> countersunk, and the 2.4 mm panel is too thin for a self-tapper to hold against
> the latch pull), and the XLR chassis connector already on hand. No seals, no
> ballast, no inserts, no paver.
>
> Everything below is gen 2 — buy it when gen 1 has proven the shape is right.



Shopping list for the standalone geophone enclosure: a sealed, portable puck with a
panel XLR, a clamped element, and three leveling feet. Sealed means it can live
**outside** — on a paver bedded in earth, or (with reservations, see Siting) on the
driveway.

Design reasoning lives in `BACKLOG.md` ("Case design — power feed" → *Related —
geophone case*, and "Target siting — crawl space"). This file is only the parts.

Status: **not yet ordered.** Prices are ballpark; check before you commit.

---

## 1. Connectors & cable

The backlog specced the indoor D-series (`NC3MD-L-B`). **Superseded for outdoor use**
by Neutrik's **TOP** (True Outdoor Protection) range — IP65, UV-resistant, gold
contacts standard, and it *maintains its seal when disconnected*, so there is no dust
cap to lose. Gold contacts were already wanted for the damp crawl space, so this is
one part change that satisfies both sitings.

| Qty | Part | Notes |
|-----|------|-------|
| 1 | Neutrik **NC3MDX-TOP** — 3-pole male chassis, IP65 | On the sensor case. D-shape flange — model the cutout from Neutrik's DXF, do **not** assume the 24 mm bore / 2×M3 @ 19 mm of the standard D-series |
| 1 | Neutrik **NC3FD-L-B** — female chassis | Pi enclosure. Indoor part, fine there |
| 1 | **Off-the-shelf XLR mic cable**, 5–10 m, female→male, Neutrik or equiv. ends | See "Do not build the cable" below. ~$20–30 |
| 1 pk | Insulated crimp ferrules, 22–20 AWG | `STATUS.md`: tinned strands cold-flow under screw terminals. Ferrules, not solder |

Wiring convention unchanged: red = +, white = −, braid = shield; **shield bonded to
ground at the Pi end only**.

### Do not build the cable

TOP chassis connectors **mate mechanically with ordinary XLR** — an unsealed joint,
not a broken one. And that joint lives under a bucket on a shaded paver. So buy the
TOP part only where it is permanently exposed (the sensor chassis connector) and use a
stock cable everywhere else. A mic cable *is* shielded twisted pair; it is electrically
exactly right, not a compromise.

**The gotcha that makes this work:** commercial mic cables bond the shield to pin 1 at
*both* ends, and we need it grounded at the Pi end only. Do **not** open the cable to
fix that — **leave pin 1 unconnected inside the geophone case.** The sensor chassis
connector's pin 1 goes nowhere; the shield is then grounded solely at the Pi, with a
stock cable, no rework.

Later upgrade path, if a sealed mate is ever wanted: swap the cable's sensor end for an
**NC3FX-TOP** (female cable, IP65 when mated to a TOP partner). Nothing else changes.
Pre-terminated cables *with* TOP ends are not a stock item — Redco / Markertek /
Designacable build to order, ~$60–90 plus lead time. Not worth it for this.

Only reach for bulk **UV-rated / direct-burial** shielded twisted pair (Canare L-4E6S
or equiv.) plus loose TOP ends if the cable ends up permanently buried or in sustained
sun — a rubber-jacketed mic cable under a bucket is fine indefinitely.

## 2. Sealing

| Qty | Part | Notes |
|-----|------|-------|
| ~1 m | Silicone O-ring cord, 2.5–3 mm | Glued into a printed groove in the lid |
| 1 | Neoprene or silicone gasket sheet (small) | Cut a washer for under the XLR flange |
| 1 pk | Indicating rechargeable silica gel packets, 5–10 g | One inside; recharge in the oven when it turns |
| 1 | Dielectric / silicone grease, small tube | Connector shell, gasket faces, feet threads |

## 3. Ground coupling & leveling

Three points, not a flat face — a flat disc on rough concrete rocks on three *unknown*
high spots anyway, so make the three points deterministic and get leveling for free.

| Qty | Part | Notes |
|-----|------|-------|
| 3 | M6 × 20 stainless socket **set screws**, cone or dome point | The feet |
| 3 | M6 stainless hex nuts | Jam nuts — a jammed thread with ≤6 mm protrusion is stiff enough at 15 Hz |
| 3 | M6 brass heat-set inserts | |
| 1 | Bull's-eye bubble level, 15–20 mm ⌀ | Recessed in the top. The element is vertical; tilt matters, and you cannot re-level a bedded paver from a belly-crawl |
| 1 | Concrete paver, 12″ × 12″ | Rigid broad coupling + moisture break + a flat seat |
| 1 bag | Paver / leveling sand | Bed the paver in tamped earth |
| 1 | Butyl sound-deadening mat (Noico / Kilmat, small sheet) | Interior walls + lid. **This replaces the sand ballast** — see below |
| 1 | Tent stake or similar cable anchor | Anchor the cable to the paver a few inches out, so a tug loads the paver and not the sensor |

### No ballast — why the sand is gone

An earlier draft called for ~500 g of kiln-dried play sand. Dropped: messy, and it was
solving two problems that each have a cleaner answer.

- **Mass was never load-bearing for coupling.** Light-and-rigid is standard practice for
  a geophone; the *paver* is the mass. Adding mass to the case buys nothing here.
- **Shell-mode damping** — the real reason for the sand — is done better by butyl mat
  stuck to the inside walls. That is constrained-layer damping, which is what sand
  against a wall crudely approximates. The point stands regardless of medium: do not
  print a second structural resonance (see the 19.95/40.97 Hz pair in
  `analysis/SOURCES.md`).
- **Stability against a cable tug** is handled by the 130 mm three-point stance plus an
  external cable anchor.
- **Print the base solid** (100 % infill, floor and walls). Free mass, maximum
  stiffness, no extra parts, and it is the short stiff load path the design wanted anyway.

If heft is still wanted later, the clean version is a **cast-iron barbell plate or steel
disc** for the three feet to stand on — dense, flat, removable, no mess. No sand-fill
cavity or plug is needed, which also deletes a sealing joint.

## 4. Fasteners

| Qty | Part | Notes |
|-----|------|-------|
| 10 | M3 brass heat-set inserts | Lid, element clamp ring, XLR flange |
| 10 | M3 × 10 stainless socket cap screws | |
| 4 | M3 × 16 stainless socket cap screws | Lid, if the gasket groove eats depth |
| 1 | M3 + M6 heat-set insert soldering tips | If not already on hand |

## 5. Weather cover

| Qty | Part | Notes |
|-----|------|-------|
| 1 | 5-gallon bucket, **or** a large dark nursery pot (≥12″) | Inverted over the sensor outdoors. See Siting — this is not optional if it goes anywhere sunlit |
| 1 | Paving brick or two | Weight the bucket rim against wind |
| — | Hardware-cloth scrap (optional) | Critter exclusion; `BACKLOG.md` flags rodents for the crawl space |

Cut a notch in the bucket rim for the cable so the rim still sits flat.

## 6. Consumables — print, glue, finish

| Qty | Part | Notes |
|-----|------|-------|
| 1 kg | **PETG or ASA** filament, dark | **Not PLA.** PLA creeps under sustained clamp load and a Santa Rosa driveway in July is a PLA torture test. ASA if you have an enclosure; PETG otherwise |
| 1 | Cyanoacrylate (thin), small bottle | Tacking the O-ring cord into its groove |
| 1 | CA accelerator | Optional; makes the gasket-cord job a two-minute job |
| 1 | Neutral-cure **silicone** sealant / RTV, small tube | Sealing any print-through or a leaky seam. Neutral-cure, not acetoxy — acetic acid attacks brass and contacts |
| 1 | 2-part epoxy, 5-minute | Bonding the bubble level; backup for a blown heat-set insert |
| 1 | Threadlocker, blue (medium) | Feet jam nuts — they must not walk, and must still come apart |
| 1 | Museum putty | Already on hand. Bedding the case to a rough paver if the three feet prove insufficient; **never under the element** |
| 1 | Isopropyl alcohol + lint-free wipes | Degrease gasket faces and bond surfaces before glue |
| — | Assorted heat-shrink, 3–6 mm | Short pigtails from the chassis connector to the element inside the case (the cable itself is bought made-up) |
| 1 roll | Copper foil tape, conductive adhesive | **v2 hook only** — line the interior for front-end shielding, with a solder tab. Buy it now, wire it later; grounding stays Pi-end-only |

---

## Siting note — sealed ≠ sited

Sealing solves *water*. It does nothing for *sun*, and the driveway is the thermally
worst spot available. Direct sun on a small case is a large diurnal swing landing
straight in the sub-Hz band already diagnosed as thermal settling
(`memory: station-relocated-to-garage`) — full sun turns a transient into a daily
feature.

So: **paver bedded in earth, in shade, bucket over it.** Not bare on the driveway.
And do not site it where water pools — IP65 is rain and hose spray, not immersion, and
a pit that fills will drown the connector. If the spot holds water, put a gravel drain
layer under the paver.

## Before ordering

1. Pull the **NC3MDX-TOP DXF** from Neutrik and check both the flange pattern and the
   **panel thickness** it accepts — printed walls run thicker than sheet metal, so the
   cutout probably needs a locally thinned boss. Five minutes of CAD saves a reprint.
2. Run the **tile-coupling test first** (`BACKLOG.md`, "⚠️ COUPLING"): knife the
   plastic floor tile, sit the existing stand on bare concrete, re-measure. If the case
   arrives first, any change gets misattributed to the case when it was really the tile.

## Open question carried over

`BACKLOG.md` puts the **shunt damping resistor inside the sensor case**. At 1 m — or
even 10 m — of copper that is electrically worth a fraction of an ohm against a 375 Ω
coil, and it costs the ability to retune damping without opening a sealed case that
lives outdoors or under the house. Recommendation: **keep the R socket on the interface
board** until damping is settled, then migrate it in if ever.

## Sources

- [Neutrik NC3MDX-TOP](https://www.neutrik.com/en/product/nc3mdx-top)
- [Neutrik XLR TOP series](https://www.neutrik.us/en-us/neutrik/products/xlr-connectors/xlr-chassis-connectors/top-series)
- [NC3FDX-TOP (distributor listing)](https://www.parts-express.com/Neutrik-NC3FDX-TOP-Heavy-Duty-Female-3-Pole-XLR-Chassis-Connector-IP-65-and-UV-Rated-092-3014)

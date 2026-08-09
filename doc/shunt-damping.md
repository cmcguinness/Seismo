# Shunt damping resistor — whether to fit one, and what value

The interface board has an empty screw-down socket across AIN0/AIN1 for a shunt damping
resistor. **Nothing is fitted today.** This is the process for deciding.

It is a **measurement**, not a datasheet lookup. The element came from a mislabelled
listing, so its moving mass and generator constant are not trustworthy, and it may
already carry internal damping. Sizing a shunt from published numbers would be sizing it
from numbers we have already caught being wrong.

## The tradeoff, stated first

A shunt damps by **loading the coil**, so the ADC only sees `Rs/(Rc+Rs)` of the
open-circuit voltage. With `Rc = 375 Ω`, a 1 kΩ shunt costs **27 %** of your signal.

Absolute calibration already reads **~7.5× low** and this station is explicitly
sensitivity-first. So deliberate **under-damping is a legitimate choice here**, not a
compromise — `ringdown.py solve` prints the sensitivity cost beside every candidate so
the decision is made with both numbers in view.

What damping buys: a flatter response through 4.5 Hz, and less ringing after transients.
The ringing is the practical argument — an under-damped element rings at 4.5 Hz after
every truck and every P arrival, which lengthens apparent event durations and can feed
the STA/LTA false triggers.

## Step 0 — measure what you already have

**Do it on the bench.** An earlier version of this said to do it in situ on the slab,
which was over-cautious: ζ is set by the element's own suspension losses plus the
electrical load, and the ring-down after a tap is its mass-spring decaying against its
own damping. Bench and slab are both effectively rigid compared with that suspension —
you would only see a difference on something compliant like foam. Ambient noise does not
argue for it either, since the tap is a few hundred µV against a ~2 µV floor.

(The **noise floor** re-measurement is different and genuinely does need to be in situ —
that one is measuring the site.)

```
# station settled, quiet hour, recorder stopped
python capture_raw.py 100 60 /tmp/tap.npz     # tap the case a few times during it
python analysis/ringdown.py measure /tmp/tap.npz
```

**Tap firmly.** Full scale at gain 64 is ±78 mV and a normal tap is a few hundred µV, so
there is ~200× of headroom. The fit is much better at high SNR. Check for clipping.

Settling is *not* a concern for this measurement: the 35 min rule is about DC drift, and
a 4.5 Hz ring-down is over in a second. Tap away.

Read the result:

| measured ζ | what it means |
|---|---|
| **> 0.6** | already well damped. Leave the socket empty — a shunt would cost sensitivity for nothing. |
| **0.4 – 0.6** | optional. Decide from whether real events actually show 4.5 Hz ringing in their coda. |
| **< 0.4** | lightly damped. Expect a resonance peak and ringing. Go to step 1. |

## Step 1 — one trial shunt, then solve

Fit any convenient resistor (1 kΩ is a good first try), repeat the tap capture, and
measure ζ again. Two points is all the algebra needs:

```
python analysis/ringdown.py solve --z0 <no shunt> --z1 <with trial> --r1 1000
```

This solves for `k = G²/(2·M·ω₀)` — which folds up the mass and generator constant we do
not trust — and prints the resistor for each target ζ with its sensitivity cost.

## Step 2 — fit it, and re-measure

Fit the chosen value, tap again, confirm ζ landed where predicted. Then leave it alone.

## The physics, so the method is checkable

A tapped geophone rings as `A(t) = A₀·exp(−αt)·cos(ω_d·t)` with `α = ζω₀` and
`ω_d = ω₀√(1−ζ²)`. Those combine exactly: `ω₀ = hypot(α, ω_d)` and `ζ = α/ω₀`, so fitting
the burst gives ζ with no need to know f₀ in advance and no small-ζ approximation.

Damping splits into a fixed mechanical part and the electrical part a shunt buys:

    ζ = ζ_mech + k/(Rc + R_load),    k = G²/(2·M·ω₀)

Measure ζ at two known loads and `k` drops out. Note `R_load` with no shunt is the
**200 kΩ bias network**, not infinity — `ringdown.py` carries that explicitly.

## Estimator accuracy — do not over-read it

Validated against synthetic ring-downs of known ζ: within **0.02 for ζ ≤ 0.6**, degrading
above, over-reading by 0.13–0.19 at ζ = 0.8. The bias is in the safe direction (an
already-damped element reads as more damped, and the decision is unchanged), but **do not
quote a value above ~0.6 as precise**.

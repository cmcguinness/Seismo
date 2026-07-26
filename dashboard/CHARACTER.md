# Detection character scoring — how the thresholds were set

The detections table shows a **character** badge per trigger: `impulsive`,
`sustained`, or `near-threshold`. This documents where those thresholds came
from, and — more importantly — what the scoring does *not* claim.

Code: `render._build_character()` (scoring) + `app._char_badge()` (presentation).
Runs on the same −8/+22 s window the sparkline already slices, inside the same
memoized cache-fill, so it adds **no extra I/O** and nothing on the steady-state
request path.

## The problem it addresses

BACKLOG "Suppress faux (cultural) detections": at threshold 20 the detections are
overwhelmingly cultural impulses, and **raising the STA/LTA ratio cannot fix it** —
sharp impulses produce the *highest* ratios (250, 1746, 4165 observed), so a higher
threshold rejects real quakes first. A discriminator has to look at waveform
*shape*, not trigger strength.

## Measurement (2026-07-22)

All 127 logged triggers (`events.log`, ratio ≥ 4) with data still in the 2-day
mirror were scored. Metrics on the 1–15 Hz envelope (~0.2 s smoothing): envelope
kurtosis, seconds above 25 % of peak (`dur`), peak/median (`snr`); plus HF
fraction and spectral flatness both over the whole window and over a ±1.5 s
window centred on the envelope peak.

Two populations, cleanly separated on **kurtosis** with no overlap:

| | kurtosis | dur (s) | snr | HF fraction (peak window) |
|---|---|---|---|---|
| impulsive (n=6) | p10 **45**, med 55, p90 82 | med 0.85 | med 10.4 | med **0.09** |
| sustained/near-threshold (n=121) | p10 4.5, med 7.7, p90 **26** | med 11.3 | med 4.6 | med **0.41** |

Thresholds (env-tunable): `kurt ≥ 40`, or (`dur ≤ 1.0 s` and `snr ≥ 8`) →
`impulsive`. `snr < 6` → `near-threshold`. Otherwise `sustained`.

## The backlog's premise was wrong for this site

BACKLOG proposed scoring "by HF-energy fraction / spectral flatness", expecting
cultural thumps to be broadband/HF-rich. **The data says the opposite:** the
impulsive population is *lower* in HF fraction (median 0.09) than the sustained
one (0.41), i.e. these thumps are low-band-dominated. Measured over the full 30 s
window the metric is even more useless — a 0.3 s spike barely moves a 30 s
average, so window-level spectral measures are diluted toward the ambient noise.

HF fraction is still computed and shown in the badge tooltip as information, but
it is **not** part of the verdict. Spectral flatness was dropped entirely.

## What this is not

- **Not an earthquake classifier.** A *very local* quake is also impulsive and
  HF-rich; the backlog already flagged this. `impulsive` means "shaped like a
  thump", not "not a quake".
- **Not calibrated on a positive example.** The station has recorded no confirmed
  earthquake yet (Phase 5 is open), so the positive class is entirely
  uncalibrated — only the cultural class is measured. Thresholds are provisional
  and should be revisited once a confirmed event exists.
- **Never a hard drop.** Nothing is filtered out of the table or the log; this is
  a label. The recorder and its trigger are untouched.

The real discriminator remains an ML phase picker (EQTransformer/PhaseNet — see
BACKLOG "ML detection"), which can look for actual P/S arrivals.

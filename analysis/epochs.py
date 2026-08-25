#!/usr/bin/env python3
"""epochs.py — every configuration change that makes data non-comparable.

WHY THIS EXISTS. Comparing across a configuration change has produced a wrong answer
roughly once a week, and three times on 2026-08-12/13 alone:

  - The M2.5 St Helena sat in the amplitude CALIBRATION as a 5.6x outlier until someone
    noticed it predated the 60 -> 100 sps switch by twelve hours.
  - The "V1 electronics floor" (2026-08-03) was used to conclude "the site contributes
    0.02 uV, siting is closed" -- and published to the About page -- when three changes
    had landed after it was measured. The station later read BELOW that floor, which is
    impossible unless the instrument changed.
  - The ~20 Hz resonance was compared across a floor change and a mount change that
    happened three weeks apart, and the table implied three configurations when there
    were two.

`signatures.json` already refuses to apply a signature outside its epoch. This is the
same discipline for everything else.

AFFECTS tags say WHAT a change invalidates, so a comparison is only blocked when it
matters:
    amplitude  absolute scale: sensitivity, gain, front-end wiring
    noise      the noise floor: siting, coupling, power, shielding
    timing     sample rate or clock behaviour
    glitch     ADC glitch/despiker statistics only
    detection  what lands in events.log: trigger band, thresholds, classifier

Times are UTC. Where STATUS records only a date, the time is 00:00 and marked approx --
treat a comparison that straddles such a boundary as unsafe, not merely suspect.

    from epochs import crossed
    crossed("2026-08-11T21:35", "2026-08-13T15:30", "amplitude")
"""
from datetime import datetime, timezone

# (iso_utc, approx?, affects, description)
BOUNDARIES = [
    ("2026-07-23T00:00", True, {"noise"},
     "galvanic Ethernet isolator installed; lowered the noise floor"),
    ("2026-07-24T02:15", True, {"amplitude", "noise"},
     "demo jumpers removed from AD0/AD1 -- STATUS declares a new epoch"),
    ("2026-07-25T23:45", False, {"amplitude", "noise", "timing"},
     "60 -> 100 sps; files not mergeable with the older archive"),
    ("2026-07-31T20:40", False, {"noise"},
     "geophone off the plastic tile, onto the garage floor (coupling test)"),
    ("2026-07-31T23:41", False, {"amplitude", "noise"},
     "STATION FAULT begins -- stray shield strand; data to 08-03 is suspect"),
    ("2026-08-03T00:00", True, {"amplitude", "noise"},
     "fault fixed; V1 electronics floor measured on this configuration"),
    ("2026-08-07T00:00", True, {"amplitude", "noise"},
     "front end REBUILT (interface board rewired, XLR in the chain)"),
    ("2026-08-08T00:00", True, {"noise"},
     "printed geophone case in service (3-point contact replaces flat/cup)"),
    ("2026-08-12T00:51", False, {"noise"},
     "Pi enclosure closed; 5 V via GPIO from the Mean Well; Ethernet not Wi-Fi"),
    ("2026-08-12T15:24", False, {"noise"},
     "moved to the current garage-floor position"),
    ("2026-08-12T16:55", False, {"glitch"},
     "despiker v3 (local scale, centred window)"),
    ("2026-08-14T03:40", False, {"detection"},
     "STA/LTA band-limited to 1-15 Hz + hf_lf classifier; event RATE drops ~80-95%, "
     "so event counts are NOT comparable across this line (amplitudes unaffected)"),
    ("2026-08-25T19:46", False, {"timing", "glitch"},
     "C reader (station/adsreader) owns the ADS1256: DRDY as a kernel interrupt with "
     "hardware timestamps, lost conversions counted+filled, blocks contiguous. Before "
     "this line every 10 s block is stretched 0.2% with an 18 ms gap after it (a "
     "0.1 Hz comb on sub-Hz spectra); amplitudes unaffected"),
]


def _t(x):
    if isinstance(x, str):
        x = datetime.fromisoformat(x.replace("Z", "+00:00"))
    if x.tzinfo is None:
        x = x.replace(tzinfo=timezone.utc)
    return x


def crossed(t0, t1, aspect=None):
    """Boundaries strictly between t0 and t1 that invalidate `aspect` (all if None)."""
    a, b = sorted((_t(t0), _t(t1)))
    out = []
    for iso, approx, affects, desc in BOUNDARIES:
        when = _t(iso)
        if a < when < b and (aspect is None or aspect in affects):
            out.append((iso, approx, sorted(affects), desc))
    return out


def warn_if_crossed(t0, t1, aspect, label=""):
    """Print a warning and return True if the interval straddles a boundary."""
    hits = crossed(t0, t1, aspect)
    if not hits:
        return False
    print(f"  ⚠️ {label or 'comparison'} straddles {len(hits)} {aspect} boundary/ies:")
    for iso, approx, affects, desc in hits:
        print(f"     {iso}{' (approx)' if approx else ''}  {desc}")
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        for iso, approx, affects, desc in crossed(sys.argv[1], sys.argv[2],
                                                  sys.argv[3] if len(sys.argv) > 3 else None):
            print(f"{iso}{' (approx)' if approx else ''}  {','.join(affects):<28} {desc}")
    else:
        print(f"{'when (UTC)':<18} {'affects':<30} what changed")
        for iso, approx, affects, desc in BOUNDARIES:
            print(f"{iso}{'~' if approx else ' '} {','.join(sorted(affects)):<30} {desc}")

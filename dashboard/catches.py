#!/usr/bin/env python3
"""catches.py — the "Catches" page: earthquakes this station has actually recorded.

Presentation data, in the content.py style: no logic beyond assembling HTML. Each catch
is a dict; the images are static PNGs in dashboard/catches/, rendered from the archive
with analysis/quake_share.py (and shrunk to ~150 KB for the web). The detection-range
map is analysis/detection_map.py's output, copied here whenever the harvest CSV it
calibrates from is refreshed.

Why static images: the events are historical, the day-files live on the station and
pi5 (not on the public copy), and a share image is a considered artefact, not a live
render. Regenerate with:

    analysis/.venv/bin/python analysis/quake_share.py --mseed <day.mseed> \\
        --usgs-near <trigger time> --spectrogram --out dashboard/catches/<name>.png
    analysis/.venv/bin/python analysis/detection_map.py --out dashboard/catches/detection-range-map.png

Conventions follow content.py: HTML entities, "{place}" substituted by the caller.
"""
import os

CATCH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catches")

INTRO = (
    "<p>These are the earthquakes the station has recorded and that the USGS catalog "
    "confirms &mdash; magnitude, location, depth and origin time are the catalog&rsquo;s; "
    "the waveform, the peak and the timing are ours. A single geophone <em>detects</em>; "
    "a network <em>confirms</em>, and every event here was also recorded by professional "
    "stations, which is what makes it an earthquake and not a truck.</p>"
    "<p>Each image is the raw 1&ndash;15&nbsp;Hz trace with its smoothed envelope, and a "
    "spectrogram below it: an earthquake arrives as a burst that <em>starts</em> at low "
    "frequency and stays there, because the ground filters out the high frequencies on "
    "the way; a local disturbance is broadband and impulsive. That difference is how the "
    "detector tells them apart.</p>"
)

MAP_TEXT = (
    "<p>How far can a 4.5&nbsp;Hz geophone on a garage floor hear? The rings are the "
    "predicted reach by magnitude, inverted from the same amplitude model the harvester "
    "uses and corrected by what the confirmed catches actually measured. Three rings per "
    "magnitude: the inner is a noisy afternoon, the outer a quiet night. Dots are the "
    "confirmed catches &mdash; 28 of them, out to 89&nbsp;km; the dashed line is the furthest "
    "one; the X is an M3.4 at 348&nbsp;km that was looked for and not seen, the one hard "
    "constraint on the far field. Corrected for what the catches measured, the station "
    "reads about 1.8&times; quieter than the textbook California attenuation predicts.</p>"
    "<p>Everything past the dashed line is extrapolation. Beyond ~150&nbsp;km what survives "
    "is low-frequency Lg energy, exactly where this geophone is deaf, so the outer rings "
    "are upper bounds. The map is regenerated whenever the catalog comparison is "
    "re-run.</p>"
)

# (image, headline, subtitle, facts-as-html-list-items)
CATCHES = [
    dict(
        img="2026-07-29-m4.2-cloverdale.png",
        head="M4.2 &middot; Cloverdale &middot; 2026-07-29",
        sub="02:40:06 UTC &middot; 38.777&deg;N 122.936&deg;W &middot; depth 5.9 km &middot; 46 km NW, on the Maacama fault",
        facts=[
            "The biggest event yet. Peak <b>1,406 &micro;V</b> in 1&ndash;15&nbsp;Hz against a "
            "~1.5&nbsp;&micro;V floor, an ~80&nbsp;s coda, and a detector ratio of 8,535 &mdash; the "
            "previous record was 645.",
            "Not remotely clipped: the whole event used ~3.5&nbsp;% of the digitizer&rsquo;s range.",
            "First arrival at <b>+9.06&nbsp;s</b>. That was 1.4&nbsp;s later than the textbook "
            "P-velocity predicted, and with four other events the same day it pinned the "
            "station&rsquo;s own crustal velocity at 5.19&nbsp;km/s &mdash; the number every "
            "prediction on this site now uses.",
            "Four more confirmed events the same day: three aftershocks at 46&nbsp;km and an M1.5 "
            "near Angwin at 29&nbsp;km.",
        ],
    ),
    dict(
        img="2026-08-13-san-leandro-m4.1.png",
        head="M3.8 &middot; San Leandro &middot; 2026-08-13",
        sub="15:30:04 UTC &middot; 37.755&deg;N 122.150&deg;W &middot; depth 5.5 km &middot; 88 km SSE, on the Hayward fault (first reported as M4.1)",
        facts=[
            "The <b>furthest confirmed catch</b>, nearly twice the previous record. Peak "
            "503&nbsp;&micro;V at +30&nbsp;s, with the energy arriving as a long train of S and "
            "surface waves rather than a sharp onset &mdash; what 88&nbsp;km of crust does to a "
            "signal.",
            "The Hayward and Rodgers Creek faults are one connected system; this is the "
            "neighbour to the south announcing itself.",
            "A second event of M2.8 followed 37 minutes later and was recorded too. Both were "
            "used to calibrate this station against a USGS strong-motion instrument 1.6&nbsp;km "
            "away.",
        ],
    ),
    dict(
        img="2026-07-25-m2.5-st-helena.png",
        head="M2.5 &middot; St. Helena &middot; 2026-07-25",
        sub="11:31:41 UTC &middot; 38.507&deg;N 122.435&deg;W &middot; depth 6.2 km &middot; 18 km ENE, the Rodgers Creek / Maacama step-over",
        facts=[
            "<b>The first confirmed earthquake</b>, five days after the station moved to the "
            "garage. A clean, impulsive local event: sharp P at +3.97&nbsp;s, peak 117&nbsp;&micro;V, "
            "signal-to-noise ~85&times;.",
            "Close enough that P and S are only ~2.4&nbsp;s apart and merge into one burst &mdash; "
            "there is no independent S&ndash;P distance from one trace; the 18&nbsp;km is the "
            "catalog&rsquo;s.",
            "Also recorded by BK.CMB (broadband, 185&nbsp;km) and CE.68327 (Santa Rosa strong-"
            "motion). Their picks are what located it.",
        ],
    ),
    dict(
        img="2026-08-12-geysers-m3.2.png",
        head="M3.2 &middot; The Geysers &middot; 2026-08-12",
        sub="10:28:21 UTC &middot; 43 km NNW &middot; the geothermal field",
        facts=[
            "Peak 227&nbsp;&micro;V. The Geysers is the world&rsquo;s largest geothermal field and "
            "produces several small earthquakes a day, driven by the wastewater injected to "
            "recharge the steam reservoir &mdash; some of it Santa Rosa&rsquo;s own.",
            "That makes it a permanent calibration source 45&nbsp;km away: same path every "
            "time, a new event every few days.",
        ],
    ),
    dict(
        img="2026-08-11-geysers-m2.8.png",
        head="M2.8 &middot; The Geysers &middot; 2026-08-11",
        sub="21:35:14 UTC &middot; 45 km NNW",
        facts=[
            "Peak 159&nbsp;&micro;V. The workhorse event: its waveform was scaled and superposed "
            "onto recorded cultural noise to measure how much sensitivity the station loses "
            "while someone is dragging trash cans past it (about two thirds of a magnitude "
            "unit, as it turns out).",
            "Compared against the strong-motion station 1.6&nbsp;km away, it says this geophone "
            "reads about 3&times; quieter than its nameplate &mdash; the calibration now in use.",
        ],
    ),
    dict(
        img="2026-07-27-m2.5-the-geysers.png",
        head="M2.5 &middot; The Geysers &middot; 2026-07-27",
        sub="06:29:25 UTC &middot; 38.798&deg;N 122.781&deg;W &middot; depth 3.5 km &middot; 41 km NNW",
        facts=[
            "The second confirmed event, two days after the first, and the first from The "
            "Geysers. Onset at +8.15&nbsp;s &mdash; one of the five points that fixed the "
            "station&rsquo;s P velocity.",
        ],
    ),
    dict(
        img="2026-08-25-geysers-m2.4.png",
        head="M2.4 &middot; The Geysers &middot; 2026-08-25",
        sub="00:22:31 UTC &middot; 38.821&deg;N 122.843&deg;W &middot; depth 1.7 km &middot; 45 km NNW",
        facts=[
            "Peak 79&nbsp;&micro;V at 17:22 on a weekday afternoon, through the daytime traffic "
            "floor. The P onset landed on the predicted +9.0&nbsp;s to within a sample.",
            "Recorded with the station&rsquo;s original Python acquisition loop, a few hours "
            "before it was replaced by the C reader that now owns the digitizer.",
        ],
    ),
]



# Newest first. The image names start with the event date, so the filename IS the sort
# key -- add a catch anywhere in the list above and it lands in the right place.
CATCHES.sort(key=lambda c: c["img"], reverse=True)


def image_path(name):
    """Static image under dashboard/catches/, or None if the name is not one of ours."""
    if not name or "/" in name or not name.endswith(".png"):
        return None
    p = os.path.join(CATCH_DIR, name)
    return p if os.path.isfile(p) else None


def catch_html(c):
    facts = "".join(f"<li>{f}</li>" for f in c["facts"])
    return (
        f'<img src="/catches/{c["img"]}" class="plot" loading="lazy" alt="{c["head"]}">'
        f'<p class="text-muted small mt-2 mb-2">{c["sub"]}</p>'
        f'<ul class="mb-0">{facts}</ul>'
    )

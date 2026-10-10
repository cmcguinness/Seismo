#!/usr/bin/env python3
"""teleseisms.py — earthquakes recorded from the far side of the planet.

Presentation data in the content.py style. Kept out of catches.py on purpose, for two
reasons. The first is size: catches.py is past 1,000 lines. The second is the data:
a teleseism is NOT in confirmed.json. That file, the range map and the superlatives
all describe 1–15 Hz local detections. A P wave pulled out of 0.5–1.6 Hz by a
null-distribution test is a different measurement, so it must not leak into the range
fit or win "furthest recorded".

The figure is analysis/teleseism_p.py's output, copied into dashboard/catches/ (served
by the same /catches/{name} route). Regenerate with the command line in that script's
docstring, then copy it here. The numbers in the prose come from its printout and
STATUS.md 2026-10-09.
"""
import os

from catches import CATCH_DIR, _ver

PANAMA_IMG = "teleseism-2026-10-09-m7.7.png"
PANAMA_ALT = (
    "Three-panel chart of the M7.7 Panama earthquake as recorded 5,409 km away. "
    "Top: this station's filtered trace over 14 minutes. A vertical line marks the "
    "earthquake at 17:56:06 UTC; the trace stays a steady band of background noise for "
    "8 minutes 44 seconds, then thickens sharply at the predicted P arrival and stays "
    "louder for about two and a half minutes, past the PcP and PP markers. "
    "Middle: loudness in 10-second steps relative to background, for this station and "
    "for BK.HOPS, a broadband station 60 km north. Both hover near 1 until P, then HOPS "
    "jumps to about 10 to 15 times and this station to about 2 times, rising and "
    "falling together. "
    "Bottom: a histogram of the same measurement taken every two minutes that day, "
    "clustered between 0.9 and 1.14; the value at the Panama P wave, 1.98, sits far "
    "to the right of all of them."
)

TEASER = (
    "<p>The furthest thing this station has recorded is not in the table below. On "
    "9&nbsp;October 2026 an M7.7 off Panama, <b>5,409&nbsp;km</b> away, sent a P wave through "
    "the Earth&rsquo;s mantle, and 8&nbsp;minutes 44&nbsp;seconds later it reached the "
    "garage. It is a different kind of catch from everything here: a faint rise below "
    "2&nbsp;Hz that a statistical test separates from the background, not a burst you "
    "can see in the 1&ndash;15&nbsp;Hz band. So it is kept out of this page&rsquo;s numbers "
    "and written up on <a href=\"/range#teleseism\">the Range page</a>.</p>"
)


def text():
    v = _ver(os.path.join(CATCH_DIR, PANAMA_IMG))
    return (
        "<p>Everything on the map above is local or regional. On 9&nbsp;October 2026 an "
        "M7.7 struck 12&nbsp;km WSW of Pitaloza Arriba, Panama, at 17:56:06&nbsp;UTC, "
        "<b>5,409&nbsp;km</b> from here. Its P wave is a compressional pulse that dives "
        "through the mantle and comes back up. It arrived "
        "<b>8&nbsp;minutes 44&nbsp;seconds</b> later, and the station recorded it. This is our "
        "first <em>teleseism</em>: an earthquake recorded from the other side of the "
        "world.</p>"
        f'<img src="/catches/{PANAMA_IMG}?v={v}" class="plot" '
        f'alt="{PANAMA_ALT}">'
        "<p><b>What we saw.</b> Between 0.5 and 1.6&nbsp;Hz, the ground motion rose to about "
        "<b>twice</b> its background within 10&nbsp;seconds of the predicted P arrival. It "
        "stayed up for about two and a half minutes, through PcP (P reflected off the "
        "core) and PP (P that bounced once off the surface on the way). To check that this "
        "was not ordinary afternoon noise, we ran the same measurement every two minutes "
        "for the rest of the day. <b>None of 639 windows passed 1.14&times;.</b> BK.HOPS, a "
        "professional broadband station 60&nbsp;km north, rises in the same 10&nbsp;seconds, "
        "and the two envelopes track each other (r&nbsp;=&nbsp;0.74).</p>"
        "<p><b>What we didn&rsquo;t.</b> At this distance most of a big quake&rsquo;s energy "
        "travels as surface waves with periods of 20&ndash;50&nbsp;seconds. HOPS recorded "
        "them at over 300&times; its background; we recorded nothing. Below its 4.5&nbsp;Hz "
        "resonance a geophone&rsquo;s sensitivity falls as the square of frequency, so at "
        "0.03&nbsp;Hz it is about 22,000&times; down. That is the price of a cheap, sensitive "
        "sensor, and no processing buys it back.</p>"
        "<p><b>What it taught us.</b> In August, after an M5.5 in El Salvador left no trace, "
        "this project wrote that teleseisms were &ldquo;structurally impossible here, "
        "however large.&rdquo; That was right about surface waves and wrong about "
        "&ldquo;however large.&rdquo; Recording the P wave also showed that the "
        "station&rsquo;s own ~1.04&nbsp;Hz electronic hum sits in the middle of this band. "
        "Filtering it out roughly doubles how clearly the P wave stands out. One honest "
        "caveat: the band and that filter were chosen after looking at this one "
        "earthquake. The next big one will test them.</p>"
        "<p><b>The limit.</b> Two and a half hours later an M6.6 aftershock struck almost the "
        "same spot, and this time the station saw nothing. HOPS recorded its P wave at "
        "about a third of the strength, which is below what this station can pick out. So "
        "at this distance the smallest quake we can hear lies somewhere between M6.6 and "
        "M7.7.</p>"
    )

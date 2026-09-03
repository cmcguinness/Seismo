"""sound.py — the "How the sound is made" page.

Prose for the audio: why the ground has to be moved into hearing, what the vocoder does
to it, what the two tunings are each faithful to, and what the ear is not being told.
Every number is read from listen.py, so the page cannot drift from the engine the way
the Listen page's "twelve filters" did.

Sections are (heading, html) pairs in the content.py style; seismo_dashboard.py wraps
each in a card with a deep-linkable id.
"""
import listen


def _n(x, d=0):
    return f"{x:,.{d}f}"


def _bands_table():
    rows = []
    for b in listen._band_plan():
        rows.append(f'<tr><td class="text-end">{_n(b["fin"], 2)}</td>'
                    f'<td class="text-end">{_n(b["fout"], 0)}</td>'
                    f'<td class="text-end">{_n(b["foutT"], 0)}</td></tr>')
    return ('<div class="table-responsive"><table class="table table-sm mono small">'
            '<thead><tr><th class="text-end">ground band centre (Hz)</th>'
            '<th class="text-end">compressed tone (Hz)</th>'
            '<th class="text-end">subwoofer tone (Hz)</th></tr></thead>'
            '<tbody>' + "".join(rows) + '</tbody></table></div>')


_N = listen.N_BANDS
_LO, _HI = listen.BAND_LO, listen.BAND_HI
_OCT_IN = __import__("math").log2(_HI / _LO)
_OUT_LO = listen.OUT_HZ / 2 ** (listen.OUT_OCTAVES / 2)
_OUT_HI = listen.OUT_HZ * 2 ** (listen.OUT_OCTAVES / 2)
_MULT = listen.TRUE_MULT

SECTIONS = [
    ("The problem", (
        f"<p>Everything this station records lives between {_n(_LO, 0)} and {_n(_HI, 0)}&nbsp;Hz. "
        "Human hearing starts around 20&nbsp;Hz and is not much use below 40. So the ground "
        "cannot simply be played; it has to be <em>moved</em>, and how you move it decides "
        "what you end up perceiving. There are three ways, and two of them are wrong for "
        "this.</p>"
        "<p><b>Speed it up.</b> Play the samples back sixty times faster and 1&ndash;15&nbsp;Hz "
        "becomes 60&ndash;900&nbsp;Hz. Nearly every earthquake sound you are likely to hear does this. "
        "Two to compare against: the USGS&rsquo;s "
        "<a href=\"https://earthquake.usgs.gov/education/listen/music/\" target=\"_blank\" "
        "rel=\"noopener\">Earthquake Quartet&nbsp;#1</a>, Parkfield and the 1992 Landers quake "
        "played eighty times faster, and IRIS&rsquo;s "
        "<a href=\"https://ds.iris.edu/ds/products/seissound/\" target=\"_blank\" "
        "rel=\"noopener\">SeisSound</a> clips, sped up by hundreds. It also compresses the time axis sixty-fold: a fifty-second "
        "earthquake lasts under a second, and a live feed is impossible, because you would be "
        "listening to the past. That doesn&rsquo;t work for us. We want to hear the ground in "
        "real time, as it happens, not a "
        "<a href=\"https://en.wikipedia.org/wiki/Alvin_and_the_Chipmunks\" target=\"_blank\" "
        "rel=\"noopener\">chipmunks</a> version of the event.</p>"
        "<p><b>Ride it on a carrier.</b> Mix the ground signal with a 440&nbsp;Hz tone, the "
        "way a radio does. That shifts frequencies by <em>adding</em>: 440&nbsp;+&nbsp;1 "
        "to 440&nbsp;+&nbsp;15&nbsp;Hz, which spans a twentieth of an octave. You would "
        "hear one note with a faint waver. No choice of carrier fixes it; the trouble is "
        "additive versus multiplicative.</p>"
        "<p><b>Multiply the frequencies.</b> Pitch is logarithmic: an octave is a doubling, "
        "wherever it sits. Multiplying every frequency by the same number keeps every "
        "interval intact and leaves time alone. That is what this does, and the only "
        "question left is by how much.</p>"
    )),
    ("The machine", (
        f"<p>A <b>filter-bank vocoder</b>. {_N} band-pass filters, spaced evenly in pitch "
        f"across {_n(_LO, 0)}&ndash;{_n(_HI, 0)}&nbsp;Hz, run over the station&rsquo;s "
        "100-samples-per-second record in your browser. Each filter&rsquo;s output is "
        "smoothed into a loudness envelope, and that envelope sets the volume of one sine "
        "tone. Thirteen filters, thirteen tones. What you hear is a chord whose balance, "
        "moment to moment, is the shape of the ground&rsquo;s motion.</p>"
        "<p>The ground signal itself never enters the audio path. It only ever turns volumes "
        "up and down, which is why a 100-sample-per-second source and a 48,000-sample-"
        "per-second audio system are not in conflict, and why nothing has to be resampled. "
        "The same trick is how a 1970s vocoder made a synthesiser talk: the voice shaped the "
        "loudness of the bands, and the synthesiser supplied the tones.</p>"
        "<p>The cost is <b>phase</b>. The filters keep how much energy is in each band and "
        "discard the waveform&rsquo;s exact shape, so a sharp P-wave crack and a truck&rsquo;s "
        "thud become the same thirteen tones in different proportions. Keeping phase would "
        "need a different instrument (a phase vocoder) and would give up the explicit "
        "control over where the sound sits that makes the two tunings below possible.</p>"
        "<p>Why thirteen, and not more? The ear cannot separate tones closer than about a "
        "third of an octave, and thirteen across 3.9 octaves is already at that limit. "
        "Sharper filters would resolve more, but a filter&rsquo;s ring time grows with its "
        "sharpness: at 1&nbsp;Hz the bottom band already takes most of a second to respond, "
        "and doubling the sharpness would smear every onset into a swell. The bands are as "
        "narrow as the onsets allow.</p>"
    )),
    ("Two tunings", (
        f"<p><b>Compressed</b> squeezes the {_OCT_IN:.1f} octaves of the ground into "
        f"{listen.OUT_OCTAVES:.0f} octaves of sound, {_n(_OUT_LO, 0)}&ndash;{_n(_OUT_HI, 0)}&nbsp;Hz, "
        "centred an octave below concert A. It plays on anything, a phone included. The "
        "price is that intervals shrink: a 4:1 ratio in the ground arrives as 2:1 in the ear, "
        "so an octave in the ground no longer sounds like an octave. A happy accident of "
        f"thirteen bands over exactly two octaves is that the tones fall on a whole-tone "
        "scale, so the chord is never sour with itself.</p>"
        f"<p><b>Subwoofer</b> is a straight multiply by {_MULT:.0f}: four octaves up, no "
        f"warping, {_n(_LO * _MULT, 0)}&ndash;{_n(_HI * _MULT, 0)}&nbsp;Hz. An octave in the "
        "ground is an octave in the ear, which is the only thing this tuning claims and "
        "the reason it is not snapped to any scale. Most of an earthquake&rsquo;s energy "
        "lands around 50&ndash;100&nbsp;Hz, the bottom bands at 16&ndash;30&nbsp;Hz, and "
        "laptop speakers reproduce none of that. It wants a subwoofer or good headphones, "
        "and then it is the more honest of the two.</p>"
        "<p>The switch between them changes only the tones. The filter bank analysing the "
        "ground is identical, which is why you can flip it mid-note and hear the same "
        "moment two ways.</p>"
        + _bands_table()
    )),
    ("Loudness", (
        f"<p>Each band&rsquo;s envelope is measured in decibels above a floor. For the "
        f"<b>live</b> feed the floor is {listen.FLOOR_UV:g}&nbsp;µV, a quiet night, mapped to "
        f"silence, and {listen.CEIL_DB:.0f}&nbsp;dB above it is full volume: the same "
        "microvolt is always the same loudness, so a loud night sounds louder than a quiet "
        "one and an earthquake is louder than either. The volume law is gentle at the bottom "
        "and steep at the top, so the neighbourhood murmurs and the earthquake arrives.</p>"
        "<p>The <b>recorded clips</b> on the Catches page are handled differently, on "
        "purpose. Their peaks span a range of forty decibels, and the largest of them sits "
        "well above the live ceiling, so on the live scale every tone was pinned at full "
        "volume for most of the clip: thirteen sines at full amplitude, beating against each "
        "other, which the ear reports as distortion. Each clip is therefore run through the "
        "filter bank once before it plays, and its own pre-event level becomes the floor and "
        "its own peak becomes full scale. Only the peak moment is loud. The consequence is "
        "stated under every play button: the volume of a clip tells you how the energy "
        "changes before, during and after the event, not how big the earthquake was. An "
        "M1.4 and an M4.2 play equally loud; what differs is how they evolve.</p>"
        "<p>A limiter sits at the very end of the chain, so the sum of thirteen tones can "
        "never exceed what the audio system can carry. It is a safety net, not a sound.</p>"
    )),
    ("What you are not being told", (
        "<p><b>The ocean.</b> The microseism, the swell of the Pacific pressing on the "
        "coast, lives at 0.07&ndash;0.15&nbsp;Hz. It is below the bottom of the analysed "
        "band, and this 4.5&nbsp;Hz geophone is nearly deaf to it anyway. The lowest tones "
        "here are the slow end of traffic and weather, not surf.</p>"
        "<p><b>Absolute loudness at low pitch.</b> The ear is less sensitive at the bottom "
        "of the compressed range, so a low band sounds quieter than its gain says, and "
        "laptop speakers roll off hard below about 200&nbsp;Hz. Neither is compensated, "
        "because a per-band loudness trim would misstate the relative amplitude of the "
        "bands, which is the one thing the sound is faithful about.</p>"
        "<p><b>Time, in the live feed.</b> Playback runs at exactly real time behind a "
        f"{listen.PREBUFFER_S:.0f}-second head start, which is also the dropout tolerance, "
        f"and a session stops after {listen.MAX_S:.0f}&nbsp;seconds. That bound is a "
        "simplification rather than a limit: it keeps a muted tab from polling all week, "
        "and browsers require a click before sound anyway.</p>"
        "<p><b>Direction and waveform.</b> One vertical sensor, and phase discarded. The "
        "sound cannot tell you which way the ground moved, only how much and at what "
        "pitch.</p>"
    )),
    ("Where to hear it", (
        "<p>The <a href=\"/listen\">Listen</a> page plays the ground live. The "
        "<a href=\"/catches\">Catches</a> page has a clip under each featured earthquake, "
        "with the P arrival marked where it was picked and the S arrival marked where it "
        "was predicted, so you know when to listen for the change. The exact constants, "
        "and the reasoning behind each one, are in <code>dashboard/listen.py</code> in the "
        "<a href=\"https://github.com/cmcguinness/Seismo\">station&rsquo;s repository</a>.</p>"
    )),
]

#!/usr/bin/env python3
"""content.py — the dashboard's long-form prose, kept out of the route handlers.

Everything here is presentation TEXT: the Seismology 101 sections, the About sections,
and the two explainer blocks that sit under a chart. It has no imports, no logic and no
state -- `seismo_dashboard` renders these strings into cards and does the one
substitution they need ({place}).

WHY IT IS A SEPARATE FILE (2026-08-15). seismo_dashboard.py had grown past 1,300 lines
and roughly a third of it was paragraphs. Prose changes far more often than routing
does, they were reviewed together, and a typo fix and a routing change looked identical
in the diff. Moving the paragraphs out drops the app module back under the 1,000-line
line and makes "what does the site SAY" one file you can read end to end.

Conventions:
  - HTML entities, not literal unicode punctuation (&mdash;, &nbsp;, &rsquo;) -- these
    strings go straight into the page.
  - "{place}" is substituted with SEISMO_PLACE by the caller.
  - Sections are (header, inner_html) pairs; /learn slugs the header into an anchor id,
    so EDITING A HEADER CHANGES ITS URL. #how-to-read-the-helicorder is linked from
    under every drum.
"""


# Shown as real HTML under every drum, on the front page and in History. It exists
# because a first-time viewer asked whether the four colours were four simultaneous
# data feeds -- which is the single most misleading thing about a helicorder, and no
# amount of in-image legend was going to fix it (the image is where the confusion
# comes FROM). Keep it short here; the full walk-through is the /learn section.
HELI_HOWTO = (
    '<div class="text-muted small mt-3 mb-0">'
    '<p class="mb-1"><b>Each row is 15 minutes</b> of ground motion, oldest at the top &mdash; '
    'read it like lines on a page. Height means how hard the ground moved, so an earthquake '
    'is a sudden fat burst that tapers away, while ordinary noise is an even fuzz.</p>'
    '<p class="mb-1"><b>The four colours carry no meaning.</b> They cycle red, green, blue, '
    'black purely so your eye can follow one row without sliding into the next. This is a '
    '<i>single</i> sensor recording a <i>single</i> channel &mdash; not four feeds at once.</p>'
    '<p class="mb-1"><b>Faded stretches are things happening nearby</b> &mdash; footsteps, a '
    'door, a car. They are identified by pitch: only something within a few metres arrives '
    'with energy above 15&nbsp;Hz, because distance strips the high frequencies out of a real '
    'earthquake. The solid core drawn inside a faded burst is the 1&ndash;8&nbsp;Hz part, the '
    'band a quake would occupy.</p>'
    '<p class="mb-0"><b>Coloured triangles</b> mark where an earthquake from the USGS '
    'catalogue <i>should</i> have arrived &mdash; where to look, not a claim that this station '
    'caught it. <a href="/learn#how-to-read-the-helicorder">Full guide to reading the '
    'drum&nbsp;&rarr;</a></p></div>')


ACTIVITY_TEXT = (
    '<p class="mb-2">Every cell is one hour, coloured by how much the ground was moving '
    '&mdash; the median of that hour&rsquo;s four helicorder intervals. Pale blue is '
    'quiet, deep red is busy, and the colour also darkens the whole way, so the picture '
    'survives being printed or read by a colourblind eye. '
    'Times are <b>local</b>, not UTC, because this chart is about people: indexed by UTC '
    'the morning rush would land in the middle of the night.</p>'
    '<p class="mb-0">Almost everything here is human. The quiet band across the small '
    'hours is the neighbourhood asleep; it lifts around 05:00, runs loud through the '
    'working day, and falls away again after dark. Roughly a <b>4&times; swing</b> between '
    '4&nbsp;AM and mid-afternoon, and none of it is geology. That is also why this station '
    'detects smaller earthquakes at night &mdash; the same quake has to compete with four '
    'times less noise.</p>')


# Appended only when the window actually CONTAINS a configuration change -- otherwise
# the page explains grey cells and a dashed staircase that are not on the chart, which
# is how it read for the nine days after 2026-08-12. `activity.has_prior_cells()` is
# the switch.
ACTIVITY_PRIOR_TEXT = (
    '<p class="mb-0 mt-2"><b>Grey cells are a different instrument.</b> The colour scale '
    'is absolute microvolts, so rebuilding the front end or moving the sensor shifts the '
    'whole picture &mdash; and would read as the neighbourhood falling silent. Hours '
    'recorded before the most recent such change are therefore not coloured at all, and '
    'the dashed staircase marks where it happened.</p>')


LEARN_SECTIONS = [
    ("Start here: what this thing actually measures",
     '<p class="prose">A seismometer does not measure earthquakes &mdash; it measures '
     '<b>ground motion</b>, continuously, whether or not anything interesting is happening. '
     'Earthquakes are just one of the things that move it.</p>'
     '<p class="prose"><b>This</b> instrument measures one specific thing: <b>how fast the ground '
     'moves up and down</b>. &ldquo;Up and down&rdquo; because it is a single vertical sensor '
     '(others add the two horizontal directions), and &ldquo;how fast&rdquo; &mdash; velocity '
     '&mdash; because of how it works. Instruments built differently report the ground&rsquo;s '
     'displacement or its acceleration instead; see the glossary.</p>'
     '<p class="prose">Inside the sensor (a <i>geophone</i>) is a heavy magnet hanging on a spring '
     'inside a coil of wire. When the ground jolts, the case moves but the magnet&rsquo;s inertia '
     'makes it lag behind &mdash; and a magnet moving inside a coil generates a voltage. That '
     'voltage is the measurement. It is <b>tiny</b>: the quietest signals here are under a '
     'millionth of a volt, which is why so much of this project is about fighting electrical '
     'noise.</p>'
     '<p class="mb-0 prose">The speeds involved are small too. A quiet night here is ground motion '
     'of roughly <b>35 nanometres per second</b> &mdash; about the width of a virus, per second. '
     'A person walking past is thousands of times bigger than that.</p>'),

    ("Putting real numbers on it",
     '<p class="prose">The voltage the sensor produces converts straight to a ground speed, because '
     'this geophone gives <b>28.8 volts for every metre-per-second</b> of motion. Working that down '
     'to the sizes we actually see:</p>'
     '<div class="table-responsive"><table class="table table-sm align-middle">'
     '<thead><tr><th>At the sensor</th><th>Ground speed</th></tr></thead><tbody>'
     '<tr><td><b>1 microvolt</b> (µV)</td><td><b>34.7 nm/s</b> at the sensor&rsquo;s <i>nominal</i> rating</td></tr>'
     '<tr><td>&hellip; but measured against a reference station</td><td><b>~111 nm/s</b> &mdash; see below</td></tr>'
     '<tr><td>1 nanometre/second</td><td>0.029 µV, or about 3 of the digitizer&rsquo;s steps</td></tr>'
     '<tr><td>Smallest step the digitizer can resolve</td><td>0.32 nm/s</td></tr>'
     '<tr><td>Quiet-night noise floor (~1.1 µV, 10&ndash;15 Hz)</td><td>~37 nm/s</td></tr>'
     '<tr><td>Deep-night floor, 1&ndash;15 Hz</td><td>~0.8 µV</td></tr>'
     '</tbody></table></div>'
     '<p class="prose"><b>How far does the ground actually travel?</b> That is a different question '
     'from how fast, and the answer depends on frequency &mdash; a fast wiggle covers less distance '
     'than a slow one at the same speed (distance = speed &divide; 2&pi;&#8202;&times;&#8202;'
     'frequency). At the quiet-night floor, the ground is physically moving by about:</p>'
     '<div class="table-responsive"><table class="table table-sm align-middle">'
     '<thead><tr><th>Frequency</th><th>How far it moves</th></tr></thead><tbody>'
     '<tr><td>4.5 Hz</td><td>~0.8 nm</td></tr>'
     '<tr><td>10 Hz</td><td>~0.4 nm</td></tr>'
     '<tr><td>20 Hz</td><td>~0.2 nm</td></tr>'
     '</tbody></table></div>'
     '<p class="prose">Those distances are <b>smaller than a single atom is wide</b> '
     '(an atom is about 0.1&ndash;0.5&nbsp;nm). Detecting motion that small on thirty dollars of '
     'hardware sitting on a garage floor is the part worth being slightly amazed by.</p>'
     '<p class="prose">How quiet it gets depends enormously on the hour. At 2&nbsp;AM the '
     'noise across the quake band (1&ndash;15&nbsp;Hz) falls to about <b>0.8&nbsp;µV</b>, roughly '
     'four times quieter than the same measurement at nine in the morning. Almost all of that '
     'difference is people: traffic, appliances, footsteps.</p>'
     '<p class="prose"><b>How do we know any of these numbers are right?</b> There is a USGS strong-motion accelerometer &mdash; station NP.1835, at a Santa Rosa fire house &mdash; <b>1.64&nbsp;km from this one</b>, and its recordings are public. Comparing the two instruments on the same earthquakes, in a band where this sensor&rsquo;s response is flat, says this station reads about <b>3.2× low</b>: its real sensitivity is nearer 9&nbsp;V/(m/s) than the 28.8 on the datasheet. Four events agree, spanning M2.8 to M4.1. That correction is <i>provisional</i> &mdash; the two sites are 1.64&nbsp;km apart and ground can respond differently over that distance &mdash; and it does not yet say whether the sensor or the amplifier is responsible.</p><p class="prose">The same comparison answers a fair question: what can this see that a professional instrument cannot? Honestly, nothing. Above 5&nbsp;Hz the fire-house accelerometer resolves slightly smaller motions than this does. What a home station offers is not superior hardware &mdash; it is a continuous record of one specific place, owned by the person standing on it.</p><p class="prose">An honest caveat on all of this: the last careful measurement of the '
     '<i>instrument&rsquo;s own</i> noise &mdash; taken with the sensor disconnected &mdash; put '
     'it at 1.18&nbsp;µV, and the station now routinely reads below that on a quiet night. So the '
     'electronics have improved since that measurement and nobody has re-measured them yet. Until '
     'that is redone, we genuinely do not know how much of the remaining noise is the ground and '
     'how much is the amplifier.</p>'
     '<p class="mb-0 prose"><b>One catch</b>, and it is why the <a href="/spectrum">spectrum</a> is '
     'cut off at the left: the &ldquo;34.7 nm/s per µV&rdquo; figure only holds <b>above about '
     '4.5&nbsp;Hz</b>. Below that the sensor goes progressively deaf, so the same voltage means '
     '<i>much</i> more real ground motion &mdash; roughly 5× more at 2&nbsp;Hz, 20× at 1&nbsp;Hz. '
     'It is a velocity meter with an honest range, not a universal ruler.</p>'),

    ("P waves, S waves, and how one station can guess the distance",
     '<p class="prose">An earthquake sends out several kinds of wave, and they travel at different '
     'speeds. That difference is the single most useful fact in seismology.</p>'
     '<div class="table-responsive"><table class="table table-sm align-middle">'
     '<thead><tr><th>Wave</th><th>Speed</th><th>Motion</th><th>What you see</th></tr></thead>'
     '<tbody>'
     '<tr><td><b>P</b> (primary)</td><td>~6 km/s</td><td>push&ndash;pull, like sound</td>'
     '<td>arrives <b>first</b>, usually smaller &mdash; a sharp tick</td></tr>'
     '<tr><td><b>S</b> (secondary)</td><td>~3.5 km/s</td><td>side-to-side shear</td>'
     '<td>arrives <b>later</b>, usually <b>bigger</b> &mdash; the real shaking</td></tr>'
     '<tr><td><b>Surface</b></td><td>~3 km/s</td><td>rolling, like ocean swell</td>'
     '<td>slowest, longest-lasting; dominates <i>distant</i> quakes</td></tr>'
     '</tbody></table></div>'
     '<p class="prose">Because P outruns S, the gap between them grows with distance &mdash; and a '
     '<b>single</b> station can therefore estimate how far away a quake was, even though it cannot '
     'tell which <i>direction</i> it came from. The rule of thumb: <b>multiply the P&ndash;S gap in '
     'seconds by about 8 to get kilometres.</b> A 3-second gap means roughly 25 km away; a '
     '10-second gap, about 80 km.</p>'
     '<p class="prose">If that feels familiar, it is <i>exactly</i> the same trick as '
     '<b>counting the seconds between the lightning flash and the thunder</b> and dividing by '
     'five for miles. One event, two signals, different speeds: the gap between their arrivals '
     'grows in proportion to distance, at a rate set only by the <b>difference between the two '
     'speeds</b>. For light and sound that difference works out to five seconds per mile; for '
     'P and S waves, about eight kilometres per second of gap. Same law, different numbers.</p>'
     '<p class="mb-0 prose">This is also the honest way to tell a real earthquake from someone '
     'closing a door: a quake shows <b>two arrivals</b> a few seconds apart, then a long tail that '
     'fades slowly (the <i>coda</i>). A door is one thump that stops.</p>'),

    ("Microseisms: the ocean, humming, forever",
     '<p class="prose">Even with no earthquakes anywhere and nobody moving, the ground is never '
     'still. Ocean waves press rhythmically on the seafloor, and that pressure radiates through '
     'the crust as a continuous, worldwide vibration called the <b>microseism</b>. It is the '
     'loudest thing in most seismic records &mdash; a permanent background hum, strongest in '
     'winter storm season.</p>'
     '<p class="prose">It is slow: peaks around <b>0.07&nbsp;Hz and 0.15&nbsp;Hz</b>, meaning one '
     'cycle every 7 to 14 seconds. You could not feel it, but a good instrument sees it '
     'constantly.</p>'
     '<p class="prose"><b>This station cannot hear it</b>, and that is by design rather than by '
     'fault &mdash; see the next section for why. If you wonder why the spectrum page is cut off '
     'at the left, that is the reason.</p>'
     '<p class="mb-0 prose">There <i>are</i> peaks down in that range on our spectrum, but they '
     'are not the ocean, and the shape gives it away. A microseism is a <b>broad hump</b> '
     'spreading across 0.05&ndash;0.2&nbsp;Hz. What we actually have is a set of <b>narrow '
     'spikes</b> at 0.035, 0.07, 0.14 and 0.195&nbsp;Hz &mdash; a fundamental with a period of '
     '28.6&nbsp;seconds plus its harmonics, which is the fingerprint of a machine cycling on and '
     'off somewhere in the house, not of an ocean. (Confirmed by measurement, 2026-07-23. It is '
     'a nice coincidence trap: the 0.07&nbsp;Hz harmonic lands squarely in the microseism band.) '
     'Underneath them the curve rises smoothly toward the left, and that part is the '
     'instrument&rsquo;s own electrical noise.</p>'
     '<p class="mb-0 prose small text-muted">The <a href="/spectrum">spectrum page</a> does shade the microseism band, but only to show you <i>where</i> it lives relative to what this sensor can reach &mdash; it is labelled &ldquo;below our response&rdquo; for that reason.</p>'),

    ("What this geophone can and cannot hear",
     '<p class="prose">Every sensor has a band of frequencies it responds to. This one is a '
     '<b>4.5&nbsp;Hz geophone</b>: it hears things that vibrate a few times per second and faster, '
     'and it goes progressively deaf below that. By the microseism it is around '
     '<b>60&nbsp;dB down</b> &mdash; a factor of a thousand &mdash; so those slow ocean waves are '
     'simply below the instrument, not missing from the world.</p>'
     '<div class="table-responsive"><table class="table table-sm align-middle">'
     '<thead><tr><th>Source</th><th>Frequency</th><th>Heard here?</th></tr></thead><tbody>'
     '<tr><td>Footsteps, doors, appliances, cars</td><td>2&ndash;30 Hz</td>'
     '<td class="text-success"><b>Loud and clear</b> &mdash; most of what we record</td></tr>'
     '<tr><td>Small local earthquake, tens of km</td><td>2&ndash;20 Hz</td>'
     '<td class="text-success"><b>Yes</b> &mdash; the target</td></tr>'
     '<tr><td>Moderate quake, a few hundred km</td><td>1&ndash;10 Hz</td>'
     '<td>Usually, if big enough</td></tr>'
     '<tr><td>Great quake on the far side of the planet</td><td>0.01&ndash;0.05 Hz</td>'
     '<td class="text-danger"><b>No</b> &mdash; arrives as slow swells we are deaf to</td></tr>'
     '<tr><td>Ocean microseism</td><td>0.07&ndash;0.15 Hz</td>'
     '<td class="text-danger"><b>No</b> &mdash; ~1000× below our response</td></tr>'
     '<tr><td>Earth&rsquo;s &ldquo;hum&rdquo; (free oscillations)</td><td>0.002&ndash;0.007 Hz</td>'
     '<td class="text-danger"><b>No</b> &mdash; needs a million-dollar gravimeter</td></tr>'
     '</tbody></table></div>'
     '<p class="mb-0 prose">So this is a <b>local earthquake instrument</b>. The trade is '
     'deliberate: a sensor that hears the whole planet costs thousands and needs a vault, while '
     'this one costs about thirty dollars and sits on a garage floor above an active fault '
     'system.</p>'),

    ("Why most &ldquo;detections&rdquo; are not earthquakes",
     '<p class="prose">The station watches for sudden jumps in energy (see <i>STA/LTA</i> in the '
     'glossary) and logs each one. Nearly all of them are <b>cultural noise</b> &mdash; the '
     'seismologist&rsquo;s word for humans and machinery. Footsteps, a door, the fridge '
     'compressor, a car in the driveway.</p>'
     '<p class="prose">Frustratingly, you cannot filter them out by size: a sharp thump right next '
     'to the sensor produces a <i>bigger</i> reading than a genuine earthquake fifty kilometres '
     'away. So the table shows a <b>character</b> label describing the <i>shape</i> of each '
     'detection, which is a better clue than its amplitude. It is a description, not a verdict.</p>'
     '<p class="mb-0 prose">If you want to check something yourself, the '
     '<a href="https://earthquake.usgs.gov/earthquakes/map/">USGS map</a> lists real quakes with '
     'times in UTC. A detection here that matches a catalogue entry, at a sensible P&ndash;S gap, '
     'is the real thing.</p>'),

    ("Reading the views on the front page",
     '<p class="prose"><b>Live waveform</b> &mdash; the last 30 seconds, scrolling. Flat means '
     'quiet. The numbers underneath give the current noise level; the smaller the better.</p>'
     '<p class="prose"><b>Live spectrum</b> &mdash; the same 30 seconds, but broken out by '
     'frequency instead of time: <i>which</i> vibrations are present rather than <i>when</i>. '
     'The rise at the left is the instrument going deaf, not real ground motion.</p>'
     '<p class="mb-0 prose"><b>Helicorder</b> &mdash; the classic paper-drum view, one row per '
     '15&nbsp;minutes, four hours per screen. This is where an earthquake looks like an '
     'earthquake: a sudden fat burst that tapers off, unlike the even fuzz of ordinary noise. '
     'Fat rows during the day and thin rows at 4&nbsp;AM are people, not geology. '
     'Small coloured carets mark where quakes in the USGS catalogue <i>should</i> have arrived, so '
     'you can check the record yourself &mdash; a prediction of where to look, not a claim that this '
     'station caught anything. Catalogue entries appear minutes to hours after the event, so the '
     'newest rows are always unmarked. The drum has its own section below &mdash; '
     '<a href="#how-to-read-the-helicorder">how to read the helicorder</a> &mdash; including '
     'what the colours do and do not mean.</p>'),

    # Written after a first-time viewer asked whether the drum's four colours were four
    # simultaneous data feeds. Everything here answers a question somebody actually had.
    ("How to read the helicorder",
     '<p class="prose">The drum &mdash; the <i>helicorder</i> &mdash; is the oldest display in '
     'seismology and the least self-explanatory. It imitates a machine that really existed: a '
     'paper drum turning under an inked pen, the pen tracing the ground&rsquo;s motion, the drum '
     'shifting down one line each rotation so a day of shaking fitted on one sheet. Everything '
     'odd about the layout follows from that.</p>'
     '<p class="prose"><b>Each row is 15 minutes</b>, and there are 16 of them, so one screen is '
     'four hours. The oldest row is at the top and time runs left to right along each row, then '
     'down to the next &mdash; exactly like lines of text. The numbers along the bottom are '
     'minutes <i>into</i> a row, not clock time; the clock time of each row is the label on its '
     'left. Everything is <b>UTC</b>, which in California is 7 hours ahead of local time &mdash; '
     'so a row labelled 09:00 is two in the morning here.</p>'
     '<p class="prose"><b>The four colours mean nothing at all.</b> This is the question '
     'everyone asks first, and the honest answer is that red, green, blue and black simply '
     'repeat every fourth row so your eye can follow one line without sliding into its '
     'neighbour. There is <i>one</i> sensor here, measuring <i>one</i> thing &mdash; vertical '
     'ground velocity. They are not four instruments, four stations, or four frequency bands. '
     'On a busy row the trace is tall enough to overlap the rows above and below, and without '
     'alternating colours it becomes impossible to tell whose wiggle is whose.</p>'
     '<p class="prose"><b>Height is how hard the ground moved.</b> A quiet line is a thin fuzzy '
     'band; a loud one swells into a fat spindle. The scale is set by each window&rsquo;s own '
     'typical noise, so a quiet night is not drawn smaller than a busy afternoon &mdash; compare '
     'shapes, not heights, between windows. Anything enormous is clipped to three rows tall '
     'rather than being allowed to scribble over half the screen.</p>'
     '<p class="prose"><b>What an earthquake looks like:</b> a sudden onset, a fat burst, then a '
     'tapering tail lasting tens of seconds &mdash; loud, then gradually not. What ordinary '
     'noise looks like: even fuzz, roughly the same thickness all the way across. What a door '
     'slam looks like: a single narrow spike with nothing before or after it. Fat rows through '
     'the working day and thin rows at 4&nbsp;AM are people, not geology.</p>'
     '<h6 class="mt-4">Faded stretches: near or far</h6>'
     '<p class="prose">A loud burst is genuinely ambiguous on a drum &mdash; somebody wheeling a '
     'bin past the garage and a real earthquake can look identical. So the station separates '
     'them by <b>pitch</b> rather than by size, and it can, because of a fact about how the '
     'ground carries vibration: <b>distance filters out the high frequencies.</b> Rock is not a '
     'perfect transmitter; the fast wiggles die out within a few kilometres while the slow ones '
     'travel on. A real earthquake, even a close one, arrives with almost all its energy below '
     '15&nbsp;Hz. Something happening three metres away arrives with its high frequencies '
     'intact.</p>'
     '<p class="prose">Measured here, that difference is stark. An M4.1 earthquake 88&nbsp;km '
     'away put 30 times more energy below 8&nbsp;Hz than above 15. Rolling a wheelie bin past '
     'the sensor did the exact opposite, by a factor of eight. Nothing in between was '
     'ambiguous.</p>'
     '<p class="prose">So any stretch of the trace that is both <b>loud</b> and '
     '<b>high-pitched</b> is drawn <b>faded</b>: that is the station saying <i>this one came '
     'from nearby &mdash; a footstep, a door, a car in the driveway</i>. Inside a faded burst '
     'you will see a <b>solid full-colour core</b>. That is the same moment redrawn using only '
     'the 1&ndash;8&nbsp;Hz part of the signal &mdash; the band an earthquake would live in. It '
     'lets you see through the local racket: if the core stays thin, everything that happened '
     'was near-field noise; if the core swells, something arrived in the seismic band and is '
     'worth a closer look.</p>'
     '<p class="prose">Two honest limits. <b>Fading is a positive identification, not an '
     'exhaustive one</b> &mdash; only unambiguously high-frequency bursts get marked, so a '
     'quieter or lower-pitched local source stays at full strength. Reading &ldquo;not '
     'faded&rdquo; as &ldquo;earthquake&rdquo; is exactly the mistake to avoid. And <b>the core '
     'is not the earthquake</b>: it is whatever motion existed in that band, noise included. '
     'It narrows the question; it does not answer it.</p>'
     '<p class="prose">Does the fading hide anything? No &mdash; nothing is removed, and the '
     'full recording is kept. It costs sensitivity, not data: measured against a real '
     'earthquake replayed into a recorded burst of local noise, an event hiding inside one is '
     'about <b>0.8 magnitude units</b> harder to see than the same event on a quiet night. '
     'During a noisy stretch this is a less sensitive station, not a deaf one.</p>'
     '<h6 class="mt-4">The triangles</h6>'
     '<p class="mb-0 prose">Small coloured carets mark where an earthquake from the '
     '<b>USGS catalogue</b> should have arrived, given its distance and the speed of seismic '
     'waves through this crust. The label is its magnitude, and the colour is how likely this '
     'station was to feel it at all &mdash; strong, likely, or marginal. They are a prompt to '
     'look at a particular second, <b>not</b> a claim that anything was detected: the eye '
     'decides. Catalogue entries are published minutes to hours after the fact, so the newest '
     'rows are always unmarked.</p>'),

    ("Glossary",
     '<div class="table-responsive"><table class="table table-sm align-middle"><tbody>'
     '<tr><td><b>Geophone</b></td><td>The sensor: magnet on a spring inside a coil. Converts '
     'ground <i>velocity</i> into a voltage.</td></tr>'
     '<tr><td><b>4.5&nbsp;Hz</b></td><td>This geophone&rsquo;s corner frequency &mdash; roughly '
     'where it stops responding well as frequencies fall.</td></tr>'
     '<tr><td><b>Hz (hertz)</b></td><td>Cycles per second. 10&nbsp;Hz = ten vibrations per '
     'second.</td></tr>'
     '<tr><td><b>µV (microvolt)</b></td><td>A millionth of a volt. Our quiet-night signal is under '
     'one.</td></tr>'
     '<tr><td><b>nm/s</b></td><td>Nanometres per second &mdash; actual ground speed. A quiet night '
     'here is ~35.</td></tr>'
     '<tr><td><b>Velocity / displacement / acceleration</b></td><td>Three ways to describe the '
     'same motion. A geophone (this station) senses <i>velocity</i> &mdash; how fast the ground '
     'moves. Broadband seismometers report <i>displacement</i> (how far) and accelerometers '
     'report <i>acceleration</i> (how hard the shove); each suits a different job.</td></tr>'
     '<tr><td><b>Component</b></td><td>The direction a sensor listens along &mdash; vertical (Z, '
     'like ours), or the two horizontals (N and E). A full station runs all three.</td></tr>'
     '<tr><td><b>ADC / counts</b></td><td>The analogue-to-digital converter turns the voltage into '
     'whole numbers (&ldquo;counts&rdquo;) 100 times a second.</td></tr>'
     '<tr><td><b>sps</b></td><td>Samples per second. This station records 100.</td></tr>'
     '<tr><td><b>P wave / S wave</b></td><td>The fast push&ndash;pull arrival and the slower, '
     'larger shear arrival. Their gap gives distance.</td></tr>'
     '<tr><td><b>Coda</b></td><td>The long fading tail after a quake, from waves scattering off '
     'underground structure.</td></tr>'
     '<tr><td><b>Microseism</b></td><td>Continuous worldwide background hum driven by ocean waves, '
     '0.07&ndash;0.15&nbsp;Hz. Below this instrument.</td></tr>'
     '<tr><td><b>Cultural noise</b></td><td>Vibration from people and machines. Dominates any '
     'suburban station.</td></tr>'
     '<tr><td><b>Teleseism</b></td><td>A distant earthquake, thousands of km away. Needs a '
     'broadband sensor, not this one.</td></tr>'
     '<tr><td><b>STA/LTA</b></td><td>Short-Term Average over Long-Term Average: compares recent '
     'energy to the recent past. A big ratio means &ldquo;something just started&rdquo; and trips '
     'a detection.</td></tr>'
     '<tr><td><b>Helicorder</b></td><td>Drum-style plot, one row per time interval &mdash; named '
     'for the rotating paper drums of mechanical seismographs.</td></tr>'
     '<tr><td><b>Spectrum / ASD</b></td><td>Amplitude spectral density: signal strength per '
     'frequency, in µV per root-hertz. Lets you compare noise at one frequency against '
     'another.</td></tr>'
     '<tr><td><b>High-pass filter</b></td><td>Throws away slow drift and keeps the fast wiggles, '
     'so slow temperature-driven tilt does not swamp the quake band.</td></tr>'
     '<tr><td><b>Magnitude</b></td><td>Earthquake size on a logarithmic scale: each whole number '
     'is ~32× more energy. M2 is barely felt; M6 damages buildings.</td></tr>'
     '<tr><td><b>UTC</b></td><td>Universal time, used for everything here so records worldwide '
     'line up. Local time is UTC&nbsp;&minus;&nbsp;7 in summer.</td></tr>'
     '<tr><td><b>miniSEED</b></td><td>The standard file format for seismic data, so this '
     'station&rsquo;s recordings work with professional tools.</td></tr>'
     '<tr><td><b>Noise floor</b></td><td>The smallest motion the instrument can distinguish from '
     'its own electrical hiss. Lowering it is most of the work.</td></tr>'
     '</tbody></table></div>'),

    ("Where this station sits, and why here",
     '<p class="prose">{place} &mdash; on valley-margin sediments essentially on top of the active '
     '<b>Rodgers Creek</b> fault system, with the <b>Maacama</b> fault nearby and '
     '<b>The Geysers</b> geothermal field about 30&nbsp;km north. The Geysers is the most '
     'seismically active spot in Northern California, producing hundreds of small quakes a year, '
     'which makes it the most likely source of anything genuine this station records.</p>'
     '<p class="mb-0 prose">Sitting on soft sediment is a mixed blessing: it <i>amplifies</i> '
     'shaking, which helps a sensitive instrument, but it also carries more everyday noise. For a '
     'station whose goal is catching small local events, that is the right side of the trade.</p>'),
    ("Keep learning",
     '<p class="prose">A few public-facing explainers worth your time, in roughly the order '
     'you might want them. All free, none of them ours.</p>'
     '<ul class="prose mb-0">'
     '<li><a href="https://www.usgs.gov/programs/earthquake-hazards/science-earthquakes">'
     'The Science of Earthquakes</a> (USGS) &mdash; the one-page version of what a fault is, '
     'what slips, and why it shakes. Start here if the glossary above was new.</li>'
     '<li><a href="https://www.usgs.gov/programs/earthquake-hazards/earthquake-magnitude-energy-release-and-shaking-intensity">'
     'Magnitude, energy and shaking intensity</a> (USGS) &mdash; why an M4 is thirty-two times '
     'the energy of an M3, and why magnitude is not the same thing as how hard it shook '
     'where you were.</li>'
     '<li><a href="https://www.iris.edu/hq/inclass">IRIS / EarthScope classroom animations</a> '
     '&mdash; short animated explainers of P and S waves, how a seismometer works, and how '
     'three stations locate an earthquake. The best pictures of the ideas on this page.</li>'
     '<li><a href="https://seismo.berkeley.edu/">Berkeley Seismology Lab</a> &mdash; the '
     'professionals who watch Northern California, with the faults, the recent events, and '
     'the research behind the Hayward&ndash;Rodgers Creek system this station sits on.</li>'
     '<li><a href="https://pubs.usgs.gov/fs/2008/3019/">The Hayward Fault &mdash; is it due '
     'for a repeat?</a> (USGS fact sheet) &mdash; the local hazard in eight pages, and why the '
     'fault under Oakmont is the one to know about.</li>'
     '<li><a href="https://earthquake.usgs.gov/earthquakes/map/">USGS Latest Earthquakes</a> '
     '&mdash; the live map; every catch on this site was confirmed against it.</li>'
     '<li><a href="https://www.earthquakecountry.org/roots/">Putting Down Roots in Earthquake '
     'Country</a> &mdash; what to actually do about all of this, from the people who write '
     'California&rsquo;s preparedness guidance.</li>'
     '<li><a href="https://www.shakealert.org/">ShakeAlert</a> &mdash; earthquake early warning '
     'for the West Coast. If you live here and your phone is not set up for it, this is the '
     'most useful link on the page.</li>'
     '</ul>'),
]


ABOUT_SECTIONS = [
    ("What this is",
     '<p class="mb-0 prose">A homemade (&ldquo;DIY&rdquo;) seismometer &mdash; an amateur '
     'instrument that senses the ground moving: earthquakes, the ocean, and everyday cultural '
     'vibration. It records continuously and is <b>independent</b> (not part of a formal seismic '
     'network), built for curiosity and learning. <b>Not for scientific or emergency use.</b> '
     'The station is still being <b>tested, tuned, and modified</b>, so spurious signals '
     '(from the work itself, not the ground) may appear in the data.</p>'
     '<p class="mb-0 prose">New to any of this? <a href="/learn">Seismology&nbsp;101</a> explains P and S waves, microseisms, what this sensor can and cannot hear, and every term used on these pages.</p>'),
    ("Hardware",
     '<ul class="mb-0"><li><b>Sensor:</b> LGT-4.5 geophone &mdash; a 4.5&nbsp;Hz vertical geophone '
     '(a coil-and-magnet <i>velocity</i> sensor), ~28.8&nbsp;V per m/s, 385&nbsp;&#8486; coil.</li>'
     '<li><b>Digitizer:</b> Waveshare High-Precision <b>ADS1256</b> &mdash; 24-bit ADC, read '
     'differentially at gain&nbsp;64, 100&nbsp;samples/sec.</li>'
     '<li><b>Computers:</b> a Raspberry&nbsp;Pi&nbsp;2B does acquisition (owns the ADC); a '
     'Raspberry&nbsp;Pi&nbsp;5 renders these charts and serves this page.</li>'
     '<li><b>Front end:</b> differential bias network into the ADC (shunt damping to come).</li></ul>'),
    ("How to read the charts",
     '<p class="prose"><b>Live waveform</b> &mdash; the ground moving <i>right now</i>, in microvolts '
     'of sensor output (proportional to ground velocity). Flat = quiet; wiggles = motion. It '
     'auto-scales, so a calm trace and a busy one can look similar in height &mdash; watch the '
     '&ldquo;pp&rdquo; number.</p>'
     '<p class="prose"><b>Helicorder (drum plot)</b> &mdash; the classic seismograph view. Each row '
     'is 15&nbsp;minutes; read it like a book &mdash; left&nbsp;&rarr;&nbsp;right, then down to the '
     'next row. The last 4&nbsp;hours (UTC). Earthquakes and bumps appear as bursts standing out from '
     'the steady background hum.</p>'
     '<p class="prose"><b>Spectrum (Welch ASD)</b> &mdash; the ground&rsquo;s frequency <i>content</i>: '
     'how much signal sits at each frequency. &ldquo;ASD&rdquo; is amplitude spectral density '
     '(&micro;V per &radic;Hz); &ldquo;Welch&rdquo; is the averaging method that turns a jittery '
     'signal into a smooth, trustworthy curve. Shaded/annotated zones: the <b>ocean microseism</b> '
     '(~0.1&ndash;0.35&nbsp;Hz, the ever-present hum of Pacific swell), the <b>local-earthquake band</b> '
     '(~1&ndash;15&nbsp;Hz), the geophone&rsquo;s <b>4.5&nbsp;Hz corner</b> (it&rsquo;s flat/sensitive '
     'above this, and goes progressively deaf below it), and the flat <b>electronic noise floor</b> at '
     'high frequency. The plot stops at 0.05&nbsp;Hz on the left: below the microseism, a 4.5&nbsp;Hz '
     'geophone is ~60&nbsp;dB down, so anything lower is the instrument&rsquo;s own noise, not the '
     'ground. Seeing below that (distant &ldquo;teleseismic&rdquo; quakes, Earth&rsquo;s slow hum) takes '
     'a different sensor &mdash; a force-balance broadband, or a DIY long-period pendulum.</p>'
     '<p class="mb-0 prose"><b>Detections</b> (on their <a href="/detections">own page</a>) &mdash; '
     'automatic STA/LTA triggers (sudden energy '
     'jumps). Most are <i>cultural</i> (footsteps, machinery, doors), not earthquakes &mdash; a genuine '
     'local quake would show a sharp P&nbsp;arrival followed seconds later by a larger S. '
     'The <b>character</b> column describes the <i>shape</i> of each detection, nothing more: '
     '&ldquo;impulsive&rdquo; means a single sharp spike in an otherwise quiet window, which is what '
     'household thumps look like; &ldquo;sustained&rdquo; means the energy lasts, and '
     '&ldquo;near-threshold&rdquo; means it barely cleared the trigger. It is deliberately <b>not</b> an '
     'earthquake/not-earthquake verdict &mdash; a very close quake is impulsive too, and this station has '
     'yet to record a confirmed one to check the labels against.</p>'),
    ("Where it sits",
     '<p class="mb-0 prose">{place} &mdash; on valley-margin alluvium at the foot of the '
     'Sonoma/Mayacamas volcanics, essentially atop the active <b>Rodgers Creek fault</b> system. A '
     'sensitive spot for local events, at the cost of a bit more everyday noise.</p>'),
]

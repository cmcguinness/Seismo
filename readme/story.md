# The story

## Why?

The origin of the project was my noticing that a chandelier in our house, which is
hanging on about 10 feet of chain, was very sensitive to ground motion. If my wife
yelled out "was that an earthquake?" and I was unsure, I'd go look at the chandelier to
see if it was moving. I joked that I should attach permanent magnets to the chandelier
and then wrap it in a giant coil to turn it into a geophone. My wife did not approve
whatsoever of the idea. Next I thought about using computer vision to read its
movements. However, research proved it would not be a good device for that either. But
at that point the idea of a home seismometer was planted in my brain.

The natural approach to building a home device is to buy an off-the-shelf
[Raspberry Shake](https://raspberryshake.org) box. That's a great option. But I learn by
building things, not just having them, so I decided to do so using the Shake as a design
inspiration: clearly a Raspberry Pi, an A/D board and a small geophone would work and,
in the famous ignorance of a programmer, "how hard could that be."

Before the era of agentic programming, or in my case Claude Code, the answer would have
been very hard. With AI's help, it became merely hard. That difference is what made this
happen instead of being put on the backlog. That is part of the story here and what
makes this interesting.

## Caveats and truths

I am not a professional seismologist; I am a professional software engineer, with a
graduate degree in AI. I'm also an amateur hardware engineer; much of this project was
spent with a soldering iron in hand.

To "get it right", I've done a few things. One is to reference successful designs, like
the Shake. I did not copy their design, but I also didn't do something completely
different. Another is that a USGS strong-motion accelerometer, station NP.1835 of the
National Strong Motion Project, sits about a mile from my house, so I have a professional
benchmark for my device. And, indeed, the professional instrument validates the readings
my device gives: after one empirical sensitivity factor the two agree to about 1.2x, and
that ratio is flat across the band where the comparison is fair. How that was checked is
in [reproducing.md](reproducing.md).

So I am confident that the design is good. But, of course, I am not a professional
seismologist...

## What it has done so far

As of 2026-09-02: 34 catalogue-confirmed earthquakes inside a validated detection range
of 88.8 km for M2, plus an M4.8 off Petrolia at 319 km, verified by arrival time. Every
confirmed event is shown beside NP.1835's record, in ground velocity on the same axes, at
https://seismo.mcguinness.ai/catches.

The geophone's natural frequency and damping are still nominal values from the
datasheet; an inline calibration injector (`calibrator/`, `doc/BOM-calibrator.md`) is
being built to measure them.

For the current state of the system, `STATUS.md` at the repo root is always more
current than this page.

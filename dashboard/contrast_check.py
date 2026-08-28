#!/usr/bin/env python3
"""WCAG contrast gate for the dashboard's colour tokens.

The palette lives in one place (the CSS block in seismo_dashboard.py) and every colour
on the site comes from it, so the whole site's contrast can be checked by checking that
block. This reads the tokens straight out of the source -- no second copy to drift --
and asserts a ratio for each pair that actually meets on screen, in BOTH themes.

    python3 contrast_check.py          # report + exit 1 on any failure

Targets (WCAG 2.1):
  AAA  7.0   body and caption text -- this site is mostly reading, so prose gets AAA
  AA   4.5   normal-size text that is not body copy (links, axis labels, badges)
  AA   3.0   large text (>=24px, or >=18.7px bold) and graphical objects (1.4.11):
             the live trace, plot axes, the status lamp, form borders, focus ring
"""
import re
import sys

SRC = "seismo_dashboard.py"


def parse_tokens(css: str) -> dict[str, dict[str, str]]:
    """{theme: {token: hex}} for the :root and [data-bs-theme="dark"] blocks."""
    out: dict[str, dict[str, str]] = {}
    for theme, opener in (("light", r":root\{"), ("dark", r'\[data-bs-theme="dark"\]\{')):
        m = re.search(opener + r"(.*?)\n \}", css, re.S)
        if not m:
            raise SystemExit(f"{SRC}: no {theme} token block found")
        out[theme] = {k: v.strip().lower()
                      for k, v in re.findall(r"--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})", m.group(1))}
    # the dark block only overrides; anything it omits still comes from :root
    out["dark"] = {**out["light"], **out["dark"]}
    return out


def luminance(hex_colour: str) -> float:
    c = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    lo, hi = sorted((a, b))
    return (hi + 0.05) / (lo + 0.05)


# (foreground token, background token, minimum ratio, what it is)
CHECKS = [
    ("ink",        "ground", 7.0, "body text on the page"),
    ("ink",        "panel",  7.0, "body text on a lifted surface"),
    ("ink",        "rail",   7.0, "station code and active nav item"),
    # ink-dim carries whole paragraphs (drum how-to, figure captions, the lede), not
    # just micro-labels, so it is held to the body-text target rather than AA.
    ("ink-dim",    "ground", 7.0, "secondary prose and captions"),
    ("ink-dim",    "rail",   7.0, "rail labels, nav items, provenance"),
    ("copper",     "ground", 4.5, "links and the hero reading"),
    ("copper",     "rail",   4.5, "the active nav marker and rail reading"),
    ("copper-lit", "ground", 4.5, "link hover"),
    ("rose",       "ground", 4.5, "the 4.5 Hz marker label and warnings"),
    ("plot-label", "ground", 4.5, "axis numbers on the live canvases"),
    ("plot-trace", "ground", 3.0, "the live trace (graphical object)"),
    ("plot-axis",  "ground", 3.0, "canvas axis lines (graphical object)"),
    ("lamp",       "rail",   3.0, "the recording lamp (state indicator)"),
    ("ground",     "copper", 4.5, "button label on a copper fill"),
    ("yes",        "ground", 7.0, "inline yes verdicts in prose"),
    ("no",         "ground", 7.0, "inline no verdicts in prose"),
]


def main() -> int:
    css = open(SRC, encoding="utf-8").read()
    tokens = parse_tokens(css)
    bad = 0
    for theme in ("light", "dark"):
        print(f"\n{theme}")
        t = tokens[theme]
        for fg, bg, need, what in CHECKS:
            if fg not in t or bg not in t:
                print(f"  ??  --{fg} / --{bg}: token missing")
                bad += 1
                continue
            r = ratio(t[fg], t[bg])
            ok = r >= need
            bad += not ok
            print(f"  {'ok ' if ok else 'FAIL'} {r:5.2f}:1  (need {need:.1f})  "
                  f"--{fg} {t[fg]} on --{bg} {t[bg]}   {what}")
    print()
    if bad:
        print(f"{bad} contrast failure(s)")
    else:
        print("all pairs pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

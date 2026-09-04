#!/usr/bin/env python3
"""docpage.py — render a repo Markdown document as a page on this site.

WHY THIS EXISTS RATHER THAN A COPY IN content.py. Every other page's prose lives in
`content.py` as hand-written HTML, and the obvious way to put `readme/classifier.md` on
the site would be to paste it in there and reformat. That would create a SECOND COPY of
a document whose whole value is being correct, and the two would drift -- not
hypothetically: on 2026-09-04 the classifier's headline precision in STATUS.md was found
to be three weeks stale, quoted at the wrong threshold, and copied out of an entry whose
own caveat had been left behind. One source, rendered on demand, cannot do that.

So the file in `readme/` is the single source. GitHub renders it for anyone reading the
repo; this module renders the same bytes for anyone reading the website.

MERMAID. GitHub renders ```mermaid fences natively. Browsers do not, so the page loads
mermaid.js and hands it `<pre class="mermaid">` blocks -- the selector its auto-loader
looks for. The diagram source has to be kept AWAY from the Markdown parser on the way
through, because arrows and pipes and braces are all Markdown-significant and it would
happily mangle them into emphasis and tables. Hence extract-then-reinsert below rather
than a parser extension: fewer moving parts, and you can read it.

    from docpage import render_doc
    html, title = render_doc("classifier.md")
"""
import os
import re

# Where the Markdown actually is, in the two places this app runs.
#
# Deployed, deploy.sh rsyncs readme/*.md into the build context as docs/ -- the same
# trick already used for analysis/epochs.py, and for the same reason: the Docker build
# context is the dashboard/ directory, so anything from elsewhere in the repo has to be
# copied in. Locally, the repo is right there and no copy exists. Try both, in that
# order, so the deployed copy always wins on the hosts that have one.
_HERE = os.path.dirname(os.path.abspath(__file__))
DOC_DIRS = [os.path.join(_HERE, "docs"),
            os.path.join(os.path.dirname(_HERE), "readme")]

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"

# The UMD bundle loaded by a plain <script>, NOT `import mermaid from .../mermaid.min.js`
# as a module: that file is UMD and exports no `default`, so the module form fails with
# "does not provide an export named 'default'" and the diagrams silently stay as source
# text. (jsdelivr's `/+esm` path would work, but it pulls a code-split tree of further
# requests for no benefit here.)
#
# startOnLoad is off and run() is called explicitly, so nothing depends on whether
# DOMContentLoaded has already fired by the time the CDN answers.
#
# securityLevel 'strict' keeps mermaid from honouring any HTML or click handlers inside
# diagram source. That source is ours, but the setting costs nothing and the rule is that
# a renderer should not be able to inject markup into the page.
#
# The theme is read from the same `data-bs-theme` attribute the rest of the site uses.
# Mermaid bakes its colours into the SVG at draw time, so a diagram drawn in light mode
# stays light when the visitor flips to dark -- black text on a dark ground -- hence the
# redraw on the site's own `seismo:theme` event, from the stashed original source.
MERMAID_TAG = f"""<script src="{MERMAID_CDN}"></script>
<script>
(function () {{
  if (!window.mermaid) return;
  var blocks = document.querySelectorAll('pre.mermaid');
  if (!blocks.length) return;
  blocks.forEach(function (el) {{ el.dataset.src = el.textContent; }});

  function theme() {{
    return document.documentElement.getAttribute('data-bs-theme') === 'dark'
      ? 'dark' : 'default';
  }}
  function draw() {{
    // Edge labels ("yes", "no -- go again") otherwise get mermaid's own pale label
    // background, which reads as a grey chip sitting on top of a dark page. Handing it
    // the page's actual background colour makes them sit on the page instead.
    var bg = getComputedStyle(document.body).backgroundColor;
    mermaid.initialize({{
      startOnLoad: false, theme: theme(), securityLevel: 'strict',
      themeVariables: {{edgeLabelBackground: bg}}
    }});
    mermaid.run({{querySelector: 'pre.mermaid'}});
  }}
  draw();

  window.addEventListener('seismo:theme', function () {{
    blocks.forEach(function (el) {{
      el.innerHTML = '';
      el.textContent = el.dataset.src;
      el.removeAttribute('data-processed');
    }});
    draw();
  }});
}})();
</script>"""

_FENCE = re.compile(r"^```mermaid[ \t]*\n(.*?)^```[ \t]*$", re.S | re.M)
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)


def doc_path(name):
    """Absolute path to a doc by bare filename, or None. Refuses anything with a path
    separator in it -- this is reached from a URL."""
    if not name.endswith(".md") or "/" in name or "\\" in name or ".." in name:
        return None
    for d in DOC_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


_LINK_OPEN = re.compile(r'<a href="([^"]+)"')


def _rewrite_links(html):
    """Point repo-relative links at GitHub, leave everything else alone.

    A file in readme/ links to its siblings as `architecture.md` and to code as
    `../analysis/trigger_train.py`. Neither resolves on this website, and a silently
    broken link in a teaching document is worse than no link, so they are sent to the
    repo instead of dropped. Absolute URLs, `mailto:` and in-page anchors (the footnote
    links, among others) are untouched.
    """
    def fix(m):
        href = m.group(1)
        if href.startswith(("http://", "https://", "#", "mailto:")):
            return m.group(0)
        rel = href[3:] if href.startswith("../") else "readme/" + href
        return f'<a href="https://github.com/cmcguinness/Seismo/blob/main/{rel}" rel="noopener"'
    return _LINK_OPEN.sub(fix, html)


def render_doc(name):
    """(html, title) for a repo Markdown doc, or (None, None) if there is no such doc."""
    import markdown

    p = doc_path(name)
    if not p:
        return None, None
    with open(p, encoding="utf-8") as fh:
        src = fh.read()

    # Title from the H1, which is then dropped: the site draws its own title block, and
    # two identical headings stacked looks like a bug.
    m = _H1.search(src)
    title = m.group(1) if m else name
    if m:
        src = src[:m.start()] + src[m.end():]

    # Park the diagrams somewhere the parser will not touch them. The placeholder is a
    # bare word on its own line so Markdown leaves it as a paragraph we can find again.
    diagrams = []

    def stash(mm):
        diagrams.append(mm.group(1))
        return f"\n\nMERMAIDBLOCK{len(diagrams) - 1}ENDMERMAID\n\n"

    src = _FENCE.sub(stash, src)

    html = markdown.markdown(src, extensions=["tables", "fenced_code", "footnotes",
                                              "attr_list", "sane_lists"],
                             extension_configs={"footnotes": {"BACKLINK_TEXT": "&#8617;"}})

    for i, d in enumerate(diagrams):
        html = html.replace(f"<p>MERMAIDBLOCK{i}ENDMERMAID</p>",
                            f'<pre class="mermaid">{d}</pre>')

    return _rewrite_links(html), title

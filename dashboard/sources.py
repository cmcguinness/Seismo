#!/usr/bin/env python3
"""sources.py — score the live spectrum against the signature registry.

Reads signatures.json (data, not code) and answers one question: does this window
look like any source we have characterised? Pure numpy — no obspy, no I/O per call —
so it runs on the live ring beside the spectrum that is already being computed.

Doctrine, inherited from the character badge (dashboard/CHARACTER.md): this is a
SOFT LABEL. It never filters a detection, never suppresses anything, and says
"looks like" rather than "is". Thresholds are set for RECALL — false positives are
currently cheap and are the labelling queue.

Two guards that exist because we have already been burned:

  EPOCH. A signature is only applied inside the acquisition epoch it was derived in
  (valid_from + derived_at_sps). Everything measurable here depends on the front end,
  and this station had three epochs in one week.

  STANDING LINES. The station carries permanent lines near 41 Hz and 20 Hz that score
  ~10x over their own local continuum with nothing running. A rule keyed only on
  peak-over-continuum calls those machinery. Every line feature therefore also has an
  absolute amplitude floor (min_asd).
"""
import json
import os

import numpy as np

SIG_PATH = os.environ.get("SEISMO_SIGNATURES",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "signatures.json"))
_cache = {"mtime": None, "sigs": [], "err": None}


def _load():
    """Signatures, reloaded when the file changes (edit + refresh, no rebuild)."""
    try:
        m = os.path.getmtime(SIG_PATH)
    except OSError as e:
        _cache.update(mtime=None, sigs=[], err=str(e))
        return _cache["sigs"]
    if _cache["mtime"] == m:
        return _cache["sigs"]
    try:
        with open(SIG_PATH) as f:
            doc = json.load(f)
        sigs = [s for s in doc.get("signatures", []) if s.get("id")]
        _cache.update(mtime=m, sigs=sigs, err=None)
    except Exception as e:                      # bad edit -> keep serving the old set
        _cache.update(mtime=m, err=f"{type(e).__name__}: {e}")
    return _cache["sigs"]


def _epoch_ok(sig, fs, now_iso):
    """True if this signature may be applied to data at `fs` taken at `now_iso`."""
    want = sig.get("derived_at_sps")
    if want is not None and abs(float(fs) - float(want)) > 0.5:
        return False
    vf = sig.get("valid_from")
    return not (vf and now_iso and now_iso < vf)


def _score_line(feat, f, asd):
    """Score a `line` feature. Returns (passed, detail) or (False, None) if the band
    isn't in range."""
    lo, hi = feat["band"]
    m = (f >= lo) & (f <= hi)
    if not m.any():
        return False, None
    k = int(np.argmax(asd[m]))
    fpk, apk = float(f[m][k]), float(asd[m][k])
    s_lo, s_hi = feat.get("shoulder", [1.5, 4.0])
    sh = (((f > fpk - s_hi) & (f < fpk - s_lo)) |
          ((f > fpk + s_lo) & (f < fpk + s_hi)))
    cont = float(np.median(asd[sh])) if sh.any() else float("nan")
    ratio = apk / cont if cont and np.isfinite(cont) and cont > 0 else float("nan")
    ok = (apk >= feat.get("min_asd", 0.0)
          and np.isfinite(ratio) and ratio >= feat.get("min_peak_shoulder", 0.0))
    return bool(ok), {"hz": round(fpk, 2), "asd": round(apk, 2),
                      "peak_shoulder": round(ratio, 1) if np.isfinite(ratio) else None}


_KINDS = {"line": _score_line}


def match(f, asd, fs, now_iso=None):
    """Signatures whose every feature passes, best (strongest line) first.

    f/asd are a raw Welch spectrum of the window. Returns a list of dicts ready to
    hand to a template: id, label, hint, status, detail.
    """
    out = []
    if f is None or asd is None or not len(f):
        return out
    for sig in _load():
        if not _epoch_ok(sig, fs, now_iso):
            continue
        feats = sig.get("features") or []
        if not feats:
            continue
        details, ok = {}, True
        for feat in feats:
            scorer = _KINDS.get(feat.get("kind"))
            if scorer is None:                  # unknown kind -> don't claim a match
                ok = False
                break
            passed, det = scorer(feat, f, asd)
            if det:
                details.update(det)
            if not passed:
                ok = False
                break
        if ok:
            out.append({"id": sig["id"], "label": sig.get("label", sig["id"]),
                        "pill": sig.get("pill") or sig.get("label", sig["id"]),
                        "hint": sig.get("hint", ""),
                        "status": sig.get("status", "provisional"),
                        "detail": details})
    out.sort(key=lambda r: -(r["detail"].get("asd") or 0))
    return out

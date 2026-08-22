#!/usr/bin/env python3
"""dc_watch.py — watchdog on the DC baseline, so a broken front end says so.

WHY THIS EXISTS. On 2026-07-31 the station lost the DC path on an input leg. The
baseline went to -2.2M counts and the detector emitted false EVENTs for hours, and
the way that was discovered was Charles noticing the drum looked wrong. The fault
had a perfectly clean signature the whole time -- the DC level -- but nothing was
watching it, because nothing was even keeping it (every stage of the pipeline
de-means, so the number was destroyed before anyone could look). `heli_build` now
banks it per interval; this module is the thing that watches it.

Three checks, cheapest first, most severe wins:

  STALE      no fresh interval -- the collector, the rsync mirror or the builder
             stopped. Not a DC fault at all, but the same "the station is broken"
             alarm, and three lines to add.
  EXCURSION  the last hour sits outside the envelope the station normally occupies.
             Scaled off the station's OWN recent history, not a hardcoded band: the
             DC level is strongly diurnal (~3800 counts p-p over a 4 C day) and a
             fixed threshold would either cry wolf every hot afternoon or be too
             wide to catch anything.
  STEP       a discontinuity between the last hour and the three before it that is
             large against the biggest hourly move the station normally makes. In
             practice EXCURSION catches most real faults first (they are enormous and
             they persist), so STEP covers the narrower case of a jump that lands
             INSIDE the usual band -- a connector, a knock, a rebuild that happens to
             settle somewhere plausible.

Notification hygiene matters more than sensitivity here: a watchdog that cries wolf
gets muted, and a muted watchdog is worse than none. So it fires only on a CHANGE of
state (into trouble, and back out), re-reminds at most every RENOTIFY_H hours while a
fault persists, and persists its state to disk so a container restart is not an event.

It also refuses to arm until it has ARM_HOURS of history: with a cold `dc` field the
baseline would be three points wide and everything would look like an excursion.

Notifications go to ntfy (see ~/.claude-personal/references/ntfy.md) when
SEISMO_NTFY_URL/TOPIC/TOKEN are set, and to stdout regardless -- an unconfigured
watchdog still works, it just talks to `dokku logs` instead of a phone.

Standalone:

    python dc_watch.py [heli_dir]        # print the verdict, notify nobody
"""
import datetime as dt
import glob
import json
import os
import time

import numpy as np

HELI = os.environ.get("SEISMO_HELI", "/data/heli")
STATE = os.environ.get("SEISMO_DC_STATE", "/data/dc_watch.json")
GAIN = int(os.environ.get("SEISMO_GAIN", "64"))
UV_PER_COUNT = 2.5 * 2 / (GAIN * (2 ** 23 - 1)) * 1e6

BASELINE_DAYS = float(os.environ.get("SEISMO_DC_BASELINE_DAYS", "7"))
ARM_HOURS = float(os.environ.get("SEISMO_DC_ARM_HOURS", "48"))
RECENT_N = 4                 # the last hour, at 4 intervals/hour
PRIOR_N = 12                 # the three hours before it
STALE_MIN = float(os.environ.get("SEISMO_DC_STALE_MIN", "45"))
EXCURSION_K = float(os.environ.get("SEISMO_DC_EXCURSION_K", "3.0"))
STEP_K = float(os.environ.get("SEISMO_DC_STEP_K", "3.0"))
RENOTIFY_H = float(os.environ.get("SEISMO_DC_RENOTIFY_H", "12"))
# Floors, so an unusually calm week cannot shrink the thresholds to nothing and
# start alarming on ordinary wander.
SPREAD_FLOOR = 500.0         # counts, ~4.7 uV
STEP_FLOOR = 2000.0          # counts, ~19 uV

_cache = {}                  # path -> (t0, dc); completed interval files never change


def _series(heli_dir=HELI, days=BASELINE_DAYS, now=None):
    """[(t0, dc)] over the trailing `days`, oldest first, for files carrying `dc`."""
    now = time.time() if now is None else now
    cutoff = now - days * 86400
    out = []
    for p in sorted(glob.glob(os.path.join(heli_dir, "heli.*.npz"))):
        hit = _cache.get(p)
        if hit is None:
            try:
                with np.load(p) as d:
                    if "dc" not in d.files:
                        continue          # pre-2026-08-21 interval; honestly has none
                    hit = (float(d["t0"]), float(d["dc"]))
            except Exception:
                continue                  # a torn file must not take the watchdog down
            if len(_cache) > 4000:
                _cache.clear()
            _cache[p] = hit
        if hit[0] >= cutoff and np.isfinite(hit[1]):
            out.append(hit)
    return sorted(out)


def check(heli_dir=HELI, now=None):
    """{state, detail, ...} for the DC baseline right now.

    state is one of OK / WARMING / STALE / EXCURSION / STEP. `detail` is one line of
    human-readable prose -- it is what lands on the phone, so it carries the numbers.
    """
    now = time.time() if now is None else now
    rows = _series(heli_dir, now=now)
    if not rows:
        return {"state": "WARMING", "detail": "no interval carries a DC value yet"}

    t = np.array([r[0] for r in rows])
    v = np.array([r[1] for r in rows])
    age_min = (now - (t[-1] + 900)) / 60.0
    if age_min > STALE_MIN:
        return {"state": "STALE", "age_min": age_min,
                "detail": f"no fresh interval for {age_min:.0f} min "
                          f"(newest {dt.datetime.utcfromtimestamp(t[-1]):%H:%M UTC}) "
                          "-- collector, mirror or builder has stopped"}

    span_h = (t[-1] - t[0]) / 3600.0
    if span_h < ARM_HOURS or len(v) < RECENT_N + PRIOR_N + 8:
        return {"state": "WARMING", "span_h": span_h,
                "detail": f"{span_h:.1f} h of DC history, arming at {ARM_HOURS:.0f} h"}

    recent = float(np.median(v[-RECENT_N:]))
    prior = float(np.median(v[-RECENT_N - PRIOR_N:-RECENT_N]))
    base = v[:-RECENT_N] if len(v) > RECENT_N * 4 else v
    centre = float(np.median(base))
    # The band this station normally occupies, and half its width. Distance is measured
    # from the BAND EDGE, not from the centre: the DC level is diurnal, so a perfectly
    # healthy afternoon already sits a full half-swing off centre and a centre-based
    # threshold spends most of its margin on the daily cycle it is supposed to ignore.
    # Outside-the-band excess is 0 all through a normal day and only grows when the
    # station goes somewhere it has not been this week.
    lo_b = float(np.percentile(base, 1))
    hi_b = float(np.percentile(base, 99))
    half = max((hi_b - lo_b) / 2.0, SPREAD_FLOOR)
    # The BIGGEST hourly move this station normally makes (p99 of |diff| between
    # consecutive hourly medians), not the typical one. Measured 2026-08-21: median
    # 194 counts but p99 1720 and max 1940, because the evening warming ramp is an
    # order of magnitude steeper than the flat small hours. Scaling on the median
    # made an ordinary fast-warming evening read as a step -- caught by the "hot day"
    # fixture, which is exactly what that fixture is for.
    hourly = v[:len(v) // RECENT_N * RECENT_N].reshape(-1, RECENT_N)
    typical = max(float(np.percentile(np.abs(np.diff(np.median(hourly, axis=1))), 99)),
                  STEP_FLOOR)

    excess = max(0.0, recent - hi_b, lo_b - recent) / half
    step = abs(recent - prior)
    common = {"dc": recent, "centre": centre, "half": half, "typical": typical,
              "excess": excess, "step": step, "span_h": span_h}
    if excess > EXCURSION_K:
        return dict(common, state="EXCURSION",
                    detail=f"DC baseline {recent:,.0f} counts ({recent * UV_PER_COUNT:.0f} µV) "
                           f"is {excess:.1f} half-swings OUTSIDE the {lo_b:,.0f}-{hi_b:,.0f} "
                           "band it has held all week -- the front end has changed")
    if step > STEP_K * typical:
        return dict(common, state="STEP",
                    detail=f"DC baseline stepped {recent - prior:+,.0f} counts "
                           f"({(recent - prior) * UV_PER_COUNT:+.1f} µV) in an hour, "
                           f"{step / typical:.1f}x the biggest hourly move it normally "
                           "makes -- something moved")
    return dict(common, state="OK",
                detail=f"DC {recent:,.0f} counts ({recent * UV_PER_COUNT:.0f} µV), "
                       f"{excess:.2f} half-swings outside its usual band")


# --- notification -------------------------------------------------------------

def _load_state():
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_state(s):
    try:
        tmp = STATE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(s, fh)
        os.replace(tmp, STATE)
    except Exception as e:
        print(f"dc_watch: cannot write {STATE}: {e}", flush=True)


def _notify(title, message, priority, tags):
    """Publish to ntfy if configured. Always echo to stdout -- an unconfigured
    watchdog must still be a working watchdog, it just talks to the logs."""
    print(f"dc_watch: {title} -- {message}", flush=True)
    url = os.environ.get("SEISMO_NTFY_URL")
    topic = os.environ.get("SEISMO_NTFY_TOPIC")
    token = os.environ.get("SEISMO_NTFY_TOKEN")
    if not (url and topic):
        return False
    try:
        import requests
        headers = {"Title": title, "Priority": priority, "Tags": tags}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        requests.post(f"{url.rstrip('/')}/{topic}", data=message.encode("utf-8"),
                      headers=headers, timeout=10)
        return True
    except Exception as e:
        print(f"dc_watch: ntfy publish failed: {e}", flush=True)
        return False


BAD = {"STALE", "EXCURSION", "STEP"}
PRIORITY = {"STALE": "high", "EXCURSION": "high", "STEP": "default"}
TAGS = {"STALE": "warning,zzz", "EXCURSION": "rotating_light", "STEP": "warning"}


def poll(heli_dir=HELI, now=None):
    """Run a check and notify on a CHANGE of state (or a stale reminder).

    Returns the verdict dict, with `notified` set. Swallows nothing -- the caller
    is a background worker that already guards every job in a try/except.
    """
    now = time.time() if now is None else now
    got = check(heli_dir, now=now)
    prev = _load_state()
    was, state = prev.get("state", "WARMING"), got["state"]
    last_note = float(prev.get("last_notified", 0.0))

    notify = False
    if state in BAD and was != state:
        notify = True                                  # entered trouble
    elif state in BAD and now - last_note >= RENOTIFY_H * 3600:
        notify = True                                  # still broken, gentle reminder
    elif state not in BAD and was in BAD:
        notify = True                                  # recovered

    if notify:
        if state in BAD:
            _notify(f"Seismo: {state.title()}", got["detail"],
                    PRIORITY[state], TAGS[state])
        else:
            _notify("Seismo: recovered", f"back to {state} -- {got['detail']}",
                    "default", "white_check_mark")
        last_note = now
    got["notified"] = notify
    _save_state({"state": state, "last_notified": last_note,
                 "since": prev.get("since", now) if was == state else now,
                 "detail": got["detail"], "checked": now})
    return got


if __name__ == "__main__":
    import sys
    got = check(sys.argv[1] if len(sys.argv) > 1 else HELI)
    print(f"{got['state']}: {got['detail']}")
    for k, val in sorted(got.items()):
        if k not in ("state", "detail"):
            print(f"  {k} = {val:,.1f}" if isinstance(val, float) else f"  {k} = {val}")

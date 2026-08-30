#!/usr/bin/env python3
"""reharvest.py — re-run the harvest over recent events and, if the result is sane,
publish it.

WHY THIS EXISTS. USGS publishes small events as `automatic` solutions within minutes and
a human reviews them days later. Between the two, epicentres move kilometres, depths
escape boundary pins (the M2.3 near Graton on 2026-08-30 came out at -0.71 km, almost
certainly the solver against a limit), magnitudes shift as `md` becomes `ml`, and events
are occasionally deleted outright. Everything downstream is computed from those numbers:
the harvest rows, the detection map's calibration, and the labels the trigger classifier
trains on. A harvest run the day after an event is therefore built on parameters that are
still moving. This re-runs it a week later, when they have settled.

WHERE IT RUNS. On the Mac, under launchd. Publishing needs GitHub write access and root
on apps02; pi5 has neither on purpose ("Nothing here can write to the repo" —
pi5/autodeploy.sh), and that read-only posture is worth more than the convenience of
running it next to the archive.

THE GATES. Charles asked for auto-publish with no human in the loop, so the judgement a
human would have applied has to live here instead. On 2026-08-29 a single cultural spike
at 348 km — one 8.8x bang lasting 1.35 s, inside a window that was 70 s long — briefly
qualified as a confirmed detection and would have quadrupled the published validated
range from 88.8 km to 348 km. It was caught by eye. Nothing publishes here unless the
headline numbers move by amounts a week of catalogue revisions can plausibly explain; if
they do not, the run reports and stops, leaving the candidate CSV for inspection.

    reharvest.py                 # the weekly run: sync, harvest, gate, publish
    reharvest.py --dry-run       # everything except commit/push/deploy
    reharvest.py --days 60       # widen the rolling window
"""
import argparse
import csv
import fcntl
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CSV_LIVE = HERE / "event_harvest.csv"
MAP_OUT = ROOT / "dashboard" / "catches" / "detection-range-map.png"
DATA = HERE / "data"
PI5 = os.environ.get("SEISMO_PI5_HOST", "pi5")
VENV = HERE / ".venv" / "bin" / "python"
NTFY_ENV = Path.home() / ".config" / "seismo" / "ntfy.env"

# A week of catalogue revisions moves things a little. These bound "a little". Anything
# outside them is a pipeline fault or a bad row, not the USGS changing its mind.
GATES = dict(
    rows_drop_frac=0.10,      # the catalogue does not lose 10% of its events in a week
    conf_drop_frac=0.25,
    conf_grow_frac=1.00,
    reach_ratio=1.50,         # the Toms Place spike was 3.9x
    deficit_dex=0.15,         # the site deficit is a property of the site
    seen_flip_frac=0.15,
)


LOCK_PATH = Path(tempfile.gettempdir()) / "seismo-reharvest.lock"


def take_lock():
    """Refuse to run twice at once. A run takes ~4 minutes and ends in a commit, a push
    and a deploy; two of them interleaving means one publishes on top of the other's
    half-written CSV. It happened during bring-up (2026-08-29) when a hand-run raced the
    scheduled one, and only luck kept the repo consistent. The handle is returned and
    deliberately never closed -- the flock lives as long as the process."""
    f = open(LOCK_PATH, "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(f"another reharvest holds {LOCK_PATH}; exiting")
    f.write(f"{os.getpid()}\n")
    f.flush()
    return f


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), cwd=kw.pop("cwd", ROOT),
                          capture_output=True, text=True, **kw)


def ntfy(title, body, priority="default", tags=""):
    """Best effort. A failed notification must never fail the run."""
    if not NTFY_ENV.exists():
        print(f"[ntfy skipped] {title}: {body}")
        return
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", NTFY_ENV.read_text(), re.M))
    url = env.get("SEISMO_NTFY_URL", "").strip().strip('"')
    topic = env.get("SEISMO_NTFY_TOPIC", "").strip().strip('"')
    token = env.get("SEISMO_NTFY_TOKEN", "").strip().strip('"')
    if not (url and topic):
        return
    try:
        import urllib.request
        # ntfy.mcguinness.ai sits behind Cloudflare, whose browser-integrity check
        # 403s the literal User-Agent "Python-urllib/x.y" with `error code: 1010`.
        # curl and python-requests pass, urllib does not -- so say who we are. This
        # cost an evening once; do not remove the header.
        req = urllib.request.Request(
            f"{url}/{topic}", data=body.encode(),
            headers={"Title": title, "Priority": priority, "Tags": tags,
                     "User-Agent": "seismo-reharvest/1.0",
                     **({"Authorization": f"Bearer {token}"} if token else {})})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as exc:
        print(f"ntfy failed (ignored): {exc}", file=sys.stderr)


def sync_dayfiles(days):
    """Pull any day-files the window needs that we do not already have. The archive on
    pi5 is the source of truth; analysis/data is a working copy."""
    today = datetime.date.today()
    want = [(today - datetime.timedelta(days=d)).strftime("%Y.%j")
            for d in range(days + 1)]
    missing = [w for w in want if not (DATA / f"XX.OAKMT.00.SHZ.D.{w}.mseed").exists()]
    if not missing:
        return 0
    DATA.mkdir(exist_ok=True)
    got = 0
    for w in missing:
        name = f"XX.OAKMT.00.SHZ.D.{w}.mseed"
        r = sh(["scp", "-q", f"{PI5}:seismo-archive/{name}", str(DATA / name)])
        if r.returncode == 0:
            got += 1
    return got


def read_csv(path):
    with open(path, newline="") as f:
        return {r["origin"]: r for r in csv.DictReader(f)}


def calibration(csv_path):
    """n_conf / reach / site deficit for a candidate CSV, using the map's own filter so
    the gates measure exactly what would be published."""
    sys.path.insert(0, str(HERE))
    import detection_map as dm
    dm.CSV = Path(csv_path)
    cal = dm.calibrate()
    return dict(n_conf=cal["n_conf"], reach=cal["reach"], deficit=cal["resid_med"])


def diff_rows(old, new):
    """What actually changed, in catalogue terms and in ours."""
    out = {"revised": [], "new": [], "deleted": [], "seen_flip": []}
    for k, n in new.items():
        o = old.get(k)
        if o is None:
            out["new"].append((k, n))
            continue
        moved = []
        for f, label in (("mag", "mag"), ("dist_km", "dist"), ("depth_km", "depth")):
            if o.get(f) != n.get(f):
                moved.append(f"{label} {o.get(f)} -> {n.get(f)}")
        if moved:
            out["revised"].append((k, n, moved))
        if o.get("seen") != n.get("seen"):
            out["seen_flip"].append((k, n, f"seen {o.get('seen')} -> {n.get('seen')}"))
    for k, o in old.items():
        if k not in new:
            out["deleted"].append((k, o))
    return out


def check_gates(old, new, cal_old, cal_new):
    """Returns a list of reasons to refuse to publish. Empty means go."""
    bad = []
    if len(new) < len(old) * (1 - GATES["rows_drop_frac"]):
        bad.append(f"row count fell {len(old)} -> {len(new)} "
                   f"(> {GATES['rows_drop_frac']:.0%})")
    if cal_new["n_conf"] < cal_old["n_conf"] * (1 - GATES["conf_drop_frac"]):
        bad.append(f"confirmed events fell {cal_old['n_conf']} -> {cal_new['n_conf']}")
    if cal_new["n_conf"] > cal_old["n_conf"] * (1 + GATES["conf_grow_frac"]):
        bad.append(f"confirmed events jumped {cal_old['n_conf']} -> {cal_new['n_conf']}")
    r_old, r_new = cal_old["reach"], cal_new["reach"]
    if r_old > 0 and not (1 / GATES["reach_ratio"] <= r_new / r_old <= GATES["reach_ratio"]):
        bad.append(f"validated range moved {r_old:.1f} -> {r_new:.1f} km "
                   f"({r_new / r_old:.2f}x; the 2026-08-29 spike was 3.9x)")
    if abs(cal_new["deficit"] - cal_old["deficit"]) > GATES["deficit_dex"]:
        bad.append(f"site deficit moved {cal_old['deficit']:+.3f} -> "
                   f"{cal_new['deficit']:+.3f} dex")
    seen_old = sum(1 for r in old.values() if r.get("seen") == "1")
    flips = sum(1 for k, n in new.items()
                if k in old and old[k].get("seen") != n.get("seen"))
    if seen_old and flips > seen_old * GATES["seen_flip_frac"]:
        bad.append(f"{flips} seen-flips against {seen_old} seen rows")
    return bad


def summarise(d, cal_old, cal_new):
    L = []
    for k, n, moved in d["revised"][:8]:
        L.append(f"  {n['origin'][:19]} M{n['mag']} {n['place'][:26]}: " + "; ".join(moved))
    for k, n in d["new"][:5]:
        L.append(f"  NEW  {n['origin'][:19]} M{n['mag']} {n['place'][:26]} "
                 f"{n['dist_km']} km seen={n['seen']}")
    for k, o in d["deleted"][:5]:
        L.append(f"  GONE {o['origin'][:19]} M{o['mag']} {o['place'][:26]} "
                 f"(withdrawn from the catalogue)")
    for k, n, msg in d["seen_flip"][:8]:
        L.append(f"  {n['origin'][:19]} M{n['mag']} {n['place'][:26]}: {msg}")
    L.append(f"  calibration: {cal_old['n_conf']} -> {cal_new['n_conf']} confirmed, "
             f"reach {cal_old['reach']:.1f} -> {cal_new['reach']:.1f} km, "
             f"deficit {cal_old['deficit']:+.3f} -> {cal_new['deficit']:+.3f} dex")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30,
                    help="rolling window; every event is re-examined until it ages out")
    ap.add_argument("--radius", type=float, default=400.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    _lock = take_lock()          # held for the life of the process

    if not CSV_LIVE.exists():
        sys.exit("no committed event_harvest.csv to compare against")

    # Preflight. A scheduled run gets launchd's minimal PATH, and both direnv and git
    # are under /opt/homebrew here -- without them the run dies in the publish stage
    # after four minutes of harvesting, which is the worst place to find out.
    missing = [b for b in ("direnv", "git", "scp") if not shutil.which(b)]
    if missing:
        ntfy("reharvest MISCONFIGURED", f"not on PATH: {', '.join(missing)}\n"
             f"PATH={os.environ.get('PATH','')}", priority="high", tags="rotating_light")
        sys.exit(f"not on PATH: {missing} (PATH={os.environ.get('PATH','')})")

    r = sh(["git", "status", "--porcelain"])
    if r.stdout.strip() and not args.dry_run:
        ntfy("reharvest skipped", "working tree is dirty; refusing to publish over "
             "uncommitted work", priority="low", tags="warning")
        sys.exit("working tree dirty -- refusing to publish")

    got = sync_dayfiles(args.days)
    print(f"day-files pulled: {got}")

    start = (datetime.date.today() - datetime.timedelta(days=args.days)).isoformat()
    end = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    tmp = Path(tempfile.mkdtemp(prefix="reharvest.")) / "candidate.csv"
    # The window is rolling, but the CSV is whole-history: harvest the full span so the
    # candidate is directly comparable to what is committed.
    r = sh([str(VENV), str(HERE / "harvest_events.py"), "--start", "2026-07-19",
            "--end", end, "--radius", str(args.radius), "--out", str(tmp)])
    if r.returncode != 0:
        ntfy("reharvest FAILED", f"harvest_events.py exited {r.returncode}\n"
             f"{r.stderr[-600:]}", priority="high", tags="rotating_light")
        sys.exit(r.stderr[-2000:])

    old, new = read_csv(CSV_LIVE), read_csv(tmp)
    cal_old, cal_new = calibration(CSV_LIVE), calibration(tmp)
    d = diff_rows(old, new)
    changed = any(d[k] for k in ("revised", "new", "deleted", "seen_flip"))
    body = summarise(d, cal_old, cal_new)
    print(body)

    if not changed and cal_old == cal_new:
        print("nothing moved; no publish")
        return

    bad = check_gates(old, new, cal_old, cal_new)
    if bad:
        keep = ROOT / "analysis" / "reharvest-rejected.csv"
        shutil.copy(tmp, keep)
        ntfy("reharvest BLOCKED — needs a look",
             "Refused to publish:\n  " + "\n  ".join(bad) + "\n\n" + body +
             f"\n\ncandidate kept at {keep.relative_to(ROOT)}",
             priority="high", tags="warning")
        sys.exit("gates failed:\n  " + "\n  ".join(bad))

    if args.dry_run:
        print("\n[dry run] would publish")
        return

    shutil.copy(tmp, CSV_LIVE)
    r = sh([str(VENV), str(HERE / "detection_map.py"), "--out", str(MAP_OUT)])
    if r.returncode != 0:
        sh(["git", "checkout", "--", str(CSV_LIVE)])
        ntfy("reharvest FAILED", f"detection_map.py exited {r.returncode}",
             priority="high", tags="rotating_light")
        sys.exit(r.stderr[-2000:])
    sh([str(ROOT / ".venv" / "bin" / "python"), "-c",
        f"from PIL import Image; import os; p='{MAP_OUT}';"
        "im=Image.open(p).convert('RGB');w=1400;"
        "im=im.resize((w,int(im.height*w/im.width)), Image.LANCZOS);"
        "im.convert('P', palette=Image.ADAPTIVE, colors=128).save(p, optimize=True)"])

    msg = (f"harvest: weekly re-harvest picked up catalogue revisions\n\n"
           f"{body}\n\nAutomated by analysis/reharvest.py.")
    for cmd in (["git", "add", str(CSV_LIVE), str(MAP_OUT)],
                ["git", "commit", "-q", "-m", msg],
                ["git", "push"]):
        r = sh(["direnv", "exec", ".", *cmd])
        if r.returncode != 0:
            ntfy("reharvest: publish failed", f"{' '.join(cmd)}\n{r.stderr[-500:]}",
                 priority="high", tags="rotating_light")
            sys.exit(r.stderr[-2000:])
    r = sh("direnv exec . ./deploy.sh public")
    ok = r.returncode == 0
    ntfy("reharvest published" if ok else "reharvest: deploy failed",
         body + ("\n\npushed; pi5 autodeploys, apps02 deployed"
                 if ok else f"\n\ncommitted and pushed, but deploy.sh public failed:\n"
                            f"{r.stderr[-400:]}"),
         priority="default" if ok else "high",
         tags="white_check_mark" if ok else "rotating_light")
    print("published" if ok else "published to git; apps02 deploy failed")


if __name__ == "__main__":
    main()

# pi5 — autodeploy

pi5 pulls this repo on a 2-minute timer and redeploys only what changed. A GitHub
**webhook cannot work**: pi5 resolves only on the LAN, so GitHub can never reach it
inbound. Polling is the only option that needs no exposure, and at 2 minutes it is
indistinguishable from a hook for this project.

## What runs where

| repo path | pi5 path | service |
|---|---|---|
| `server/seismo_server.py`, `store.py` | `~/seismo-server/` | `seismo-server` |
| `server/udp_collector.py`, `detector.py`, `stalta.py`, `trigger_features.py` + `analysis/models/trigger_gbm.joblib` | `~/seismo-collector/` | `seismo-collector`, `seismo-detector` |
| `dashboard/**` | `~/seismo-dashboard/` | Dokku app `seismo`, via `seismo-dash:latest` |

## Install (once)

```bash
# 1. read-only deploy key, already generated at ~/.ssh/id_seismo_deploy on pi5.
#    Add the .pub to GitHub: repo -> Settings -> Deploy keys (do NOT allow write).
# 2. clone through the `github-seismo` ssh alias
git clone github-seismo:cmcguinness/Seismo.git ~/seismo-src
# 3. install the units
sudo cp ~/seismo-src/pi5/seismo-autodeploy.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now seismo-autodeploy.timer
```

## Operating it

```bash
systemctl list-timers seismo-autodeploy.timer     # when it next runs
journalctl -u seismo-autodeploy -n 50             # what it did
sudo systemctl start seismo-autodeploy.service    # force a check now
cat ~/seismo-dashboard/DEPLOYED_SHA               # what is live
```

`deploy.sh` at the repo root still works from the Mac for an immediate push, and is the
escape hatch if autodeploy is wedged.

## Notes

- **Only `main` is deployed.** Work on a branch and nothing goes live.
- **Build-then-swap:** a failed `docker build` leaves the running image untouched and logs
  to `/tmp/seismo-build.log`.
- **No `--delete` on any sync.** `~/seismo-collector` holds the shared `.venv` and
  `~/seismo-dashboard` a gitignored `.sesskey`.
- **Host state that is NOT in the repo** (2026-08-26): the Dokku app has a second mount
  `/home/charles/seismo-archive:/archive` and `SEISMO_EVENTS=/archive/events.log` (the
  dashboard reads the pi5 detector's log); `/etc/seismo/ntfy.env` (root:charles 640)
  holds the ntfy URL/topic/token for the detector's push; scikit-learn + joblib are
  installed in `~/seismo-collector/.venv`. Rebuilding pi5 means redoing those three.
- The image records its commit as `SEISMO_BUILD_SHA` (`docker image inspect`), because
  Dokku's `GIT_REV` is not populated by `from-image` deploys.

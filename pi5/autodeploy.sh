#!/usr/bin/env bash
# autodeploy.sh — runs ON pi5, on a timer. Pulls this repo and redeploys only what changed.
#
# WHY POLLING (2026-08-12): a GitHub webhook would have to reach pi5 inbound, and
# pi5.mcguinness.ai resolves only on the LAN. Pull-based is the only option that works
# without exposing anything, and a 2-minute poll is indistinguishable from a hook here.
#
# WHY PATH-SCOPED: most commits touch analysis/ or STATUS.md and have nothing to deploy.
# Rebuilding the Docker image on those would burn minutes of Pi CPU for no change. A tick
# with nothing relevant costs one `git fetch` and a string compare.
#
# Credentials: a READ-ONLY GitHub deploy key (~/.ssh/id_seismo_deploy, via the
# `github-seismo` ssh alias). Nothing here can write to the repo.
set -euo pipefail

SRC="${SEISMO_SRC:-$HOME/seismo-src}"
BRANCH="${SEISMO_BRANCH:-main}"
IMAGE="seismo-dash:latest"
APP="seismo"

log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }

cd "$SRC"

git fetch --quiet origin "$BRANCH"
OLD="$(git rev-parse HEAD)"
NEW="$(git rev-parse "origin/$BRANCH")"

if [[ "$OLD" == "$NEW" ]]; then
  exit 0                       # nothing new; the common case, stay silent
fi

log "new commits ${OLD:0:7} -> ${NEW:0:7}"
CHANGED="$(git diff --name-only "$OLD" "$NEW")"
git reset --hard --quiet "$NEW"
SHA="$(git rev-parse --short HEAD)"

want() { grep -q "^$1" <<<"$CHANGED"; }

deployed_any=0

if want "server/"; then
  log "server/ changed -> syncing and restarting services"
  # cp, not rsync --delete: ~/seismo-collector holds the shared .venv.
  install -m644 server/seismo_server.py server/store.py "$HOME/seismo-server/"
  install -m644 server/udp_collector.py server/detector.py server/stalta.py \
          "$HOME/seismo-collector/"
  sudo systemctl restart seismo-server seismo-collector seismo-detector
  sleep 3
  if ! systemctl is-active --quiet seismo-server; then
    log "ERROR: seismo-server did not come back; check journalctl -u seismo-server"
  fi
  printf '%s\n%s\n' "$SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$HOME/seismo-server/DEPLOYED_SHA"
  cp "$HOME/seismo-server/DEPLOYED_SHA" "$HOME/seismo-collector/DEPLOYED_SHA"
  deployed_any=1
fi

if want "dashboard/"; then
  log "dashboard/ changed -> building image"
  rsync -rl --exclude '__pycache__' --exclude '.sesskey' --exclude '*.pyc' \
        dashboard/ "$HOME/seismo-dashboard/"
  # Build FIRST, deploy only on success: a failed build must leave the running image
  # alone rather than take the dashboard down.
  if sudo docker build --build-arg GIT_SHA="$SHA" -t "$IMAGE" "$HOME/seismo-dashboard" \
       >/tmp/seismo-build.log 2>&1; then
    dokku git:from-image "$APP" "$IMAGE" >/dev/null
    printf '%s\n%s\n' "$SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      > "$HOME/seismo-dashboard/DEPLOYED_SHA"
    log "dashboard deployed at $SHA"
    deployed_any=1
  else
    log "ERROR: docker build FAILED, keeping the running image. See /tmp/seismo-build.log"
    tail -20 /tmp/seismo-build.log
    exit 1
  fi
fi

if [[ "$deployed_any" == "0" ]]; then
  log "nothing deployable changed (now at $SHA)"
fi

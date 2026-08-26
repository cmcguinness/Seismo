#!/usr/bin/env bash
# deploy.sh — push this repo's pi5 code to pi5, and make the deployed version visible.
#
# WHY THIS EXISTS (2026-08-12): pi5 has no git repositories, no crontab and no CI. Every
# service there was updated by hand-copying files, and nothing recorded which commit was
# live. dashboard/signatures.json drifted for two weeks without anyone noticing, and the
# only way to find out was to ssh in and read the files.
#
#   ./deploy.sh status      what is live vs local HEAD (read-only, safe)
#   ./deploy.sh dashboard   sync + docker build + dokku git:from-image  (restarts the app)
#   ./deploy.sh services    sync + systemctl restart of the three python services
#   ./deploy.sh all         both
#   ./deploy.sh public      the PUBLIC copy of the dashboard on apps02 (same image, fed
#                           by rsync from pi5, SEISMO_HELI_BUILD=0 -- see STATUS.md
#                           2026-08-25 "PUBLIC DASHBOARD")
#
# Every ssh here is `ssh -n`. Without it ssh inherits the script's stdin and reads it
# to EOF -- when bash is reading the script from that same stream, the remainder of
# the file is swallowed and bash dies on whatever half-line it is left holding
# ("deploy.sh: line 139: unexpected EOF while looking for matching", seen on a
# `public` deploy 2026-08-26, AFTER the app had already shipped). None of these
# remote commands want stdin.
#
# Deliberately no --delete on any rsync: ~/seismo-collector holds the shared .venv and
# ~/seismo-dashboard holds a gitignored .sesskey. Deleting remote extras would break both.
set -euo pipefail

HOST="${SEISMO_PI5_HOST:-pi5}"          # ssh alias; the FQDN is only needed by dokku git
PUBLIC_HOST="${SEISMO_PUBLIC_HOST:-root@apps02.mcguinness.ai}"   # public Dokku host
APP="seismo"
IMAGE="seismo-dash:latest"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

RSYNC_EXCLUDES=(--exclude '__pycache__' --exclude '.sesskey' --exclude '.venv'
                --exclude '*.pyc' --exclude '.DS_Store')

SHA="$(git rev-parse --short HEAD)"
DIRTY=""
git diff --quiet && git diff --cached --quiet || DIRTY=" (DIRTY)"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

require_clean() {
  if [[ -n "$DIRTY" && "${FORCE:-0}" != "1" ]]; then
    echo "working tree is dirty; commit first or run with FORCE=1" >&2
    echo "deploying uncommitted code is how you get a live version that matches no commit." >&2
    exit 1
  fi
}

stamp() {   # stamp <remote-dir> — record what was deployed, so drift is visible later
  ssh -n "$HOST" "printf '%s\n' '$SHA$DIRTY' '$(date -u +%Y-%m-%dT%H:%M:%SZ)' > $1/DEPLOYED_SHA"
}

do_status() {
  say "local HEAD: $SHA$DIRTY"
  for d in seismo-dashboard seismo-server seismo-collector; do
    printf '  %-20s ' "$d"
    ssh -n "$HOST" "cat ~/$d/DEPLOYED_SHA 2>/dev/null | tr '\n' ' '" || true
    echo
  done
  # -c: compare by CHECKSUM, not size+mtime. mtimes drift constantly (a file copy
  # resets them) and would list every file as changed, burying the real ones.
  say "drift (repo -> pi5; content differences only)"
  rsync -rinc "${RSYNC_EXCLUDES[@]}" dashboard/ "$HOST":seismo-dashboard/ | sed 's/^/  dashboard  /'
  rsync -inc analysis/epochs.py "$HOST":seismo-dashboard/ | sed 's/^/  dashboard  /'
  rsync -rinc "${RSYNC_EXCLUDES[@]}" server/seismo_server.py server/store.py \
        "$HOST":seismo-server/ | sed 's/^/  server     /'
  rsync -rinc "${RSYNC_EXCLUDES[@]}" server/udp_collector.py server/detector.py \
        server/stalta.py server/trigger_features.py "$HOST":seismo-collector/ | sed 's/^/  collector  /'
  rsync -inc analysis/models/trigger_gbm.joblib "$HOST":seismo-collector/ | sed 's/^/  collector  /'
  echo
  say "dokku image currently deployed"
  ssh -n "$HOST" "dokku apps:report $APP 2>/dev/null | grep -i 'deploy source metadata'"
}

do_dashboard() {
  require_clean
  say "sync dashboard/ -> $HOST:~/seismo-dashboard/"
  rsync -rlv "${RSYNC_EXCLUDES[@]}" dashboard/ "$HOST":seismo-dashboard/
  # epochs.py lives in analysis/ and is the ONE register of configuration changes.
  # activity.py draws from it, so it has to be in the build context -- copied rather
  # than duplicated in git, because a forked epoch table is worse than none.
  rsync -lv analysis/epochs.py "$HOST":seismo-dashboard/
  # Tag by SHA as well as :latest. With ONLY :latest, `dokku git:from-image` sees an
  # unchanged reference, prints "No changes detected, skipping git commit", exits
  # non-zero and deploys NOTHING -- the app keeps running the old image while the
  # build reports success (hit 2026-08-12). A per-commit tag always looks new.
  say "build $IMAGE + seismo-dash:$SHA on $HOST"
  # sudo: charles is not in the docker group on pi5.
  ssh -n "$HOST" "cd ~/seismo-dashboard && sudo docker build --build-arg GIT_SHA='$SHA' -t 'seismo-dash:$SHA' -t $IMAGE ."
  say "dokku git:from-image $APP seismo-dash:$SHA   (this restarts the app)"
  ssh -n "$HOST" "dokku git:from-image $APP 'seismo-dash:$SHA'"
  stamp '~/seismo-dashboard'
}

do_public() {
  # Same Dockerfile, same SHA tag, different host. apps02 is aarch64 like pi5, root
  # runs docker directly (no sudo), and the build context lives in /root.
  require_clean
  say "sync dashboard/ -> $PUBLIC_HOST:~/seismo-dashboard/"
  rsync -rlv "${RSYNC_EXCLUDES[@]}" dashboard/ "$PUBLIC_HOST":seismo-dashboard/
  rsync -lv analysis/epochs.py "$PUBLIC_HOST":seismo-dashboard/
  say "build seismo-dash:$SHA on $PUBLIC_HOST"
  ssh -n "$PUBLIC_HOST" "cd ~/seismo-dashboard && docker build --build-arg GIT_SHA='$SHA' -t 'seismo-dash:$SHA' -t $IMAGE ."
  say "dokku git:from-image $APP seismo-dash:$SHA on $PUBLIC_HOST   (restarts the app)"
  ssh -n "$PUBLIC_HOST" "dokku git:from-image $APP 'seismo-dash:$SHA'"
  ssh -n "$PUBLIC_HOST" "printf '%s\n' '$SHA$DIRTY' '$(date -u +%Y-%m-%dT%H:%M:%SZ)' > ~/seismo-dashboard/DEPLOYED_SHA"
  say "public dashboard: $(ssh -n "$PUBLIC_HOST" "dokku url $APP 2>/dev/null" || true)"
}

do_services() {
  require_clean
  say "sync server/ -> $HOST"
  rsync -rlv "${RSYNC_EXCLUDES[@]}" server/seismo_server.py server/store.py \
        "$HOST":seismo-server/
  rsync -rlv "${RSYNC_EXCLUDES[@]}" server/udp_collector.py server/detector.py \
        server/stalta.py server/trigger_features.py "$HOST":seismo-collector/
  # The trigger classifier is TRAINED on the Mac (analysis/trigger_train.py) and only
  # pushed here -- Charles, 2026-08-26. No training on pi5.
  rsync -lv analysis/models/trigger_gbm.joblib "$HOST":seismo-collector/
  say "restart services"
  ssh -n "$HOST" "sudo systemctl restart seismo-server seismo-collector seismo-detector"
  sleep 3
  ssh -n "$HOST" "systemctl is-active seismo-server seismo-collector seismo-detector"
  stamp '~/seismo-server'
  stamp '~/seismo-collector'
}

case "${1:-status}" in
  status)    do_status ;;
  dashboard) do_dashboard; do_status ;;
  services)  do_services;  do_status ;;
  all)       do_services;  do_dashboard; do_status ;;
  public)    do_public ;;
  *) echo "usage: $0 {status|dashboard|services|all|public}" >&2; exit 2 ;;
esac

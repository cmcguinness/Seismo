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
#
# Deliberately no --delete on any rsync: ~/seismo-collector holds the shared .venv and
# ~/seismo-dashboard holds a gitignored .sesskey. Deleting remote extras would break both.
set -euo pipefail

HOST="${SEISMO_PI5_HOST:-pi5}"          # ssh alias; the FQDN is only needed by dokku git
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
  ssh "$HOST" "printf '%s\n' '$SHA$DIRTY' '$(date -u +%Y-%m-%dT%H:%M:%SZ)' > $1/DEPLOYED_SHA"
}

do_status() {
  say "local HEAD: $SHA$DIRTY"
  for d in seismo-dashboard seismo-server seismo-collector; do
    printf '  %-20s ' "$d"
    ssh "$HOST" "cat ~/$d/DEPLOYED_SHA 2>/dev/null | tr '\n' ' '" || true
    echo
  done
  # -c: compare by CHECKSUM, not size+mtime. mtimes drift constantly (a file copy
  # resets them) and would list every file as changed, burying the real ones.
  say "drift (repo -> pi5; content differences only)"
  rsync -rinc "${RSYNC_EXCLUDES[@]}" dashboard/ "$HOST":seismo-dashboard/ | sed 's/^/  dashboard  /'
  rsync -rinc "${RSYNC_EXCLUDES[@]}" server/seismo_server.py server/store.py \
        "$HOST":seismo-server/ | sed 's/^/  server     /'
  rsync -rinc "${RSYNC_EXCLUDES[@]}" server/udp_collector.py server/detector.py \
        server/stalta.py "$HOST":seismo-collector/ | sed 's/^/  collector  /'
  echo
  say "dokku image currently deployed"
  ssh "$HOST" "dokku apps:report $APP 2>/dev/null | grep -i 'deploy source metadata'"
}

do_dashboard() {
  require_clean
  say "sync dashboard/ -> $HOST:~/seismo-dashboard/"
  rsync -rlv "${RSYNC_EXCLUDES[@]}" dashboard/ "$HOST":seismo-dashboard/
  say "build $IMAGE on $HOST (GIT_SHA=$SHA)"
  # sudo: charles is not in the docker group on pi5.
  ssh "$HOST" "cd ~/seismo-dashboard && sudo docker build --build-arg GIT_SHA='$SHA' -t $IMAGE ."
  say "dokku git:from-image $APP $IMAGE   (this restarts the app)"
  ssh "$HOST" "dokku git:from-image $APP $IMAGE"
  stamp '~/seismo-dashboard'
}

do_services() {
  require_clean
  say "sync server/ -> $HOST"
  rsync -rlv "${RSYNC_EXCLUDES[@]}" server/seismo_server.py server/store.py \
        "$HOST":seismo-server/
  rsync -rlv "${RSYNC_EXCLUDES[@]}" server/udp_collector.py server/detector.py \
        server/stalta.py "$HOST":seismo-collector/
  say "restart services"
  ssh "$HOST" "sudo systemctl restart seismo-server seismo-collector seismo-detector"
  sleep 3
  ssh "$HOST" "systemctl is-active seismo-server seismo-collector seismo-detector"
  stamp '~/seismo-server'
  stamp '~/seismo-collector'
}

case "${1:-status}" in
  status)    do_status ;;
  dashboard) do_dashboard; do_status ;;
  services)  do_services;  do_status ;;
  all)       do_services;  do_dashboard; do_status ;;
  *) echo "usage: $0 {status|dashboard|services|all}" >&2; exit 2 ;;
esac

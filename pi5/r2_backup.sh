#!/usr/bin/env bash
# r2_backup.sh — off-site copy of the miniSEED archive to Cloudflare R2.
#
# WHY THIS EXISTS. Every copy of the archive is in one house: the station writes
# day-files, pi5 collects them, the Mac pulls a few for analysis, and pi4 sits on the
# same shelf as pi5. Sonoma County has demonstrated whole-house loss more than once in
# the last decade and Oakmont has been under evacuation orders; in an evacuation you
# take people and pets, not a Raspberry Pi off a garage shelf. The day-files are the
# only thing here that cannot be regenerated -- the database, the harvest CSV and every
# derived figure can be rebuilt from them, and they cannot be rebuilt from anything.
# So this is the one backup that matters, and it is deliberately NOT a local one.
#
# COPY, NEVER SYNC. `rclone sync` deletes remote objects with no local counterpart --
# i.e. one bad SEISMO_ARCHIVE value would instruct the backup to erase the backup.
# `copy` has no delete path at all. Belt and braces: put a bucket lock on the archive/
# prefix in the Cloudflare dashboard, which makes objects immutable for a retention
# period and takes precedence over lifecycle rules, so neither this script nor a
# compromised token can remove history.
#
# SETUP (once, on pi5):
#   sudo apt install rclone
#   mkdir -p ~/.config/seismo && chmod 700 ~/.config/seismo
#   cp .env ~/.config/seismo/r2.env && chmod 600 ~/.config/seismo/r2.env
#   # then in the Cloudflare dashboard: bucket lock on archive/, retention as you like.
#
# The first run backfills the whole archive -- ~26 MB/day since 2026-07-20, so roughly
# 10 GB. BWLIMIT exists because pi5 also feeds apps02 (rsync every minute, live ring
# every 3 s) and saturating a residential uplink for an hour would visibly stall the
# public dashboard. Default 2 MB/s puts the backfill at ~80 minutes and leaves headroom.
set -euo pipefail

ENV_FILE="${SEISMO_R2_ENV:-$HOME/.config/seismo/r2.env}"
ARCHIVE="${SEISMO_ARCHIVE:-$HOME/seismo-archive}"
PREFIX="${SEISMO_R2_PREFIX:-archive}"
BWLIMIT="${SEISMO_R2_BWLIMIT:-2M}"
LOCK="/tmp/seismo-r2-backup.lock"
# Two conventions in this project and they disagree: pi5's services read
# /etc/seismo/ntfy.env (root:charles 640, see seismo-detector.service), while
# reharvest.py on the Mac reads ~/.config/seismo/ntfy.env. Search both, pi5 first --
# guessing one would have left this script silently unable to alert on the very host it
# runs on, which is the exact failure mode the alerting exists to prevent.
NTFY_ENV="${SEISMO_NTFY_ENV:-}"
if [ -z "$NTFY_ENV" ]; then
  for c in /etc/seismo/ntfy.env "$HOME/.config/seismo/ntfy.env"; do
    [ -r "$c" ] && { NTFY_ENV="$c"; break; }
  done
fi
# Backup chatter arguably does not belong on the earthquake channel, but the ntfy token
# is topic-scoped: seismo-ops returns 403, seismo-alerts 200 (checked at deploy, 09-07).
# So default to whatever the env file says and leave the override for later -- moving it
# needs a token grant on the ntfy side first, and a notifier that 403s silently is worse
# than one on a slightly wrong channel.
R2_TOPIC="${SEISMO_R2_NTFY_TOPIC:-}"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# ntfy.mcguinness.ai sits behind Cloudflare, whose browser-integrity check rejects
# requests without a named User-Agent -- same reason reharvest.py sets one.
notify() {   # notify <title> <body> [priority] [tags]
  [ -n "$NTFY_ENV" ] && [ -r "$NTFY_ENV" ] || { log "[ntfy skipped] $1: $2"; return 0; }
  # shellcheck disable=SC1090
  set +u; . "$NTFY_ENV"; set -u
  local url="${SEISMO_NTFY_URL:-}" topic="${R2_TOPIC:-${SEISMO_NTFY_TOPIC:-}}" tok="${SEISMO_NTFY_TOKEN:-}"
  [ -n "$url" ] && [ -n "$topic" ] || { log "[ntfy unconfigured] $1: $2"; return 0; }
  curl -fsS -m 20 -X POST "$url/$topic" \
    -H "User-Agent: seismo-r2-backup/1.0" \
    -H "Title: $1" -H "Priority: ${3:-default}" -H "Tags: ${4:-}" \
    ${tok:+-H "Authorization: Bearer $tok"} \
    -d "$2" >/dev/null || log "ntfy post failed (non-fatal)"
}

fail() { log "FAILED: $*"; notify "R2 backup FAILED" "$*" high rotating_light; exit 1; }

exec 9>"$LOCK"
flock -n 9 || { log "another run holds $LOCK; exiting"; exit 0; }

[ -f "$ENV_FILE" ] || fail "no credentials at $ENV_FILE"
[ -d "$ARCHIVE" ]  || fail "archive not found at $ARCHIVE"
command -v rclone >/dev/null || fail "rclone not installed (apt install rclone)"

# shellcheck disable=SC1090
set +u; . "$ENV_FILE"; set -u
: "${R2_BUCKET_NAME:?missing in $ENV_FILE}"
: "${R2_S3_API:?missing in $ENV_FILE}"
: "${R2_ACCESS_KEY_ID:?missing in $ENV_FILE}"
: "${R2_SECRET_ACCESS_KEY:?missing in $ENV_FILE}"

# Configure rclone entirely through the environment: no rclone.conf on disk, so the
# secret exists only in this process. RCLONE_CONFIG_<REMOTE>_<KEY> is the documented form.
# Cloudflare's bucket settings page labels "https://<acct>.r2.cloudflarestorage.com/<bucket>"
# as the S3 API URL, so that is what you naturally paste in -- but it is endpoint PLUS
# bucket path, and rclone appends the bucket again, giving .../seismo/seismo/archive/.
# With NO_CHECK_BUCKET set that failure is SILENT: the write succeeds into the doubled
# path and only the read-back fails. Strip everything after the host and accept either
# form. (Found by probing a real write on 2026-09-07; it would otherwise have shipped
# ten gigabytes to the wrong prefix and reported success.)
endpoint=$(printf '%s' "$R2_S3_API" | sed -E 's#(https://[^/]+).*#\1#')
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ENDPOINT="$endpoint"
export RCLONE_CONFIG_R2_REGION=auto
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true

dest="R2:${R2_BUCKET_NAME}/${PREFIX}"
log "copy $ARCHIVE -> $dest (bwlimit $BWLIMIT)"

# --min-age 25h: the current UTC day's file is still being written, and a file that
#   closed at 00:00Z is only hours old. 25h guarantees we only ship closed days.
# --immutable: error out if a file already uploaded has changed locally. Day-files are
#   append-then-frozen, so a change means something is wrong and we want to hear about
#   it rather than quietly overwrite the good copy.
# --ignore-checksum is NOT set: R2 returns MD5 etags for single-part uploads, so let
#   rclone verify. The archive is small enough that correctness beats speed.
set +e
out=$(rclone copy "$ARCHIVE" "$dest" \
        --include "*.mseed" \
        --min-age 25h \
        --immutable \
        --transfers 2 --checkers 4 \
        --bwlimit "$BWLIMIT" \
        --retries 3 --low-level-retries 10 \
        --stats-one-line --stats 5m \
        --log-level NOTICE 2>&1)
rc=$?
set -e
[ -n "$out" ] && log "$out"
[ $rc -eq 0 ] || fail "rclone exited $rc: $(printf '%s' "$out" | tail -c 500)"

remote_n=$(rclone size "$dest" --json 2>/dev/null | sed -n 's/.*"count":\([0-9]*\).*/\1/p' || echo "?")
local_n=$(find "$ARCHIVE" -name '*.mseed' -mmin +1500 | wc -l | tr -d ' ')
log "ok: $remote_n objects at $dest, $local_n closed day-files local"

# Silence means healthy, so the two ways this can fail quietly both have to speak up.
# A new day-file appears every day; if the remote count stops tracking the local count
# the recorder has stopped, the path is wrong, or uploads are silently no-oping.
if [ "$remote_n" != "?" ] && [ "$remote_n" -lt "$local_n" ]; then
  notify "R2 backup incomplete" \
    "remote has $remote_n objects, $local_n closed day-files locally" default warning
elif [ "$(date -u +%u)" = "7" ]; then
  notify "R2 backup healthy" "$remote_n day-files off-site" low white_check_mark
fi

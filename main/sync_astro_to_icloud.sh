#!/bin/bash
set -euo pipefail

SOURCE_DIR="/Users/koni/astro_projects"
ICLOUD_ROOT="${HOME}/Library/Mobile Documents/com~apple~CloudDocs"
TARGET_DIR="${ICLOUD_ROOT}/astro_projects"

DRY_RUN=0
DELETE=0

usage() {
  cat <<'EOF'
Sync local astro project folder to iCloud Drive.

Usage:
  scripts/main/sync_astro_to_icloud.sh [--dry-run] [--delete]

Options:
  --dry-run   Show what would be copied without changing files.
  --delete    Also delete files in iCloud that no longer exist locally.
  -h, --help  Show this help.

Default:
  Copies/updates files from /Users/koni/astro_projects to
  ~/Library/Mobile Documents/com~apple~CloudDocs/astro_projects.
  It does not delete iCloud files unless --delete is used.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --delete)
      DELETE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "Source folder not found: ${SOURCE_DIR}" >&2
  exit 1
fi

if [[ ! -d "${ICLOUD_ROOT}" ]]; then
  echo "iCloud Drive folder not found: ${ICLOUD_ROOT}" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

RSYNC_ARGS=(
  -a
  --human-readable
  --stats
  --exclude ".DS_Store"
  --exclude "._*"
  --exclude "__pycache__/"
  --exclude "*.pyc"
  --exclude "lightcurves/"
  --exclude "cheops_followup/.deps/"
)

if [[ "${DRY_RUN}" -eq 1 ]]; then
  RSYNC_ARGS+=(--dry-run)
fi

if [[ "${DELETE}" -eq 1 ]]; then
  RSYNC_ARGS+=(--delete)
fi

echo "Source: ${SOURCE_DIR}/"
echo "Target: ${TARGET_DIR}/"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Mode: dry run"
else
  echo "Mode: sync"
fi
if [[ "${DELETE}" -eq 1 ]]; then
  echo "Delete: enabled"
else
  echo "Delete: disabled"
fi
echo

rsync "${RSYNC_ARGS[@]}" "${SOURCE_DIR}/" "${TARGET_DIR}/"

echo
echo "Done."

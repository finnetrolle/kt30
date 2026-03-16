#!/bin/sh
set -eu

ensure_owned_dir() {
  dir="$1"
  mkdir -p "$dir"

  if [ "$(id -u)" = "0" ]; then
    chown -R app:app "$dir"
  fi
}

ensure_owned_dir "${UPLOAD_FOLDER:-uploads}"
ensure_owned_dir "${ARTIFACTS_ROOT:-analysis_runs}"
ensure_owned_dir "${RESULTS_STORAGE_DIR:-results_data}"
ensure_owned_dir "${PROGRESS_STORAGE_DIR:-progress_data}"
ensure_owned_dir "${RUNTIME_DIR:-runtime}"
ensure_owned_dir "$(dirname "${JOB_QUEUE_DB_PATH:-runtime/job_queue.sqlite3}")"
ensure_owned_dir "$(dirname "${RATE_LIMIT_DB_PATH:-runtime/rate_limits.sqlite3}")"

if [ "$(id -u)" = "0" ]; then
  exec gosu app "$@"
fi

exec "$@"

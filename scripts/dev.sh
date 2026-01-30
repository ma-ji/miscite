#!/usr/bin/env bash
set -euo pipefail

python -m server.main "$@" &
web_pid=$!

python -m server.worker "$@" &
worker_pid=$!

trap 'kill $web_pid $worker_pid' INT TERM EXIT

wait -n "$web_pid" "$worker_pid"

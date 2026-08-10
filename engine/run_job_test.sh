#!/bin/bash
# run_job_test.sh — Run the Among-I server handler to process a queued job.
#
# Prerequisites:
#   1. A .env file with OPEN_ROUTER_API_KEY (or OPENAI_API_KEY)
#   2. A queued job in Firestore (use create_test_job.py to make one)
#   3. firebase-key.json in this directory
#
# Usage:
#   cd engine
#   bash run_job_test.sh
#
# This polls Firestore for queued jobs and runs the first one found.
# The server registers as "test-server" and processes only jobs whose
# study_id matches --study.

set -euo pipefail
cd "$(dirname "$0")"

PENV=/home/callisto/penv/bin/python3

echo "=== Starting server handler ==="
echo "Study filter: test-study"
echo "Log dir: /tmp/amongi-test-logs"
echo ""

exec "$PENV" server_handler.py \
  --name test-server \
  --study test-study \
  --heartbeat-interval 60 \
  --poll-interval 3 \
  --log-dir /tmp/amongi-test-logs

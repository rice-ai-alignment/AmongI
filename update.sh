#!/bin/bash
# update.sh — Pull latest, bump version, rebuild, and restart the server.
#
# Usage:
#   ./update.sh              # patch bump (1.0.0 → 1.0.1)
#   ./update.sh --minor      # minor bump (1.0.0 → 1.1.0)
#
# Requires: docker compose, git

set -euo pipefail
cd "$(dirname "$0")"

BUMP="patch"
if [[ "${1:-}" == "--minor" ]]; then BUMP="minor"; fi

echo "=== Pulling latest ==="
git pull origin main

echo ""
echo "=== Bumping version ==="
cd engine
python3 -c "
from version import bump_version
v = bump_version(patch=${BUMP} == 'patch')
print(f'Version: {v}')
"
cd ..

echo ""
echo "=== Rebuilding Docker image ==="
docker compose build

echo ""
echo "=== Restarting container ==="
docker compose down
docker compose up -d

echo ""
echo "=== Done ==="
docker compose logs --tail 5

#!/usr/bin/env bash
# Export component schema from the engine to the dashboard's public/ dir.
# Run from the dashboard/ directory.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../engine"
python3 -c "
from experiment import export_schema, _init_registry
_init_registry()
export_schema('../dashboard/public/schema.json')
"

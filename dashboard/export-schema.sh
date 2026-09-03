#!/usr/bin/env bash
# Sync compiler artifacts from the engine to the dashboard's public/ dir:
#   1. schema.json         — component registry (exported from Python)
#   2. schema_compiler.js  — the shared config compiler (single source of truth)
#   3. examples/           — example configs (engine/examples/ is canonical)
# Run from the dashboard/ directory (prebuild / predev hook).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE_DIR="$SCRIPT_DIR/../engine"
PUBLIC_DIR="$SCRIPT_DIR/public"

# 1. Export schema.json from the Python component registry
cd "$ENGINE_DIR"
python3 -c "
from experiment import export_schema, _init_registry
_init_registry()
export_schema('$PUBLIC_DIR/schema.json')
"

# 2. Copy the shared JS compiler — engine/ is the canonical copy
cp "$ENGINE_DIR/schema_compiler.js" "$PUBLIC_DIR/schema_compiler.js"

# 3. Sync example configs — remove previously synced example folders
#    (fixtures at the sample_data root, e.g. sample_games.json, are kept)
mkdir -p "$PUBLIC_DIR/sample_data"
find "$PUBLIC_DIR/sample_data" -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +
cp -r "$ENGINE_DIR/examples/." "$PUBLIC_DIR/sample_data/"

echo "[export-schema] schema.json + schema_compiler.js + examples/ synced to public/"

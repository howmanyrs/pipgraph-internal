#!/usr/bin/env bash
# Copy built plugin artifacts (manifest.json, main.js, styles.css) into the
# dev vault's plugin folder. Run after `npm run build`.
#
# Override the destination by exporting VAULT_PLUGIN_DIR before running:
#   VAULT_PLUGIN_DIR=/path/to/vault/.obsidian/plugins/pipgraph ./deploy-to-vault.sh

set -euo pipefail

VAULT_PLUGIN_DIR="${VAULT_PLUGIN_DIR:-/mnt/c/Users/Anton/dev-vault/.obsidian/plugins/pipgraph}"

cd "$(dirname "$0")"

if [[ ! -f main.js ]]; then
  echo "Error: main.js not found. Run 'npm run build' first." >&2
  exit 1
fi

mkdir -p "$VAULT_PLUGIN_DIR"
cp -v manifest.json main.js styles.css "$VAULT_PLUGIN_DIR/"
echo "Deployed to: $VAULT_PLUGIN_DIR"

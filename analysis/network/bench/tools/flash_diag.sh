#!/usr/bin/env bash
# Build + flash the Meshtastic relay diagnostic onto stratolink-2 over J-Link.
# Usage:  ./flash_diag.sh
set -euo pipefail
ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
PIO="$HOME/.platformio/penv/bin/pio"
cd "$ROOT/firmware"
echo "[flash_diag] building + uploading env:meshtastic_relay_diag (J-Link)…"
"$PIO" run -e meshtastic_relay_diag -t upload
echo "[flash_diag] done. The board now auto-cycles phases; watch with ./watch_mrd.sh"

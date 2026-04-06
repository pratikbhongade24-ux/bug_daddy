#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

"${SCRIPT_DIR}/deploy-backend.sh"
"${SCRIPT_DIR}/deploy-frontend.sh"

echo "Full platform deploy complete."

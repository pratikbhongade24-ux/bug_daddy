#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$BASE_DIR/agents/src/agentic_solution"
APPS_DIR="$BASE_DIR/agents/apps"
# All agents are deployed as a single combined runtime via bug_daddy/main.py.
# incident_daddy, reviewer_daddy, and sme_agent are routed internally by combined.py.
DEPLOY_TARGET="bug_daddy"

AWS_PROFILE="${AWS_PROFILE:-bug-daddy}"
AWS_REGION="${AWS_REGION:-ap-south-1}"

# ── 1. Sync shared source ─────────────────────────────────────────────────────
echo "Syncing agents/src/agentic_solution → $DEPLOY_TARGET..."
TARGET="$APPS_DIR/$DEPLOY_TARGET/agentic_solution"
rm -rf "$TARGET"
cp -r "$SRC" "$TARGET"
echo "  ✓ $DEPLOY_TARGET"

# ── 2. Deploy ─────────────────────────────────────────────────────────────────
echo ""
echo "Deploying $DEPLOY_TARGET..."
(
  cd "$APPS_DIR/$DEPLOY_TARGET"
  AWS_PROFILE="$AWS_PROFILE" \
  AWS_REGION="$AWS_REGION" \
  AWS_DEFAULT_REGION="$AWS_REGION" \
  agentcore deploy
)
echo "  ✓ $DEPLOY_TARGET deployed"

echo ""
echo "Done."

#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$BASE_DIR/agents/src/agentic_solution"
APPS_DIR="$BASE_DIR/agents/apps"
APPS=("bug_daddy" "incident_daddy" "reviewer_daddy" "sme_agent")

AWS_PROFILE="${AWS_PROFILE:-bug-daddy}"
AWS_REGION="${AWS_REGION:-ap-south-1}"

# ── 1. Sync shared source to all app copies ──────────────────────────────────
echo "Syncing agents/src/agentic_solution → app copies..."
for app in "${APPS[@]}"; do
  TARGET="$APPS_DIR/$app/agentic_solution"
  rm -rf "$TARGET"
  cp -r "$SRC" "$TARGET"
  echo "  ✓ $app"
done

# ── 2. Deploy each app ───────────────────────────────────────────────────────
DEPLOY_TARGETS=("${@-}")  # pass app names as args, or deploy all if none given
if [ ${#DEPLOY_TARGETS[@]} -eq 0 ]; then
  DEPLOY_TARGETS=("${APPS[@]}")
fi

for app in "${DEPLOY_TARGETS[@]}"; do
  APP_DIR="$APPS_DIR/$app"
  if [ ! -d "$APP_DIR" ]; then
    echo "⚠️  Skipping $app — directory not found"
    continue
  fi
  echo ""
  echo "Deploying $app..."
  (
    cd "$APP_DIR"
    AWS_PROFILE="$AWS_PROFILE" \
    AWS_REGION="$AWS_REGION" \
    AWS_DEFAULT_REGION="$AWS_REGION" \
    agentcore deploy
  )
  echo "  ✓ $app deployed"
done

echo ""
echo "Done."

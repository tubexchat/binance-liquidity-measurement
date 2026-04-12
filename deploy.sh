#!/usr/bin/env bash
set -euo pipefail

# --- Config ---
SERVER="ubuntu@43.153.133.202"
SSH_KEY="$HOME/Documents/tencent_vpn"
REMOTE_DIR="/home/ubuntu/binance-liquidity-measurement"
SSH_OPTS="-i $SSH_KEY -o ServerAliveInterval=30 -o StrictHostKeyChecking=accept-new"

echo "==> Syncing project files to server..."
rsync -avz --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.db' \
  --exclude '.venv' \
  --exclude 'logs' \
  --exclude '.ruff_cache' \
  --exclude '.pytest_cache' \
  -e "ssh $SSH_OPTS" \
  "$(dirname "$0")/" \
  "$SERVER:$REMOTE_DIR/"

echo "==> Ensuring .env exists on server..."
ssh $SSH_OPTS "$SERVER" "test -f $REMOTE_DIR/.env || { echo 'ERROR: .env not found on server. Please create it first.'; exit 1; }"

echo "==> Checking Docker availability..."
ssh $SSH_OPTS "$SERVER" "command -v docker >/dev/null 2>&1 || { echo 'Installing Docker...'; curl -fsSL https://get.docker.com | sh; sudo usermod -aG docker \$USER; echo 'Docker installed. You may need to re-login for group changes.'; }"

echo "==> Building and starting container..."
ssh $SSH_OPTS "$SERVER" "cd $REMOTE_DIR && docker compose down 2>/dev/null; docker compose up -d --build"

echo "==> Waiting for container to start..."
sleep 3

echo "==> Container status:"
ssh $SSH_OPTS "$SERVER" "cd $REMOTE_DIR && docker compose ps"

echo "==> Recent logs:"
ssh $SSH_OPTS "$SERVER" "cd $REMOTE_DIR && docker compose logs --tail 20"

echo ""
echo "==> Deployment complete!"
echo "    View logs:   ssh $SSH_OPTS $SERVER 'cd $REMOTE_DIR && docker compose logs -f'"
echo "    Stop:        ssh $SSH_OPTS $SERVER 'cd $REMOTE_DIR && docker compose down'"

#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ubuntu/safelensai-backend/safelensai-backend-api-server"
cd "${APP_DIR}"

# Track which step we're on — if the script fails, the trap reports exactly where
CURRENT_STEP=""
trap 'echo ""; echo "DEPLOYMENT FAILED at: ${CURRENT_STEP}"; echo "   Check the error output above for details."; exit 1' ERR

echo "=========================================="
echo "  SafeLens Dev Deployment Starting"
echo "  Time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=========================================="
echo ""

CURRENT_STEP="[1/6] Setting up virtual environment (10%)"
echo "=== ${CURRENT_STEP} ==="
python3 -m venv venv
source "${APP_DIR}/venv/bin/activate"
echo "[OK] Virtual environment ready"
echo ""

CURRENT_STEP="[2/6] Installing dependencies (20%)"
echo "=== ${CURRENT_STEP} ==="
"${APP_DIR}/venv/bin/pip" install --upgrade pip --quiet
"${APP_DIR}/venv/bin/pip" install -r requirements.txt --quiet
echo "[OK] Dependencies installed"
echo ""

CURRENT_STEP="[3/6] Collecting static files (40%)"
echo "=== ${CURRENT_STEP} ==="
"${APP_DIR}/venv/bin/python" manage.py collectstatic --noinput
echo "[OK] Static files collected"
echo ""
CURRENT_STEP="[4/6] Running database migrations (55%)"
echo "=== ${CURRENT_STEP} ==="
"${APP_DIR}/venv/bin/python" manage.py migrate --no-input
echo "[OK] Migrations complete"
echo ""

CURRENT_STEP="[5/6] Restarting services (80%)"
echo "=== ${CURRENT_STEP} ==="
sudo systemctl restart safelens.service
echo "  -> safelens.service restarted"
sudo systemctl restart safelens-poll-events.service
echo "  -> safelens-poll-events.service restarted"
echo "[OK] All services restarted"
echo ""

CURRENT_STEP="[6/6] Verifying services are active (95%)"
echo "=== ${CURRENT_STEP} ==="
for SVC in safelens.service safelens-poll-events.service; do
  STATUS=$(sudo systemctl is-active "$SVC")
  if [ "$STATUS" = "active" ]; then
    echo "  -> ${SVC}: active"
  else
    echo "  -> ${SVC}: ${STATUS}"
    exit 1
  fi
done
echo "[OK] All services verified"
echo ""

echo "=========================================="
echo "  DEPLOYMENT COMPLETE (100%)"
echo "  Time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=========================================="

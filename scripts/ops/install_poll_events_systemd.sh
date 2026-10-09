#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ubuntu/app/database-api"
UNIT_NAME="safelens-poll-events.service"
UNIT_SRC="${APP_DIR}/deploy/systemd/safelens-poll-events.service"
UNIT_DST="/etc/systemd/system/${UNIT_NAME}"

if [[ ! -d "${APP_DIR}" ]]; then
  echo "ERROR: App dir not found: ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -f "${UNIT_SRC}" ]]; then
  echo "ERROR: Unit file not found: ${UNIT_SRC}" >&2
  echo "Make sure your repo has deploy/systemd/safelens-poll-events.service" >&2
  exit 1
fi

echo "Installing ${UNIT_NAME}..."
sudo cp -f "${UNIT_SRC}" "${UNIT_DST}"
sudo systemctl daemon-reload
sudo systemctl restart "${UNIT_NAME}" || true
sudo systemctl enable --now "${UNIT_NAME}"

echo
echo "Status:"
sudo systemctl status "${UNIT_NAME}" --no-pager
echo
echo "Logs (tail):"
sudo journalctl -u "${UNIT_NAME}" -n 100 --no-pager

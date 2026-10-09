#!/bin/bash
 
cd /home/ubuntu/safelensai-backend/safelensai-backend-api-server
 
echo "Using virtual environment python"
 
VENV_PYTHON=/home/ubuntu/safelensai-backend/safelensai-backend-api-server/venv/bin/python
 
echo "Setting environment variables"
 
export DB_HOST=safelensai-db.chmsomou27n1.ap-south-1.rds.amazonaws.com
 
export DB_NAME=worker_safety_db
 
export DB_USER=safelens_user
 
export DB_PASSWORD=SafeLens@123
 
export DB_PORT=5432
 
echo "Running migrations"
 
$VENV_PYTHON manage.py migrate
 
echo "Starting Django app (via systemd)"
 
sudo systemctl restart safelens.service
 
echo "Starting notification poller (via systemd)"
 
sudo systemctl restart safelens-poll-events.service
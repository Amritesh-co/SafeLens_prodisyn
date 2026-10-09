#!/bin/bash

echo "Stopping app..."
sudo systemctl stop safelens.service || true
sudo systemctl stop safelens-poll-events.service || true
pkill -f runserver || true
pkill -f gunicorn || true
pkill -f "manage.py poll_events" || true

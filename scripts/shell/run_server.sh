#!/bin/bash
# Run script for Worker Safety API

source venv/bin/activate
echo "🔥 Starting Worker Safety API server..."
python manage.py runserver 0.0.0.0:8000

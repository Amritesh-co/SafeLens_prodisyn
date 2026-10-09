#!/bin/bash
# Setup script for Worker Safety API

echo "🚀 Setting up Worker Safety API..."

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "⬇️ Installing dependencies..."
pip install -r requirements.txt

# Run migrations
echo "🗄️ Running database migrations..."
python manage.py migrate

echo "✅ Setup complete!"
echo "To start the server, run: ./run_server.sh"

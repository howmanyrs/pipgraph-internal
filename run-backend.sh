#!/bin/bash

# PipGraph Backend Runner
# Activates virtual environment and runs the FastAPI backend
#
# USAGE:
#   ./run-backend.sh [uvicorn-options]
#
# EXAMPLES:
#   # Basic run (default: host=0.0.0.0, port=8000, reload=true)
#   ./run-backend.sh
#
#   # Run on localhost only
#   HOST=127.0.0.1 ./run-backend.sh
#
#   # Run on custom port
#   PORT=8080 ./run-backend.sh
#
#   # Production mode (no reload)
#   RELOAD=false ./run-backend.sh
#
#   # Custom host, port, and no reload
#   HOST=127.0.0.1 PORT=8080 RELOAD=false ./run-backend.sh
#
#   # With additional uvicorn options
#   ./run-backend.sh --log-level debug
#   ./run-backend.sh --workers 4
#   ./run-backend.sh --ssl-keyfile key.pem --ssl-certfile cert.pem
#
# ENVIRONMENT VARIABLES:
#   HOST    - Server host (default: 0.0.0.0)
#   PORT    - Server port (default: 8000)
#   RELOAD  - Enable auto-reload (default: true)
#
# REQUIREMENTS:
#   - Virtual environment at backend/.venv
#   - Dependencies installed (uv pip install -r requirements.txt)
#   - .env file with configuration (OPENROUTER_API_KEY, NEO4J_*, etc.)
#
# SETUP (first time):
#   cd backend/
#   uv venv
#   uv pip install -r requirements.txt
#   cp .env.example .env  # and edit with your credentials
#   cd ..
#   ./run-backend.sh

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

# Default settings
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"
RELOAD="${RELOAD:-true}"

# Check if backend directory exists
if [ ! -d "$BACKEND_DIR" ]; then
    echo "Error: backend directory not found at $BACKEND_DIR"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Error: Virtual environment not found at $VENV_DIR"
    echo "Please create it first with: cd backend && uv venv && uv pip install -r requirements.txt"
    exit 1
fi

# Change to backend directory
cd "$BACKEND_DIR" || exit 1

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found at $BACKEND_DIR/.env"
    echo "Backend may not work correctly without configuration."
    echo "Please create .env file with required settings:"
    echo "  - OPENROUTER_API_KEY"
    echo "  - NEO4J_URI"
    echo "  - NEO4J_USER"
    echo "  - NEO4J_PASSWORD"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Check if dependencies are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    uv pip install -r requirements.txt
fi

# Build uvicorn command
UVICORN_CMD="uvicorn app.api.main:app --host $HOST --port $PORT"

if [ "$RELOAD" = "true" ]; then
    UVICORN_CMD="$UVICORN_CMD --reload"
fi

# Add any additional arguments passed to the script
if [ $# -gt 0 ]; then
    UVICORN_CMD="$UVICORN_CMD $@"
fi

# Display startup info
echo "========================================="
echo "Starting PipGraph Backend"
echo "========================================="
echo "Host: $HOST"
echo "Port: $PORT"
echo "Reload: $RELOAD"
echo "Working directory: $BACKEND_DIR"
echo "Command: $UVICORN_CMD"
echo "========================================="
echo ""

# Run the backend
exec $UVICORN_CMD
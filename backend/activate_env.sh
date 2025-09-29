#!/bin/bash

# PipGraph Backend Environment Activation Script
# This script activates the Python virtual environment for the backend

# Check if we're in the correct directory
if [ ! -f "requirements.txt" ]; then
    echo "Error: requirements.txt not found. Please run this script from the backend directory."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies if they haven't been installed yet
if [ ! -f ".venv/pyvenv.cfg" ] || [ ! -d ".venv/lib" ]; then
    echo "Installing dependencies..."
    uv pip install -r requirements.txt
fi

echo "Environment activated! You can now run:"
echo "  uvicorn app.api.main:app --reload"
echo ""
echo "To deactivate, run: deactivate"
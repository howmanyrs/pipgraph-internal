#!/bin/bash

# PipGraph CLI Runner
# Activates virtual environment and runs the CLI

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_DIR="$SCRIPT_DIR/pipgraph-cli"
VENV_DIR="$CLI_DIR/.venv"

# Check if CLI directory exists
if [ ! -d "$CLI_DIR" ]; then
    echo "Error: pipgraph-cli directory not found at $CLI_DIR"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Error: Virtual environment not found at $VENV_DIR"
    echo "Please create it first with: cd pipgraph-cli && uv venv"
    exit 1
fi

# Activate virtual environment and run CLI
cd "$CLI_DIR" || exit 1

# Source the virtual environment
source "$VENV_DIR/bin/activate"

# Check if the package is installed
if ! command -v pipgraph &> /dev/null; then
    echo "Installing pipgraph-cli in editable mode..."
    uv pip install -e .
fi

# Run the CLI with any passed arguments
pipgraph "$@"

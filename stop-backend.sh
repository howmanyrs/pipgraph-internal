#!/bin/bash

# PipGraph Backend Stopper
# Stops the FastAPI backend running on specified port
#
# USAGE:
#   ./stop-backend.sh [port]
#
# EXAMPLES:
#   # Stop backend on default port (8001)
#   ./stop-backend.sh
#
#   # Stop backend on custom port
#   ./stop-backend.sh 8080
#
#   # Force stop with sudo (if needed)
#   sudo ./stop-backend.sh
#
# ENVIRONMENT VARIABLES:
#   PORT - Server port (default: 8001)

# Default port (matches run-backend.sh default)
PORT="${1:-${PORT:-8001}}"

echo "========================================="
echo "Stopping PipGraph Backend"
echo "========================================="
echo "Port: $PORT"
echo ""

# Method 1: Try lsof (most reliable for ports)
echo "🔍 Searching for processes on port $PORT..."
PID=$(lsof -ti:$PORT 2>/dev/null)

# Method 2: If lsof didn't find anything, try with sudo
if [ -z "$PID" ] && [ "$EUID" -ne 0 ]; then
    echo "🔍 Trying with sudo..."
    PID=$(sudo lsof -ti:$PORT 2>/dev/null)
fi

# Method 3: If still nothing, search by process name
if [ -z "$PID" ]; then
    echo "🔍 Searching by process name (uvicorn)..."
    PID=$(ps aux | grep -E "[u]vicorn.*app\.api\.main:app.*$PORT" | awk '{print $2}')
fi

# Method 4: Search for any uvicorn process
if [ -z "$PID" ]; then
    echo "🔍 Searching for any uvicorn process..."
    PID=$(pgrep -f "uvicorn.*app.api.main")
fi

# If no process found
if [ -z "$PID" ]; then
    echo "❌ No process found on port $PORT"
    echo ""
    echo "Checking all uvicorn processes:"
    ps aux | grep -E "[u]vicorn" || echo "  No uvicorn processes running"
    echo ""
    echo "Checking all processes on port $PORT:"
    lsof -i:$PORT 2>/dev/null || echo "  No processes using port $PORT (or insufficient permissions)"
    exit 0
fi

# Show process info before killing
echo ""
echo "✅ Found process(es): $PID"
echo ""
echo "Process details:"
ps aux | grep -E "$(echo $PID | tr ' ' '|')" | grep -v grep
echo ""

# Ask for confirmation if multiple PIDs
PID_COUNT=$(echo $PID | wc -w)
if [ $PID_COUNT -gt 1 ]; then
    echo "⚠️  Found $PID_COUNT processes. Will stop all of them."
fi

echo "Stopping process(es)..."

# Try graceful stop first (SIGTERM)
KILLED=false
for pid in $PID; do
    if kill $pid 2>/dev/null; then
        echo "  → Sent SIGTERM to PID $pid"
        KILLED=true
    elif [ "$EUID" -ne 0 ]; then
        echo "  → Trying with sudo for PID $pid..."
        if sudo kill $pid 2>/dev/null; then
            echo "  → Sent SIGTERM to PID $pid (with sudo)"
            KILLED=true
        fi
    fi
done

if [ "$KILLED" = true ]; then
    echo ""
    echo "⏳ Waiting for graceful shutdown..."
    sleep 2

    # Check if processes are still running
    REMAINING=""
    for pid in $PID; do
        if kill -0 $pid 2>/dev/null; then
            REMAINING="$REMAINING $pid"
        fi
    done

    if [ -n "$REMAINING" ]; then
        echo "⚠️  Some processes still running:$REMAINING"
        echo "   Forcing shutdown (SIGKILL)..."

        for pid in $REMAINING; do
            if kill -9 $pid 2>/dev/null; then
                echo "  → Force killed PID $pid"
            elif [ "$EUID" -ne 0 ]; then
                sudo kill -9 $pid 2>/dev/null && echo "  → Force killed PID $pid (with sudo)"
            fi
        done

        echo "✅ Force stop completed"
    else
        echo "✅ All processes stopped gracefully"
    fi
else
    echo "❌ Failed to stop processes. Permission denied."
    echo ""
    echo "Try running with sudo:"
    echo "  sudo ./stop-backend.sh $PORT"
    exit 1
fi

# Final verification
sleep 1
FINAL_CHECK=$(lsof -ti:$PORT 2>/dev/null || sudo lsof -ti:$PORT 2>/dev/null)
if [ -n "$FINAL_CHECK" ]; then
    echo ""
    echo "⚠️  WARNING: Port $PORT is still in use by PID $FINAL_CHECK"
    echo "   You may need to wait a moment or manually kill the process:"
    echo "   sudo kill -9 $FINAL_CHECK"
else
    echo ""
    echo "✅ Port $PORT is now free"
fi

echo ""
echo "========================================="
echo "Backend stopped"
echo "========================================="

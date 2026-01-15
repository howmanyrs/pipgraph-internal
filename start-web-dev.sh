#!/bin/bash

# Script to start pipgraph-web development server
# Location: /home/anton/pipgraph/start-web-dev.sh

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting PipGraph Web Development Server${NC}"
echo ""

# Check if we're in the project root
if [ ! -d "pipgraph-web" ]; then
    echo -e "${RED}Error: pipgraph-web directory not found${NC}"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Navigate to pipgraph-web
cd pipgraph-web

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}node_modules not found. Installing dependencies...${NC}"
    npm install
    echo ""
fi

# Check if .env.local exists (optional)
if [ ! -f ".env.local" ]; then
    echo -e "${YELLOW}Warning: .env.local not found${NC}"
    echo "Using default API URL: http://localhost:8000"
    echo "To customize, create .env.local with NEXT_PUBLIC_API_URL"
    echo ""
fi

# Start the development server
echo -e "${GREEN}Starting Next.js development server...${NC}"
echo -e "${GREEN}Web UI will be available at: http://localhost:3000${NC}"
echo ""

npm run dev

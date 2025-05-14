#!/bin/bash
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Stopping AnaptIQ Chat System...\033[0m"

if [ -f logs/api_server.pid ]; then
    API_PID=$(cat logs/api_server.pid)
    echo -e "${YELLOW}Stopping API server (PID: $API_PID)...\033[0m"
    kill $API_PID 2>/dev/null || true
    rm logs/api_server.pid
fi

if [ -f logs/frontend_server.pid ]; then
    FRONTEND_PID=$(cat logs/frontend_server.pid)
    echo -e "${YELLOW}Stopping frontend server (PID: $FRONTEND_PID)...\033[0m"
    kill $FRONTEND_PID 2>/dev/null || true
    rm logs/frontend_server.pid
fi

echo -e "${GREEN}AnaptIQ Chat System stopped.\033[0m"

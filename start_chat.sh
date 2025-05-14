#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Anaptyss Chat System${NC}"
echo "=================================="

# Check if we're in the right directory
if [ ! -f "main.py" ] || [ ! -f "test_frontend.html" ]; then
    echo -e "${RED}Error: main.py or test_frontend.html not found.${NC}"
    echo "Please run this script from the root directory of your Anaptyss Chat project."
    exit 1
fi

# Function to check if a port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null ; then
        return 0
    else
        return 1
    fi
}

# Kill any processes using our ports
if check_port 8000; then
    echo -e "${YELLOW}Port 8000 is in use. Attempting to free it...${NC}"
    lsof -ti:8000 | xargs kill -9
    echo -e "${GREEN}Port 8000 freed.${NC}"
fi

if check_port 8080; then
    echo -e "${YELLOW}Port 8080 is in use. Attempting to free it...${NC}"
    lsof -ti:8080 | xargs kill -9
    echo -e "${GREEN}Port 8080 freed.${NC}"
fi

# Add missing imports to main.py if needed
echo -e "${YELLOW}Checking for missing imports in main.py...${NC}"
if grep -q "def get_session_duration.*timedelta" main.py && ! grep -q "from datetime import.*timedelta" main.py; then
    echo -e "${YELLOW}Adding missing timedelta import to main.py${NC}"
    sed -i '1s/^/from datetime import datetime, timedelta\n/' main.py
    echo -e "${GREEN}Fixed imports in main.py${NC}"
fi

# Start the FastAPI backend
echo -e "${YELLOW}Starting API server on port 8000...${NC}"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload > api_server.log 2>&1 &
API_PID=$!
echo -e "${GREEN}API server started with PID: $API_PID${NC}"

# Wait longer for the API to start (up to 10 seconds)
echo -e "${YELLOW}Waiting for API server to initialize...${NC}"
max_attempts=10
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if check_port 8000; then
        echo -e "${GREEN}API server is running on port 8000${NC}"
        break
    fi
    attempt=$((attempt+1))
    echo -n "."
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "\n${RED}Failed to start API server after $max_attempts seconds. Check api_server.log for details.${NC}"
    exit 1
fi

# Create a temporary directory for the frontend
echo -e "${YELLOW}Setting up frontend on port 8080...${NC}"
rm -rf temp_frontend 2>/dev/null
mkdir -p temp_frontend

# Copy the test frontend to the temporary directory
cp test_frontend.html temp_frontend/index.html

# Start a simple HTTP server for the frontend
cd temp_frontend
python3 -m http.server 8080 > ../frontend_server.log 2>&1 &
FRONTEND_PID=$!
cd ..

# Wait for the frontend to start (up to 5 seconds)
echo -e "${YELLOW}Waiting for frontend server to initialize...${NC}"
max_attempts=5
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if check_port 8080; then
        echo -e "${GREEN}Frontend server is running on port 8080${NC}"
        break
    fi
    attempt=$((attempt+1))
    echo -n "."
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "\n${RED}Failed to start frontend server. Check frontend_server.log for details.${NC}"
    kill $API_PID
    exit 1
fi

echo
echo -e "${GREEN}Anaptyss Chat System is now running:${NC}"
echo -e "  API: ${GREEN}http://localhost:8000${NC}"
echo -e "  Frontend: ${GREEN}http://localhost:8080${NC}"
echo
echo -e "Press Ctrl+C to shutdown both servers."

# Store PIDs for cleanup
echo "$API_PID $FRONTEND_PID" > .server_pids

# Wait for user to press Ctrl+C
trap 'echo -e "\n${YELLOW}Shutting down servers...${NC}"; kill $API_PID $FRONTEND_PID 2>/dev/null; rm -rf temp_frontend .server_pids 2>/dev/null; echo -e "${GREEN}Servers stopped.${NC}"; exit 0' INT
wait

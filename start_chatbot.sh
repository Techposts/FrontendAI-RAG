#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

set -e

echo -e "${YELLOW}Starting AnaptIQ Financial Services Chat System${NC}"
echo "=================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed. Please install Python 3 to continue.${NC}"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}Virtual environment created.${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Check if requirements are installed
echo -e "${YELLOW}Checking and installing requirements...${NC}"
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file from example...${NC}"
    cp .env.example .env
    echo -e "${RED}IMPORTANT: Please edit .env file with your actual API keys before continuing.${NC}"
    echo -e "Press Enter to continue after editing, or Ctrl+C to exit..."
    read
fi

# Check and start Qdrant (Docker)
echo -e "${YELLOW}Checking if Qdrant is running...${NC}"
if ! curl -s http://localhost:6333/health > /dev/null; then
    echo -e "${YELLOW}Qdrant is not running. Starting Qdrant...${NC}"
    if command -v docker &> /dev/null; then
        if docker ps -a --format "{{.Names}}" | grep -q "qdrant"; then
            docker start qdrant
        else
            docker run -d -p 6333:6333 -p 6334:6334 --name qdrant qdrant/qdrant
        fi
        echo -e "${YELLOW}Waiting for Qdrant to initialize...${NC}"
        sleep 5
        # Check if Qdrant started successfully
        if ! curl -s http://localhost:6333/health > /dev/null; then
            echo -e "${RED}Failed to start Qdrant. Please check Docker logs.${NC}"
            echo -e "Run: docker logs qdrant"
            exit 1
        fi
    else
        echo -e "${RED}Docker is not installed. Please install Docker to run Qdrant.${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}Qdrant is running.${NC}"
fi

# Check if Qdrant is populated
echo -e "${YELLOW}Checking if Qdrant collection is initialized...${NC}"
COLLECTION_EXISTS=$(curl -s http://localhost:6333/collections/anaptyss_content | grep -c "name" || echo "0")

if [ "$COLLECTION_EXISTS" -eq 0 ]; then
    echo -e "${YELLOW}Initializing Qdrant with sample data...${NC}"
    if [ -f "initialize_qdrant.py" ]; then
        python initialize_qdrant.py
        if [ $? -ne 0 ]; then
            echo -e "${RED}Failed to initialize Qdrant. Check logs for details.${NC}"
            exit 1
        fi
        echo -e "${GREEN}Qdrant initialized successfully.${NC}"
    else
        echo -e "${YELLOW}initialize_qdrant.py not found. Creating collection manually...${NC}"
        curl -X PUT "http://localhost:6333/collections/anaptyss_content" \
            -H "Content-Type: application/json" \
            -d '{"vectors": {"size": 1536, "distance": "Cosine"}}'
        if [ $? -ne 0 ]; then
            echo -e "${RED}Failed to create Qdrant collection.${NC}"
            exit 1
        fi
        echo -e "${GREEN}Qdrant collection created.${NC}"
    fi
else
    echo -e "${GREEN}Qdrant collection already exists.${NC}"
fi

# Check for config.py
if [ ! -f "config.py" ]; then
    echo -e "${RED}config.py not found. Creating from template...${NC}"
    cat > config.py << EOL
# Configuration for AnaptIQ Chat API
import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-openai-api-key")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

# Default dummy data for Qdrant if empty/testing
DEFAULT_CONTENT = [
    {
        "title": "Digital Transformation Solutions",
        "text": """Anaptyss offers comprehensive digital transformation solutions tailored to your industry needs. Our approach combines strategic consulting, technology implementation, and change management to ensure successful digital initiatives.

We focus on these key areas:
- Business process optimization
- Customer experience enhancement
- Data-driven decision making
- Legacy system modernization

Our team of experts will work with you to identify opportunities, develop a roadmap, and implement solutions that drive tangible business value.""",
        "url": "https://anaptyss.com/solutions/digital-transformation",
        "content_type": "solution",
        "industries": ["finance", "healthcare", "manufacturing"],
        "topics": ["digital_transformation", "process_optimization"]
    }
]

# Application settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
PORT = int(os.getenv("PORT", 8000))
EOL
    echo -e "${GREEN}Created config.py template.${NC}"
fi

# Function to kill processes using a port
kill_port() {
    local port=$1
    if command -v lsof &> /dev/null; then
        lsof -ti:$port | xargs -r kill -9
    elif command -v fuser &> /dev/null; then
        fuser -k $port/tcp
    else
        echo -e "${YELLOW}Cannot kill processes on port $port. Please ensure it's not in use.${NC}"
    fi
    sleep 2
}

# Check and clean API port
echo -e "${YELLOW}Checking port 8000...${NC}"
if lsof -i:8000 &> /dev/null || fuser 8000/tcp &> /dev/null 2>&1; then
    echo -e "${YELLOW}Port 8000 is in use. Freeing it...${NC}"
    kill_port 8000
fi

# Start API server with proper logging and detached from the terminal
echo -e "${YELLOW}Starting API server on port 8000...${NC}"
mkdir -p logs
API_LOG="logs/api_server.log"
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --reload > "$API_LOG" 2>&1 &
API_PID=$!

# Save the PID to a file for later management
echo $API_PID > logs/api_server.pid

# Wait for API to start
echo -e "${YELLOW}Waiting for API server to start...${NC}"
max_attempts=10
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:8000/health > /dev/null; then
        break
    fi
    attempt=$((attempt+1))
    echo -e "${YELLOW}Waiting for API server (attempt $attempt/$max_attempts)...${NC}"
    sleep 2
done

# Check if API started successfully
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo -e "${RED}API server failed to start. Check logs at $API_LOG${NC}"
    echo -e "Last 10 lines of log:"
    tail -n 10 "$API_LOG"
    echo -e "${RED}Cleaning up...${NC}"
    kill $API_PID 2>/dev/null || true
    exit 1
fi

HEALTH_CHECK=$(curl -s http://localhost:8000/health || echo '{"status":"error"}')
if ! echo $HEALTH_CHECK | grep -q '"status":"ok"'; then
    echo -e "${YELLOW}API server might have issues. Last 10 lines of log:${NC}"
    tail -n 10 "$API_LOG"
    echo -e "${YELLOW}Continuing anyway...${NC}"
else
    echo -e "${GREEN}API server is running on port 8000${NC}"
fi

# Check and clean frontend port
echo -e "${YELLOW}Checking port 8080...${NC}"
if lsof -i:8080 &> /dev/null || fuser 8080/tcp &> /dev/null 2>&1; then
    echo -e "${YELLOW}Port 8080 is in use. Freeing it...${NC}"
    kill_port 8080
fi

# Create public directory for frontend if it doesn't exist
echo -e "${YELLOW}Setting up frontend server...${NC}"
mkdir -p public
# Copy test_frontend.html directly (don't rename to index.html)
if [ ! -f "public/test_frontend.html" ] || [ "$(diff -q test_frontend.html public/test_frontend.html 2>/dev/null)" ]; then
    echo -e "${YELLOW}Copying frontend files...${NC}"
    cp test_frontend.html public/test_frontend.html
fi

# Start frontend server with proper logging and detached from the terminal
echo -e "${YELLOW}Starting frontend server on port 8080...${NC}"
FRONTEND_LOG="logs/frontend_server.log"
cd public
nohup python3 -m http.server 8080 > "../$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
cd ..

# Save the PID to a file for later management
echo $FRONTEND_PID > logs/frontend_server.pid

# Check if frontend server started
sleep 2
if ! curl -s http://localhost:8080/test_frontend.html > /dev/null; then
    echo -e "${RED}Frontend server failed to start or test_frontend.html is not accessible. Check logs at $FRONTEND_LOG${NC}"
    echo -e "Last 10 lines of log:"
    tail -n 10 "$FRONTEND_LOG"
    echo -e "${RED}Cleaning up...${NC}"
    kill $API_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 1
fi

echo -e "\n${GREEN}AnaptIQ Financial Services Chat System is now running:${NC}"
echo "  API: http://localhost:8000 (http://209.38.136.155:8000)"
echo "  Frontend: http://localhost:8080/test_frontend.html (http://209.38.136.155:8080/test_frontend.html)"
echo -e "\n${YELLOW}Services will continue running after you close this terminal.${NC}"
echo -e "To stop them later, run: ${GREEN}./stop_chatbot.sh${NC}"
echo -e "To check their status: ${GREEN}cat logs/api_server.log${NC} or ${GREEN}cat logs/frontend_server.log${NC}"
echo -e "\nServer PIDs: API=$API_PID, Frontend=$FRONTEND_PID\n"


# Create a stop script for later use
cat > stop_chatbot.sh << EOL
#!/bin/bash
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "\${YELLOW}Stopping AnaptIQ Chat System...${NC}"

if [ -f logs/api_server.pid ]; then
    API_PID=\$(cat logs/api_server.pid)
    echo -e "\${YELLOW}Stopping API server (PID: \$API_PID)...${NC}"
    kill \$API_PID 2>/dev/null || true
    rm logs/api_server.pid
fi

if [ -f logs/frontend_server.pid ]; then
    FRONTEND_PID=\$(cat logs/frontend_server.pid)
    echo -e "\${YELLOW}Stopping frontend server (PID: \$FRONTEND_PID)...${NC}"
    kill \$FRONTEND_PID 2>/dev/null || true
    rm logs/frontend_server.pid
fi

echo -e "\${GREEN}AnaptIQ Chat System stopped.${NC}"
EOL

chmod +x stop_chatbot.sh
echo -e "${GREEN}Created stop_chatbot.sh script for stopping the services later${NC}"
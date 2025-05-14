#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Fixing Anaptyss Chat System Dependencies${NC}"
echo "========================================"

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

# Install dependencies with pip
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

# Double check uvicorn is installed
if ! command -v uvicorn &> /dev/null; then
    echo -e "${YELLOW}Uvicorn not found in PATH, installing specifically...${NC}"
    pip install uvicorn[standard]
    
    # Add venv bin to PATH temporarily
    export PATH="$PWD/venv/bin:$PATH"
    
    if ! command -v uvicorn &> /dev/null; then
        echo -e "${RED}Failed to install uvicorn. Please install manually: pip install uvicorn[standard]${NC}"
        exit 1
    fi
fi

echo -e "${YELLOW}Testing uvicorn installation...${NC}"
uvicorn --version

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Uvicorn is correctly installed!${NC}"
else
    echo -e "${RED}Uvicorn installation appears to have issues.${NC}"
    exit 1
fi

# Check Qdrant connection
echo -e "${YELLOW}Checking Qdrant connection...${NC}"
python -c "from qdrant_client import QdrantClient; client = QdrantClient(url='http://localhost:6333'); print('Connected to Qdrant: ' + str(client.get_collections()))"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Qdrant connection successful!${NC}"
else
    echo -e "${YELLOW}Could not connect to Qdrant. Make sure it's running on port 6333.${NC}"
    echo -e "You can start it with Docker: docker run -d -p 6333:6333 -p 6334:6334 --name qdrant qdrant/qdrant"
fi

# Check OpenAI API key
echo -e "${YELLOW}Checking OpenAI API key...${NC}"
OPENAI_API_KEY=$(grep OPENAI_API_KEY .env | cut -d '=' -f2)

if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}OPENAI_API_KEY not found in .env file.${NC}"
else
    echo -e "${GREEN}OPENAI_API_KEY found in .env file.${NC}"
    # Test OpenAI connection
    python -c "from openai import OpenAI; client = OpenAI(api_key='$OPENAI_API_KEY'); models = client.models.list(); print('OpenAI connection successful. Available models: ' + str(len(models.data)))"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}OpenAI API connection successful!${NC}"
    else
        echo -e "${RED}Could not connect to OpenAI API. Check your API key.${NC}"
    fi
fi

echo -e "\n${GREEN}All dependencies checked and fixed!${NC}"
echo -e "You can now run the chatbot API server with: ${YELLOW}uvicorn main:app --host 0.0.0.0 --port 8000${NC}"
echo -e "Then access the frontend at: ${YELLOW}http://localhost:8080/test_frontend.html${NC}"

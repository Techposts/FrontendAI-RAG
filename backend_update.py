#!/usr/bin/env python3
import os
import sys
import shutil
from pathlib import Path

print("Anaptyss Backend Update Script")
print("===============================")

# Check if main.py exists
if not Path("main.py").exists():
    print("Error: main.py not found. Please run this script from the project root directory.")
    sys.exit(1)

# Create a leads endpoint
print("Adding lead capture endpoint...")

# Create a backup of main.py
shutil.copy("main.py", "main.py.bak")
print("Backup created: main.py.bak")

# Read the existing main.py
with open("main.py", "r") as f:
    main_content = f.read()

# Create the lead capture model
lead_model = """
class LeadData(BaseModel):
    name: str
    email: str
    interest: Optional[str] = None
    session_id: Optional[str] = None
"""

# Create the lead capture endpoint
lead_endpoint = """
@app.post("/leads")
async def capture_lead(lead: LeadData):
    """Capture and store lead information"""
    try:
        # Log the lead data
        logger.info(f"Lead captured: {lead.name}, {lead.email}, {lead.interest}")
        
        # You can implement additional logic here:
        # - Store leads in a database
        # - Send email notifications
        # - Add to a CRM system
        
        return {
            "status": "success",
            "message": "Lead information captured successfully"
        }
    
    except Exception as e:
        logger.error(f"Error capturing lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))
"""

# Create the feedback endpoint
feedback_model = """
class FeedbackData(BaseModel):
    session_id: str
    message_index: int
    feedback_type: str  # 'positive' or 'negative'
    comment: Optional[str] = None
"""

feedback_endpoint = """
@app.post("/feedback")
async def record_feedback(feedback: FeedbackData):
    """Record user feedback on chat responses"""
    try:
        # Log the feedback
        logger.info(f"Feedback received: {feedback.feedback_type} for message {feedback.message_index} in session {feedback.session_id}")
        
        # You can implement additional logic here:
        # - Store feedback in a database
        # - Use feedback to improve responses
        
        return {
            "status": "success", 
            "message": "Feedback recorded successfully"
        }
    
    except Exception as e:
        logger.error(f"Error recording feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))
"""

# Find the right place to insert the models
if "class ChatRequest(BaseModel):" in main_content:
    # Insert lead and feedback models before ChatRequest
    main_content = main_content.replace(
        "class ChatRequest(BaseModel):", 
        f"{lead_model}\n\n{feedback_model}\n\nclass ChatRequest(BaseModel):"
    )
else:
    # Fallback: Add after BaseModel import
    main_content = main_content.replace(
        "from pydantic import BaseModel",
        f"from pydantic import BaseModel\n\n{lead_model}\n\n{feedback_model}"
    )

# Add endpoints to the end (before if __name__ == "__main__":)
if "if __name__ == \"__main__\":" in main_content:
    main_content = main_content.replace(
        "if __name__ == \"__main__\":", 
        f"{lead_endpoint}\n\n{feedback_endpoint}\n\nif __name__ == \"__main__\":"
    )
else:
    # Fallback: Add to the end
    main_content += f"\n\n{lead_endpoint}\n\n{feedback_endpoint}\n"

# Write the modified content back to main.py
with open("main.py", "w") as f:
    f.write(main_content)

print("Added lead capture and feedback endpoints to main.py")

# Create a simple script to serve static files
print("Creating script to serve the React frontend...")

serve_script = """#!/usr/bin/env python3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import importlib
import sys
from pathlib import Path

# Check if static directory exists
if not Path("static").exists() or not Path("static/index.html").exists():
    print("Error: Static frontend files not found.")
    print("Please run update_frontend.sh first to build the React frontend.")
    sys.exit(1)

# Import the main app
sys.path.insert(0, '.')
main_module = importlib.import_module('main')

# Get the FastAPI app instance
app = main_module.app

# Add static files serving
app.mount("/", StaticFiles(directory="static", html=True), name="frontend")

if __name__ == "__main__":
    print("Starting Anaptyss Chat with React frontend...")
    print("Server running at: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""

# Write the serve script
with open("serve_chatbot.py", "w") as f:
    f.write(serve_script)

# Make it executable
os.chmod("serve_chatbot.py", 0o755)

print("Created serve_chatbot.py to serve the React frontend")
print("\nBackend update complete!")
print("\nNext steps:")
print("1. Run './update_frontend.sh' to build the React frontend")
print("2. Start the complete application with './serve_chatbot.py'")

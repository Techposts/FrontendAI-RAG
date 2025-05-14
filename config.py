# config.py
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QDRANT_URL       = os.getenv("QDRANT_URL")
SITE_URL         = os.getenv("SITE_URL", "https://techposts.org")

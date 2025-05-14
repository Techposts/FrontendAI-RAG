#!/usr/bin/env python3
"""
Debug tool for Anaptyss Chatbot System

This script helps diagnose issues with the chatbot system by:
1. Testing connections to all components
2. Validating Qdrant collection and content
3. Testing OpenAI API connectivity
4. Performing test queries against the API
5. Validating configuration files
"""

import os
import sys
import json
import requests
import time
from dotenv import load_dotenv
import argparse

# Try to import the required packages, showing helpful error if missing
try:
    from openai import OpenAI
    from qdrant_client import QdrantClient
    from fastapi import FastAPI
    import uvicorn
except ImportError as e:
    missing_package = str(e).split("'")[1]
    print(f"ERROR: Missing required package: {missing_package}")
    print("Please install all required packages with: pip install -r requirements.txt")
    sys.exit(1)

# Load environment variables
load_dotenv()

def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 50)
    print(f" {text}")
    print("=" * 50)

def check_env_vars():
    """Check if all required environment variables are set."""
    print_header("Checking Environment Variables")
    
    required_vars = ["OPENAI_API_KEY", "QDRANT_URL", "SITE_URL"]
    missing = []
    
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing.append(var)
            print(f"❌ Missing: {var}")
        else:
            # Mask API keys for security
            if "API_KEY" in var:
                displayed_value = value[:5] + "..." + value[-4:]
            else:
                displayed_value = value
            print(f"✅ {var} = {displayed_value}")
    
    if missing:
        print("\n⚠️  Missing environment variables. Please check your .env file.")
        return False
    
    return True

def check_openai_connection():
    """Test connection to OpenAI API."""
    print_header("Testing OpenAI API Connection")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Cannot test OpenAI connection: API key missing")
        return False
    
    client = OpenAI(api_key=api_key)
    
    try:
        print("Attempting to list models...")
        models = client.models.list()
        print(f"✅ Successfully connected to OpenAI API. Found {len(models.data)} models")
        return True
    except Exception as e:
        print(f"❌ Failed to connect to OpenAI API: {str(e)}")
        return False

def check_qdrant_connection():
    """Test connection to Qdrant and verify collection."""
    print_header("Testing Qdrant Connection")
    
    qdrant_url = os.getenv("QDRANT_URL")
    if not qdrant_url:
        print("❌ Cannot test Qdrant connection: QDRANT_URL missing")
        return False
    
    try:
        client = QdrantClient(url=qdrant_url)
        collections = client.get_collections()
        
        print(f"✅ Successfully connected to Qdrant. Found {len(collections.collections)} collections:")
        for collection in collections.collections:
            print(f"  - {collection.name}")
        
        # Check for Anaptyss content collection
        content_collection = "anaptyss_content"
        collection_exists = any(c.name == content_collection for c in collections.collections)
        
        if collection_exists:
            print(f"✅ Found required collection: '{content_collection}'")
            # Check collection stats
            try:
                collection_info = client.get_collection(content_collection)
                print(f"  - Points count: {collection_info.points_count}")
                print(f"  - Vectors size: {collection_info.config.params.vectors.size}")
                print(f"  - Distance: {collection_info.config.params.vectors.distance}")
                
                # If empty, suggest running ingest script
                if collection_info.points_count == 0:
                    print("⚠️  The collection exists but contains no vectors. Run the ingest.py script to populate it.")
            except Exception as e:
                print(f"❌ Error getting collection details: {str(e)}")
        else:
            print(f"❌ Required collection '{content_collection}' not found")
            print("   Run ingest.py to create and populate the collection")
        
        return True
    except Exception as e:
        print(f"❌ Failed to connect to Qdrant: {str(e)}")
        if "Connection refused" in str(e):
            print("\nℹ️  Troubleshooting tips:")
            print("   1. Make sure Qdrant is running. Start with: docker run -d -p 6333:6333 -p 6334:6334 --name qdrant qdrant/qdrant")
            print("   2. Check if the QDRANT_URL in .env is correct (usually http://localhost:6333)")
        return False

def check_api_server():
    """Test if the API server is running and healthy."""
    print_header("Testing API Server")
    
    api_url = "http://localhost:8000/health"
    
    try:
        print(f"Attempting to connect to API at {api_url}...")
        response = requests.get(api_url, timeout=5)
        
        if response.status_code == 200:
            health_data = response.json()
            if health_data.get("status") == "ok":
                print("✅ API server is running and healthy")
                return True
            else:
                print(f"⚠️  API server returned status: {health_data.get('status')}")
                print(f"   Message: {health_data.get('message', 'No message provided')}")
        else:
            print(f"❌ API server returned status code: {response.status_code}")
        
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Failed to connect to API server (connection refused)")
        print("\nℹ️  Troubleshooting tips:")
        print("   1. Make sure the API server is running: uvicorn main:app --host 0.0.0.0 --port 8000")
        print("   2. Check api_server.log for startup errors")
        return False
    except Exception as e:
        print(f"❌ Error connecting to API server: {str(e)}")
        return False

def test_chat_query(query="Tell me about your financial services offerings"):
    """Test a chat query against the API."""
    print_header(f"Testing Chat Query: '{query}'")
    
    api_url = "http://localhost:8000/chat"
    
    try:
        print("Sending test query to API...")
        start_time = time.time()
        
        response = requests.post(
            api_url,
            json={"message": query, "session_id": None},
            timeout=30
        )
        
        elapsed_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Query successful (took {elapsed_time:.2f} seconds)")
            print(f"✅ Session ID: {result.get('session_id')}")
            
            # Check response quality
            reply = result.get("reply", "")
            sources = result.get("sources", [])
            
            print("\nResponse preview:")
            print(f"---\n{reply[:200]}{'...' if len(reply) > 200 else ''}\n---")
            
            print(f"\nSources found: {len(sources)}")
            for idx, source in enumerate(sources[:3], 1):
                title = source.get("title", "Untitled")
                url = source.get("url", "No URL")
                score = source.get("score", 0)
                print(f"  {idx}. {title} (relevance: {score:.2f})")
                print(f"     {url}")
            
            if len(sources) > 3:
                print(f"  ... and {len(sources) - 3} more sources")
            
            return True
        else:
            print(f"❌ API returned status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing chat query: {str(e)}")
        return False

def check_dependencies():
    """Check if all required Python packages are installed."""
    print_header("Checking Python Dependencies")
    
    required_packages = [
        "fastapi", "uvicorn", "openai", "qdrant-client", 
        "python-dotenv", "requests", "tiktoken", "beautifulsoup4"
    ]
    
    missing = []
    installed = []
    
    for package in required_packages:
        try:
            __import__(package)
            installed.append(package)
        except ImportError:
            missing.append(package)
    
    if missing:
        print("❌ Missing Python packages:")
        for package in missing:
            print(f"  - {package}")
        print("\nInstall with: pip install -r requirements.txt")
        return False
    else:
        print("✅ All required Python packages are installed:")
        for package in installed:
            print(f"  - {package}")
        return True

def check_file_structure():
    """Check if all required files exist."""
    print_header("Checking File Structure")
    
    required_files = [
        "main.py",
        "ingest.py",
        "config.py",
        "requirements.txt",
        "service_descriptions.py",
        ".env"
    ]
    
    missing = []
    
    for file in required_files:
        if not os.path.exists(file):
            missing.append(file)
            print(f"❌ Missing: {file}")
        else:
            print(f"✅ Found: {file}")
    
    if missing:
        print("\n⚠️  Some required files are missing")
        return False
    
    return True

def test_specific_query(query, expected_content=None):
    """Test a specific query against the API and check for expected content."""
    print(f"\n>> Testing query: '{query}'")
    
    api_url = "http://localhost:8000/chat"
    
    try:
        response = requests.post(
            api_url,
            json={"message": query, "session_id": None},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            reply = result.get("reply", "")
            
            # If expected content is provided, check if it's in the reply
            if expected_content and any(content.lower() in reply.lower() for content in expected_content):
                print("✅ Query returned expected content")
            elif expected_content:
                print("⚠️  Query did not return expected content")
                print(f"Expected one of: {expected_content}")
                print(f"Got: {reply[:100]}...")
            else:
                print("✅ Query successful")
            
            return True
        else:
            print(f"❌ API returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def run_financial_services_test_suite():
    """Run a suite of tests specifically for financial services queries."""
    print_header("Financial Services Query Test Suite")
    
    test_queries = [
        {
            "query": "What are the key challenges in financial regulatory compliance?",
            "expected": ["Basel", "regulation", "compliance", "KYC", "AML"]
        },
        {
            "query": "How can banks modernize their core banking systems?",
            "expected": ["legacy", "modernization", "digital transformation", "core banking"]
        },
        {
            "query": "Explain model risk management for banks",
            "expected": ["model risk", "validation", "MRM", "regulatory", "framework"]
        },
        {
            "query": "What services do you offer for data analytics in finance?",
            "expected": ["analytics", "insights", "data", "dashboard", "reporting"]
        },
        {
            "query": "How can you help with digital banking transformation?",
            "expected": ["digital", "transformation", "customer experience", "modernization"]
        }
    ]
    
    results = []
    
    for test in test_queries:
        success = test_specific_query(test["query"], test["expected"])
        results.append(success)
        time.sleep(1)  # Small pause between queries
    
    success_rate = sum(results) / len(results) * 100
    print(f"\nTest suite completed with {success_rate:.0f}% success rate")

def main():
    """Run the debug script."""
    parser = argparse.ArgumentParser(description="Debug tool for Anaptyss Chatbot")
    parser.add_argument("--all", action="store_true", help="Run all checks")
    parser.add_argument("--env", action="store_true", help="Check environment variables")
    parser.add_argument("--openai", action="store_true", help="Test OpenAI API connection")
    parser.add_argument("--qdrant", action="store_true", help="Test Qdrant connection")
    parser.add_argument("--api", action="store_true", help="Test API server")
    parser.add_argument("--query", type=str, help="Test a specific chat query")
    parser.add_argument("--dependencies", action="store_true", help="Check Python dependencies")
    parser.add_argument("--files", action="store_true", help="Check file structure")
    parser.add_argument("--finance-tests", action="store_true", help="Run financial services test suite")
    
    args = parser.parse_args()
    
    # If no specific checks are requested, run all checks
    if not any(vars(args).values()):
        args.all = True
    
    results = {}
    
    if args.all or args.env:
        results["env"] = check_env_vars()
    
    if args.all or args.dependencies:
        results["dependencies"] = check_dependencies()
    
    if args.all or args.files:
        results["files"] = check_file_structure()
    
    if args.all or args.openai:
        results["openai"] = check_openai_connection()
    
    if args.all or args.qdrant:
        results["qdrant"] = check_qdrant_connection()
    
    if args.all or args.api:
        results["api"] = check_api_server()
    
    if args.query:
        results["query"] = test_chat_query(args.query)
    elif args.all:
        results["query"] = test_chat_query()
    
    if args.finance_tests:
        run_financial_services_test_suite()
    
    # Print summary
    if results:
        print_header("Debug Summary")
        
        all_passed = all(results.values())
        
        for check, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} - {check}")
        
        if all_passed:
            print("\n🎉 All checks passed! Your Anaptyss chatbot system is ready.")
        else:
            print("\n⚠️  Some checks failed. Please fix the issues above before continuing.")
            return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

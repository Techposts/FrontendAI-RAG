#!/usr/bin/env python3
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

def check_env_vars():
    """Check required environment variables."""
    required_vars = ["OPENAI_API_KEY", "QDRANT_URL", "SITE_URL"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        print("❌ Missing environment variables:")
        for var in missing:
            print(f"  - {var}")
        return False
    
    print("✅ All required environment variables found")
    return True

def check_openai_api():
    """Test OpenAI API connectivity."""
    from openai import OpenAI
    
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    
    try:
        models = client.models.list()
        print(f"✅ OpenAI API working, found {len(models.data)} models")
        return True
    except Exception as e:
        print(f"❌ OpenAI API error: {str(e)}")
        return False

def check_qdrant():
    """Test Qdrant connectivity."""
    from qdrant_client import QdrantClient
    
    qdrant_url = os.getenv("QDRANT_URL")
    try:
        client = QdrantClient(url=qdrant_url)
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]
        
        print(f"✅ Qdrant API working, found {len(collection_names)} collections:")
        for name in collection_names:
            print(f"  - {name}")
            
        if "anaptyss_content" in collection_names:
            print(f"✅ 'anaptyss_content' collection exists")
            # Check how many points are in the collection
            collection_info = client.get_collection("anaptyss_content")
            print(f"  - Contains {collection_info.points_count} vectors")
        else:
            print(f"❌ 'anaptyss_content' collection not found, need to run ingest.py")
            
        return True
    except Exception as e:
        print(f"❌ Qdrant API error: {str(e)}")
        return False

def check_wordpress_api():
    """Test WordPress API connectivity."""
    site_url = os.getenv("SITE_URL")
    
    try:
        resp = requests.get(f"{site_url}/wp-json", timeout=10)
        if resp.status_code == 200:
            print(f"✅ WordPress API at {site_url} is accessible")
            return True
        else:
            print(f"❌ WordPress API error: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ WordPress API error: {str(e)}")
        return False

def check_dependencies():
    """Check Python dependencies."""
    required_packages = [
        "fastapi", "uvicorn", "openai", "qdrant_client", 
        "python-dotenv", "requests", "tiktoken", "beautifulsoup4"
    ]
    
    try:
        import pkg_resources
        
        missing = []
        for package in required_packages:
            try:
                pkg_resources.get_distribution(package)
            except pkg_resources.DistributionNotFound:
                missing.append(package)
        
        if missing:
            print("❌ Missing Python packages:")
            for package in missing:
                print(f"  - {package}")
            print("\nInstall with: pip install -r requirements.txt")
            return False
        
        print("✅ All required Python packages installed")
        return True
    except Exception as e:
        print(f"❌ Error checking dependencies: {str(e)}")
        return False

def main():
    """Run all checks."""
    print("🔍 Checking Anaptyss Chat setup...\n")
    
    checks = [
        ("Environment Variables", check_env_vars),
        ("Python Dependencies", check_dependencies),
        ("OpenAI API", check_openai_api),
        ("Qdrant", check_qdrant),
        ("WordPress API", check_wordpress_api)
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n=== Checking {name} ===")
        result = check_func()
        results.append((name, result))
        print()
    
    # Summary
    print("\n=== Summary ===")
    all_passed = all(result for _, result in results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    if all_passed:
        print("\n🎉 All checks passed! Your setup is ready.")
        print("\nNext steps:")
        print("1. Run 'python ingest.py' to populate Qdrant with your content (if not already done)")
        print("2. Start the API with 'uvicorn main:app --reload'")
        return 0
    else:
        print("\n❌ Some checks failed. Please fix the issues above before continuing.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

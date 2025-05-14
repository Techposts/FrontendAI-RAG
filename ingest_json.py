#!/usr/bin/env python3
import requests
import tiktoken
import time
import uuid
import re
import json
import sys
from datetime import datetime
from bs4 import BeautifulSoup
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct
from config import OPENAI_API_KEY, QDRANT_URL, SITE_URL, SEARCH_CONFIG

# HTTP HEADERS
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# Sanity check WP REST API
print(f"▶︎ Testing SITE_URL: {SITE_URL}")
r_root = requests.get(f"{SITE_URL}/wp-json", headers=HEADERS)
print(f"  /wp-json → {r_root.status_code}")
r_test = requests.get(f"{SITE_URL}/wp-json/wp/v2/posts?per_page=1", headers=HEADERS)
print(f"  /wp-json/wp/v2/posts?per_page=1 → {r_test.status_code}, starts with:\n{r_test.text[:200]}\n")

# Init OpenAI & Qdrant clients
openai = OpenAI(api_key=OPENAI_API_KEY)
qdrant = QdrantClient(url=QDRANT_URL)

COLLECTION = "anaptyss_content"
existing = [c.name for c in qdrant.get_collections().collections]
if COLLECTION not in existing:
    # Using dictionary instead of VectorsConfig for better compatibility
    qdrant.create_collection(
        collection_name=COLLECTION,
        vectors_config={
            "size": 1536,
            "distance": "Cosine"
        }
    )
    print(f"Created Qdrant collection '{COLLECTION}'")
else:
    print(f"Qdrant collection '{COLLECTION}' already exists")

# Helper function to clean HTML content
def clean_html(html_content):
    if not html_content:
        return ""
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.extract()
    
    # Get text
    text = soup.get_text(separator=' ')
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

# Define all content types to fetch
CONTENT_TYPES = [
    {"type": "posts", "name": "Blog Post"},
    {"type": "pages", "name": "Page"},
    {"type": "success-stories", "name": "Case Study"},
    {"type": "white-paper", "name": "White Paper"},
    {"type": "webinars", "name": "Webinar"}
]

# Fetch WordPress content for all types
all_docs = []
for content_type in CONTENT_TYPES:
    pt = content_type["type"]
    type_name = content_type["name"]
    print(f"\nFetching content type: {type_name} ({pt})")
    
    page = 1
    items_count = 0
    while True:
        url = f"{SITE_URL}/wp-json/wp/v2/{pt}?per_page=100&page={page}"
        resp = requests.get(url, headers=HEADERS)
        
        if resp.status_code == 404:
            print(f"  → Content type {pt} not found on this WordPress site, skipping.")
            break
            
        # Modified HTTP status code handling - only stop on critical errors
        # Continue if we get a 400 error which typically means "end of pagination"
        if resp.status_code == 400:
            print(f"  → {pt} page {page} → HTTP 400, finished pagination.")
            break
            
        if resp.status_code != 200:
            print(f"  → {pt} page {page} → HTTP {resp.status_code}, error response: {resp.text[:200]}")
            break
            
        data = resp.json()
        if not data:
            print(f"  → {pt} page {page} → No data returned, finished.")
            break
            
        for item in data:
            html_content = item.get("content", {}).get("rendered", "")
            clean_text = clean_html(html_content)
            
            # Extract publication date
            try:
                pub_date = datetime.fromisoformat(item.get('date', '').replace('Z', '+00:00'))
            except (ValueError, TypeError):
                pub_date = datetime.now()
            
            # Get the title
            title = ""
            if isinstance(item.get("title"), dict):
                title = item.get("title", {}).get("rendered", "")
            elif isinstance(item.get("title"), str):
                title = item.get("title", "")
            
            # Extract categories and tags if available
            categories = item.get('categories', [])
            tags = item.get('tags', [])
            
            # Extract custom fields if available
            custom_fields = {}
            acf = item.get('acf', {})
            if acf:
                custom_fields = acf
            
            # Extract excerpt if available
            excerpt = ""
            if isinstance(item.get("excerpt"), dict):
                excerpt_html = item.get("excerpt", {}).get("rendered", "")
                excerpt = clean_html(excerpt_html)
            
            # Create a properly formatted ID that preserves content type
            # This ensures we don't lose content type information during embedding
            content_id = f"{pt}-{item['id']}"
            
            all_docs.append({
                "id": content_id,
                "title": title,
                "url": item.get("link", ""),
                "text": clean_text,
                "excerpt": excerpt,
                "published_date": pub_date.isoformat(),  # Store as ISO string consistently
                "categories": categories,
                "tags": tags,
                "content_type": pt,
                "content_type_name": type_name,
                "custom_fields": custom_fields
            })
            items_count += 1
            
        print(f"  → {pt} page {page} → HTTP 200, found {len(data)} items")
        page += 1
    
    print(f"  Fetched {items_count} {type_name} items")

print(f"\nFetched {len(all_docs)} total documents from WordPress.\n")

if not all_docs:
    print("No documents fetched. Please check your WordPress API endpoints.")
    sys.exit(1)

# Write out the document metadata to a JSON file for reference
with open("content_inventory.json", "w") as f:
    json.dump([{
        "id": doc["id"],
        "title": doc["title"],
        "url": doc["url"],
        "content_type": doc["content_type"],
        "content_type_name": doc["content_type_name"],
        "date": doc["published_date"]
    } for doc in all_docs], f, indent=2)

print(f"Content inventory written to content_inventory.json")

# Chunk & embed with progress logs
encoder = tiktoken.get_encoding("cl100k_base")
MAX_TOKENS = 500

def chunk_text(text: str):
    tokens = encoder.encode(text)
    for i in range(0, len(tokens), MAX_TOKENS):
        yield encoder.decode(tokens[i : i + MAX_TOKENS])

points = []
total_chunks = sum(len(list(chunk_text(doc["text"]))) for doc in all_docs)
print(f"Total chunks to embed: {total_chunks}\n")

counter = 0
for doc in all_docs:
    doc_chunks = list(chunk_text(doc["text"]))
    
    # Log the content type for each document being processed
    print(f"Processing {doc['content_type_name']}: {doc['title']} ({len(doc_chunks)} chunks)")
    
    for idx, chunk in enumerate(doc_chunks):
        counter += 1
        print(f"[{counter}/{total_chunks}] Embedding {doc['id']} chunk #{idx} …", end="", flush=True)
        
        # Add rate limiting to avoid OpenAI API rate limits
        if counter > 1 and counter % 50 == 0:
            print(" (rate limiting pause)")
            time.sleep(5)
        
        resp = openai.embeddings.create(
            input=chunk, 
            model=SEARCH_CONFIG['embedding_model']
        )
        vector = resp.data[0].embedding
        print(" done.")

        # Create a unique point ID that preserves content type information
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc['id']}-{idx}"))
        
        # Ensure the payload contains all relevant metadata 
        payload = {
            "doc_id": doc['id'],
            "title": doc['title'],
            "url": doc['url'],
            "chunk_index": idx,
            "text": chunk,
            "excerpt": doc.get('excerpt', ''),
            "published_date": doc['published_date'],
            "categories": doc['categories'],
            "tags": doc['tags'],
            "content_type": doc['content_type'],
            "content_type_name": doc['content_type_name'],
            "custom_fields": doc.get('custom_fields', {})
        }
        points.append(PointStruct(id=point_id, vector=vector, payload=payload))

# Upsert into Qdrant
print(f"\nUpserting {len(points)} points in batches…")
BATCH_SIZE = 64
for i in range(0, len(points), BATCH_SIZE):
    batch = points[i : i + BATCH_SIZE]
    qdrant.upsert(collection_name=COLLECTION, points=batch)
    print(f"  • Upserted points {i + 1}–{i + len(batch)}")

# Add summary of content types processed
content_type_summary = {}
for doc in all_docs:
    content_type = doc['content_type_name']
    if content_type in content_type_summary:
        content_type_summary[content_type] += 1
    else:
        content_type_summary[content_type] = 1

print("\nContent type summary:")
for content_type, count in content_type_summary.items():
    print(f"  • {content_type}: {count} items")

print("\n✅ Ingestion complete!")
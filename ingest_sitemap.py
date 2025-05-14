#!/usr/bin/env python3
import requests
import tiktoken
import time
import uuid
import re
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct
from config import OPENAI_API_KEY, QDRANT_URL, SITE_URL, SEARCH_CONFIG

# Namespaces for XML parsing
NAMESPACES = {
    'sitemap': 'http://www.sitemaps.org/schemas/sitemap/0.9',
    'news': 'http://www.google.com/schemas/sitemap-news/0.9'
}

# Sitemap URLs
SITEMAP_URLS = [
    f"{SITE_URL}/post-sitemap.xml",
    f"{SITE_URL}/page-sitemap.xml",
    f"{SITE_URL}/e-book-sitemap.xml",
    f"{SITE_URL}/news-room-sitemap.xml", 
    f"{SITE_URL}/success-stories-sitemap.xml",
    f"{SITE_URL}/webinars-sitemap.xml",
    f"{SITE_URL}/white-paper-sitemap.xml"
]

# HTTP HEADERS
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# Init OpenAI & Qdrant clients
openai = OpenAI(api_key=OPENAI_API_KEY)
qdrant = QdrantClient(url=QDRANT_URL)

COLLECTION = "anaptyss_content"
existing = [c.name for c in qdrant.get_collections().collections]
if COLLECTION not in existing:
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

# Function to extract comprehensive metadata
def extract_page_metadata(soup, url, content_type_slug, content_type_name):
    metadata = {
        'url': url,
        'content_type': content_type_slug,
        'content_type_name': content_type_name,
        'tags': [],
        'categories': [],
        'excerpt': '',
        'publication_date': datetime.now().isoformat(),
        'last_modified': datetime.now().isoformat(),
        'author': '',
        'keywords': []
    }

    try:
        # Title extraction
        title_elem = soup.find('h1')
        metadata['title'] = title_elem.get_text(strip=True) if title_elem else url.split('/')[-1]

        # Excerpt extraction
        excerpt_elem = soup.find(['div', 'p'], class_=['excerpt', 'post-excerpt'])
        if excerpt_elem:
            metadata['excerpt'] = clean_html(str(excerpt_elem))

        # Publication date
        date_elem = soup.find(['time', 'span'], class_=['published', 'post-date'])
        if date_elem and date_elem.get('datetime'):
            try:
                metadata['publication_date'] = datetime.fromisoformat(date_elem['datetime']).isoformat()
            except:
                pass

        # Author extraction
        author_elem = soup.find(['span', 'a'], class_=['author', 'post-author'])
        if author_elem:
            metadata['author'] = author_elem.get_text(strip=True)

        # Tags extraction (for blog posts and similar content)
        tag_elems = soup.find_all(['a', 'span'], class_=['tag', 'post-tag'])
        metadata['tags'] = [tag.get_text(strip=True) for tag in tag_elems]

        # Categories extraction
        category_elems = soup.find_all(['a', 'span'], class_=['category', 'post-category'])
        metadata['categories'] = [cat.get_text(strip=True) for cat in category_elems]

        # Keywords extraction from meta tags
        keywords_meta = soup.find('meta', attrs={'name': 'keywords'})
        if keywords_meta:
            metadata['keywords'] = [kw.strip() for kw in keywords_meta.get('content', '').split(',')]

    except Exception as e:
        print(f"Metadata extraction error for {url}: {e}")

    return metadata

# Function to extract content type from URL
def extract_content_type(url):
    # Map URL segments to content types
    type_mapping = {
        'post-sitemap.xml': ('posts', 'Blog Post'),
        'page-sitemap.xml': ('pages', 'Page'),
        'e-book-sitemap.xml': ('e-books', 'E-book'),
        'news-room-sitemap.xml': ('news', 'News'),
        'success-stories-sitemap.xml': ('success-stories', 'Case Study'),
        'webinars-sitemap.xml': ('webinars', 'Webinar'),
        'white-paper-sitemap.xml': ('white-paper', 'White Paper')
    }
    
    for key, (type_slug, type_name) in type_mapping.items():
        if key in url:
            return type_slug, type_name
    
    return 'unknown', 'Unknown'

# Function to parse sitemap XML and extract URLs
def parse_sitemap(sitemap_url):
    try:
        response = requests.get(sitemap_url, headers=HEADERS)
        response.raise_for_status()
        
        # Determine content type based on sitemap URL
        content_type_slug, content_type_name = extract_content_type(sitemap_url)
        
        # Parse XML
        root = ET.fromstring(response.content)
        
        # Collect URLs
        urls = []
        for url_elem in root.findall('.//sitemap:url', NAMESPACES):
            loc_elem = url_elem.find('sitemap:loc', NAMESPACES)
            if loc_elem is not None:
                url = loc_elem.text
                
                # Try to extract date
                lastmod_elem = url_elem.find('sitemap:lastmod', NAMESPACES)
                last_modified = lastmod_elem.text if lastmod_elem is not None else datetime.now().isoformat()
                
                urls.append({
                    'url': url,
                    'last_modified': last_modified,
                    'content_type_slug': content_type_slug,
                    'content_type_name': content_type_name
                })
        
        return urls
    except Exception as e:
        print(f"Error parsing sitemap {sitemap_url}: {e}")
        return []

# Chunk & embed function
encoder = tiktoken.get_encoding("cl100k_base")
MAX_TOKENS = 500

def chunk_text(text: str):
    tokens = encoder.encode(text)
    for i in range(0, len(tokens), MAX_TOKENS):
        yield encoder.decode(tokens[i : i + MAX_TOKENS])

# Main ingestion function
def ingest_content():
    all_urls = []
    for sitemap_url in SITEMAP_URLS:
        all_urls.extend(parse_sitemap(sitemap_url))
    
    print(f"Total URLs found: {len(all_urls)}")
    
    points = []
    total_chunks = 0
    processed_urls = 0
    
    for url_info in all_urls:
        try:
            # Fetch the page content
            resp = requests.get(url_info['url'], headers=HEADERS)
            
            if resp.status_code != 200:
                print(f"Skipping {url_info['url']} - HTTP {resp.status_code}")
                continue
            
            # Parse the HTML
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Extract metadata
            metadata = extract_page_metadata(
                soup, 
                url_info['url'], 
                url_info['content_type_slug'], 
                url_info['content_type_name']
            )
            
            # Extract main content (adjust selectors as needed)
            content_elem = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
            
            if not content_elem:
                print(f"No content found for {url_info['url']}")
                continue
            
            # Clean the text
            text = clean_html(str(content_elem))
            
            # Chunk the text
            chunks = list(chunk_text(text))
            total_chunks += len(chunks)
            
            print(f"Processing {metadata['content_type_name']}: {metadata['title']} ({len(chunks)} chunks)")
            
            # Embed chunks
            for idx, chunk in enumerate(chunks):
                # Rate limiting
                if processed_urls > 0 and processed_urls % 50 == 0:
                    time.sleep(5)
                
                # Generate embedding
                resp = openai.embeddings.create(
                    input=chunk, 
                    model=SEARCH_CONFIG['embedding_model']
                )
                vector = resp.data[0].embedding
                
                # Create unique point ID
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url_info['url']}-{idx}"))
                
                # Prepare payload with comprehensive metadata
                payload = {
                    **metadata,  # Include all extracted metadata
                    "text": chunk,
                    "chunk_index": idx
                }
                
                points.append(PointStruct(id=point_id, vector=vector, payload=payload))
            
            processed_urls += 1
            
        except Exception as e:
            print(f"Error processing {url_info['url']}: {e}")
    
    # Upsert into Qdrant
    print(f"\nUpserting {len(points)} points in batches…")
    BATCH_SIZE = 64
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        qdrant.upsert(collection_name=COLLECTION, points=batch)
        print(f"  • Upserted points {i + 1}–{i + len(batch)}")
    
    # Content type summary
    content_type_summary = {}
    for point in points:
        content_type = point.payload.get('content_type_name', 'Unknown')
        content_type_summary[content_type] = content_type_summary.get(content_type, 0) + 1
    
    print("\nContent type summary:")
    for content_type, count in content_type_summary.items():
        print(f"  • {content_type}: {count} items")
    
    print("\n✅ Ingestion complete!")

# Run the ingestion
if __name__ == "__main__":
    ingest_content()
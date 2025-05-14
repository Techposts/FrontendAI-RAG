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
from qdrant_client.http import models as rest_models
from qdrant_client.http.models import PointStruct  # Add this import
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

# Collection configuration
COLLECTION = "anaptyss_enhanced_content"
VECTOR_CONFIG = {
    "size": 1536,
    "distance": "Cosine"
}

# Initialize clients
openai = OpenAI(api_key=OPENAI_API_KEY)
qdrant = QdrantClient(url=QDRANT_URL)

# Check and create collection
def ensure_collection_exists():
    """Ensure the Qdrant collection exists."""
    existing_collections = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION not in existing_collections:
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=rest_models.VectorParams(
                size=VECTOR_CONFIG["size"], 
                distance=rest_models.Distance.COSINE
            )
        )
        print(f"Created Qdrant collection '{COLLECTION}'")
        
        # Create payload schema for more structured indexing
        qdrant.create_payload_index(
            collection_name=COLLECTION,
            field_name="content_type",
            field_schema=rest_models.PayloadSchemaType.KEYWORD
        )
        qdrant.create_payload_index(
            collection_name=COLLECTION,
            field_name="content_type_name",
            field_schema=rest_models.PayloadSchemaType.KEYWORD
        )
        qdrant.create_payload_index(
            collection_name=COLLECTION,
            field_name="publication_date",
            field_schema=rest_models.PayloadSchemaType.DATETIME
        )
    else:
        print(f"Qdrant collection '{COLLECTION}' already exists")

# Helper function to clean HTML content
def clean_html(html_content):
    """Clean HTML content and extract main text."""
    if not html_content:
        return ""
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script, style, and other non-content elements
    for script in soup(["script", "style", "head", "header", "footer", "nav"]):
        script.decompose()
    
    # Try to find main content areas
    content_areas = [
        soup.find('main'),
        soup.find('article'),
        soup.find('div', class_=['content', 'entry-content']),
        soup.body
    ]
    
    # Select first non-None content area
    main_content = next((area for area in content_areas if area), soup)
    
    # Get text
    text = main_content.get_text(separator=' ', strip=True)
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

# Function to extract comprehensive metadata
def extract_page_metadata(soup, url, content_type_slug, content_type_name):
    """Extract comprehensive metadata from the page."""
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
        # Title extraction - prioritize h1 and og:title
        title_elem = soup.find('h1')
        og_title = soup.find('meta', property='og:title')
        metadata['title'] = (
            title_elem.get_text(strip=True) if title_elem 
            else (og_title['content'] if og_title else url.split('/')[-1])
        )

        # Excerpt extraction from meta description or first paragraph
        desc_meta = soup.find('meta', attrs={'name': 'description'})
        if desc_meta:
            metadata['excerpt'] = desc_meta.get('content', '')

        # Publication date extraction
        date_sources = [
            soup.find('meta', property='article:published_time'),
            soup.find('meta', attrs={'name': 'publication_date'}),
            soup.find('time', class_=['published', 'post-date']),
            soup.find('span', class_=['date', 'published'])
        ]
        
        for date_source in date_sources:
            if date_source:
                try:
                    date_str = date_source.get('datetime', date_source.get('content', date_source.get_text(strip=True)))
                    parsed_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    metadata['publication_date'] = parsed_date.isoformat()
                    break
                except Exception:
                    continue

        # Last modified date
        last_mod_meta = soup.find('meta', property='article:modified_time')
        if last_mod_meta:
            try:
                metadata['last_modified'] = datetime.fromisoformat(
                    last_mod_meta['content'].replace('Z', '+00:00')
                ).isoformat()
            except:
                pass

        # Author extraction
        author_sources = [
            soup.find('meta', property='author'),
            soup.find('meta', attrs={'name': 'author'}),
            soup.find(['span', 'a'], class_=['author', 'post-author'])
        ]
        
        for author_source in author_sources:
            if author_source:
                metadata['author'] = author_source.get_text(strip=True) if hasattr(author_source, 'get_text') else author_source.get('content', '')
                break

        # Tags and categories extraction
        tag_sources = soup.find_all(['a', 'span'], class_=['tag', 'post-tag', 'category', 'post-category'])
        metadata['tags'] = [tag.get_text(strip=True) for tag in tag_sources if 'tag' in tag.get('class', [])]
        metadata['categories'] = [cat.get_text(strip=True) for cat in tag_sources if 'category' in cat.get('class', [])]

        # Keywords extraction from meta tags
        keywords_meta = soup.find('meta', attrs={'name': 'keywords'})
        if keywords_meta:
            metadata['keywords'] = [kw.strip() for kw in keywords_meta.get('content', '').split(',')]

    except Exception as e:
        print(f"Metadata extraction error for {url}: {e}")

    return metadata

# Function to parse sitemap XML and extract URLs
def parse_sitemap(sitemap_url):
    """Parse a single sitemap XML and return list of URLs."""
    try:
        response = requests.get(sitemap_url, headers=HEADERS)
        response.raise_for_status()
        
        # Determine content type based on sitemap URL
        content_type_mapping = {
            'post-sitemap.xml': ('posts', 'Blog Post'),
            'page-sitemap.xml': ('pages', 'Page'),
            'e-book-sitemap.xml': ('e-books', 'E-book'),
            'news-room-sitemap.xml': ('news', 'News'),
            'success-stories-sitemap.xml': ('success-stories', 'Case Study'),
            'webinars-sitemap.xml': ('webinars', 'Webinar'),
            'white-paper-sitemap.xml': ('white-paper', 'White Paper')
        }
        
        sitemap_filename = sitemap_url.split('/')[-1]
        content_type_slug, content_type_name = content_type_mapping.get(
            sitemap_filename, 
            ('unknown', 'Unknown')
        )
        
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
    """Chunk text into tokens."""
    tokens = encoder.encode(text)
    for i in range(0, len(tokens), MAX_TOKENS):
        yield encoder.decode(tokens[i : i + MAX_TOKENS])

# Main ingestion function
def ingest_content():
    """Main content ingestion function."""
    # Ensure collection exists
    ensure_collection_exists()
    
    # Collect all URLs from sitemaps
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
            
            # Extract main content 
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
    
    # Write out the document metadata to a JSON file for reference
    metadata_output = []
    for point in points:
        metadata_output.append({
            "id": point.payload.get('url', ''),
            "title": point.payload.get('title', ''),
            "url": point.payload.get('url', ''),
            "content_type": point.payload.get('content_type', ''),
            "content_type_name": point.payload.get('content_type_name', ''),
            "date": point.payload.get('publication_date', '')
        })
    
    with open("content_inventory.json", "w") as f:
        json.dump(metadata_output, f, indent=2)
    
    print("\n✅ Ingestion complete!")

# Run the ingestion
if __name__ == "__main__":
    ingest_content()
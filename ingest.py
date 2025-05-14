#!/usr/bin/env python3
import requests
import tiktoken
import time
import uuid
import re
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct
from config import OPENAI_API_KEY, QDRANT_URL, SITE_URL
from urllib.parse import urljoin

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 300
MAX_TOKENS = 2000

class ContentProcessor:
    def __init__(self):
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))
    
    def preprocess_text(self, text: str) -> str:
        """Enhanced text preprocessing."""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Standardize quotes and dashes
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace('–', '-').replace('—', '-')
        
        # Remove URLs but keep link text
        text = re.sub(r'http[s]?://\S+[\w]', '', text)
        
        # Remove email addresses
        text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', text)
        
        return text
    
    def create_chunks(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create semantic chunks of text with metadata."""
        chunks = []
        
        # Preprocess text
        text = self.preprocess_text(text)
        
        # Split into semantic units (paragraphs)
        paragraphs = text.split('\n\n')
        
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para)
            para_tokens = self.count_tokens(para)
            
            # If this paragraph alone exceeds chunk size, split it into sentences
            if para_tokens > MAX_TOKENS:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sentence in sentences:
                    sentence_tokens = self.count_tokens(sentence)
                    if current_size + sentence_tokens > MAX_TOKENS:
                        if current_chunk:
                            chunk_text = ' '.join(current_chunk)
                            chunk_data = {
                                "text": chunk_text,
                                "metadata": {**metadata},
                                "token_count": self.count_tokens(chunk_text)
                            }
                            chunks.append(chunk_data)
                        current_chunk = [sentence]
                        current_size = sentence_tokens
                    else:
                        current_chunk.append(sentence)
                        current_size += sentence_tokens
            
            # If adding this paragraph exceeds chunk size
            elif current_size + para_tokens > MAX_TOKENS:
                if current_chunk:
                    chunk_text = ' '.join(current_chunk)
                    chunk_data = {
                        "text": chunk_text,
                        "metadata": {**metadata},
                        "token_count": self.count_tokens(chunk_text)
                    }
                    chunks.append(chunk_data)
                current_chunk = [para]
                current_size = para_tokens
            else:
                current_chunk.append(para)
                current_size += para_tokens
        
        # Add the last chunk if it exists
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunk_data = {
                "text": chunk_text,
                "metadata": {**metadata},
                "token_count": self.count_tokens(chunk_text)
            }
            chunks.append(chunk_data)
        
        return chunks

def clean_html(html_content: str) -> str:
    """Enhanced HTML cleaning with better structure preservation."""
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove unwanted elements
    for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'form']):
        element.decompose()
    
    # Process text with structure preservation
    blocks = []
    
    # Handle headings
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        level = int(heading.name[1])
        text = heading.get_text().strip()
        if text:
            blocks.append(('#' * level) + ' ' + text)
    
    # Handle lists
    for list_tag in soup.find_all(['ul', 'ol']):
        for item in list_tag.find_all('li'):
            text = item.get_text().strip()
            if text:
                blocks.append('- ' + text)
    
    # Handle paragraphs and other text blocks
    for p in soup.find_all(['p', 'div']):
        text = p.get_text().strip()
        if text:
            blocks.append(text)
    
    # Handle tables
    for table in soup.find_all('table'):
        blocks.append('Table content:')
        for row in table.find_all('tr'):
            cells = [cell.get_text().strip() for cell in row.find_all(['td', 'th'])]
            blocks.append(' | '.join(cells))
    
    # Join blocks with appropriate spacing
    return '\n\n'.join(blocks)

def extract_metadata(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """Extract metadata from the page."""
    metadata = {
        'url': url,
        'title': '',
        'content_type': 'article',
        'industries': [],
        'topics': [],
        'categories': [],
        'tags': [],
        'date': '',
        'author': 'Unknown'
    }
    
    # Extract title
    title_tag = soup.find('title')
    if title_tag:
        metadata['title'] = title_tag.text.strip()
    
    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        metadata['description'] = meta_desc.get('content', '')
    
    # Extract date
    date_tag = soup.find('time')
    if date_tag:
        metadata['date'] = date_tag.get('datetime', '')
    
    # Extract author
    author_tag = soup.find('a', class_='author')
    if author_tag:
        metadata['author'] = author_tag.text.strip()
    
    # Extract categories and tags
    category_links = soup.find_all('a', class_='category')
    if category_links:
        metadata['categories'] = [cat.text.strip() for cat in category_links]
    
    tag_links = soup.find_all('a', class_='tag')
    if tag_links:
        metadata['tags'] = [tag.text.strip() for tag in tag_links]
    
    # Determine content type
    if any(term in url.lower() for term in ['/case-study', '/case-studies']):
        metadata['content_type'] = 'case_study'
    elif any(term in url.lower() for term in ['/whitepaper', '/white-paper']):
        metadata['content_type'] = 'whitepaper'
    elif any(term in url.lower() for term in ['/blog', '/news']):
        metadata['content_type'] = 'blog'
    
    # Extract industries and topics from content
    content_text = soup.get_text().lower()
    
    industries = {
        "finance": ["banking", "finance", "investment", "insurance", "wealth management"],
        "healthcare": ["health", "medical", "healthcare", "hospital"],
        "technology": ["tech", "software", "digital", "IT"],
        "manufacturing": ["manufacturing", "industrial", "production"],
        "retail": ["retail", "ecommerce", "commerce"],
        "energy": ["energy", "utilities", "power"]
    }
    
    for industry, keywords in industries.items():
        if any(keyword in content_text for keyword in keywords):
            metadata['industries'].append(industry)
    
    topics = {
        "digital_transformation": ["digital transformation", "digitalization", "modernization"],
        "operations": ["operations", "workflow", "process improvement"],
        "analytics": ["analytics", "data", "insights", "intelligence"],
        "security": ["security", "compliance", "risk"],
        "cloud": ["cloud", "aws", "azure", "digital infrastructure"],
        "ai_ml": ["ai", "machine learning", "artificial intelligence", "automation"]
    }
    
    for topic, keywords in topics.items():
        if any(keyword in content_text for keyword in keywords):
            metadata['topics'].append(topic)
    
    return metadata

def fetch_site_urls() -> List[str]:
    """Fetch URLs from specific sitemaps."""
    logger.info("Starting URL discovery from sitemaps...")
    
    sitemap_urls = [
        "https://www.anaptyss.com/post-sitemap.xml",
        "https://www.anaptyss.com/page-sitemap.xml",
        "https://www.anaptyss.com/e-book-sitemap.xml",
        "https://www.anaptyss.com/news-room-sitemap.xml",
        "https://www.anaptyss.com/success-stories-sitemap.xml",
        "https://www.anaptyss.com/webinars-sitemap.xml",
        "https://www.anaptyss.com/white-paper-sitemap.xml",
        "https://www.anaptyss.com/category-sitemap.xml"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/xml,application/xml,application/xhtml+xml,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.anaptyss.com/",
        "Connection": "keep-alive",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1"
    }
    
    all_urls = set()
    
    for sitemap_url in sitemap_urls:
        logger.info(f"Processing sitemap: {sitemap_url}")
        try:
            response = requests.get(sitemap_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Parse XML
            root = ET.fromstring(response.content)
            
            # Extract URLs from sitemap
            # Handle both standard sitemap format and WordPress sitemap format
            urls = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            if not urls:  # Try WordPress format
                urls = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            
            for url in urls:
                url_text = url.text.strip()
                # Skip category sitemap URLs as they're not content pages
                if not url_text.endswith('-sitemap.xml'):
                    all_urls.add(url_text)
            
            logger.info(f"Found {len(urls)} URLs in {sitemap_url}")
            
        except Exception as e:
            logger.error(f"Error processing sitemap {sitemap_url}: {str(e)}")
            continue
    
    logger.info(f"URL discovery complete. Found {len(all_urls)} unique URLs")
    return list(all_urls)

def fetch_page_content(url: str) -> Dict[str, Any]:
    """Fetch and process content from a single page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract metadata
        metadata = extract_metadata(soup, url)
        
        # Get main content
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
        if main_content:
            content = clean_html(str(main_content))
        else:
            content = clean_html(response.text)
        
        return {
            'url': url,
            'title': metadata['title'],
            'content': content,
            'content_type': metadata['content_type'],
            'industries': metadata['industries'],
            'topics': metadata['topics'],
            'categories': metadata['categories'],
            'tags': metadata['tags'],
            'date': metadata['date'],
            'author': metadata['author'],
            'importance': 1.0
        }
        
    except Exception as e:
        logger.error(f"Error fetching page {url}: {str(e)}")
        return None

def main():
    logger.info("Starting content ingestion process...")
    
    # Initialize clients
    logger.info("Initializing OpenAI and Qdrant clients...")
    openai = OpenAI(api_key=OPENAI_API_KEY)
    qdrant = QdrantClient(url=QDRANT_URL)
    processor = ContentProcessor()
    
    # Ensure collection exists
    COLLECTION = "anaptyss_content"
    collections = [c.name for c in qdrant.get_collections().collections]
    
    if COLLECTION not in collections:
        logger.info(f"Creating new collection '{COLLECTION}'")
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config={
                "size": 1536,
                "distance": "Cosine"
            }
        )
    else:
        logger.info(f"Using existing collection '{COLLECTION}'")
    
    # Fetch URLs by scraping
    urls = fetch_site_urls()
    if not urls:
        logger.error("No URLs found. Exiting.")
        return
    
    # Process and upload content
    points = []
    total_items = 0
    total_chunks = 0
    total_uploads = 0
    
    for idx, url in enumerate(urls, 1):
        logger.info(f"Processing page {idx}/{len(urls)}: {url}")
        
        # Fetch and process page content
        content_data = fetch_page_content(url)
        if not content_data:
            continue
        
        # Skip pages with too little content
        if len(content_data['content'].split()) < 50:  # Skip pages with less than 50 words
            logger.info(f"Skipping page with insufficient content: {url}")
            continue
        
        # Create chunks with metadata
        chunks = processor.create_chunks(
            text=f"{content_data['title']}\n\n{content_data['content']}",
            metadata={
                'title': content_data['title'],
                'url': content_data['url'],
                'content_type': content_data['content_type'],
                'categories': content_data['categories'],
                'tags': content_data['tags'],
                'date': content_data['date'],
                'author': content_data['author'],
                'importance': content_data['importance']
            }
        )
        
        logger.info(f"Created {len(chunks)} chunks for page {idx}")
        
        for chunk_idx, chunk in enumerate(chunks, 1):
            if chunk['token_count'] > MAX_TOKENS:
                logger.warning(f"Skipping chunk {chunk_idx} (too many tokens: {chunk['token_count']})")
                continue
                
            try:
                # Get embedding with retry logic
                max_retries = 3
                retry_count = 0
                while retry_count < max_retries:
                    try:
                        logger.debug(f"Generating embedding for chunk {chunk_idx}")
                        response = openai.embeddings.create(
                            input=chunk['text'],
                            model="text-embedding-ada-002"
                        )
                        embedding = response.data[0].embedding
                        break
                    except Exception as e:
                        retry_count += 1
                        if retry_count == max_retries:
                            raise e
                        logger.warning(f"Retry {retry_count} for embedding generation...")
                        time.sleep(2 ** retry_count)
                
                # Create point
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={
                        'text': chunk['text'],
                        **chunk['metadata']
                    }
                )
                points.append(point)
                total_chunks += 1
                
                # Upload in batches of 100
                if len(points) >= 100:
                    logger.info(f"Uploading batch of {len(points)} chunks...")
                    qdrant.upsert(
                        collection_name=COLLECTION,
                        points=points
                    )
                    total_uploads += len(points)
                    logger.info(f"Successfully uploaded {total_uploads} chunks so far")
                    points = []
                
            except Exception as e:
                logger.error(f"Error processing chunk {chunk_idx} of page {idx}: {str(e)}")
                continue
            
        total_items += 1
        if idx % 5 == 0:
            logger.info(f"Progress: {idx}/{len(urls)} pages processed ({(idx/len(urls)*100):.1f}%)")
    
    # Upload remaining points
    if points:
        logger.info(f"Uploading final batch of {len(points)} chunks...")
        qdrant.upsert(
            collection_name=COLLECTION,
            points=points
        )
        total_uploads += len(points)
    
    logger.info(f"\nIngestion complete!")
    logger.info(f"Total pages processed: {total_items}")
    logger.info(f"Total chunks created: {total_chunks}")
    logger.info(f"Total chunks uploaded: {total_uploads}")

if __name__ == "__main__":
    main()

import os
import sys
import uuid
import shutil
import logging
from typing import List, Dict, Any, Optional

import PyPDF2
import docx
import pandas as pd
import magic  # for mime type detection

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

# Import configuration 
from config import OPENAI_API_KEY, QDRANT_URL

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DocumentStorageConfig:
    """Configuration for document storage and management"""
    # Base directory for document storage
    BASE_STORAGE_DIR = "/root/anaptyss-chatbot-backend/document_repository"
    
    # Expanded document types to include all Anaptyss content types
    DOCUMENT_TYPES = {
        "whitepapers": "whitepapers",
        "reports": "reports",
        "compliance_docs": "compliance",
        "product_specs": "product_specifications",
        "case_studies": "case_studies",
        "webinars": "webinars",
        "internal_docs": "internal"
    }
    
    # Mapping WordPress post types to document types
    WP_TO_DOCUMENT_TYPE = {
        "white-paper": "whitepapers",
        "success-stories": "case_studies", 
        "webinars": "webinars",
        "posts": "reports",
        "pages": "internal_docs"
    }
def import_from_wordpress(self, content_inventory_path):
    """
    Import WordPress content from content inventory JSON file
    This complements the ingest.py script
    """
    import json
    import os
    
    try:
        with open(content_inventory_path, 'r') as file:
            inventory = json.load(file)
            
        imported_count = 0
        for item in inventory:
            # Map WordPress content type to document type
            wp_type = item.get('content_type')
            doc_type = DocumentStorageConfig.WP_TO_DOCUMENT_TYPE.get(
                wp_type, "internal_docs"  # Default to internal docs
            )
            
            # Store metadata about the WordPress content
            metadata = {
                "original_filename": f"{item.get('title')}.txt",
                "wp_id": item.get('id'),
                "wp_url": item.get('url'),
                "wp_type": wp_type,
                "wp_type_name": item.get('content_type_name'),
                "published_date": item.get('date')
            }
            
            # Create a simple text representation if needed
            # (Only needed if you want to create actual files in the filesystem)
            # This is mostly for tracking purposes as the content is in Qdrant
            tracking_dir = os.path.join(
                DocumentStorageConfig.BASE_STORAGE_DIR, 
                "wp_inventory"
            )
            os.makedirs(tracking_dir, exist_ok=True)
            tracking_file = os.path.join(tracking_dir, f"{item.get('id')}.json")
            
            with open(tracking_file, 'w') as f:
                json.dump(item, f, indent=2)
            
            # Update Qdrant metadata if needed
            # The Qdrant integration is already handled by ingest.py
            
            imported_count += 1
            self.logger.info(f"Imported WP content: {item.get('title')} [{wp_type}]")
            
        return imported_count
    
    except Exception as e:
        self.logger.error(f"Error importing WordPress content: {e}")
        return 0

# Add this method to DocumentManager class
def search_by_content_type(
    self, 
    query: str, 
    content_types: List[str] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Search documents of specific content types
    """
    # Generate query embedding
    try:
        query_embedding = self.openai_client.embeddings.create(
            input=query,
            model=self.embedding_model
        ).data[0].embedding
    except Exception as e:
        self.logger.error(f"Query embedding failed: {e}")
        return []
    
    # Prepare Qdrant filter for content types if specified
    filter_obj = None
    if content_types and len(content_types) > 0:
        filter_obj = Filter(
            must=[
                FieldCondition(
                    key="content_type_name",
                    match=MatchAny(any=content_types)
                )
            ]
        )
    
    # Perform search
    try:
        search_results = self.qdrant_client.search(
            collection_name="anaptyss_content",  # Use the WordPress collection
            query_vector=query_embedding,
            limit=limit,
            with_payload=True,
            filter=filter_obj
        )
        
        # Process and enrich results
        results = []
        for hit in search_results:
            result = {
                "document_id": hit.id,
                "score": hit.score,
                "payload": hit.payload
            }
            results.append(result)
        
        return results
    
    except Exception as e:
        self.logger.error(f"Content type search failed: {e}")
        return []
        
class DocumentManager:
    """
    Manages document storage, embedding, and semantic search
    Supports multiple document types and provides advanced search capabilities
    """
    def __init__(
        self, 
        qdrant_url: str = QDRANT_URL, 
        openai_api_key: str = OPENAI_API_KEY, 
        collection_name: str = "anaptyss_enterprise_documents",
        embedding_model: str = "text-embedding-ada-002"
    ):
        # Initialize clients
        self.qdrant_client = QdrantClient(url=qdrant_url)
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.embedding_model = embedding_model
        self.collection_name = collection_name
        
        # Setup logging
        self.logger = logger
        
        # Ensure storage directories exist
        self._setup_storage_directories()
    
    def _setup_storage_directories(self):
        """Create base and document type directories"""
        base_dir = DocumentStorageConfig.BASE_STORAGE_DIR
        os.makedirs(base_dir, exist_ok=True)
        
        for doc_type in DocumentStorageConfig.DOCUMENT_TYPES.values():
            os.makedirs(os.path.join(base_dir, doc_type), exist_ok=True)
    
    def _extract_text_from_document(self, file_path: str) -> str:
        """
        Extract text from various document types
        Supports: PDF, DOCX, TXT, CSV
        """
        # Detect mime type
        mime = magic.Magic(mime=True)
        file_mime_type = mime.from_file(file_path)
        
        try:
            if file_mime_type == 'application/pdf':
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    text = " ".join([page.extract_text() for page in reader.pages])
            
            elif file_mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                doc = docx.Document(file_path)
                text = " ".join([para.text for para in doc.paragraphs])
            
            elif file_mime_type == 'text/plain':
                with open(file_path, 'r', encoding='utf-8') as file:
                    text = file.read()
            
            elif file_mime_type in ['text/csv', 'application/vnd.ms-excel']:
                df = pd.read_csv(file_path)
                text = " ".join(df.apply(lambda row: " ".join(row.astype(str)), axis=1))
            
            else:
                self.logger.warning(f"Unsupported file type: {file_mime_type}")
                return ""
            
            return text.strip()
        
        except Exception as e:
            self.logger.error(f"Error extracting text from {file_path}: {e}")
            return ""
    
    def store_document(
        self, 
        file_path: str, 
        doc_type: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Store document in local filesystem and Qdrant vector database
        """
        # Validate document type
        if doc_type not in DocumentStorageConfig.DOCUMENT_TYPES:
            raise ValueError(f"Invalid document type: {doc_type}")
        
        # Generate unique document ID
        doc_id = str(uuid.uuid4())
        
        # Extract text content
        text_content = self._extract_text_from_document(file_path)
        
        # Generate embedding
        try:
            embedding_response = self.openai_client.embeddings.create(
                input=text_content,
                model=self.embedding_model
            )
            embedding = embedding_response.data[0].embedding
        except Exception as e:
            self.logger.error(f"Embedding generation failed: {e}")
            embedding = [0.0] * 1536  # Default zero embedding
        
        # Determine storage path
        filename = f"{doc_id}_{os.path.basename(file_path)}"
        storage_dir = os.path.join(
            DocumentStorageConfig.BASE_STORAGE_DIR, 
            DocumentStorageConfig.DOCUMENT_TYPES[doc_type]
        )
        
        # Copy file to storage location
        dest_path = os.path.join(storage_dir, filename)
        shutil.copy2(file_path, dest_path)
        
        # Prepare metadata
        default_metadata = {
            "document_id": doc_id,
            "original_filename": os.path.basename(file_path),
            "document_type": doc_type,
            "storage_path": dest_path,
            "extracted_text_length": len(text_content)
        }
        metadata = {**default_metadata, **(metadata or {})}
        
        # Store in Qdrant
        try:
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=doc_id,
                        vector=embedding,
                        payload={
                            "text": text_content,
                            **metadata
                        }
                    )
                ]
            )
        except Exception as e:
            self.logger.error(f"Qdrant storage failed: {e}")
        
        return {
            "document_id": doc_id,
            "storage_path": dest_path,
            "metadata": metadata
        }
    
    def process_directory(
        self, 
        directory_path: str, 
        doc_type: str
    ) -> List[Dict[str, Any]]:
        """
        Process all documents in a given directory
        """
        processed_docs = []
        
        # Ensure directory exists
        if not os.path.exists(directory_path):
            self.logger.error(f"Directory not found: {directory_path}")
            return processed_docs
        
        # Iterate through files
        for filename in os.listdir(directory_path):
            file_path = os.path.join(directory_path, filename)
            
            # Skip directories and hidden files
            if os.path.isfile(file_path) and not filename.startswith('.'):
                try:
                    # Store the document
                    result = self.store_document(
                        file_path=file_path,
                        doc_type=doc_type,
                        metadata={
                            "original_filename": filename
                        }
                    )
                    processed_docs.append(result)
                    self.logger.info(f"Processed: {filename} - ID: {result['document_id']}")
                except Exception as e:
                    self.logger.error(f"Error processing {filename}: {e}")
        
        return processed_docs
    
    def search_documents(
        self, 
        query: str, 
        limit: int = 5, 
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search across stored documents with optional filtering
        """
        # Generate query embedding
        try:
            query_embedding = self.openai_client.embeddings.create(
                input=query,
                model=self.embedding_model
            ).data[0].embedding
        except Exception as e:
            self.logger.error(f"Query embedding failed: {e}")
            return []
        
        # Prepare Qdrant filter if filters are provided
        qdrant_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value)
                    )
                )
            qdrant_filter = Filter(must=conditions)
        
        # Perform search
        try:
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                with_payload=True,
                filter=qdrant_filter
            )
            
            # Process and enrich results
            results = []
            for hit in search_results:
                result = {
                    "document_id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload
                }
                results.append(result)
            
            return results
        
        except Exception as e:
            self.logger.error(f"Document search failed: {e}")
            return []
    
    def retrieve_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve full document details by ID
        """
        try:
            # Search Qdrant for document metadata
            search_result = self.qdrant_client.retrieve(
                collection_name=self.collection_name,
                ids=[document_id]
            )
            
            if not search_result:
                return None
            
            document = search_result[0]
            
            # Attempt to read the physical file
            storage_path = document.payload.get('storage_path')
            if storage_path and os.path.exists(storage_path):
                with open(storage_path, 'rb') as file:
                    file_content = file.read()
            else:
                file_content = None
            
            return {
                "document_id": document_id,
                "metadata": document.payload,
                "file_content": file_content
            }
        
        except Exception as e:
            self.logger.error(f"Document retrieval failed: {e}")
            return None

def process_all_documents():
    """
    Process documents from all predefined document type directories
    """
    # Initialize document manager
    doc_manager = DocumentManager()
    
    # Total processed documents counter
    total_processed = 0
    
    # Process documents in each document type directory
    for doc_type, dir_name in DocumentStorageConfig.DOCUMENT_TYPES.items():
        directory_path = os.path.join(
            DocumentStorageConfig.BASE_STORAGE_DIR, 
            dir_name
        )
        
        # Process all files in the directory
        processed_docs = doc_manager.process_directory(
            directory_path=directory_path,
            doc_type=doc_type
        )
        
        # Print results for each directory
        print(f"Processed {len(processed_docs)} documents in {dir_name}")
        total_processed += len(processed_docs)
    
    print(f"\nTotal documents processed: {total_processed}")

def search_documents():
    """
    Perform a search across documents with command-line input
    """
    # Initialize document manager
    doc_manager = DocumentManager()
    
    # Get search query from command line
    if len(sys.argv) < 3:
        print("Usage: python3 document_ingestion.py search \"your search query\"")
        sys.exit(1)
    
    search_query = " ".join(sys.argv[2:])
    
    # Perform search
    results = doc_manager.search_documents(
        query=search_query,
        limit=5
    )
    
    # Print search results
    if not results:
        print(f"No results found for '{search_query}'")
        return
    
    print(f"\nSearch Results for '{search_query}':")
    for result in results:
        print("\n---")
        print(f"Document ID: {result['document_id']}")
        print(f"Relevance Score: {result['score']:.3f}")
        print("Filename:", result['payload'].get('original_filename', 'N/A'))
        print("Document Type:", result['payload'].get('document_type', 'N/A'))
        # Print a snippet of text
        text_snippet = result['payload'].get('text', 'No text available')
        print("Text Snippet:", text_snippet[:300] + "..." if len(text_snippet) > 300 else text_snippet)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == 'search':
            search_documents()
        else:
            print("Invalid command. Use 'search' or run without arguments to process all documents.")
    else:
        process_all_documents()

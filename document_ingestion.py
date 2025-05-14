import os
import sys
sys.path.append('/root/anaptyss-chatbot-backend')

from document_manager import DocumentManager, DocumentStorageConfig

def main():
    # Initialize document manager
    doc_manager = DocumentManager()
    
    # Total processed documents counter
    total_processed = 0
    
    # Process documents for each type
    for doc_type, dir_name in DocumentStorageConfig.DOCUMENT_TYPES.items():
        directory_path = os.path.join(
            DocumentStorageConfig.BASE_STORAGE_DIR, 
            dir_name
        )
        
        # Process documents in the directory
        processed_docs = doc_manager.process_directory(
            directory_path=directory_path,
            doc_type=doc_type
        )
        
        # Print results for each directory
        print(f"Processed {len(processed_docs)} documents in {dir_name}")
        total_processed += len(processed_docs)
    
    print(f"\nTotal documents processed: {total_processed}")

def search_documents():
    # Initialize document manager
    doc_manager = DocumentManager()
    
    # Get search query from command line
    if len(sys.argv) < 2:
        print("Please provide a search query")
        sys.exit(1)
    
    search_query = " ".join(sys.argv[1:])
    
    # Perform search
    results = doc_manager.search_documents(
        query=search_query,
        limit=5
    )
    
    # Print search results
    print(f"\nSearch Results for '{search_query}':")
    for result in results:
        print("\n---")
        print(f"Document ID: {result['document_id']}")
        print(f"Relevance Score: {result['score']}")
        print("Filename:", result['payload'].get('original_filename', 'N/A'))
        print("Document Type:", result['payload'].get('document_type', 'N/A'))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'search':
        search_documents()
    else:
        main()

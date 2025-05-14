"""
This module provides key functions for integrating with the Qdrant vector database.
These functions improve the chatbot's ability to retrieve relevant content from the 
vector database before falling back to hardcoded responses.
"""

from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from openai import OpenAI

def parse_qdrant_results(hits: List[Any]) -> List[Dict[str, Any]]:
    """
    Parse Qdrant search results into a standardized format.
    
    Args:
        hits: Raw search results from Qdrant
        
    Returns:
        List of parsed sources with normalized fields
    """
    sources = []
    for hit in hits:
        if not hit or not hasattr(hit, 'payload'):
            continue
            
        payload = hit.payload
        if 'url' not in payload or 'title' not in payload:
            continue
            
        source = {
            "title": payload['title'],
            "url": payload['url'],
            "score": round(hit.score, 3) if hasattr(hit, 'score') else 0.0
        }
        
        # Add additional fields if available
        if 'content_type' in payload:
            source["content_type"] = payload.get('content_type', 'article')
        if 'content_type_name' in payload:
            source["content_type_name"] = payload.get('content_type_name', '')
        if 'industries' in payload:
            source["industries"] = payload.get('industries', [])
        if 'topics' in payload:
            source["topics"] = payload.get('topics', [])
        if 'excerpt' in payload:
            source["excerpt"] = payload.get('excerpt', '')
        if 'publication_date' in payload:
            source["publication_date"] = payload.get('publication_date', '')
            
        sources.append(source)
        
    return sources

def search_qdrant_with_filters(
    client: QdrantClient,
    openai_client: OpenAI,
    query: str,
    collection_name: str,
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 5,
    score_threshold: float = 0.65
) -> List[Any]:
    """
    Search Qdrant with vector embedding and optional filters.
    
    Args:
        client: Qdrant client instance
        openai_client: OpenAI client for generating embeddings
        query: User query to search for
        collection_name: Name of the Qdrant collection
        filters: Optional filters to apply to search
        limit: Maximum number of results to return
        score_threshold: Minimum similarity score threshold
        
    Returns:
        List of search hits from Qdrant
    """
    # Generate embedding for query
    embedding_response = openai_client.embeddings.create(
        input=query,
        model="text-embedding-ada-002"
    )
    query_vector = embedding_response.data[0].embedding
    
    # Build search parameters
    search_params = {
        "collection_name": collection_name,
        "query_vector": query_vector,
        "limit": limit,
        "score_threshold": score_threshold
    }
    
    # Add filters if provided
    if filters:
        search_params["filter"] = filters
    
    # Execute search
    return client.search(**search_params)

def get_relevant_case_study(
    client: QdrantClient,
    openai_client: OpenAI,
    industry: str,
    topic: str,
    collection_name: str
) -> Optional[Dict[str, Any]]:
    """
    Search for a relevant case study based on industry and topic.
    
    Args:
        client: Qdrant client instance
        openai_client: OpenAI client for generating embeddings
        industry: Industry to search for (e.g., "finance", "healthcare")
        topic: Topic to search for (e.g., "compliance", "analytics")
        collection_name: Name of the Qdrant collection
        
    Returns:
        Most relevant case study or None if none found
    """
    # Create a specific query for the case study
    case_study_query = f"{industry} {topic} case study"
    
    # Search for relevant case studies
    hits = search_qdrant_with_filters(
        client=client,
        openai_client=openai_client,
        query=case_study_query,
        collection_name=collection_name,
        filters={
            "must": [
                {"key": "content_type", "match": {"value": "success-stories"}}
            ]
        },
        limit=3,
        score_threshold=0.6
    )
    
    # Return the top result if found
    if hits and len(hits) > 0:
        return hits[0].payload
    
    return None

def extract_suggested_questions_from_hits(hits: List[Any], limit: int = 3) -> List[str]:
    """
    Generate suggested questions based on search results.
    
    Args:
        hits: Search results from Qdrant
        limit: Maximum number of questions to return
        
    Returns:
        List of suggested follow-up questions
    """
    questions = []
    
    for hit in hits[:3]:  # Use top 3 hits
        if not hit or not hasattr(hit, 'payload'):
            continue
            
        payload = hit.payload
        if 'title' not in payload:
            continue
            
        # Extract key terms from title
        title_words = payload['title'].split()
        key_terms = [w for w in title_words if len(w) > 4][:2]  # Get significant words
        
        if key_terms:
            content_type = payload.get('content_type_name', payload.get('content_type', 'content'))
            questions.append(f"Tell me more about {' '.join(key_terms)}")
            
            # Add specific questions based on content type
            if content_type == 'Case Study' or content_type == 'success-stories':
                questions.append(f"Do you have other case studies like {key_terms[0]}?")
            elif content_type == 'Blog Post' or content_type == 'posts':
                questions.append(f"What other insights do you have about {key_terms[0]}?")
            elif content_type == 'Webinar':
                questions.append(f"Are there recordings of this webinar about {key_terms[0]}?")
    
    # Return unique questions
    unique_questions = list(dict.fromkeys(questions))
    return unique_questions[:limit]

def determine_qdrant_filters(query: str) -> Dict[str, Any]:
    """
    Determine appropriate Qdrant filters based on the query.
    
    Args:
        query: The user's query string
        
    Returns:
        Filter dictionary to use with Qdrant
    """
    query_lower = query.lower()
    filter_conditions = []
    
    # Content type filtering
    if any(word in query_lower for word in ['case study', 'case studies', 'success']):
        filter_conditions.append({"key": "content_type", "match": {"value": "success-stories"}})
    elif any(word in query_lower for word in ['blog', 'article', 'post']):
        filter_conditions.append({"key": "content_type", "match": {"value": "posts"}})
    elif any(word in query_lower for word in ['webinar', 'video', 'presentation']):
        filter_conditions.append({"key": "content_type", "match": {"value": "webinars"}})
    
    # Industry filtering
    if 'finance' in query_lower or 'banking' in query_lower:
        filter_conditions.append({"key": "industries", "match": {"value": "finance"}})
    elif 'health' in query_lower:
        filter_conditions.append({"key": "industries", "match": {"value": "healthcare"}})
    elif 'manufactur' in query_lower:
        filter_conditions.append({"key": "industries", "match": {"value": "manufacturing"}})
    
    # Topic filtering
    if 'compliance' in query_lower:
        filter_conditions.append({"key": "topics", "match": {"value": "compliance"}})
    elif 'analytics' in query_lower or 'data' in query_lower:
        filter_conditions.append({"key": "topics", "match": {"value": "analytics"}})
    elif 'cloud' in query_lower:
        filter_conditions.append({"key": "topics", "match": {"value": "cloud"}})
    elif 'security' in query_lower or 'cyber' in query_lower:
        filter_conditions.append({"key": "topics", "match": {"value": "security"}})
        
    # Build the filter dictionary if we have conditions
    if filter_conditions:
        return {"must": filter_conditions}
    
    return {}

def format_qdrant_response(payload: Dict[str, Any], include_metadata: bool = True) -> str:
    """
    Format a Qdrant payload into a readable response.
    
    Args:
        payload: Qdrant payload containing content
        include_metadata: Whether to include metadata in the response
        
    Returns:
        Formatted markdown text response
    """
    response = []
    
    # Check if we have the necessary fields
    if 'title' not in payload or 'text' not in payload:
        return "Sorry, I couldn't find detailed information on that topic."
    
    # Add title
    response.append(f"## {payload['title']}")
    
    # Add content with proper line breaks for bullet points
    text_content = payload['text']
    # Make sure bullet points render properly by adding a newline before each bullet
    text_content = text_content.replace("\n- ", "\n\n- ")
    text_content = text_content.replace("\n• ", "\n\n• ")
    response.append(text_content)
    
    if include_metadata:
        response.append("\n---")
        
        # Add metadata section
        metadata = []
        if 'content_type' in payload or 'content_type_name' in payload:
            content_type = payload.get('content_type_name', payload.get('content_type', '')).replace('_', ' ').title()
            metadata.append(f"📄 Type: {content_type}")
            
        if 'industries' in payload and payload['industries']:
            industries = payload['industries'] if isinstance(payload['industries'], list) else [payload['industries']]
            metadata.append(f"🏢 Industry: {', '.join(i.title() for i in industries)}")
            
        if 'topics' in payload and payload['topics']:
            topics = payload['topics'] if isinstance(payload['topics'], list) else [payload['topics']]
            metadata.append(f"🏷️ Topics: {', '.join(t.replace('_', ' ').title() for t in topics)}")
            
        if 'publication_date' in payload:
            metadata.append(f"📅 Published: {payload['publication_date'][:10]}")
            
        response.append(" | ".join(metadata))
        
        # Add source link
        response.append(f"\n👉 [Read full article]({payload['url']})")
    
    # Join with double newlines to ensure proper markdown rendering
    formatted_text = "\n\n".join(response)
    
    return formatted_text

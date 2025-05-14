#!/usr/bin/env python3
import uuid
import logging
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from openai import OpenAI
from qdrant_client import QdrantClient
from config import OPENAI_API_KEY, QDRANT_URL

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Anaptyss Chat API")

# ─── CORS CONFIG ───────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── CLIENTS & COLLECTION ───────────────────────────────────────────────────────
openai = OpenAI(api_key=OPENAI_API_KEY)
qdrant = QdrantClient(url=QDRANT_URL)
COLLECTION = "anaptyss_content"

# ─── ENHANCED SESSION STORE ───────────────────────────────────────────────────
class ConversationMemory:
    def __init__(self):
        self.messages: List[Dict[str, str]] = []
        self.summary: str = ""
        self.interaction_count: int = 0
        self.sentiment_history: List[Dict[str, float]] = []
        self.topics_discussed: List[str] = []
        self.last_form_trigger: Optional[datetime] = None
        self.financial_context: Dict[str, Any] = {
            "industry_vertical": None,
            "topics_of_interest": [],
            "potential_use_cases": [],
            "detected_pain_points": []
        }
        self.last_sources: List[Dict[str, Any]] = []
        
    def add_exchange(self, user_msg: str, assistant_msg: str, sentiment: Dict[str, float] = None, topics: List[str] = None):
        if sentiment is None:
            sentiment = {"positive": 0.33, "negative": 0.33, "neutral": 0.34}
        if topics is None:
            topics = []
            
        self.messages.extend([
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg}
        ])
        
        self.interaction_count += 1
        self.sentiment_history.append(sentiment)
        self.topics_discussed.extend([t for t in topics if t not in self.topics_discussed])
        
        # Update summary if conversation gets long
        if len(self.messages) > 10:
            self.summarize_conversation()
            
    def summarize_conversation(self):
        """Summarize the conversation to maintain context while reducing token usage."""
        if not self.messages:
            return
            
        summary_prompt = "Summarize the key points of this conversation about financial services topics:\n\n"
        for msg in self.messages:
            summary_prompt += f"{msg['role']}: {msg['content']}\n"
            
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3
        )
        
        self.summary = response.choices[0].message.content
        # Keep only last 4 exchanges after summarization
        self.messages = self.messages[-8:]
        
    def update_financial_context(self, query: str):
        """Extract and update financial industry context from the query."""
        if self.interaction_count <= 1:
            # Only analyze full context after initial exchange
            return
            
        # Combine all user messages to create context
        all_user_messages = " ".join([msg["content"] for msg in self.messages if msg["role"] == "user"])
        
        analysis_prompt = f"""
Analyze the following conversation from a financial services perspective.
Extract the following information in JSON format:

1. industry_vertical: The specific financial industry vertical mentioned (banking, insurance, wealth management, etc.)
2. topics_of_interest: Financial topics the user seems interested in (up to 3)
3. potential_use_cases: Potential use cases the user might be exploring (up to 3)
4. detected_pain_points: Business challenges or pain points mentioned (up to 3)

Conversation: {all_user_messages}

Respond ONLY with valid JSON, no other text.
"""
        
        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": analysis_prompt}],
                temperature=0.1
            )
            
            result_text = response.choices[0].message.content
            
            # Extract JSON from the response (handling possible text before/after)
            import re
            json_match = re.search(r'({[\s\S]*})', result_text)
            if json_match:
                try:
                    analysis = json.loads(json_match.group(1))
                    # Update financial context, preserving existing values if new ones are None
                    for key, value in analysis.items():
                        if key in self.financial_context and value:
                            if isinstance(value, list):
                                # For lists, add new items without duplicates
                                self.financial_context[key] = list(set((self.financial_context[key] or []) + value))
                            else:
                                self.financial_context[key] = value or self.financial_context[key]
                except json.JSONDecodeError:
                    logger.warning("Failed to parse financial context JSON")
        except Exception as e:
            logger.warning(f"Error updating financial context: {e}")

    def should_show_form(self, intent_scores: Dict[str, float]) -> bool:
        """Determine if we should show the lead form based on various factors."""
        # Show form after 10 exchanges
        if self.interaction_count >= 10:
            return True
            
        # Enhanced for financial services context
        high_value_topics = ["core banking", "digital transformation", "compliance", "risk management", 
                            "Basel", "KYC", "AML", "wealth management", "modernization"]
        
        topics_text = ' '.join(self.topics_discussed).lower()
        has_high_value_topic = any(topic.lower() in topics_text for topic in high_value_topics)
        
        # Show form if there's high sales intent
        if intent_scores.get("product_interest", 0) > 0.6 or intent_scores.get("contact_request", 0) > 0.5:
            return True
        
        # Lead-related detection - check for keywords in the recent messages
        recent_msgs = self.messages[-min(4, len(self.messages)):]
        recent_text = ' '.join([msg["content"] for msg in recent_msgs if msg["role"] == "user"]).lower()
        lead_keywords = ["contact", "email", "call", "talk to", "expert", "consultant", "demo", "meeting", 
                        "speak with", "pricing", "cost", "quote", "proposal", "help us", "our bank", "our company"]
        
        if any(keyword in recent_text for keyword in lead_keywords):
            return True
            
        # Show form if discussing important financial services topics after enough exchanges
        if has_high_value_topic and self.interaction_count >= 3:
            # Check if sentiment is positive
            recent_sentiments = self.sentiment_history[-min(3, len(self.sentiment_history)):]
            avg_positive = sum(s.get("positive", 0) for s in recent_sentiments) / len(recent_sentiments)
            if avg_positive > 0.65:
                return True
        
        return False

# Maps session_id → ConversationMemory
sessions: Dict[str, ConversationMemory] = {}

# ─── REQUEST & RESPONSE SCHEMAS ────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    show_form: bool
    session_id: str
    sources: List[Dict[str, Any]] = []
    suggested_questions: List[str] = []  # Keep it in the model but don't populate it

class LeadRequest(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    message: Optional[str] = None
    industry: Optional[str] = None  # Added for financial services
    job_title: Optional[str] = None  # Added for financial services
    company_size: Optional[str] = None  # Added for financial services

class LeadResponse(BaseModel):
    status: str
    message: str

# ─── DEPENDENCIES ───────────────────────────────────────────────────────────────
def get_openai_client():
    return openai

def get_qdrant_client():
    return qdrant

# ─── HEALTHCHECK ───────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    # Check OpenAI connection
    try:
        openai.models.list()
    except Exception as e:
        logger.error(f"OpenAI connection error: {e}")
        return {"status": "error", "message": "OpenAI connection failed"}
    
    # Check Qdrant connection
    try:
        collections = qdrant.get_collections()
        collection_names = [c.name for c in collections.collections]
        if COLLECTION not in collection_names:
            return {"status": "warning", "message": f"Qdrant connection OK but collection '{COLLECTION}' not found"}
    except Exception as e:
        logger.error(f"Qdrant connection error: {e}")
        return {"status": "error", "message": "Qdrant connection failed"}
        
    return {"status": "ok"}

# ─── GREETING HANDLER ───────────────────────────────────────────────────────────
def is_greeting(message: str) -> bool:
    """Check if the message is a simple greeting."""
    greetings = [
        'hi', 'hello', 'hey', 'greetings', 'good morning', 
        'good afternoon', 'good evening', 'howdy', 'hi there'
    ]
    
    # Convert to lowercase and strip punctuation
    cleaned_message = message.lower().strip().rstrip('.!?')
    
    return cleaned_message in greetings or cleaned_message.startswith(tuple(g + ' ' for g in greetings))

def generate_greeting_response(is_first_greeting=False, name: str = "AnaptIQ") -> str:
    """Generate a personalized greeting response."""
    import random
    
    # If this is the first greeting, return the welcome message
    if is_first_greeting:
        return generate_welcome_message()
    
    # Otherwise, use a more conversational greeting for repeat greetings
    greeting_templates = [
        f"Hello again! How can I assist with your financial services technology questions today?",
        
        f"Hi there! What financial technology topics would you like to explore?",
        
        f"Good to see you again. I'm ready to discuss your financial services technology needs. What can I help with?",
        
        f"Welcome back! How may I help with your banking technology questions today?"
    ]
    
    return random.choice(greeting_templates)

def clean_response_format(text: str) -> str:
    """Clean up formatting artifacts from responses."""
    if not text:
        return text
        
    # Replace Executive Summary markers with case insensitivity
    text = re.sub(r'\*\*Executive Summary:?\*\*', '## Executive Summary', text, flags=re.IGNORECASE)
    text = re.sub(r'Executive Summary:', '## Executive Summary', text, flags=re.IGNORECASE)
    
    # Remove Response markers with case insensitivity
    text = re.sub(r'\*\*Response:?\*\*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Response:', '', text, flags=re.IGNORECASE)
    
    # Remove common meta-text phrases with more aggressive matching
    phrases = [
        r'To address (?:the user|your) query(?:.*?)(?=\n|$)',
        r'In response to your question(?:.*?)(?=\n|$)',
        r'As requested,(?:.*?)(?=\n|$)',
        r'Below is information about(?:.*?)(?=\n|$)',
        r'Let me provide(?:.*?)(?=\n|$)',
        r'(?:This|The) (?:response|answer) (?:addresses|provides)(?:.*?)(?=\n|$)'
    ]
    
    for phrase in phrases:
        text = re.sub(phrase, '', text, flags=re.IGNORECASE)
    
    # Clean up extra whitespace and fix formatting
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'^\s+', '', text)
    text = re.sub(r'\n\s+\n', '\n\n', text)
    
    # Fix bullet points after cleanup
    text = re.sub(r'\n\n(•|\-)', '\n\n$1', text)
    
    return text
    
# ─── FINANCIAL SERVICES SPECIFIC HELPERS ───────────────────────────────────────
def extract_financial_terms(text: str) -> List[str]:
    """Extract financial services specific terminology from text."""
    financial_terms = [
        "Basel", "GDPR", "KYC", "AML", "core banking", "digital transformation", 
        "open banking", "PSD2", "stress testing", "FRTB", "capital adequacy",
        "model risk", "risk management", "wealth management", "regulatory compliance",
        "credit risk", "market risk", "operational risk", "BCBS", "liquidity",
        "VAR", "value at risk", "CVA", "XVA", "trading book", "banking book"
    ]
    
    found_terms = []
    text_lower = text.lower()
    
    for term in financial_terms:
        if term.lower() in text_lower:
            found_terms.append(term)
            
    return found_terms

def create_financial_filters(terms: List[str]) -> Dict[str, Any]:
    """Create Qdrant filters based on financial terms."""
    if not terms:
        return {}
        
    # Map terms to industries and topics
    industry_map = {
        "core banking": "banking",
        "open banking": "banking",
        "wealth management": "wealth_management",
        "credit risk": "banking",
        "market risk": "banking",
        "trading book": "investment_banking"
    }
    
    topic_map = {
        "Basel": "regulatory_compliance",
        "GDPR": "regulatory_compliance",
        "KYC": "regulatory_compliance",
        "AML": "regulatory_compliance",
        "digital transformation": "digital_transformation",
        "risk management": "risk_management",
        "regulatory compliance": "regulatory_compliance",
        "model risk": "risk_management"
    }
    
    industry_conditions = []
    topic_conditions = []
    
    for term in terms:
        if term in industry_map:
            industry_conditions.append({
                "key": "industries",
                "match": {"value": industry_map[term]}
            })
        if term in topic_map:
            topic_conditions.append({
                "key": "topics",
                "match": {"value": topic_map[term]}
            })
    
    conditions = []
    if industry_conditions:
        conditions.append({"should": industry_conditions})
    if topic_conditions:
        conditions.append({"should": topic_conditions})
    
    if conditions:
        return {"must": conditions}
    
    return {}

def enhanced_financial_search(query: str, qdrant_client, openai_client, limit: int = 7):
    """Enhanced search optimized for financial services queries."""
    # Extract financial terms
    financial_terms = extract_financial_terms(query)
    
    # Generate embedding
    emb_response = openai_client.embeddings.create(
        input=query,
        model="text-embedding-ada-002"
    )
    query_vector = emb_response.data[0].embedding
    
    # Initial semantic search
    search_results = qdrant_client.search(
        collection_name=COLLECTION,
        query_vector=query_vector,
        limit=limit,
        score_threshold=0.7
    )
    
    # If financial terms detected or limited results, try with filters
    if financial_terms and (len(search_results) < 3 or max([r.score for r in search_results] or [0]) < 0.75):
        filters = create_financial_filters(financial_terms)
        
        if filters:
            filtered_results = qdrant_client.search(
                collection_name=COLLECTION,
                query_vector=query_vector,
                filter=filters,
                limit=limit,
                score_threshold=0.65  # Lower threshold for filtered search
            )
            
            # Combine and deduplicate results
            seen_ids = set(r.id for r in search_results)
            combined_results = list(search_results)
            
            for result in filtered_results:
                if result.id not in seen_ids:
                    combined_results.append(result)
                    seen_ids.add(result.id)
            
            # Sort by score and return top results
            combined_results.sort(key=lambda x: x.score, reverse=True)
            return combined_results[:limit]
    
    return search_results

def generate_financial_prompt(query: str, context: str, memory: ConversationMemory) -> str:
    """Generate a specialized prompt for financial services queries with reduced redundancy."""
    # Extract financial context
    financial_terms = extract_financial_terms(query)
    has_financial_terms = len(financial_terms) > 0
    
    # Check for follow-up patterns
    is_followup = any(phrase in query.lower() for phrase in ["more", "additional", "follow up", "followup", "another", "similar", "also", "too"])
    
    # Get previous responses to check for redundancy
    previous_responses = [msg["content"] for msg in memory.messages if msg["role"] == "assistant"]
    
    system_prompt = """You are AnaptIQ, an executive-level consultant specializing in digital transformation, banking technology, and managed services for the financial services industry. Your responses should:

1. Be authoritative and demonstrate deep industry knowledge in banking, financial services, compliance, risk management, and digital transformation
2. Reference specific content from the provided context with proper attribution
3. Use industry-specific terminology appropriately and explain complex concepts clearly
4. Balance technical accuracy with strategic business insights
5. Always provide actionable recommendations when appropriate
6. Maintain a professional, confident, and consultative tone

IMPORTANT: If this appears to be a follow-up question on the same topic as a previous response, DO NOT repeat the same introduction or general information. Instead, focus on providing new, additional details that directly address the specific follow-up question.

When you don't have specific information, draw upon your knowledge of industry best practices and regulatory frameworks like Basel, GDPR, PCI-DSS, etc.
"""
    
    # Add memory context if available
    memory_context = ""
    if memory.financial_context["industry_vertical"]:
        memory_context += f"The user appears to be in the {memory.financial_context['industry_vertical']} industry. "
    
    if memory.financial_context["detected_pain_points"]:
        memory_context += f"They've mentioned these challenges: {', '.join(memory.financial_context['detected_pain_points'])}. "
    
    if memory.financial_context["potential_use_cases"]:
        memory_context += f"Potential use cases include: {', '.join(memory.financial_context['potential_use_cases'])}. "
    
    if memory.summary:
        memory_context += f"\n\nPrevious conversation summary: {memory.summary}"
    
    # Add financial terminology context
    financial_context = ""
    if has_financial_terms:
        financial_context = "\n\nFinancial terms in query: " + ", ".join(financial_terms)
        financial_context += "\n\nWhen answering, demonstrate expertise in these financial concepts."
    
    # Add redundancy prevention directives based on context
    redundancy_context = ""
    if is_followup and len(previous_responses) > 0:
        redundancy_context = """
REDUNDANCY WARNING: This appears to be a follow-up question. Do NOT repeat your previous introduction paragraphs, explanations of what AI is, or general descriptions already provided. 
Instead:
1. Start with a brief 1-2 sentence executive summary specific to THIS question
2. Focus only on NEW information directly relevant to this specific follow-up question
3. Use different examples and case studies than in previous responses
4. Do not repeat the general benefits of AI or technology that you've already mentioned
"""
    
    # Combine all elements
    full_prompt = f"{system_prompt}\n\n{redundancy_context}\n\n{memory_context}{financial_context}\n\nContext from knowledge base:\n\n{context}\n\nUser query: {query}\n\nProvide a well-structured, focused response that demonstrates financial services expertise. For complex topics, include a brief executive summary at the beginning without repeating general information already provided."
    
    return full_prompt

def format_financial_response(response: str, query: str) -> str:
    """Format response for financial services with executive summary and improved readability."""
    # Check if response already has good structure
    has_headers = '##' in response or '# ' in response
    
    # Check if response is long and complex
    is_complex = len(response.split()) > 200 and any(term in query.lower() for term in [
        "how", "explain", "describe", "what is", "strategy", "implementation", 
        "approach", "framework", "methodology"
    ])
    
    # If response already has good structure and not complex, return as is
    if has_headers and not is_complex:
        return response
    
    # For complex responses without good structure, generate an executive summary
    if is_complex and not has_headers:
        summary_prompt = f"""
Create a brief executive summary (2-3 bullet points) of the following response to a financial services question.
Focus on key strategic insights and actionable recommendations. Keep it concise and impactful.

Query: {query}
Response: {response}

Format as "## Executive Summary" followed by bullet points.
"""

        try:
            summary_result = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3
            )
            
            summary = summary_result.choices[0].message.content
            
            # Add summary to the beginning of the response
            if "executive summary" not in response.lower():
                # Split the response into paragraphs
                paragraphs = response.split('\n\n')
                
                # Improve readability for long paragraphs
                improved_paragraphs = []
                for paragraph in paragraphs:
                    # If paragraph is very long, split into smaller chunks
                    if len(paragraph.split()) > 100:
                        # Try to split at logical points
                        sentences = re.split(r'(?<=[.!?]) +', paragraph)
                        current_chunk = []
                        current_length = 0
                        
                        for sentence in sentences:
                            # Add sentence to current chunk if it's not too long
                            if current_length + len(sentence.split()) <= 70:
                                current_chunk.append(sentence)
                                current_length += len(sentence.split())
                            else:
                                # Add current chunk to paragraphs and start a new one
                                if current_chunk:
                                    improved_paragraphs.append(' '.join(current_chunk))
                                current_chunk = [sentence]
                                current_length = len(sentence.split())
                        
                        # Add the last chunk if it exists
                        if current_chunk:
                            improved_paragraphs.append(' '.join(current_chunk))
                    else:
                        improved_paragraphs.append(paragraph)
                
                # Format with improved structure
                structured_response = f"{summary}\n\n"
                
                # Add section headers if they don't exist
                if '##' not in response and '# ' not in response and len(improved_paragraphs) > 2:
                    # Try to identify logical sections
                    current_section = "## Background"
                    formatted_paragraphs = [f"{current_section}"]
                    
                    # Add a details section after first 2 paragraphs if there are more
                    if len(improved_paragraphs) > 2:
                        formatted_paragraphs.append(improved_paragraphs[0])
                        if "case study" in query.lower() or "case studies" in query.lower():
                            current_section = "## Case Studies"
                        else:
                            current_section = "## Details"
                        formatted_paragraphs.append(f"\n{current_section}")
                        
                        # Add remaining paragraphs
                        for paragraph in improved_paragraphs[1:]:
                            formatted_paragraphs.append(paragraph)
                            
                        # Add recommendations section at the end if not already present
                        if not any(keyword in ' '.join(improved_paragraphs[-2:]).lower() for keyword in ["recommend", "conclusion", "next steps"]):
                            formatted_paragraphs.append("\n## Recommendations")
                            formatted_paragraphs.append("Based on the information above, consider these strategic recommendations:")
                            
                            # Generate recommendations if needed
                            recommendation_prompt = f"""
Based on this response about {query}, generate 3 concise, bullet-point recommendations for financial services executives.
Focus on actionable, specific guidance.

Response: {response}

Format as bullet points only, no introduction text.
"""
                            try:
                                rec_result = openai.chat.completions.create(
                                    model="gpt-3.5-turbo",
                                    messages=[{"role": "user", "content": recommendation_prompt}],
                                    temperature=0.3
                                )
                                recommendations = rec_result.choices[0].message.content
                                formatted_paragraphs.append(recommendations)
                            except Exception as e:
                                logger.warning(f"Error generating recommendations: {e}")
                                formatted_paragraphs.append("• Consider implementing the solutions discussed above to drive business value\n• Partner with experienced consultants to ensure successful execution\n• Start with a pilot project to validate the approach before scaling")
                    else:
                        # For very short responses, just add paragraphs without additional structure
                        formatted_paragraphs.extend(improved_paragraphs)
                        
                    structured_response += '\n\n'.join(formatted_paragraphs)
                else:
                    # If headers already exist in paragraphs, just add improved paragraphs
                    structured_response += '\n\n'.join(improved_paragraphs)
                
                return structured_response
        except Exception as e:
            logger.warning(f"Error generating executive summary: {e}")
    
    return response

# ─── CHAT HELPERS ───────────────────────────────────────────────────────────────
def format_source_reference(source: Dict[str, Any]) -> str:
    """Format a source reference in markdown."""
    return f"[{source['title']}]({source['url']})"

def classify_intent(message: str) -> Dict[str, float]:
    """Classify user intent with financial services focus."""
    prompt = f"""Classify the user's message into these categories for a financial services chatbot (respond with numbers 0-1 for each):
    - information_seeking: Looking for general information
    - product_interest: Interest in specific products/services
    - technical_question: Technical or implementation questions
    - contact_request: Wanting to contact or engage with sales
    - compliance_question: Questions about regulatory compliance
    - implementation_interest: Interest in implementation details or methodology
    
    Message: {message}
    
    Respond in JSON format only."""
    
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    try:
        import json
        return json.loads(response.choices[0].message.content)
    except:
        return {
            "information_seeking": 0.25,
            "product_interest": 0.25,
            "technical_question": 0.25,
            "contact_request": 0.25,
            "compliance_question": 0.0,
            "implementation_interest": 0.0
        }

# ─── INTELLIGENCE FUNCTIONS ───────────────────────────────────────────────────
def analyze_sentiment(text: str) -> Dict[str, float]:
    """Analyze sentiment of user message."""
    prompt = f"""Analyze the sentiment of this message and return ONLY a JSON object with these scores (0-1):
    - positive: How positive/satisfied the user seems
    - negative: How negative/frustrated the user seems
    - neutral: How neutral/objective the user seems
    
    Message: {text}"""
    
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    try:
        return json.loads(response.choices[0].message.content)
    except:
        return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}

def extract_topics(text: str) -> List[str]:
    """Extract main topics from text with financial services focus."""
    prompt = f"""Extract 2-3 main financial services topics/themes from this text as a comma-separated list.
    Focus on banking, finance, compliance, technology, and related domains.
    
    Text: {text}"""
    
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    topics = [t.strip() for t in response.choices[0].message.content.split(",")]
    return topics[:3]

def personalize_response(base_response: str, memory: ConversationMemory) -> str:
    """Personalize response based on conversation history and financial context."""
    if not memory.topics_discussed and not memory.financial_context["industry_vertical"]:
        return base_response
    
    # Add financial context if available
    financial_context = ""
    if memory.financial_context["industry_vertical"]:
        financial_context += f"Industry vertical: {memory.financial_context['industry_vertical']}\n"
    if memory.financial_context["topics_of_interest"]:
        financial_context += f"Topics of interest: {', '.join(memory.financial_context['topics_of_interest'])}\n"
    if memory.financial_context["detected_pain_points"]:
        financial_context += f"Pain points: {', '.join(memory.financial_context['detected_pain_points'])}\n"
        
    prompt = f"""Personalize this response for a financial services professional based on their interests and conversation history.
    Previous topics discussed: {', '.join(memory.topics_discussed)}
    {financial_context}
    Current response: {base_response}
    
    Make the response more relevant to their specific financial services interests and industry context.
    Keep the same information but tailor the examples, terminology, and focus to their context.
    Use markdown formatting. Do not add an executive summary if one already exists."""
    
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    
    return response.choices[0].message.content

def generate_lead_email(memory: ConversationMemory) -> str:
    """Generate lead email content based on conversation history with financial services focus."""
    topics = list(set(memory.topics_discussed))  # Remove duplicates
    sentiment_summary = "Positive" if sum(s.get("positive", 0) for s in memory.sentiment_history) > sum(s.get("negative", 0) for s in memory.sentiment_history) else "Mixed"
    
    # Add financial context if available
    financial_context = ""
    if memory.financial_context["industry_vertical"]:
        financial_context += f"\n- Industry vertical: {memory.financial_context['industry_vertical']}"
    if memory.financial_context["potential_use_cases"]:
        financial_context += f"\n- Potential use cases: {', '.join(memory.financial_context['potential_use_cases'])}"
    if memory.financial_context["detected_pain_points"]:
        financial_context += f"\n- Pain points: {', '.join(memory.financial_context['detected_pain_points'])}"
    
    # Extract recent conversation (last 3 exchanges)
    recent_conversation = ""
    if len(memory.messages) > 0:
        recent_msgs = memory.messages[-min(6, len(memory.messages)):]
        for msg in recent_msgs:
            role_name = "Customer" if msg["role"] == "user" else "AnaptIQ"
            recent_conversation += f"\n{role_name}: {msg['content'][:300]}..."
    
    email_content = f"""
    New Financial Services Lead from Chatbot Interaction
    
    Interaction Summary:
    - Number of exchanges: {memory.interaction_count}
    - Overall sentiment: {sentiment_summary}
    - Topics discussed: {', '.join(topics)}{financial_context}
    
    Recent Conversation:
    {recent_conversation}
    
    Summary:
    {memory.summary if memory.summary else 'No summary available'}
    
    Suggested Follow-up: Based on the conversation, this lead appears interested in {', '.join(topics[:2])} and may benefit from a personalized discussion about our solutions in these areas.
    """
    
    return email_content

def detect_content_preferences(message: str) -> Dict[str, Any]:
    """Detect content type and topic preferences with financial services focus."""
    prompt = f"""Analyze this message and return ONLY a JSON object with these fields:
    - content_type: What type of content they're looking for (case_study, whitepaper, blog, guide, or null if unclear)
    - industry: Which financial industry they're interested in (banking, insurance, wealth_management, investment_banking, payments, or null)
    - topic: What financial topic they're interested in (digital_transformation, core_banking, compliance, risk_management, payments, cloud, ai_ml, or null)
    
    Message: {message}
    
    Example response: {{"content_type": "case_study", "industry": "banking", "topic": "digital_transformation"}}"""
    
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    try:
        return json.loads(response.choices[0].message.content)
    except:
        return {"content_type": None, "industry": None, "topic": None}

def generate_clarification_prompt(preferences: Dict[str, Any], available_content: List[Dict[str, Any]]) -> str:
    """Generate a clarification prompt based on available content with financial services focus."""
    if not available_content:
        return """I couldn't find an exact match for your financial services query. Could you clarify what you're looking for?
        
- Are you interested in a specific financial industry (e.g., banking, insurance, wealth management)?
- What type of content would you prefer (case study, whitepaper, guide)?
- Any specific financial topic (e.g., digital transformation, compliance, risk management)?"""
    
    # Extract unique values from available content
    industries = set()
    topics = set()
    content_types = set()
    
    for content in available_content:
        if 'industries' in content:
            industries.update(content['industries'])
        if 'topics' in content:
            topics.update(content['topics'])
        if 'content_type' in content:
            content_types.add(content['content_type'])
    
    prompt = "I found some related financial services content. Could you specify which interests you most?\n\n"
    
    if industries:
        prompt += f"**Industries**: {', '.join(industry.replace('_', ' ').title() for industry in industries)}\n"
    if topics:
        prompt += f"**Topics**: {', '.join(topic.replace('_', ' ').title() for topic in topics)}\n"
    if content_types:
        prompt += f"**Content Types**: {', '.join(content_type.replace('_', ' ').title() for content_type in content_types)}\n"
    
    return prompt

def format_response(content: Dict[str, Any], include_metadata: bool = True) -> str:
    """Format content response with proper markdown and metadata for financial services."""
    response = []
    
    # Add title
    response.append(f"## {content['title']}")
    
    # Add content
    response.append(content['text'])
    
    if include_metadata:
        response.append("\n---")
        
        # Add metadata section
        metadata = []
        if content.get('content_type'):
            readable_type = content['content_type'].replace('_', ' ').title()
            if content.get('content_type_name'):
                readable_type = content['content_type_name']
            metadata.append(f"📄 Type: {readable_type}")
        if content.get('industries'):
            readable_industries = [i.replace('_', ' ').title() for i in content['industries']]
            metadata.append(f"🏢 Industry: {', '.join(readable_industries)}")
        if content.get('topics'):
            readable_topics = [t.replace('_', ' ').title() for t in content['topics']]
            metadata.append(f"🏷️ Topics: {', '.join(readable_topics)}")
        
        response.append(" | ".join(metadata))
        
        # Add source link
        response.append(f"\n👉 [Read full article]({content['url']})")
    
    return "\n\n".join(response)

def generate_welcome_message() -> str:
    """Generate a welcome message with financial services focus."""
    return """# Welcome to AnaptIQ

I'm your executive-level consultant for financial services technology. I can help with:

- 📊 **Digital Transformation** in banking and financial services
- 💼 **Core Banking Modernization** strategies and implementation approaches
- 🔒 **Regulatory Compliance** solutions including Basel, KYC/AML, and GDPR
- 📈 **Risk Management** frameworks and technology solutions
- 💡 **AI & Analytics** implementation in financial services
- 🌐 **Cloud Migration** for financial institutions

How can I assist with your financial services technology needs today?"""
    
def clean_response_format(text: str) -> str:
    """Clean up formatting artifacts from responses."""
    if not text:
        return text
        
    # Replace Executive Summary markers with case insensitivity
    text = re.sub(r'\*\*Executive Summary:?\*\*', '## Executive Summary', text, flags=re.IGNORECASE)
    text = re.sub(r'Executive Summary:', '## Executive Summary', text, flags=re.IGNORECASE)
    
    # Remove any lingering bold markup around Executive Summary
    text = re.sub(r'\*\*## Executive Summary\*\*', '## Executive Summary', text)
    
    # Remove Response markers with case insensitivity
    text = re.sub(r'\*\*Response:?\*\*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Response:', '', text, flags=re.IGNORECASE)
    
    # Remove common meta-text phrases with more aggressive matching
    phrases = [
        r'To address (?:the user|your) query(?:.*?)(?=\n|$)',
        r'In response to your question(?:.*?)(?=\n|$)',
        r'As requested,(?:.*?)(?=\n|$)',
        r'Below is information about(?:.*?)(?=\n|$)',
        r'Let me provide(?:.*?)(?=\n|$)',
        r'(?:This|The) (?:response|answer) (?:addresses|provides)(?:.*?)(?=\n|$)'
    ]
    
    for phrase in phrases:
        text = re.sub(phrase, '', text, flags=re.IGNORECASE)
    
    # Clean up extra whitespace and fix formatting
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'^\s+', '', text)
    text = re.sub(r'\n\s+\n', '\n\n', text)
    
    # Fix bullet points after cleanup
    text = re.sub(r'\n\n(•|\-)', '\n\n$1', text)
    
    return text

# ─── CHAT ENDPOINT ─────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    openai_client: OpenAI = Depends(get_openai_client),
    qdrant_client: QdrantClient = Depends(get_qdrant_client)
):
    try:
        logger.info(f"Received chat request: {req.message[:50]}... (session: {req.session_id})")
        
        # Get or create session
        sid = req.session_id or str(uuid.uuid4())
        is_new_session = False
        
        if sid not in sessions:
            logger.info(f"Creating new session: {sid}")
            sessions[sid] = ConversationMemory()
            is_new_session = True
            welcome_message = generate_welcome_message()
            return ChatResponse(
                reply=welcome_message,
                show_form=False,
                session_id=sid,
                sources=[],
                suggested_questions=[]
            )
            
        memory = sessions[sid]
        
        # Check if this is a simple greeting
        if is_greeting(req.message):
            logger.info(f"Greeting detected: {req.message}")
            
            # Only show welcome message for first greeting or new session
            is_first_greeting = is_new_session or len(memory.messages) == 0
            greeting_response = generate_greeting_response(is_first_greeting)
            
            # Update conversation memory
            sentiment = {"positive": 0.8, "negative": 0.0, "neutral": 0.2}
            topics = ["greeting"]
            
            # Check for duplicate messages to avoid adding the same exchange twice
            if not memory.messages or memory.messages[-1]["content"] != greeting_response:
                memory.add_exchange(req.message, greeting_response, sentiment, topics)
            
            return ChatResponse(
                reply=greeting_response,
                show_form=False,
                session_id=sid,
                sources=[],
                suggested_questions=[]
            )
        
        # Check for duplicate message (avoid processing the same message twice)
        if memory.messages and len(memory.messages) >= 2 and memory.messages[-2]["content"] == req.message:
            logger.info(f"Duplicate message detected: {req.message}")
            return ChatResponse(
                reply="I noticed you sent the same message twice. Did you have any additional questions or would you like me to elaborate further on my previous response?",
                show_form=False,
                session_id=sid,
                sources=[],
                suggested_questions=[]
            )
        
        # Log the current request
        logger.info(f"Processing request: {req.message}")
        
        # Update financial context from query
        memory.update_financial_context(req.message)
        
        # Analyze message for content preferences with financial focus
        preferences = detect_content_preferences(req.message)
        
        # Enhanced search for financial services content
        search_results = enhanced_financial_search(
            query=req.message,
            qdrant_client=qdrant_client,
            openai_client=openai_client
        )
        
        # Handle weak or no results
        if not search_results or (len(search_results) == 1 and search_results[0].score < 0.7):
            clarification = generate_clarification_prompt(preferences, [h.payload for h in search_results])
            
            # Get default suggested questions for financial services
            default_questions = [
                "What are your digital transformation services for banks?",
                "How do you help with regulatory compliance?",
                "Can you share a case study on core banking modernization?"
            ]
            
            logger.info(f"Weak search results. Using default questions: {default_questions}")
            
            return ChatResponse(
                reply=clarification,
                show_form=False,
                session_id=sid,
                sources=[h.payload for h in search_results],
                suggested_questions=[]
            )
        
        # Prepare context and sources
        context_blocks = []
        sources = []
        
        for h in search_results:
            p = h.payload
            context_blocks.append(format_response(p, include_metadata=False))
            sources.append({
                "title": p['title'],
                "url": p['url'],
                "score": round(h.score, 3),
                "content_type": p.get('content_type', 'article'),
                "content_type_name": p.get('content_type_name', p.get('content_type', 'article').replace('_', ' ').title()),
                "industries": p.get('industries', []),
                "topics": p.get('topics', [])
            })
        
        logger.info(f"Found {len(sources)} sources for query")
        
        # Store sources in memory for reference in follow-up questions
        memory.last_sources = sources
        
        context = "\n\n---\n\n".join(context_blocks)
        
        # Generate financial services specialized prompt
        specialized_prompt = generate_financial_prompt(req.message, context, memory)
        
        # Prepare conversation history
        messages = [
            {
                "role": "system",
                "content": specialized_prompt
            }
        ]
        
        # Add previous messages for context (without duplicating system prompt)
        messages.extend(memory.messages)
        
        # Get chat completion
        logger.info(f"Calling OpenAI chat completion API")
        chat_response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7
        )

        answer = chat_response.choices[0].message.content.strip()

        # Clean up any formatting issues
        answer = clean_response_format(answer)

        # Format the response for financial services
        answer = format_financial_response(answer, req.message)

        # Final cleanup to ensure no formatting artifacts remain
        answer = clean_response_format(answer)
        
        # Check if answer is empty or too short
        if not answer or len(answer.split()) < 5:
            logger.warning(f"Received very short or empty answer: '{answer}'")
            answer = "I apologize, but I couldn't generate a complete response. Let me try a different approach. Could you please rephrase your question about financial services technology?"
        
        # Analyze sentiment and topics
        sentiment = analyze_sentiment(req.message)
        topics = extract_topics(req.message)
        
        # Update conversation memory
        memory.add_exchange(req.message, answer, sentiment, topics)
        
        
        # Classify intent for lead form decision
        intent = classify_intent(req.message)
        
        # Determine if we should show the form
        show_form = memory.should_show_form(intent)
        
        # Add logging for troubleshooting
        logger.info(f"Session ID: {sid}, Detected topics: {topics}")
        logger.info(f"Intent scores: {intent}")
        logger.info(f"Show form: {show_form}")
        logger.info(f"Memory interaction count: {memory.interaction_count}")
        
        return ChatResponse(
            reply=answer,
            show_form=show_form,
            session_id=sid,
            sources=sources,
            suggested_questions=[]  # Return an empty list instead
        )
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)  # Add exc_info=True for full stack trace
        raise HTTPException(status_code=500, detail=f"Error processing chat request: {str(e)}")

        
# ─── LEAD CAPTURE ENDPOINT ─────────────────────────────────────────────────────
@app.post("/lead", response_model=LeadResponse)
async def lead_capture(req: LeadRequest):
    try:
        logger.info(f"New lead: {req.name} <{req.email}> from {req.company or 'N/A'}")
        
        # Enhanced financial services lead generation
        # Get conversation memory if available
        sid = None
        for session_id, memory in sessions.items():
            if memory.messages and any(msg["content"] and req.email in msg["content"] for msg in memory.messages):
                sid = session_id
                break
        
        # Generate lead email with financial context
        email_content = ""
        if sid and sid in sessions:
            email_content = generate_lead_email(sessions[sid])
            logger.info(f"Generated contextual lead email for session {sid[:8]}...")
        else:
            # Basic lead email without conversation context
            email_content = f"""
            New Financial Services Lead from Chatbot
            
            Contact Information:
            - Name: {req.name}
            - Email: {req.email}
            - Company: {req.company or 'Not provided'}
            - Industry: {req.industry or 'Not provided'}
            - Job Title: {req.job_title or 'Not provided'}
            
            Message:
            {req.message or 'No message provided'}
            """
        
        # Create lead data dictionary
        lead_data = {
            "name": req.name,
            "email": req.email,
            "company": req.company,
            "job_title": req.job_title,
            "industry": req.industry,
            "company_size": req.company_size if hasattr(req, 'company_size') else None,
            "message": req.message
        }
        
        # Send email notification
        try:
            # Try to import and use email service
            try:
                from email_service import send_lead_notification
                email_sent = send_lead_notification(lead_data, email_content)
            except ImportError:
                # Try sendgrid if email_service isn't available
                try:
                    from sendgrid_service import send_lead_notification
                    email_sent = send_lead_notification(lead_data, email_content)
                except ImportError:
                    logger.warning("No email service module found. Email notification not sent.")
                    email_sent = False
            
            if not email_sent:
                logger.warning(f"Failed to send email notification for lead {req.email}")
        except Exception as e:
            logger.warning(f"Error sending email notification: {str(e)}")
        
        logger.info(f"Lead {req.email} successfully processed")
        
        return LeadResponse(
            status="ok",
            message="Thank you! A financial services expert from our team will be in touch with you shortly."
        )
    except Exception as e:
        logger.error(f"Lead capture error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing lead: {str(e)}")

# ─── SESSION MANAGEMENT ENDPOINT ────────────────────────────────────────────────
@app.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
        return {"status": "ok", "message": f"Session {session_id} cleared"}
    else:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

# Make it visible externally by default
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
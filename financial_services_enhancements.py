#!/usr/bin/env python3
"""
Financial Services Enhancements for Anaptyss Chatbot

This module extends the core chatbot functionality with specialized
financial services domain knowledge, terminology, and response patterns.
"""

import json
import re
from typing import List, Dict, Any, Optional
from openai import OpenAI

# Financial industry terminology and definitions
FINANCIAL_TERMS = {
    "Basel III": "A global regulatory framework for more resilient banks and banking systems, addressing capital adequacy, stress testing, and market liquidity risk.",
    "GDPR": "General Data Protection Regulation that standardizes data protection law across the EU and addresses the export of personal data outside the EU.",
    "PCI-DSS": "Payment Card Industry Data Security Standard - security standards for organizations that handle branded credit cards.",
    "KYC": "Know Your Customer - the process of verifying the identity of your clients and assessing their suitability, along with potential risks of illegal intentions.",
    "AML": "Anti-Money Laundering - regulations designed to prevent criminals from disguising illegally obtained funds as legitimate income.",
    "Core Banking": "A back-end system that processes daily banking transactions and posts updates to accounts and financial records.",
    "Digital Transformation": "The integration of digital technology into all areas of a business, fundamentally changing how organizations operate and deliver value to customers.",
    "GRC": "Governance, Risk, and Compliance - a structured approach to aligning IT with business objectives while managing risk and meeting compliance requirements.",
    "Model Risk Management (MRM)": "The practice of managing potential adverse consequences from decisions based on incorrect or misused financial models.",
    "Open Banking": "Banking practice that provides third-party financial service providers with access to consumer banking, transaction, and other data from banks and NBFIs."
}

# Financial services industry challenges
INDUSTRY_CHALLENGES = {
    "regulatory_compliance": {
        "title": "Regulatory Compliance",
        "description": "Financial institutions face increasingly complex regulations across jurisdictions, requiring sophisticated systems to ensure compliance.",
        "recommendations": [
            "Implement automated compliance monitoring and reporting systems",
            "Establish a centralized regulatory change management platform",
            "Adopt AI-based anomaly detection for suspicious transactions"
        ]
    },
    "digital_transformation": {
        "title": "Digital Transformation",
        "description": "Traditional financial institutions must modernize legacy systems while maintaining security and operational integrity.",
        "recommendations": [
            "Develop a phased modernization roadmap with clear business outcomes",
            "Implement API-first architecture for system integration",
            "Prioritize customer-facing digital experiences for quick wins"
        ]
    },
    "cybersecurity": {
        "title": "Cybersecurity & Data Protection",
        "description": "Financial services are prime targets for cyber attacks, requiring robust security measures to protect sensitive data.",
        "recommendations": [
            "Implement zero-trust security architecture",
            "Conduct regular penetration testing and vulnerability assessments",
            "Deploy AI-based threat detection systems for proactive defense"
        ]
    },
    "customer_experience": {
        "title": "Customer Experience",
        "description": "Meeting rising customer expectations for seamless, personalized financial services across channels.",
        "recommendations": [
            "Deploy omnichannel platforms with consistent user experience",
            "Leverage AI for personalized financial recommendations",
            "Implement real-time customer data platforms for unified profiles"
        ]
    },
    "data_analytics": {
        "title": "Data Analytics & AI",
        "description": "Harnessing vast data assets to drive insights, improve decision-making, and create competitive advantage.",
        "recommendations": [
            "Establish a centralized data lake with governance controls",
            "Implement predictive analytics for risk management and customer behavior",
            "Deploy machine learning for process automation and fraud detection"
        ]
    }
}

# Common financial service client personas
CLIENT_PERSONAS = {
    "retail_bank": {
        "name": "Regional Retail Bank",
        "challenges": ["legacy systems", "digital competition", "customer retention"],
        "goals": ["modernize core banking", "enhance digital channels", "improve customer experience"]
    },
    "investment_firm": {
        "name": "Investment Management Firm",
        "challenges": ["data fragmentation", "regulatory reporting", "client acquisition"],
        "goals": ["unified data platform", "automated compliance", "personalized client portal"]
    },
    "insurance_provider": {
        "name": "Insurance Provider",
        "challenges": ["risk assessment", "claims processing", "fraud detection"],
        "goals": ["AI-driven underwriting", "automated claims processing", "predictive risk modeling"]
    },
    "wealth_manager": {
        "name": "Wealth Management Firm",
        "challenges": ["portfolio optimization", "client reporting", "advisor productivity"],
        "goals": ["client insights platform", "automated reporting", "advisor dashboard"]
    }
}

class FinancialServicesEnhancer:
    """Enhances chatbot responses with financial services domain expertise."""
    
    def __init__(self, openai_client: OpenAI):
        """Initialize with OpenAI client."""
        self.openai_client = openai_client
    
    def detect_financial_topics(self, query: str) -> List[str]:
        """Detect financial services topics in the query."""
        topic_keywords = {
            "regulatory_compliance": ["regulation", "compliance", "basel", "gdpr", "kyc", "aml"],
            "digital_transformation": ["digital", "transformation", "modernize", "legacy"],
            "cybersecurity": ["security", "cyber", "threat", "protection", "hack"],
            "customer_experience": ["customer", "experience", "satisfaction", "journey"],
            "data_analytics": ["analytics", "data", "insights", "prediction", "ai", "ml"]
        }
        
        detected_topics = []
        query_lower = query.lower()
        
        for topic, keywords in topic_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_topics.append(topic)
        
        return detected_topics
    
    def identify_client_persona(self, query: str, conversation_history: List[Dict]) -> Optional[str]:
        """Identify the most relevant client persona based on query and conversation history."""
        # Extract all user messages
        user_messages = [msg["content"] for msg in conversation_history if msg["role"] == "user"]
        all_user_text = " ".join([query] + user_messages).lower()
        
        # Score each persona based on mentioned challenges and goals
        persona_scores = {}
        for persona_id, persona in CLIENT_PERSONAS.items():
            score = 0
            for challenge in persona["challenges"]:
                if challenge.lower() in all_user_text:
                    score += 2
            for goal in persona["goals"]:
                if goal.lower() in all_user_text:
                    score += 2
            
            # Add score for explicit mention of the persona type
            if persona_id.replace("_", " ") in all_user_text:
                score += 5
            
            persona_scores[persona_id] = score
        
        # Return the highest scoring persona, if any score > 0
        max_score = max(persona_scores.values()) if persona_scores else 0
        if max_score > 0:
            return max(persona_scores.items(), key=lambda x: x[1])[0]
        
        return None
    
    def enhance_response(self, query: str, response: str, conversation_history: List[Dict]) -> str:
        """Enhance the response with financial services expertise."""
        # Detect financial topics in the query
        topics = self.detect_financial_topics(query)
        
        # If no financial topics detected, return original response
        if not topics:
            return response
        
        # Identify client persona
        persona_id = self.identify_client_persona(query, conversation_history)
        persona_context = ""
        if persona_id:
            persona = CLIENT_PERSONAS[persona_id]
            persona_context = f"""
Client Persona: {persona['name']}
Key Challenges: {', '.join(persona['challenges'])}
Business Goals: {', '.join(persona['goals'])}
"""
        
        # Gather industry challenges and recommendations
        challenges_context = ""
        for topic in topics:
            if topic in INDUSTRY_CHALLENGES:
                challenge = INDUSTRY_CHALLENGES[topic]
                challenges_context += f"""
Topic: {challenge['title']}
Description: {challenge['description']}
Recommendations:
- {challenge['recommendations'][0]}
- {challenge['recommendations'][1]}
- {challenge['recommendations'][2]}
"""
        
        # Check if any financial terms need explanation
        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        term_explanations = ""
        terms_to_explain = []
        
        for term, explanation in FINANCIAL_TERMS.items():
            if term.lower() in query.lower() or any(word in term.lower() for word in query_words):
                terms_to_explain.append(f"{term}: {explanation}")
        
        if terms_to_explain:
            term_explanations = "Financial Terms Context:\n" + "\n".join(terms_to_explain)
        
        # Enhance response with financial services expertise
        if topics or persona_id or terms_to_explain:
            enhancement_prompt = f"""
You are an executive consultant for the financial services industry. Respond directly to this query about {', '.join(topics)}.

{persona_context}

{challenges_context}

{term_explanations}

When responding to the query: {query}

Follow these guidelines:
1. Start with a concise executive summary if the topic is complex
2. Provide industry-specific insights tailored to financial services
3. Include practical recommendations when appropriate
4. Use financial terminology correctly and professionally
5. Maintain a direct, executive-level tone
6. Be specific and actionable, avoiding generic statements
7. Do NOT use section headers like "Executive Summary:" or "Response:"
8. Never refer to "the user" or use phrases like "to address your query"
9. Write in a natural, conversational style as if speaking directly to a financial executive

Respond directly:
{response}
"""
            
            try:
                enhanced_result = self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": enhancement_prompt}],
                    temperature=0.5
                )
                
                enhanced_response = enhanced_result.choices[0].message.content
                
                # Clean up any formatting artifacts
                enhanced_response = enhanced_response.replace("**Executive Summary:**", "## Executive Summary")
                enhanced_response = enhanced_response.replace("**Response:**", "")
                
                # Remove any other artifacts
                artifacts = ["To address the user query", "To address your query", "In response to your question"]
                for artifact in artifacts:
                    enhanced_response = enhanced_response.replace(artifact, "")
                
                return enhanced_response
            except Exception as e:
                print(f"Error enhancing response: {str(e)}")
                return response
        
        return response
    
    def generate_financial_expertise_prompt(self, topics: List[str]) -> str:
        """Generate domain expertise context for specific financial topics."""
        expertise_context = "Financial Services Context:\n\n"
        
        for topic in topics:
            if topic in INDUSTRY_CHALLENGES:
                challenge = INDUSTRY_CHALLENGES[topic]
                expertise_context += f"# {challenge['title']}\n\n"
                expertise_context += f"{challenge['description']}\n\n"
                expertise_context += "Best practices:\n"
                for rec in challenge['recommendations']:
                    expertise_context += f"- {rec}\n"
                expertise_context += "\n"
        
        return expertise_context
    
    def extract_financial_insights(self, text: str) -> Dict[str, Any]:
        """Extract financial insights from text to guide response generation."""
        insight_prompt = f"""
Analyze this text from a financial services perspective and extract key insights:

Text: {text}

Please identify and return a JSON object with:
1. industry_vertical (e.g., banking, insurance, wealth management, payments)
2. use_cases (list of potential use cases mentioned)
3. challenges (list of business challenges mentioned)
4. technologies (list of technologies mentioned)
5. regulatory_concerns (list of regulations or compliance issues mentioned)

Example format:
{{
    "industry_vertical": "retail banking",
    "use_cases": ["customer onboarding", "fraud detection"],
    "challenges": ["legacy system integration", "regulatory compliance"],
    "technologies": ["AI", "cloud migration", "APIs"],
    "regulatory_concerns": ["KYC", "GDPR", "Basel III"]
}}

JSON response:
"""

        try:
            insight_result = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": insight_prompt}],
                temperature=0.1
            )
            
            insights_text = insight_result.choices[0].message.content
            # Extract JSON from the response
            json_match = re.search(r'({.*})', insights_text, re.DOTALL)
            if json_match:
                try:
                    insights = json.loads(json_match.group(1))
                    return insights
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            print(f"Error extracting financial insights: {str(e)}")
        
        # Return empty default structure if extraction fails
        return {
            "industry_vertical": "",
            "use_cases": [],
            "challenges": [],
            "technologies": [],
            "regulatory_concerns": []
        }
    
    def generate_executive_summary(self, query: str, response: str) -> str:
        """Generate an executive summary of the response for busy executives."""
        summary_prompt = f"""
Create a brief executive summary (2-3 bullet points) of the following information for a financial services executive.
Focus on strategic insights, business impact, and actionable recommendations.

Query: {query}
Response: {response}
"""

        try:
            summary_result = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3
            )
            
            summary = summary_result.choices[0].message.content
            
            # Only add if response is lengthy
            if len(response.split()) > 150:
                # Ensure proper formatting
                if "**Executive Summary:**" in summary:
                    summary = summary.replace("**Executive Summary:**", "## Executive Summary")
                
                # Check if it already has a header
                if not summary.startswith("## Executive Summary"):
                    summary = "## Executive Summary\n" + summary
                
                return f"{summary}\n\n{response}"
            return response
        except Exception as e:
            print(f"Error generating executive summary: {str(e)}")
            return response

# Function to integrate with main.py
def cleanup_formatting_artifacts(text: str) -> str:
    """Aggressively clean up formatting artifacts from the response."""
    # Remove common formatting markers
    cleaned_text = text
    
    # Remove Executive Summary marker variants
    cleaned_text = re.sub(r'\*\*Executive Summary:\*\*', '## Executive Summary', cleaned_text)
    cleaned_text = re.sub(r'\*\*Executive Summary\*\*', '## Executive Summary', cleaned_text)
    cleaned_text = re.sub(r'Executive Summary:', '## Executive Summary', cleaned_text)
    
    # Make sure there's no nested formatting (like **## Executive Summary**)
    cleaned_text = re.sub(r'\*\*## Executive Summary\*\*', '## Executive Summary', cleaned_text)
    
    # Remove Response marker variants
    cleaned_text = re.sub(r'\*\*Response:\*\*', '', cleaned_text)
    cleaned_text = re.sub(r'\*\*Response\*\*', '', cleaned_text)
    cleaned_text = re.sub(r'Response:', '', cleaned_text)
    
    # Remove meta-text phrases
    phrases_to_remove = [
        "To address the user query",
        "To address your query",
        "In response to your question",
        "In this response, I will address",
        "As requested, here is information about",
        "Below is information about",
        "Let me provide you with information on",
        "As you asked about",
        "To answer your question about"
    ]
    
    for phrase in phrases_to_remove:
        cleaned_text = cleaned_text.replace(phrase, "")
    
    # Remove any double line breaks that might have been created
    cleaned_text = re.sub(r'\n\n\n+', '\n\n', cleaned_text)
    
    # If Executive Summary was removed without proper formatting, add it back
    if cleaned_text.lstrip().startswith("•") or cleaned_text.lstrip().startswith("-"):
        if "## Executive Summary" not in cleaned_text:
            cleaned_text = "## Executive Summary\n" + cleaned_text
    
    return cleaned_text

def enhance_financial_response(openai_client, query, response, conversation_history):
    """Wrapper function to enhance responses with financial services expertise."""
    enhancer = FinancialServicesEnhancer(openai_client)
    
    # Check for duplicate response by comparing to recent messages
    if conversation_history and len(conversation_history) >= 2:
        recent_responses = [msg["content"] for msg in conversation_history 
                           if msg["role"] == "assistant"]
        
        if recent_responses and response.strip() == recent_responses[-1].strip():
            # If duplicate, create a variation instead
            try:
                variation_prompt = f"""
                The user has asked about {query} and received this response:
                
                {response}
                
                Please create a VARIATION of this response with the same information but phrased differently.
                The response should be in the same style and cover the same topics but use different wording and structure.
                """
                
                variation_result = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": variation_prompt}],
                    temperature=0.7
                )
                
                enhanced_response = variation_result.choices[0].message.content
            except Exception as e:
                print(f"Error creating response variation: {str(e)}")
                # If error, still use the enhanced version
                enhanced_response = enhancer.enhance_response(query, response, conversation_history)
        else:
            enhanced_response = enhancer.enhance_response(query, response, conversation_history)
    else:
        enhanced_response = enhancer.enhance_response(query, response, conversation_history)
    
    # Apply aggressive cleanup to remove any formatting artifacts
    enhanced_response = cleanup_formatting_artifacts(enhanced_response)
    
    return enhanced_response
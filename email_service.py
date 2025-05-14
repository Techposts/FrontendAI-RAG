"""
Email service for Anaptyss Chat system.
Handles sending lead notifications via SMTP.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Email configuration from environment variables
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "leads@anaptyss.com")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "chatbot@anaptyss.com")

def send_lead_notification(lead_data, conversation_context=None):
    """
    Send a lead notification email.
    
    Args:
        lead_data (dict): Information about the lead
        conversation_context (str, optional): Context from the conversation
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.error("SMTP credentials not configured. Cannot send email.")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = NOTIFICATION_EMAIL
        msg['Subject'] = f"New Financial Services Lead: {lead_data.get('name')} from {lead_data.get('company')}"
        
        # Build email body
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #1a4f91;">New Financial Services Lead from AnaptIQ Chatbot</h2>
            
            <h3 style="margin-top: 20px;">Contact Information:</h3>
            <ul>
                <li><strong>Name:</strong> {lead_data.get('name', 'Not provided')}</li>
                <li><strong>Email:</strong> {lead_data.get('email', 'Not provided')}</li>
                <li><strong>Company:</strong> {lead_data.get('company', 'Not provided')}</li>
                <li><strong>Job Title:</strong> {lead_data.get('job_title', 'Not provided')}</li>
                <li><strong>Industry:</strong> {lead_data.get('industry', 'Not provided')}</li>
                <li><strong>Company Size:</strong> {lead_data.get('company_size', 'Not provided')}</li>
            </ul>
            
            <h3 style="margin-top: 20px;">Message:</h3>
            <p style="padding: 10px; background-color: #f5f5f5; border-left: 4px solid #1a4f91;">
                {lead_data.get('message', 'No message provided')}
            </p>
        """
        
        # Add conversation context if available
        if conversation_context:
            body += f"""
            <h3 style="margin-top: 20px;">Conversation Context:</h3>
            <p style="padding: 10px; background-color: #f5f5f5; border-left: 4px solid #0051a8; white-space: pre-line;">
                {conversation_context}
            </p>
            """
        
        body += """
            <p style="margin-top: 30px; font-size: 12px; color: #666;">
                This lead was captured via the AnaptIQ Financial Services Chatbot. 
                Please follow up within 24 hours.
            </p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Connect to server and send
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Lead notification email sent successfully to {NOTIFICATION_EMAIL}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send lead notification email: {str(e)}")
        return False

def test_email_connection():
    """Test the SMTP connection and credentials."""
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.error("SMTP credentials not configured. Cannot test connection.")
        return False
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.quit()
        logger.info("SMTP connection test successful")
        return True
    except Exception as e:
        logger.error(f"SMTP connection test failed: {str(e)}")
        return False

if __name__ == "__main__":
    # Run a test if this file is executed directly
    print("Testing email configuration...")
    result = test_email_connection()
    
    if result:
        print("✅ SMTP connection successful! Email sending is configured correctly.")
        
        # Send a test email
        test_data = {
            "name": "Test User",
            "email": "test@example.com",
            "company": "Test Company",
            "job_title": "Test Position",
            "industry": "Banking",
            "message": "This is a test message from the email service test."
        }
        
        test_context = """
        User asked about: Digital transformation in banking
        Topics discussed: Core banking modernization, API integration, Cloud migration
        Sentiment: Positive
        """
        
        print("Sending test email...")
        if send_lead_notification(test_data, test_context):
            print("✅ Test email sent successfully!")
        else:
            print("❌ Failed to send test email.")
    else:
        print("❌ SMTP connection failed! Please check your email configuration.")

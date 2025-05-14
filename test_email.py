#!/usr/bin/env python3
"""
Test script for Email Configuration in Anaptyss Chat System
This script tests the email configuration by sending a test email.
"""

import os
import json
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def check_env_vars():
    """Check if email environment variables are properly configured."""
    print("\n=== Checking Email Configuration ===")
    
    # Check if any email configuration is present
    smtp_configured = os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD")
    sendgrid_configured = os.getenv("SENDGRID_API_KEY")
    
    if not smtp_configured and not sendgrid_configured:
        print("❌ No email configuration found in .env file.")
        print("Please configure either SMTP or SendGrid settings.")
        return False
    
    # Check SMTP configuration
    if os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD"):
        print("✅ SMTP configuration found")
        print(f"  - SMTP Server: {os.getenv('SMTP_SERVER', 'Not set')}")
        print(f"  - SMTP Port: {os.getenv('SMTP_PORT', 'Not set')}")
        print(f"  - SMTP Username: {os.getenv('SMTP_USERNAME')[:3]}{'*' * 10}")
        print(f"  - SMTP Password: {'*' * 8}")
    else:
        print("ℹ️ SMTP configuration not found or incomplete")
    
    # Check SendGrid configuration
    if os.getenv("SENDGRID_API_KEY"):
        print("✅ SendGrid configuration found")
        print(f"  - SendGrid API Key: {os.getenv('SENDGRID_API_KEY')[:5]}{'*' * 10}")
    else:
        print("ℹ️ SendGrid configuration not found")
    
    # Check common configuration
    if os.getenv("NOTIFICATION_EMAIL"):
        print(f"✅ Notification email set to: {os.getenv('NOTIFICATION_EMAIL')}")
    else:
        print("❌ NOTIFICATION_EMAIL not set in .env file")
        return False
    
    if os.getenv("SENDER_EMAIL"):
        print(f"✅ Sender email set to: {os.getenv('SENDER_EMAIL')}")
    else:
        print("❌ SENDER_EMAIL not set in .env file")
        return False
    
    return True

def test_smtp_connection():
    """Test SMTP connection using credentials in .env file."""
    if not (os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD")):
        return False
    
    import smtplib
    
    print("\n=== Testing SMTP Connection ===")
    
    try:
        # Get configuration from .env
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_username = os.getenv("SMTP_USERNAME")
        smtp_password = os.getenv("SMTP_PASSWORD")
        
        # Connect to SMTP server
        print(f"Connecting to {smtp_server}:{smtp_port}...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        
        # Login
        print("Logging in...")
        server.login(smtp_username, smtp_password)
        
        # Close connection
        server.quit()
        
        print("✅ SMTP connection test successful!")
        return True
    
    except Exception as e:
        print(f"❌ SMTP connection test failed: {str(e)}")
        return False

def test_sendgrid_connection():
    """Test SendGrid API connection using API key in .env file."""
    if not os.getenv("SENDGRID_API_KEY"):
        return False
    
    print("\n=== Testing SendGrid Connection ===")
    
    try:
        # Import and use sendgrid
        from sendgrid import SendGridAPIClient
        
        # Get API key
        api_key = os.getenv("SENDGRID_API_KEY")
        
        # Initialize client
        print("Connecting to SendGrid API...")
        sg = SendGridAPIClient(api_key)
        
        # Make a simple API call to test
        response = sg.client.suppression.blocks.get()
        
        if response.status_code == 200:
            print("✅ SendGrid connection test successful!")
            return True
        else:
            print(f"❌ SendGrid API returned status code: {response.status_code}")
            return False
    
    except ImportError:
        print("❌ SendGrid package not installed. Install with: pip install sendgrid")
        return False
    except Exception as e:
        print(f"❌ SendGrid connection test failed: {str(e)}")
        return False

def test_send_email():
    """Test sending an email using configured method."""
    print("\n=== Testing Email Sending ===")
    
    # Sample lead data
    test_data = {
        "name": "Test User",
        "email": "test@example.com",
        "company": "Test Company",
        "job_title": "Financial Analyst",
        "industry": "Banking",
        "company_size": "1001-5000",
        "message": "This is a test message to verify email configuration."
    }
    
    # Sample conversation context
    test_context = """
    User asked about: Digital transformation in banking
    Topics discussed: Core banking modernization, API integration, Cloud migration
    Sentiment: Positive
    Interaction count: 5
    """
    
    # Try SMTP first if configured
    if os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD"):
        print("Testing email sending using SMTP...")
        try:
            # Import only when needed
            import email_service
            
            # Send test email
            if email_service.send_lead_notification(test_data, test_context):
                print("✅ Test email sent successfully using SMTP!")
                return True
            else:
                print("❌ Failed to send test email using SMTP")
        except ImportError:
            print("❌ email_service.py not found. Make sure the file exists in the current directory.")
            return False
        except Exception as e:
            print(f"❌ Error sending email via SMTP: {str(e)}")
    
    # Try SendGrid if configured
    elif os.getenv("SENDGRID_API_KEY"):
        print("Testing email sending using SendGrid...")
        try:
            # Import only when needed
            import sendgrid_service
            
            # Send test email
            if sendgrid_service.send_lead_notification(test_data, test_context):
                print("✅ Test email sent successfully using SendGrid!")
                return True
            else:
                print("❌ Failed to send test email using SendGrid")
        except ImportError:
            print("❌ sendgrid_service.py not found. Make sure the file exists in the current directory.")
            return False
        except Exception as e:
            print(f"❌ Error sending email via SendGrid: {str(e)}")
    
    else:
        print("❌ No email configuration available")
    
    return False

def test_lead_capture():
    """Simulates a lead form submission and tests if email is triggered."""
    print("\n=== Testing Lead Form Submission Email ===")
    
    try:
        import requests
        import json
        
        # Sample lead data
        lead_data = {
            "name": "Test Lead User",
            "email": "testlead@example.com",
            "company": "Test Financial Company",
            "job_title": "CTO", 
            "industry": "banking",
            "message": "I'm interested in learning more about your core banking modernization solutions."
        }
        
        # Send request to lead endpoint
        print("Submitting test lead to /lead endpoint...")
        response = requests.post(
            "http://localhost:8000/lead",
            headers={"Content-Type": "application/json"},
            data=json.dumps(lead_data)
        )
        
        # Check response
        if response.status_code == 200:
            print("✅ Lead submission successful!")
            print("   If email configuration is correct, you should receive a notification.")
            print("   Response:", response.json())
            return True
        else:
            print(f"❌ Lead submission failed. Status code: {response.status_code}")
            print("   Response:", response.text)
            return False
    
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the API server. Make sure it's running on port 8000.")
        return False
    except Exception as e:
        print(f"❌ Error submitting lead: {str(e)}")
        return False

def main():
    """Main function to run all tests."""
    print("🧪 Email Configuration Test for Anaptyss Chat System")
    print("===================================================")
    
    # Check if email configuration is present in .env
    if not check_env_vars():
        print("\n❌ Email configuration incomplete. Please update your .env file.")
        return 1
    
    # Test SMTP connection if configured
    if os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD"):
        test_smtp_connection()
    
    # Test SendGrid connection if configured
    if os.getenv("SENDGRID_API_KEY"):
        test_sendgrid_connection()
    
    # Test sending an email
    email_sent = test_send_email()
    
    if email_sent:
        print("\n✅ Email configuration is working correctly!")
        
        # Ask if user wants to test lead form submission
        answer = input("\nDo you want to test lead form submission? (y/n): ")
        if answer.lower() == 'y':
            test_lead_capture()
    else:
        print("\n❌ Email sending failed. Please check your configuration.")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())

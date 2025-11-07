"""
WhatsApp Integration via Twilio
Enables customers to interact with the AI agent via WhatsApp.
"""

from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from typing import Optional
import asyncio

from config.settings import settings
from agents.sales_agent import get_sales_agent
from agents.state import create_initial_state
from config.supabase_config import save_conversation, load_conversation


class WhatsAppHandler:
    """Handles WhatsApp messages via Twilio."""
    
    def __init__(self):
        if settings.twilio_account_sid and settings.twilio_auth_token:
            self.client = Client(
                settings.twilio_account_sid,
                settings.twilio_auth_token
            )
            self.whatsapp_number = settings.twilio_whatsapp_number
            self.enabled = True
            print("✅ WhatsApp integration enabled")
        else:
            self.client = None
            self.enabled = False
            print("⚠️  WhatsApp integration disabled (no Twilio credentials)")
        
        self.sales_agent = get_sales_agent()
        self.sessions = {}  # In-memory session store
    
    async def handle_incoming_message(
        self,
        from_number: str,
        message_body: str,
        media_url: Optional[str] = None
    ) -> str:
        """
        Handle incoming WhatsApp message.
        
        Args:
            from_number: Sender's WhatsApp number
            message_body: Message text
            media_url: URL of any media attached (optional)
        
        Returns:
            Response message to send back
        """
        
        # Get or create session
        session_id = f"whatsapp_{from_number}"
        
        # Try to load existing conversation
        state = load_conversation(session_id)
        
        if state is None:
            # Create new state
            state = create_initial_state(
                session_id=session_id,
                channel="whatsapp"
            )
        
        # Process message
        try:
            result = await self.sales_agent.process_message(
                message=message_body,
                state=state,
                session_id=session_id,
                channel="whatsapp"
            )
            
            # Save conversation
            save_conversation(session_id, result["state"])
            
            response_text = result["response"]
            
            # Add suggestions if available
            if result.get("suggestions"):
                response_text += "\n\n" + "Quick replies:\n"
                for i, suggestion in enumerate(result["suggestions"][:3], 1):
                    response_text += f"{i}. {suggestion}\n"
            
            return response_text
            
        except Exception as e:
            print(f"Error processing WhatsApp message: {e}")
            return "Sorry, I encountered an error. Please try again."
    
    def send_message(self, to_number: str, message: str) -> bool:
        """
        Send a WhatsApp message.
        
        Args:
            to_number: Recipient's WhatsApp number
            message: Message to send
        
        Returns:
            True if sent successfully, False otherwise
        """
        
        if not self.enabled:
            print("WhatsApp is not enabled")
            return False
        
        try:
            message = self.client.messages.create(
                from_=self.whatsapp_number,
                body=message,
                to=to_number
            )
            
            return message.sid is not None
            
        except Exception as e:
            print(f"Error sending WhatsApp message: {e}")
            return False


# Global handler instance
whatsapp_handler = WhatsAppHandler()


# ===== FastAPI Routes =====

def setup_whatsapp_routes(app: FastAPI):
    """Add WhatsApp webhook routes to FastAPI app."""
    
    @app.post("/webhook/whatsapp")
    async def whatsapp_webhook(
        From: str = Form(...),
        Body: str = Form(...),
        MediaUrl0: Optional[str] = Form(None)
    ):
        """
        Twilio WhatsApp webhook endpoint.
        Receives incoming messages from WhatsApp.
        """
        
        if not whatsapp_handler.enabled:
            return Response(content="WhatsApp not configured", status_code=503)
        
        # Process message
        response_text = await whatsapp_handler.handle_incoming_message(
            from_number=From,
            message_body=Body,
            media_url=MediaUrl0
        )
        
        # Create TwiML response
        resp = MessagingResponse()
        resp.message(response_text)
        
        return Response(content=str(resp), media_type="application/xml")
    
    @app.get("/whatsapp/status")
    async def whatsapp_status():
        """Check WhatsApp integration status."""
        
        return {
            "enabled": whatsapp_handler.enabled,
            "number": whatsapp_handler.whatsapp_number if whatsapp_handler.enabled else None,
            "message": "WhatsApp integration is active" if whatsapp_handler.enabled else "WhatsApp integration disabled"
        }


if __name__ == "__main__":
    print("""
    ============================================
    📱 WhatsApp Integration Setup Instructions
    ============================================
    
    1. Create a Twilio Account:
       https://www.twilio.com/try-twilio
    
    2. Get your WhatsApp Sandbox:
       - Go to: https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
       - Join the sandbox by sending a code to Twilio's WhatsApp number
    
    3. Configure your .env file:
       TWILIO_ACCOUNT_SID=your_account_sid
       TWILIO_AUTH_TOKEN=your_auth_token
       TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
    
    4. Set up Webhook URL:
       - Use ngrok to expose your local server:
         ngrok http 8000
       
       - Copy the ngrok URL and add to Twilio:
         https://your-ngrok-url.ngrok.io/webhook/whatsapp
    
    5. Test:
       - Send a message to your WhatsApp sandbox number
       - The AI agent should respond!
    
    ============================================
    """)

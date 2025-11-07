"""
Post-Purchase Toolkit - Returns, exchanges, support, and feedback
Provides a specialist agent that can use a toolkit of support functions.
"""

import uuid
from typing import Dict, List, Optional, Literal
from datetime import datetime, timedelta
from enum import Enum
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# --- NEW: Imports for building the specialist agent ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langgraph.graph import MessagesState
from config.settings import settings, AgentConfig


# --- Data Models (Enums) ---
class ReturnReason(str, Enum):
    """Return request reasons."""
    SIZE_ISSUE = "size_issue"
    QUALITY_ISSUE = "quality_issue"
    DAMAGED = "damaged"
    WRONG_ITEM = "wrong_item"
    DESCRIPTION_MISMATCH = "description_mismatch"
    CHANGED_MIND = "changed_mind"
    BETTER_PRICE = "better_price"
    OTHER = "other"

class SupportTicketCategory(str, Enum):
    """Support ticket categories."""
    ORDER_ISSUE = "order_issue"
    DELIVERY_ISSUE = "delivery_issue"
    PAYMENT_ISSUE = "payment_issue"
    PRODUCT_QUESTION = "product_question"
    ACCOUNT_ISSUE = "account_issue"
    GENERAL_INQUIRY = "general_inquiry"

# --- In-Memory Database Simulation ---
_return_requests: Dict[str, Dict] = {}
_support_tickets: Dict[str, Dict] = {}

# Return policy constants
RETURN_WINDOW_DAYS = 30
REFUND_PROCESSING_DAYS = 7

# --- NEW: Initialize LLM (Module-level) ---
LLM = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.google_api_key,
    temperature=AgentConfig.TEMPERATURE
)

# --- Pydantic Schemas for Tool Arguments ---

class ReturnItem(BaseModel):
    sku: str = Field(description="The SKU of the item to return")
    quantity: int = Field(description="The quantity of this item to return")
    price: float = Field(description="The original price paid per item")

class ReturnSchema(BaseModel):
    """Input schema for initiating a return."""
    order_id: str = Field(description="The order ID the items are from.")
    customer_id: str = Field(description="The customer's unique ID.")
    items: List[ReturnItem] = Field(description="A list of items to be returned.")
    reason: ReturnReason = Field(description="The reason for the return.")
    comments: Optional[str] = Field(default=None, description="Optional customer comments.")
    images: Optional[List[str]] = Field(default_factory=list, description="List of URLs to images of the item.")

class SupportTicketSchema(BaseModel):
    """Input schema for creating a support ticket."""
    customer_id: str = Field(description="The customer's unique ID.")
    category: SupportTicketCategory = Field(description="The category of the support issue.")
    subject: str = Field(description="A brief subject line for the ticket.")
    description: str = Field(description="A detailed description of the customer's issue.")
    order_id: Optional[str] = Field(default=None, description="The related order ID, if any.")
    priority: Literal["low", "medium", "high"] = Field(default="medium", description="The priority of the ticket.")


# --- Post-Purchase Tools ---

@tool(args_schema=ReturnSchema)
def initiate_return(
    order_id: str,
    customer_id: str,
    items: List[Dict], # Pydantic v1 can auto-coerce
    reason: str,
    comments: Optional[str] = None,
    images: Optional[List[str]] = None
) -> Dict:
    """
    Initiate a return request for one or more items from an order.
    """
    # Convert Pydantic objects to dicts if needed
    if items:
        converted_items = []
        for item in items:
            if hasattr(item, 'model_dump'):
                converted_items.append(item.model_dump())
            elif hasattr(item, 'dict'):
                converted_items.append(item.dict())
            else:
                converted_items.append(item)
        items = converted_items
    
    return_id = f"RET{uuid.uuid4().hex[:10].upper()}"
    refund_amount = sum(item.get("price", 0) * item.get("quantity", 1) for item in items)
    refund_date = datetime.now() + timedelta(days=REFUND_PROCESSING_DAYS)

    return_request = {
        "return_id": return_id, "order_id": order_id, "customer_id": customer_id,
        "items": items, "reason": reason, "comments": comments, "images": images or [],
        "status": "requested", "refund_amount": refund_amount,
        "refund_estimate": {
            "amount": refund_amount,
            "estimated_date": refund_date.strftime("%Y-%m-%d"),
            "business_days": REFUND_PROCESSING_DAYS
        },
        "status_history": [{"status": "requested", "timestamp": datetime.now().isoformat(), "message": "Return request submitted"}],
        "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
    }
    _return_requests[return_id] = return_request
    
    auto_approve_reasons = [ReturnReason.DAMAGED.value, ReturnReason.WRONG_ITEM.value]
    
    if reason in auto_approve_reasons:
        return_request["status"] = "approved"
        return_request["status_history"].append({
            "status": "approved",
            "timestamp": datetime.now().isoformat(),
            "message": "Return approved automatically"
        })
        pickup_scheduled = True
        message = "Your return has been approved! We'll schedule a pickup within 24 hours."
    else:
        pickup_scheduled = False
        message = "Your return request has been submitted and will be reviewed within 24 hours."
    
    return {
        "success": True, "return_id": return_id, "status": return_request["status"],
        "pickup_scheduled": pickup_scheduled,
        "refund_estimate": return_request["refund_estimate"], "message": message
    }

@tool
def get_return_status(return_id: str) -> Optional[Dict]:
    """Get the status of a specific return request using its return_id."""
    return_request = _return_requests.get(return_id)
    
    if not return_request:
        return {"success": False, "message": "Return ID not found."}
    
    return {
        "success": True, "return_id": return_id, "status": return_request["status"],
        "refund_amount": return_request["refund_amount"],
        "refund_estimate": return_request["refund_estimate"],
        "status_history": return_request["status_history"],
    }

@tool(args_schema=SupportTicketSchema)
def create_support_ticket(
    customer_id: str,
    category: str,
    subject: str,
    description: str,
    order_id: Optional[str] = None,
    priority: str = "medium"
) -> Dict:
    """Create a customer support ticket for a complex issue."""
    
    ticket_id = f"TKT{uuid.uuid4().hex[:8].upper()}"
    response_times = {"low": "48 hours", "medium": "24 hours", "high": "4 hours"}
    
    ticket = {
        "ticket_id": ticket_id, "customer_id": customer_id, "category": category,
        "subject": subject, "description": description, "order_id": order_id,
        "priority": priority, "status": "open", "assigned_to": None,
        "messages": [{"from": "customer", "message": description, "timestamp": datetime.now().isoformat()}],
        "estimated_response_time": response_times.get(priority, "24 hours"),
        "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
    }
    _support_tickets[ticket_id] = ticket
    
    return {
        "success": True, "ticket_id": ticket_id, "status": "open",
        "estimated_response_time": ticket["estimated_response_time"],
        "message": f"Support ticket created. Our team will respond within {ticket['estimated_response_time']}."
    }

@tool
def get_faq_answer(question_category: Literal["returns", "shipping", "payment", "account"]) -> List[Dict]:
    """Get FAQ answers for common questions. Use this for general policy questions."""
    
    faqs = {
        "returns": [
            {"question": "What is your return policy?", "answer": "We accept returns within 30 days of delivery. Items must be unused and in original packaging."},
            {"question": "How long does refund take?", "answer": "Refunds are processed within 7 business days after we receive the returned item."},
        ],
        "shipping": [
            {"question": "How long does delivery take?", "answer": "Standard delivery takes 2-5 business days."},
            {"question": "Can I track my order?", "answer": "Yes! You'll receive a tracking number via SMS and email once your order ships."}
        ],
        "payment": [
            {"question": "What payment methods do you accept?", "answer": "We accept UPI, Credit/Debit Cards, Net Banking, Wallets, and Cash on Delivery."}
        ],
        "account": [
            {"question": "How do I earn loyalty points?", "answer": "Earn 1 point for every ₹1 spent. Points can be redeemed for discounts on future purchases."}
        ]
    }
    return faqs.get(question_category, [])

@tool
def list_customer_orders(customer_id: str) -> Dict:
    """List all orders for a specific customer. Use this when customer asks to track 'my order' without specifying order ID."""
    # Import orders from fulfillment agent
    from agents.fulfillment_agent import _orders
    
    customer_orders = [
        {
            "order_id": order_id,
            "status": order["status"],
            "total_amount": order["total_amount"],
            "created_at": order["created_at"],
            "items_count": len(order["items"]),
            "tracking_number": order.get("tracking_number"),
            "estimated_delivery": order.get("estimated_delivery", {})
        }
        for order_id, order in _orders.items()
        if order["customer_id"] == customer_id
    ]
    
    # Sort by creation date (newest first)
    customer_orders.sort(key=lambda x: x["created_at"], reverse=True)
    
    if not customer_orders:
        return {
            "success": False,
            "message": "No orders found for this customer.",
            "orders": []
        }
    
    return {
        "success": True,
        "total_orders": len(customer_orders),
        "orders": customer_orders,
        "message": f"Found {len(customer_orders)} order(s) for this customer."
    }

@tool
def get_order_details(order_id: str) -> Dict:
    """Get full details of a specific order including items, tracking, and delivery info."""
    from agents.fulfillment_agent import _orders
    
    order = _orders.get(order_id)
    if not order:
        return {"success": False, "message": f"Order {order_id} not found. Please check the order ID."}
    
    return {
        "success": True,
        "order_id": order_id,
        "status": order["status"],
        "items": order["items"],
        "total_amount": order["total_amount"],
        "fulfillment_type": order["fulfillment_type"],
        "delivery_address": order.get("delivery_address"),
        "tracking_number": order.get("tracking_number"),
        "shipping_partner": order.get("shipping_partner"),
        "estimated_delivery": order.get("estimated_delivery"),
        "status_history": order.get("status_history", []),
        "created_at": order["created_at"],
        "updated_at": order["updated_at"]
    }

@tool
def track_order_detailed(order_id: str) -> Dict:
    """Get detailed step-by-step tracking information for an order with live location if out for delivery."""
    from agents.fulfillment_agent import _orders, _generate_tracking_events
    import random
    
    order = _orders.get(order_id)
    if not order:
        return {"success": False, "message": f"Order {order_id} not found. Please verify the order ID."}
    
    tracking_events = _generate_tracking_events(order)
    
    live_location = None
    if order["status"] == "out_for_delivery":
        live_location = {
            "latitude": 19.0760 + random.uniform(-0.01, 0.01),
            "longitude": 72.8777 + random.uniform(-0.01, 0.01),
            "eta_minutes": random.randint(15, 45),
            "message": "Delivery partner is nearby!"
        }
    
    return {
        "success": True,
        "order_id": order_id,
        "current_status": order["status"],
        "tracking_number": order.get("tracking_number"),
        "shipping_partner": order.get("shipping_partner", {}).get("name") if order.get("shipping_partner") else None,
        "tracking_events": tracking_events,
        "estimated_delivery": order["estimated_delivery"],
        "live_location": live_location
    }

# --- Exportable list of all tools in this file ---
post_purchase_tools = [
    initiate_return,
    get_return_status,
    create_support_ticket,
    get_faq_answer,
    list_customer_orders,
    get_order_details,
    track_order_detailed
]

# --- Build and Export Agent ---

### NEW: This is the function your SalesAgent will import ###
def get_post_purchase_agent():
    """
    Builds and returns a compiled specialist agent for post-purchase support.
    """
    print("--- Initializing Post-Purchase Agent ---")
    
    # 1. Create the system prompt
    system_prompt = """You are a specialist post-purchase support assistant.
Your job is to help customers with returns, order tracking, support tickets, and general questions.

IMPORTANT: Order Tracking Intelligence:
1. When customer says "track my order" or "where is my order" WITHOUT providing an order ID:
   - FIRST use list_customer_orders tool to get all their orders
   - If they have multiple orders, ASK: "I found X orders for you. Which one would you like to track?" and list them with:
     * Order ID
     * Order date
     * Number of items
     * Current status
   - If they have only ONE order, automatically show tracking details
   - If NO orders found, politely inform them

2. When customer provides a specific order ID:
   - Directly use get_order_details or track_order tools
   - Show comprehensive tracking information

3. For tracking queries:
   - Use get_order_details for full order information
   - Use track_order (from fulfillment agent) for step-by-step tracking events
   - Always include: Status, tracking number, estimated delivery, current location

4. Memory and Context:
   - Remember order IDs mentioned in conversation
   - If customer says "that order" or "my recent order", reference the last discussed order
   - Keep context of which order is being discussed

Be empathetic, proactive in asking clarifying questions, and always use tools before responding.
Provide clear, detailed tracking information with timestamps and locations."""

    # 2. Create the pre-built agent
    agent = create_agent(
        model=LLM,
        tools=post_purchase_tools,
        system_prompt=system_prompt,
        state_schema=MessagesState
    )
    return agent
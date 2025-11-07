"""
Fulfillment Toolkit - Order fulfillment and delivery management
Provides a specialist agent that can use a toolkit of fulfillment functions.
"""

import uuid
import random
from typing import Dict, List, Optional, Literal
from datetime import datetime, timedelta
from enum import Enum
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# --- NEW: Imports for building the specialist agent ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langgraph.graph import MessagesState
from config import settings, AgentConfig


# --- Data Models (Enums) ---
class FulfillmentType(str, Enum):
    """Types of order fulfillment."""
    SHIP_TO_HOME = "ship_to_home"
    CLICK_AND_COLLECT = "click_and_collect"
    BUY_IN_STORE = "buy_in_store"

class OrderStatus(str, Enum):
    """Order status states."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"

# --- In-Memory Database Simulation ---
_orders: Dict[str, Dict] = {}

# --- Constants ---
SHIPPING_PARTNERS = [
    {"id": "BLUEDART", "name": "Blue Dart", "speed": "express"},
    {"id": "DELHIVERY", "name": "Delhivery", "speed": "standard"},
    {"id": "DTDC", "name": "DTDC", "speed": "standard"},
]

# --- NEW: Initialize LLM (Module-level) ---
LLM = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.google_api_key,
    temperature=AgentConfig.TEMPERATURE
)

# --- Pydantic Schemas for Tool Arguments ---

class CartItem(BaseModel):
    sku: str = Field(description="The unique SKU of the product.")
    name: str = Field(description="The name of the product.")
    quantity: int = Field(description="The quantity of this product.")
    price: float = Field(description="The price per unit.")

class DeliveryAddress(BaseModel):
    name: str = Field(description="Recipient's full name.")
    street: str = Field(description="Street address.")
    city: str = Field(description="City.")
    state: str = Field(description="State.")
    pincode: str = Field(description="6-digit pincode.")
    phone: str = Field(description="Recipient's 10-digit phone number.")

class CreateOrderSchema(BaseModel):
    """Input schema for creating a new order."""
    customer_id: str = Field(description="The customer's unique ID.")
    cart_items: List[CartItem] = Field(description="List of items to be included in the order.")
    total_amount: float = Field(description="The final total amount of the order after all discounts.")
    fulfillment_type: FulfillmentType = Field(description="The chosen fulfillment method.")
    delivery_address: Optional[DeliveryAddress] = Field(default=None, description="The delivery address. Required if fulfillment_type is 'ship_to_home'.")
    pickup_store_id: Optional[str] = Field(default=None, description="The store ID for pickup. Required if fulfillment_type is 'click_and_collect'.")
    special_instructions: Optional[str] = Field(default=None, description="Any special instructions from the customer.")

class ScheduleDeliverySchema(BaseModel):
    """Input schema for scheduling a delivery."""
    order_id: str = Field(description="The order ID to schedule.")
    preferred_date: str = Field(description="Preferred delivery date in 'YYYY-MM-DD' format.")
    time_slot: Literal["morning", "afternoon", "evening"] = Field(description="The preferred time slot.")

# --- Internal Helper Functions ---

def _calculate_delivery_estimate(
    fulfillment_type: str,
    delivery_address: Optional[Dict] = None
) -> Dict:
    """Calculate estimated delivery time."""
    if fulfillment_type == FulfillmentType.SHIP_TO_HOME.value:
        min_days, max_days = 2, 5
        estimated_date = datetime.now() + timedelta(days=random.randint(min_days, max_days))
        return {
            "min_days": min_days, "max_days": max_days,
            "date": estimated_date.strftime("%Y-%m-%d"),
            "day_name": estimated_date.strftime("%A"),
            "message": f"Expected delivery: {estimated_date.strftime('%d %b, %Y')}"
        }
    elif fulfillment_type == FulfillmentType.CLICK_AND_COLLECT.value:
        estimated_time = datetime.now() + timedelta(hours=24)
        return {
            "min_hours": 4, "max_hours": 24,
            "datetime": estimated_time.isoformat(),
            "message": "Ready for pickup within 24 hours"
        }
    else: # Buy in store
        return {"immediate": True, "message": "Available immediately at store"}

def _generate_tracking_events(order: Dict) -> List[Dict]:
    """Generate realistic tracking events for an order."""
    events = []
    base_time = datetime.fromisoformat(order["created_at"])
    events.append({
        "status": "confirmed", "message": "Order confirmed",
        "timestamp": base_time.isoformat(), "location": "Order Processing Center"
    })
    
    current_status = order["status"]
    status_flow = [
        OrderStatus.PROCESSING.value, OrderStatus.SHIPPED.value,
        OrderStatus.OUT_FOR_DELIVERY.value, OrderStatus.DELIVERED.value
    ]
    
    if current_status in status_flow:
        events.append({
            "status": "processing", "message": "Order is being packed",
            "timestamp": (base_time + timedelta(hours=2)).isoformat(), "location": "Warehouse"
        })
    
    if current_status in status_flow[1:]:
        events.append({
            "status": "shipped", "message": "Order shipped",
            "timestamp": (base_time + timedelta(days=1)).isoformat(), "location": "Shipping Hub"
        })
    
    if current_status in status_flow[2:]:
        events.append({
            "status": "out_for_delivery", "message": "Out for delivery",
            "timestamp": (base_time + timedelta(days=2)).isoformat(), "location": "Local Delivery Hub"
        })
    
    if current_status == OrderStatus.DELIVERED.value:
        events.append({
            "status": "delivered", "message": "Order delivered successfully",
            "timestamp": (base_time + timedelta(days=2, hours=4)).isoformat(), "location": "Delivered"
        })
    
    return events

# --- Fulfillment Tools ---

@tool(args_schema=CreateOrderSchema)
def create_order(
    customer_id: str,
    cart_items: List[Dict], # Pydantic v1 can auto-coerce
    total_amount: float,
    fulfillment_type: str,
    delivery_address: Optional[Dict] = None,
    pickup_store_id: Optional[str] = None,
    special_instructions: Optional[str] = None
) -> Dict:
    """
    Creates a new order in the system after payment is confirmed.
    """
    # Convert Pydantic objects to dicts if needed
    if cart_items:
        converted_items = []
        for item in cart_items:
            if hasattr(item, 'model_dump'):
                converted_items.append(item.model_dump())
            elif hasattr(item, 'dict'):
                converted_items.append(item.dict())
            else:
                converted_items.append(item)
        cart_items = converted_items
    
    if delivery_address:
        if hasattr(delivery_address, 'model_dump'):
            delivery_address = delivery_address.model_dump()
        elif hasattr(delivery_address, 'dict'):
            delivery_address = delivery_address.dict()
    
    order_id = f"ORD{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"
    
    estimated_delivery = _calculate_delivery_estimate(fulfillment_type, delivery_address)
    
    shipping_partner = None
    tracking_number = None
    
    if fulfillment_type == FulfillmentType.SHIP_TO_HOME.value:
        if not delivery_address:
            return {"success": False, "message": "Delivery address is required for ship_to_home."}
        shipping_partner = random.choice(SHIPPING_PARTNERS)
        tracking_number = f"{shipping_partner['id']}{uuid.uuid4().hex[:10].upper()}"
    
    if fulfillment_type == FulfillmentType.CLICK_AND_COLLECT.value and not pickup_store_id:
        return {"success": False, "message": "Pickup store ID is required for click_and_collect."}

    order = {
        "order_id": order_id, "customer_id": customer_id, "items": cart_items,
        "total_amount": total_amount, "fulfillment_type": fulfillment_type,
        "status": OrderStatus.CONFIRMED.value,
        "delivery_address": delivery_address, "pickup_store": pickup_store_id,
        "special_instructions": special_instructions,
        "shipping_partner": shipping_partner, "tracking_number": tracking_number,
        "estimated_delivery": estimated_delivery,
        "status_history": [{"status": OrderStatus.CONFIRMED.value, "timestamp": datetime.now().isoformat(), "message": "Order confirmed"}],
        "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
    }
    
    _orders[order_id] = order
    
    message = f"Order {order_id} has been confirmed."
    
    return {
        "success": True,
        "order_id": order_id,
        "status": OrderStatus.CONFIRMED.value,
        "estimated_delivery": estimated_delivery,
        "tracking_number": tracking_number,
        "message": message
    }

@tool
def get_order_status(order_id: str) -> Optional[Dict]:
    """Get the current high-level status of an order."""
    order = _orders.get(order_id)
    if not order:
        return {"success": False, "message": "Order not found."}
    
    return {
        "success": True,
        "order_id": order_id,
        "status": order["status"],
        "tracking_number": order.get("tracking_number"),
        "estimated_delivery": order["estimated_delivery"],
        "last_updated": order["updated_at"]
    }

@tool
def track_order(order_id: str) -> Dict:
    """Get detailed, step-by-step tracking information for an order."""
    order = _orders.get(order_id)
    if not order:
        return {"success": False, "message": "Order not found"}
    
    tracking_events = _generate_tracking_events(order)
    
    live_location = None
    if order["status"] == OrderStatus.OUT_FOR_DELIVERY.value:
        live_location = {
            "latitude": 19.0760 + random.uniform(-0.01, 0.01),
            "longitude": 72.8777 + random.uniform(-0.01, 0.01),
            "eta_minutes": random.randint(15, 45)
        }
    
    return {
        "success": True,
        "order_id": order_id,
        "current_status": order["status"],
        "tracking_events": tracking_events,
        "estimated_delivery": order["estimated_delivery"],
        "live_location": live_location
    }

@tool
def cancel_order(order_id: str, reason: str = "Customer request") -> Dict:
    """Cancel an order, if it has not already been shipped."""
    order = _orders.get(order_id)
    if not order:
        return {"success": False, "message": "Order not found"}
    
    cancellable_statuses = [OrderStatus.PENDING.value, OrderStatus.CONFIRMED.value, OrderStatus.PROCESSING.value]
    if order["status"] not in cancellable_statuses:
        return {"success": False, "message": "Order cannot be cancelled at this stage. Please initiate a return instead."}
    
    order["status"] = OrderStatus.CANCELLED.value
    order["cancellation_reason"] = reason
    order["updated_at"] = datetime.now().isoformat()
    order["status_history"].append({
        "status": OrderStatus.CANCELLED.value,
        "timestamp": datetime.now().isoformat(),
        "message": f"Order cancelled. Reason: {reason}"
    })
    
    return {
        "success": True,
        "order_id": order_id,
        "message": "Order cancelled successfully. Refund will be processed."
    }

@tool(args_schema=ScheduleDeliverySchema)
def schedule_delivery(order_id: str, preferred_date: str, time_slot: str) -> Dict:
    """Schedule a preferred delivery for a specific date and time slot."""
    order = _orders.get(order_id)
    if not order:
        return {"success": False, "message": "Order not found"}
    
    try:
        delivery_date = datetime.strptime(preferred_date, "%Y-%m-%d")
        if delivery_date.date() < datetime.now().date():
            return {"success": False, "message": "Delivery date must be in the future"}
    except ValueError:
        return {"success": False, "message": "Invalid date format. Use YYYY-MM-DD"}
    
    order["scheduled_delivery"] = {
        "date": preferred_date, "time_slot": time_slot
    }
    order["updated_at"] = datetime.now().isoformat()
    
    time_slot_ranges = {
        "morning": "9 AM - 12 PM",
        "afternoon": "12 PM - 4 PM",
        "evening": "4 PM - 8 PM"
    }
    
    return {
        "success": True,
        "order_id": order_id,
        "scheduled_date": preferred_date,
        "time_slot": time_slot_ranges.get(time_slot, time_slot),
        "message": f"Delivery scheduled for {preferred_date}, {time_slot_ranges.get(time_slot, time_slot)}"
    }

# --- Exportable list of all tools in this file ---
fulfillment_tools = [
    create_order,
    get_order_status,
    track_order,
    cancel_order,
    schedule_delivery
]


# --- Build and Export Agent ---

### NEW: This is the function your SalesAgent will import ###
def get_fulfillment_agent():
    """
    Builds and returns a compiled specialist agent for order fulfillment.
    """
    print("--- Initializing Fulfillment Agent ---")
    
    # 1. Create the system prompt
    system_prompt = """You are a specialist order fulfillment and delivery assistant.
Your job is to create new orders, provide tracking updates, and handle cancellations or rescheduling.
Use your tools to manage all aspects of order fulfillment.
Be professional and provide clear, accurate status updates."""

    # 2. Create the pre-built agent
    agent = create_agent(
        model=LLM,
        tools=fulfillment_tools,
        system_prompt=system_prompt,
        state_schema=MessagesState
    )
    return agent
"""
Loyalty Agent - Loyalty program management and promotions
Provides a specialist agent that can use a toolkit of loyalty functions
to interact with the Supabase database.
"""

import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# --- NEW: Import your storage ---
from config.supabase_config import get_storage

# --- NEW: Imports for building the specialist agent ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langgraph.graph import MessagesState
from config.settings import settings, AgentConfig, LoyaltyConfig


# --- NEW: Initialize Supabase Client ---
# This single 'storage' object will be used by all tools.
# It is an instance of your SupabaseDB or InMemoryStorage class.
storage = get_storage()
print(f"--- Loyalty Agent Storage Initialized (Connected: {storage.is_connected}) ---")


# --- Load Loyalty Tiers (from config) ---
TIERS = LoyaltyConfig.TIERS
POINTS_PER_RUPEE = LoyaltyConfig.POINTS_PER_RUPEE
RUPEES_PER_POINT = LoyaltyConfig.RUPEES_PER_POINT

# --- REMOVED ---
# We no longer need to load promotions.json,
# as this will now come from the 'coupons' table in Supabase.

# --- NEW: Initialize LLM (Module-level) ---
LLM = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.google_api_key,
    temperature=AgentConfig.TEMPERATURE
)

# --- Internal Helper Functions (Unchanged) ---

def _get_tier_benefits(tier: str) -> List[str]:
    """Get benefits for a loyalty tier."""
    benefits = {
        "Bronze": [
            "Earn 1 point per ₹1 spent",
            "Access to sales"
        ],
        "Silver": [
            "5% discount on all purchases",
            "Free shipping on orders above ₹499",
            "Early access to sales",
        ],
        "Gold": [
            "10% discount on all purchases",
            "Free shipping on all orders",
            "Priority customer support",
            "Birthday gift worth ₹1000",
        ],
        "Platinum": [
            "15% discount on all purchases",
            "Earn 1.5 points per ₹1 spent",
            "Free express shipping",
            "24/7 priority support",
        ]
    }
    return benefits.get(tier, [])

# --- Pydantic Schemas for Tool Arguments (Unchanged) ---

class CustomerProfilePricing(BaseModel):
    """A simplified customer profile for pricing calculations."""
    loyalty_points: int = Field(default=0, description="The customer's current total loyalty points.")

class FinalPricingSchema(BaseModel):
    """Input schema for calculating the final price with all discounts."""
    cart_total: float = Field(description="The original total price of the cart.")
    # MODIFIED: It's much simpler for the agent to just pass the ID
    customer_id: Optional[str] = Field(default=None, description="The customer's unique ID. Required for tier discounts.")
    promo_code: Optional[str] = Field(default=None, description="A discount code the user wants to apply.")
    points_to_redeem: int = Field(default=0, description="Number of loyalty points the user wants to redeem.")

class PersonalizedOffersSchema(BaseModel):
    """Input schema for generating personalized offers for a specific customer."""
    # MODIFIED: All other fields will be looked up from this ID.
    customer_id: str = Field(description="The customer's unique ID.")


# --- Loyalty Tools (Updated to use Supabase) ---

# --- NEW TOOL ---
@tool
def get_customer_profile(customer_id: str) -> Dict:
    """
    Fetches a customer's complete profile from the database using their customer_id.
    Returns all loyalty info, preferences, and personal details.
    """
    profile = storage.get_customer_profile(customer_id)
    
    if not profile:
        return {"error": f"No customer found with ID: {customer_id}"}
    
    return profile

# --- MODIFIED TOOL ---
@tool
def get_customer_tier(customer_id: str) -> Dict:
    """
    Determine a customer's loyalty tier and benefits using their customer_id.
    It fetches the customer's points from the database first.
    """
    # Use the new tool to get the profile
    profile_result = get_customer_profile.invoke({"customer_id": customer_id})
    if profile_result.get("error"):
        return profile_result # Pass the error message along
    
    total_points = profile_result.get("loyalty_points", 0)
    
    # --- The rest of your original logic is perfect ---
    current_tier = "Bronze"
    current_discount = 0
    
    for tier_name, tier_data in TIERS.items():
        if total_points >= tier_data["min_points"]:
            current_tier = tier_name
            current_discount = tier_data["discount"]
    
    benefits = _get_tier_benefits(current_tier)
    
    next_tier = None
    points_to_next = None
    tier_order = ["Bronze", "Silver", "Gold", "Platinum"]
    current_idx = tier_order.index(current_tier)
    
    if current_idx < len(tier_order) - 1:
        next_tier_name = tier_order[current_idx + 1]
        next_tier_points = TIERS[next_tier_name]["min_points"]
        points_to_next = next_tier_points - total_points
        next_tier = {
            "name": next_tier_name,
            "required_points": next_tier_points,
        }
    
    return {
        "tier": current_tier,
        "discount_percentage": current_discount,
        "benefits": benefits,
        "next_tier": next_tier,
        "points_to_next": points_to_next
    }

# --- UNCHANGED TOOL ---
@tool
def calculate_points_earned(amount: float, tier: str = "Bronze") -> int:
    """Calculate loyalty points earned for a purchase amount and customer tier."""
    points_rate = POINTS_PER_RUPEE
    if tier == "Platinum":
        points_rate = 1.5
    return int(amount * points_rate)

# --- UNCHANGED TOOL ---
@tool
def calculate_points_value(points: int) -> float:
    """Calculate the monetary value (in Rupees) of a given number of loyalty points."""
    return points * RUPEES_PER_POINT

# --- MODIFIED TOOL ---
@tool
def validate_promo_code(promo_code: str, cart_total: float, customer_tier: str = "Bronze") -> Dict:
    """
    Validate and apply a promotional code to a cart by checking the Supabase 'coupons' table.
    """
    if not storage.is_connected:
        return {"valid": False, "discount_amount": 0, "message": "Database connection is not configured."}

    try:
        # Your SupabaseDB class doesn't have a method for this,
        # so we must access the private _client to run this specific query.
        response = storage._client.table('coupons') \
                                  .select('*') \
                                  .eq('code', promo_code.upper()) \
                                  .limit(1) \
                                  .execute()
        
        if not response.data:
            return {"valid": False, "discount_amount": 0, "message": "Invalid promo code"}
        
        promo = response.data[0]
        
    except Exception as e:
        return {"valid": False, "discount_amount": 0, "message": f"Database error: {str(e)}"}
    
    # --- The rest of your validation logic is great ---
    
    # Ensure datetime is in ISO format with timezone for comparison
    now = datetime.now().astimezone().isoformat()
    
    if not promo.get('active', True):
         return {"valid": False, "discount_amount": 0, "message": "This promo code is no longer active."}

    if not (promo["valid_from"] <= now <= promo["valid_until"]):
        return {"valid": False, "discount_amount": 0, "message": "Promo code has expired or is not yet active"}
    
    if cart_total < promo.get("min_purchase", 0):
        return {"valid": False, "discount_amount": 0, "message": f"Minimum purchase of ₹{promo['min_purchase']:,.0f} required"}
    
    # Use the _tier_to_level method from your storage class
    tier_level = storage._tier_to_level(customer_tier)
    if tier_level < promo.get("min_tier_required", 0):
       return {"valid": False, "discount_amount": 0, "message": "This promo code is not available for your tier"}
    
    if promo["discount_type"] == "percentage":
        discount = (cart_total * promo["discount_value"]) / 100
        if promo.get("max_discount"):
            discount = min(discount, promo["max_discount"])
    else:  # flat
        discount = min(promo["discount_value"], cart_total)
    
    return {
        "valid": True,
        "discount_amount": discount,
        "message": f"Promo code applied! You saved ₹{discount:,.2f}",
    }

# --- MODIFIED TOOL ---
@tool(args_schema=FinalPricingSchema)
def calculate_final_pricing(
    cart_total: float,
    customer_id: Optional[str] = None,
    promo_code: Optional[str] = None,
    points_to_redeem: int = 0
) -> Dict:
    """
    Calculate final pricing with all discounts and loyalty benefits.
    Uses the customer_id to fetch their loyalty tier and apply discounts.
    """
    original_total = cart_total
    
    tier = "Bronze"
    tier_info = None
    
    # Fetch customer tier if ID is provided
    if customer_id:
        tier_info_result = get_customer_tier.invoke({"customer_id": customer_id})
        if not tier_info_result.get("error"):
            tier_info = tier_info_result
            tier = tier_info["tier"]
    
    tier_discount_pct = TIERS[tier]["discount"]
    tier_discount = (cart_total * tier_discount_pct) / 100
    cart_total -= tier_discount
    
    promo_discount = 0
    if promo_code:
        promo_result = validate_promo_code.invoke({
            "promo_code": promo_code,
            "cart_total": cart_total, # Apply promo after tier discount
            "customer_tier": tier
        })
        if promo_result["valid"]:
            promo_discount = promo_result["discount_amount"]
            cart_total -= promo_discount
    
    points_value = 0
    if points_to_redeem > 0:
        points_value_result = calculate_points_value.invoke({"points": points_to_redeem})
        points_value = min(points_value_result, cart_total)
        cart_total -= points_value
    
    # Calculate points earned using direct calculation
    points_rate = POINTS_PER_RUPEE
    if tier == "Platinum":
        points_rate = 1.5
    points_earned = int(cart_total * points_rate)
    
    return {
        "original_total": original_total,
        "tier_discount": tier_discount,
        "promo_discount": promo_discount,
        "points_redeemed_value": points_value,
        "final_total": max(cart_total, 0),
        "savings": original_total - max(cart_total, 0),
        "points_earned": points_earned
    }

# --- MODIFIED TOOL ---
@tool(args_schema=PersonalizedOffersSchema)
def get_personalized_offers(
    customer_id: str
) -> List[Dict]:
    """
    Generate personalized offers based on customer profile and behavior.
    Fetches all customer data from the database using their customer_id.
    """
    # First, get the full customer profile
    profile = storage.get_customer_profile(customer_id)
    if not profile:
        return [{"error": "Customer not found"}]

    # Now, use the data from the profile
    loyalty_points = profile.get("loyalty_points", 0)
    total_spent = profile.get("total_spent", 0)
    birthday = profile.get("birthday", None) # e.g., '1990-06-15'
    
    # Get last purchase date from orders
    last_purchase_date = None
    orders = storage.get_customer_orders(customer_id, limit=1)
    if orders:
        last_purchase_date = orders[0]['created_at']

    # --- The rest of your original logic is perfect ---
    offers = []
    
    if birthday:
        try:
            birthday_dt = datetime.fromisoformat(birthday)
            today = datetime.now()
            if birthday_dt.month == today.month:
                tier_info = get_customer_tier.invoke({"customer_id": customer_id}) # Use invoke
                gift_values = {"Bronze": 0, "Silver": 500, "Gold": 1000, "Platinum": 2000}
                gift_value = gift_values.get(tier_info.get("tier", "Bronze"), 0)
                if gift_value > 0:
                    offers.append({
                        "type": "birthday",
                        "title": "🎂 Happy Birthday!",
                        "description": f"Get ₹{gift_value} gift voucher",
                        "code": f"BDAY{customer_id[:8].upper()}"
                    })
        except Exception as e:
            print(f"Error processing birthday: {e}")
    
    if last_purchase_date:
        try:
            # Need to handle timezone-aware vs naive datetimes
            if isinstance(last_purchase_date, str):
                last_purchase_dt = datetime.fromisoformat(last_purchase_date)
            else:
                last_purchase_dt = last_purchase_date
            
            # Ensure 'now' is offset-aware if 'last_purchase_dt' is
            if last_purchase_dt.tzinfo:
                now = datetime.now(last_purchase_dt.tzinfo)
            else:
                now = datetime.now()
                
            days_since = (now - last_purchase_dt).days
            if days_since > 60:
                offers.append({
                    "type": "winback",
                    "title": "We Miss You! 💙",
                    "description": "Get 20% off on your next purchase",
                    "code": "COMEBACK20"
                })
        except Exception as e:
            print(f"Error processing last purchase date: {e}")
    
    if total_spent > 50000:
        offers.append({
            "type": "vip",
            "title": "VIP Exclusive Offer 🌟",
            "description": "Free express shipping on all orders + 500 bonus points",
            "code": "VIPSHIP"
        })
    
    if not offers:
        return [{"message": "No special offers are available for this customer right now."}]
        
    return offers

# --- Exportable list of all tools in this file ---
loyalty_tools = [
    get_customer_profile,       # <-- ADDED
    get_customer_tier,
    calculate_points_earned,
    calculate_points_value,
    validate_promo_code,
    calculate_final_pricing,
    get_personalized_offers
]

# --- Build and Export Agent (Unchanged) ---

### This is the function your SalesAgent will import ###
def get_loyalty_agent():
    """
    Builds and returns a compiled specialist agent for loyalty and promotions.
    """
    print("--- Initializing Loyalty Agent (with Supabase tools) ---")
    
    # 1. Create the system prompt
    system_prompt = """You are a specialist loyalty and promotions assistant.
Your job is to manage customer loyalty points, tiers, and apply discounts.
You MUST use your tools to fetch customer data from the database.
First, ALWAYS use 'get_customer_profile' or 'get_customer_tier' to get the customer's data.
Then, use that data to answer questions about pricing, discounts, or offers.
You are responsible for all pricing and discount calculations."""

    # 2. Create the pre-built agent
    agent = create_agent(
        model=LLM,
        tools=loyalty_tools,
        system_prompt=system_prompt,
        state_schema=MessagesState
    )
    return agent
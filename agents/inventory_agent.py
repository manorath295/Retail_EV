"""
Inventory Agent - Real-time stock checking across warehouses and stores.
Enhanced for Retail AI Streamlit frontend with clean CSS-friendly text responses.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Literal
from pydantic import BaseModel, Field

# Ensure root path is importable (fix for config import issue)
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

# Local imports (after path fix)
from config.settings import settings, AgentConfig

# LangChain & LangGraph imports
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langgraph.graph import MessagesState


# --- Data loading helpers ---
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

def _load_inventory() -> List[Dict]:
    """Load inventory data, or create dummy if missing."""
    inv_file = DATA_DIR / "inventory.json"
    if inv_file.exists():
        with open(inv_file) as f:
            print("✅ Inventory loaded successfully.")
            return json.load(f)
    else:
        print("⚠️ No inventory.json found — creating sample data...")
        sample_inventory = [
            {"sku": "ELE1069", "quantity": 12, "reserved": 2, "location_id": "MUM01", "location_type": "store"},
            {"sku": "ELE1069", "quantity": 30, "reserved": 5, "location_id": "WH_CENTRAL", "location_type": "warehouse"},
            {"sku": "CLO1025", "quantity": 15, "reserved": 0, "location_id": "DEL01", "location_type": "store"},
        ]
        with open(inv_file, "w") as f:
            json.dump(sample_inventory, f, indent=2)
        print("sampling data\n")
        print(sample_inventory)
        print("END\n")
        return sample_inventory


# --- Initialize Model ---
LLM = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.google_api_key,
    temperature=AgentConfig.TEMPERATURE
)

INVENTORY = _load_inventory()

STORES = {
    "WH_CENTRAL": {"name": "Central Warehouse", "type": "warehouse"},
    "MUM01": {"name": "Mumbai Central", "type": "store", "city": "Mumbai"},
    "DEL01": {"name": "Delhi CP", "type": "store", "city": "Delhi"},
    "BLR01": {"name": "Bangalore Koramangala", "type": "store", "city": "Bangalore"},
    "HYD01": {"name": "Hyderabad Banjara", "type": "store", "city": "Hyderabad"},
    "CHN01": {"name": "Chennai T.Nagar", "type": "store", "city": "Chennai"}
}


# --- Schemas ---
class AvailabilitySchema(BaseModel):
    sku: str = Field(description="Product SKU")
    quantity: int = Field(default=1, description="Quantity to check")


class NearestStoreSchema(BaseModel):
    sku: str
    customer_city: str


class DeliveryEstimateSchema(BaseModel):
    fulfillment_type: Literal["ship_to_home", "click_and_collect", "buy_in_store"]


class PriceSchema(BaseModel):
    sku: str


class CategorySchema(BaseModel):
    category: str


# --- Tools ---
@tool(args_schema=AvailabilitySchema)
def check_availability(sku: str, quantity: int = 1) -> str:
    """Check product availability across all stores and warehouses."""
    print("entring the sku check_availabilty")
    sku_inventory = [inv for inv in INVENTORY if inv["sku"] == sku]
    print(sku_inventory)
    if not sku_inventory:
        return f"❌ No product found for SKU `{sku}`."

    total_stock = sum(inv["quantity"] - inv.get("reserved", 0) for inv in sku_inventory)
    print("")
    if total_stock <= 0:
        return f"⚠️ The product with SKU `{sku}` is currently out of stock."

    msg = [f"### 📦 Stock Availability for **{sku}**"]
    msg.append(f"**Total Stock:** {total_stock} units\n")
    msg.append("**Available Locations:**")

    for inv in sku_inventory:
        available_qty = inv["quantity"] - inv.get("reserved", 0)
        if available_qty > 0:
            store = STORES.get(inv["location_id"], {})
            city = store.get("city", "—")
            msg.append(f"🏬 **{store.get('name', 'Unknown')}** — {available_qty} units (📍 {city})")

    msg.append("\n**✅ Fulfillment Options:**")
    msg.append("- 🚚 *Ship to Home* (2–5 days)")
    msg.append("- 🛒 *Click & Collect* (Ready within 24h)")
    msg.append("- 🏬 *Buy In Store* (Immediate availability)")
    return "\n".join(msg)


@tool(args_schema=NearestStoreSchema)
def get_nearest_store_with_stock(sku: str, customer_city: str) -> str:
    """Find nearest store with stock."""
    stores_with_stock = [
        inv for inv in INVENTORY
        if inv["sku"] == sku and inv["location_type"] == "store" and (inv["quantity"] - inv.get("reserved", 0)) > 0
    ]
    if not stores_with_stock:
        return f"❌ No stores currently have SKU `{sku}` in stock."

    same_city = [inv for inv in stores_with_stock if STORES[inv["location_id"]]["city"].lower() == customer_city.lower()]
    inv = same_city[0] if same_city else stores_with_stock[0]
    store = STORES[inv["location_id"]]
    available = inv["quantity"] - inv.get("reserved", 0)
    return f"✅ {available} units of `{sku}` available at **{store['name']}** in {store.get('city', 'N/A')}."


@tool(args_schema=DeliveryEstimateSchema)
def get_estimated_delivery(fulfillment_type: str) -> str:
    """Delivery estimate text."""
    options = {
        "ship_to_home": "🚚 Delivery in 2–5 business days.",
        "click_and_collect": "🛒 Ready for pickup within 24 hours.",
        "buy_in_store": "🏬 Available immediately at the store."
    }
    return options.get(fulfillment_type, "Standard delivery within 3–7 days.")


# Example extra tool — you can extend as you go
@tool(args_schema=PriceSchema)
def get_price_for_sku(sku: str) -> str:
    """Mock price lookup tool."""
    price_map = {"ELE1069": 24999, "CLO1025": 1599}
    if sku not in price_map:
        return f"💰 No pricing info found for SKU `{sku}`."
    return f"💰 The price for `{sku}` is ₹{price_map[sku]:,}."


# --- Agent Builder ---
def get_inventory_agent():
    """Return a LangGraph inventory specialist agent."""
    print("--- Initializing Enhanced Inventory Agent ---")

    inventory_tools = [
        check_availability,
        get_nearest_store_with_stock,
        get_estimated_delivery,
        get_price_for_sku
    ]

    system_prompt = """You are a specialist retail inventory and fulfillment assistant.
Your tasks:
- Check stock availability
- Suggest nearest store for pickup
- Provide delivery time estimates
- Return clear markdown with emojis and formatting.
Always use tools where relevant (e.g. for SKUs like 'ELE1069')."""

    return create_agent(
        model=LLM,
        tools=inventory_tools,
        system_prompt=system_prompt,
        state_schema=MessagesState
    )


# --- Direct run for testing ---
if __name__ == "__main__":
    agent = get_inventory_agent()
    print("\n🔍 Testing Inventory Agent...\n")

    response = agent.invoke({
        "messages": [
            {"role": "user", "content": "Check stock for ELE1069 and tell me price."}
        ]
    })

    print("\n🤖 Agent Response:\n", response)
    

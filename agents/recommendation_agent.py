"""
Recommendation Agent - Product recommendation and personalization
Uses customer profile, browsing history, and AI to suggest relevant products.
"""

import json
from typing import List, Dict, Optional
from pathlib import Path
import random

# --- Imports for Tools and Pydantic Schemas ---
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import create_agent
from langgraph.graph import MessagesState

from config.settings import settings, AgentConfig

# --- Load Data and Config ---
DATA_DIR = Path(__file__).parent.parent / "data"

def _load_products() -> List[Dict]:
    """Load product catalog."""
    products_file = DATA_DIR / "products.json"
    if products_file.exists():
        with open(products_file) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("⚠️ Invalid JSON file, returning empty list.")
                return []

def _load_purchase_history() -> List[Dict]:
    """Load purchase history."""
    history_file = DATA_DIR / "purchase_history.json"
    if history_file.exists():
        with open(history_file) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("⚠️ Invalid JSON file, returning empty list.")
                return []
    

# --- Initialize LLMs and Load Data (Module-level) ---
LLM = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.google_api_key,
    temperature=AgentConfig.TEMPERATURE
)

PRODUCTS = _load_products()
PURCHASE_HISTORY = _load_purchase_history()

# --- Pydantic Schemas ---
class AIRecommendation(BaseModel):
    sku: str = Field(description="The product SKU.")
    reason: str = Field(description="Brief reason why it's recommended.")
    selling_point: str = Field(description="The product's single key selling point.")

class AIRecommendationList(BaseModel):
    recommendations: List[AIRecommendation]

class PreferencesSchema(BaseModel):
    favorite_categories: Optional[List[str]] = Field(default_factory=list, description="List of mentioned categories")
    max_price: Optional[int] = Field(default=None, description="Maximum price")
    min_rating: Optional[float] = Field(default=None, description="Minimum rating")
    keywords: Optional[List[str]] = Field(default_factory=list, description="Relevant keywords")

class RecommendProductsSchema(BaseModel):
    preferences: PreferencesSchema = Field(description="Customer preferences")
    context: str = Field(description="The last user message or conversation context.")
    customer_id: Optional[str] = Field(default=None, description="Customer ID for purchase history")
    count: int = Field(default=5, description="Number of recommendations to return.")

class CartItemSchema(BaseModel):
    sku: str
    category: str

class ComplementaryProductsSchema(BaseModel):
    cart_items: List[CartItemSchema] = Field(description="List of items in the cart.")

class TrendingProductsSchema(BaseModel):
    category: Optional[str] = Field(default=None, description="Optional category to filter by.")
    count: int = Field(default=5, description="Number of products to return.")

# --- Initialize Structured LLM ---
RANKING_LLM = LLM.with_structured_output(AIRecommendationList)


# --- Internal Helper Functions ---
def _filter_products(preferences: Dict) -> List[Dict]:
    """Filter products based on preferences."""
    # print("i am printing the products")
    # print(PRODUCTS)
    filtered = PRODUCTS.copy()
    
    # Filter by categories
    if preferences.get("favorite_categories"):
        filtered = [p for p in filtered if p["category"] in preferences["favorite_categories"]]
    
    # Filter by max price
    if preferences.get("max_price"):
        filtered = [p for p in filtered if p["price"] <= preferences["max_price"]]
    
    # Filter by min rating
    if preferences.get("min_rating"):
        filtered = [p for p in filtered if p["rating"] >= preferences["min_rating"]]
    # print("i am filterning the product")
    # print(filtered)
    
    # Return filtered products or all if no matches
    return filtered if filtered else PRODUCTS[:10]

def _collaborative_filtering(past_purchases: List[Dict], available_products: List[Dict]) -> List[str]:
    """Score products based on past purchases."""
    purchased_categories = [p["category"] for p in past_purchases]
    purchased_skus = [p["sku"] for p in past_purchases]
    scored_products = []
    
    for product in available_products:
        if product["sku"] in purchased_skus: 
            continue
        score = 0
        if product["category"] in purchased_categories: 
            score += 3
        if product.get("is_featured"): 
            score += 2
        if product["rating"] >= 4.5: 
            score += 2
        if product["reviews_count"] > 200: 
            score += 1
        scored_products.append((product["sku"], score))
    
    scored_products.sort(key=lambda x: x[1], reverse=True)
    return [sku for sku, _ in scored_products[:20]]

async def _ai_rank_products(candidates: List[Dict], preferences: Dict, context: str, past_purchases: List[Dict], count: int) -> List[Dict]:
    """Use AI to rank and select best products."""
    if not candidates:
        return []
    
    past_purchase_summary = ", ".join([p.get("product_name", "item") for p in past_purchases[:5]])
    
    prompt = f"""You are a product recommendation expert. Analyze these products and select the top {count} for the customer.

Customer Context:
- Conversation: {context}
- Preferences: {json.dumps(preferences)}
- Past Purchases: {past_purchase_summary or "None"}

Available Products:
{json.dumps([{
    'sku': p['sku'], 'name': p['name'], 'category': p['category'],
    'price': p['price'], 'rating': p['rating'], 'tags': p.get('tags', [])
} for p in candidates[:10]], indent=2)}

Select the top {count} products and provide a SKU, reason, and selling point for each."""
    
    try:
        response_obj = await RANKING_LLM.ainvoke([
            SystemMessage(content="You are a helpful product recommendation assistant that always returns valid JSON."),
            HumanMessage(content=prompt)
        ])
        final_recommendations = []
        for rec in response_obj.recommendations[:count]:
            product = next((p for p in candidates if p["sku"] == rec.sku), None)
            if product:
                final_recommendations.append({
                    **product,
                    "recommendation_reason": rec.reason,
                    "selling_point": rec.selling_point
                })
        print(final_recommendations,"DEkh le bhai")        
        return final_recommendations
    except Exception as e:
        print(f"⚠️ AI ranking failed: {e}, using simple ranking")
        # Fallback: sort by rating and return top products
        sorted_products = sorted(candidates, key=lambda x: (x["rating"], x["reviews_count"]), reverse=True)
        return [{**p, "recommendation_reason": f"Highly rated with {p['rating']}⭐"} for p in sorted_products[:count]]

# --- Recommendation Tools ---

@tool(args_schema=RecommendProductsSchema)
async def recommend_products(
    preferences: Dict,
    context: str,
    customer_id: Optional[str] = None,
    count: int = 5
) -> str:
    """
    Generate personalized product recommendations based on preferences, 
    context, and optionally customer history. Returns JSON string of products.
    """
    print(f"🔍 recommend_products called with preferences: {preferences}")
    
    # Convert PreferencesSchema to dict if needed
    if hasattr(preferences, 'model_dump'):
        preferences = preferences.model_dump()
    elif hasattr(preferences, 'dict'):
        preferences = preferences.dict()
    
    # Get past purchases if customer_id provided
    past_purchases = []
    if customer_id:
        past_purchases = [h for h in PURCHASE_HISTORY if h["customer_id"] == customer_id]
    
    # Filter products based on preferences
    filtered_products = _filter_products(preferences)
    print(f"📦 Filtered to {len(filtered_products)} products")
    
    # Get candidate SKUs
    if past_purchases:
        recommended_skus = _collaborative_filtering(past_purchases, filtered_products)
    else:
        # Random selection for new customers
        max_candidates = min(count * 2, len(filtered_products))
        recommended_skus = [p["sku"] for p in random.sample(filtered_products, max_candidates)]
    
    candidates = [p for p in filtered_products if p["sku"] in recommended_skus]
    
    # Rank using AI
    final_recommendations = await _ai_rank_products(
        candidates, preferences, context, past_purchases, count
    )
    
    print(f"✅ Returning {len(final_recommendations)} recommendations")
    
    # Return as JSON string (LangChain tools need string returns)
    return json.dumps(final_recommendations)

@tool(args_schema=ComplementaryProductsSchema)
def find_complementary_products(cart_items: List[Dict]) -> str:
    """Find products that complement (cross-sell) items already in the cart. Returns JSON string."""
    if not cart_items: 
        return json.dumps([])
    
    complements_map = {
        "Footwear": ["Accessories", "Clothing"],
        "Clothing": ["Accessories", "Footwear"],
        "Electronics": ["Accessories"],
    }
    
    cart_categories = list(set(item.get("category", "") for item in cart_items))
    complement_categories = []
    for cat in cart_categories:
        complement_categories.extend(complements_map.get(cat, []))
    
    complementary = [
        p for p in PRODUCTS 
        if p["category"] in complement_categories and p.get("is_featured", False)
    ]
    
    result = sorted(complementary, key=lambda x: x["rating"], reverse=True)[:3]
    return json.dumps(result)

@tool(args_schema=TrendingProductsSchema)
def get_trending_products(category: Optional[str] = None, count: int = 5) -> str:
    """Get trending/popular products, optionally filtered by category. Returns JSON string."""
    products = PRODUCTS
    if category:
        products = [p for p in products if p["category"] == category]
    
    trending = sorted(
        products, key=lambda x: (x["reviews_count"], x["rating"]), reverse=True
    )
    
    result = trending[:count]
    return json.dumps(result)

# --- Build and Export Agent ---

def get_recommendation_agent():
    """
    Builds and returns a compiled specialist agent for product recommendations.
    """
    print("--- Initializing Recommendation Agent ---")
    
    # 1. Define the tools for this specialist
    recommendation_tools = [
        recommend_products,
        find_complementary_products,
        get_trending_products
    ]
    
    # 2. Create the system prompt
    system_prompt = """You are a specialist product recommendation assistant.
Your job is to help customers find products they'll love.

IMPORTANT: When recommending products:
1. ALWAYS use the recommend_products tool with proper parameters
2. Extract categories from the user's message (Footwear, Clothing, Electronics, Accessories)
3. Set reasonable preferences (max_price, min_rating if mentioned)
4. Include the user's context in the context parameter
5. After getting results, present them in a friendly, conversational way with product names, prices, and why they're great

NEVER just say you'll help - ALWAYS call the tool and show actual products.

Be friendly, enthusiastic, and helpful!"""

    # 3. Create the pre-built agent
    agent = create_agent(
        model=LLM,
        tools=recommendation_tools,
        system_prompt=system_prompt,
        state_schema=MessagesState
    )
    return agent

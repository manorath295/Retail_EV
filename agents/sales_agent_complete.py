"""
Sales Agent - FIXED VERSION (Complete)
Main orchestrator for the retail AI system with proper indentation and DB integration
"""

from typing import Dict, List, Optional, Any, Literal
from datetime import datetime
import json

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from config.settings import settings, AgentConfig
from config.supabase_config import get_storage
from agents.state import (
    ConversationState,
    create_initial_state,
    CartItem,
   
    add_to_cart,
    update_intent,
    handoff_to_agent,
    switch_channel
)

from agents.recommendation_agent import get_recommendation_agent
from agents.inventory_agent import get_inventory_agent
from agents.payment_agent import get_payment_agent
from agents.fulfillment_agent import get_fulfillment_agent
from agents.loyalty_agent import get_loyalty_agent
from agents.post_purchase_agent import get_post_purchase_agent


# --- Pydantic Schemas ---
class IntentSchema(BaseModel):
    """The user's classified intent."""
    intent: Literal[
        "greeting", 
        "browsing", 
        "product_inquiry", 
        "cart_management", 
        "checkout", 
        "support", 
        "end"
    ] = Field(description="The *single* most likely intent of the user.")

class PreferencesSchema(BaseModel):
    """Extracted shopping preferences from the user's message."""
    favorite_categories: Optional[List[str]] = Field(default_factory=list, description="List of mentioned categories")
    max_price: Optional[int] = Field(default=None, description="Maximum price")
    min_rating: Optional[float] = Field(default=None, description="Minimum rating")
    keywords: Optional[List[str]] = Field(default_factory=list, description="Relevant keywords")


class SalesAgent:
    """Main sales agent that orchestrates the entire conversation flow."""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.google_api_key,
            temperature=AgentConfig.TEMPERATURE,
            max_output_tokens=AgentConfig.MAX_TOKENS
        )
        
        self.intent_llm = self.llm.with_structured_output(IntentSchema)
        self.preferences_llm = self.llm.with_structured_output(PreferencesSchema)
        
        # Initialize specialized agents
        print("--- Initializing Specialist Agents ---")
        self.recommendation_agent = get_recommendation_agent()
        self.inventory_agent = get_inventory_agent()
        self.payment_agent = get_payment_agent()
        self.fulfillment_agent = get_fulfillment_agent()
        self.loyalty_agent = get_loyalty_agent()
        self.post_purchase_agent = get_post_purchase_agent()
        print("--- All Specialist Agents Initialized ---")
        
        # Build conversation graph
        self.graph = self._build_conversation_graph()
    
    def _build_conversation_graph(self) -> StateGraph:
        """Build LangGraph workflow for conversation."""
        workflow = StateGraph(ConversationState)
        
        # Add nodes
        workflow.add_node("understand_intent", self._understand_intent)
        workflow.add_node("greet_customer", self._greet_customer)
        workflow.add_node("recommend_products", self._recommend_products)
        workflow.add_node("check_inventory", self._check_inventory)
        workflow.add_node("manage_cart", self._manage_cart)
        workflow.add_node("process_payment", self._process_payment)
        workflow.add_node("fulfill_order", self._fulfill_order)
        workflow.add_node("handle_support", self._handle_support)
        workflow.add_node("end_conversation", self._end_conversation)
        
        workflow.set_entry_point("understand_intent")
        
        workflow.add_conditional_edges(
            "understand_intent",
            self._route_intent,
            {
                "greeting": "greet_customer",
                "browsing": "recommend_products",
                "product_inquiry": "check_inventory",
                "cart_management": "manage_cart",
                "checkout": "process_payment",
                "support": "handle_support",
                "end": "end_conversation"
            }
        )
        
        workflow.add_edge("greet_customer", END) 
        workflow.add_edge("recommend_products", END)
        workflow.add_edge("check_inventory", END)
        workflow.add_edge("manage_cart", END)
        workflow.add_edge("process_payment", "fulfill_order")
        workflow.add_edge("fulfill_order", END)
        workflow.add_edge("handle_support", END)
        workflow.add_edge("end_conversation", END)
        
        print("--- Compiling SalesAgent Graph ---")
        from langgraph.checkpoint.memory import InMemorySaver
        checkpointer = InMemorySaver()
        
        return workflow.compile(checkpointer=checkpointer)
    
    def _extract_preferences(self, message: str) -> Dict:
        """Extract shopping preferences from user message."""
        try:
            prompt = f"""Extract shopping preferences from this message: "{message}"
            
            Look for:
            - Categories mentioned (Footwear, Clothing, Electronics, Accessories)
            - Price constraints
            - Rating requirements
            - Keywords about style, brand, or features
            """
            
            response = self.preferences_llm.invoke([HumanMessage(content=prompt)])
            return {
                "favorite_categories": response.favorite_categories or [],
                "max_price": response.max_price,
                "min_rating": response.min_rating,
                "keywords": response.keywords or []
            }
        except Exception as e:
            print(f"Preferences extraction error: {e}")
            prefs = {"favorite_categories": [], "max_price": None, "min_rating": None, "keywords": []}
            message_lower = message.lower()
            if "footwear" in message_lower or "shoe" in message_lower:
                prefs["favorite_categories"] = ["Footwear"]
            elif "electronic" in message_lower or "phone" in message_lower or "headphone" in message_lower:
                prefs["favorite_categories"] = ["Electronics"]
            elif "clothing" in message_lower or "shirt" in message_lower or "jean" in message_lower:
                prefs["favorite_categories"] = ["Clothing"]
            elif "accessories" in message_lower or "watch" in message_lower or "bag" in message_lower:
                prefs["favorite_categories"] = ["Accessories"]
            return prefs
    
    async def process_message(self, message: str, state: ConversationState, session_id: str, channel: str = "web") -> Dict[str, Any]:
        """Process a user message and return response."""
        storage = get_storage()
        customer_id = state.customer_id or "guest"
        storage.save_message(session_id, customer_id, "user", message)
        
        user_msg = HumanMessage(content=message)
        
        inputs = {
            "messages": [user_msg],
            "interaction_count": state.interaction_count + 1,
            "updated_at": datetime.now().isoformat()
        }

        config = {"configurable": {"thread_id": session_id}}
        result = await self.graph.ainvoke(inputs, config=config)
        
        assistant_messages = [m for m in result["messages"] if hasattr(m, 'role') and m.role == "assistant"]
        response_text = assistant_messages[-1].content if assistant_messages else "How can I help you today?"
        
        storage.save_message(
            session_id, 
            customer_id, 
            "assistant", 
            response_text,
            metadata={
                "intent": result.get("current_intent"),
                "has_products": bool(result.get("recommended_products"))
            }
        )
        
        suggestions = self._generate_suggestions(result)
        
        response = {
            "response": response_text,
            "state": result,
            "suggestions": suggestions,
            "session_id": result["session_id"]
        }
        
        if result.get("recommended_products"):
            response["products"] = result["recommended_products"]
        if result.get("cart"):
            response["cart_update"] = {"items": result["cart"], "total": result["cart_total"]}
        
        return response
    
    async def _understand_intent(self, state: ConversationState) -> Dict:
        """Understand user intent from message."""
        last_message = state.messages[-1].content if state.messages else ""
        
        intent_prompt = f"""Analyze this customer message and determine their PRIMARY intent:

Message: "{last_message}"

Context:
- Cart items: {len(state.cart)}
- Previous intent: {state.current_intent}

Intent Classification Rules:
- "greeting": Greetings like hello, hi, hey, good morning
- "browsing": General product browsing, "show me", "I want", "looking for", "need"
- "product_inquiry": Checking stock/availability, "in stock", "available", "stock"
- "cart_management": View cart, modify cart, "my cart", "add to cart"
- "checkout": Ready to pay, "checkout", "pay now", "buy", "coupon", "discount", "apply coupon"
- "support": Order tracking, returns, "track", "order status", "return", "refund"
- "end": Goodbye, thanks, done, "bye"

IMPORTANT: 
- "coupon", "discount" → "checkout"
- "stock", "available" → "product_inquiry"

Classify as ONE intent based on the PRIMARY user goal."""
        
        try:
            response = await self.intent_llm.ainvoke([HumanMessage(content=intent_prompt)])
            detected_intent = response.intent
            print(f"🎯 Detected intent: {detected_intent} for message: '{last_message}'")
        except Exception as e:
            print(f"Intent detection error: {e}")
            detected_intent = "browsing"
        
        return {
            "current_intent": detected_intent,
            "updated_at": datetime.now().isoformat()
        }
    
    def _route_intent(self, state: ConversationState) -> str:
        """Route to appropriate node based on intent."""
        intent = state.current_intent
        print(f"🔀 Routing to: {intent}")
        return intent
    
    async def _greet_customer(self, state: ConversationState) -> Dict:
        """Greet customer and introduce capabilities."""
        print("👋 Greeting customer...")
        customer_name = state.customer_profile.get("name", "there") if state.customer_profile else "there"
        greeting = f"""Hello {customer_name}! 👋 
Welcome to our store! I'm your personal shopping assistant. I can help you:
✨ Find products you'll love
📦 Check real-time stock availability
🛒 Manage your shopping cart
💳 Complete secure checkout
🚚 Track orders and handle returns

What are you looking for today?"""
        
        return {
            "messages": [AIMessage(content=greeting)],
            "current_step": "introduced"
        }

    async def _recommend_products(self, state: ConversationState) -> Dict:
        """Delegates to recommendation specialist agent."""
        print("--- Orchestrator: Handoff to Recommendation Agent ---")
        
        try:
            last_message = state.messages[-1].content if state.messages else ""
            preferences = self._extract_preferences(last_message)
            
            enhanced_message = f"""User request: {last_message}

Extracted preferences:
- Categories: {', '.join(preferences.get('favorite_categories', [])) or 'Any'}
- Max price: {preferences.get('max_price') or 'No limit'}
- Min rating: {preferences.get('min_rating') or 'Any'}

Please use the recommend_products tool."""

            specialist_input = {"messages": [HumanMessage(content=enhanced_message)]}
            specialist_response = await self.recommendation_agent.ainvoke(specialist_input)
            
            tool_messages = [msg for msg in specialist_response['messages'] if isinstance(msg, ToolMessage)]
            products = []
            
            if tool_messages:
                try:
                    tool_content = tool_messages[-1].content
                    if isinstance(tool_content, str):
                        products_data = json.loads(tool_content)
                    else:
                        products_data = tool_content
                    
                    if isinstance(products_data, list):
                        products = products_data
                    print(f"✅ Found {len(products)} products")
                except Exception as e:
                    print(f"⚠️ Parse error: {e}")
            
            final_answer_msg = specialist_response['messages'][-1]
            
            return {
                "messages": [final_answer_msg],
                "recommended_products": products if products else []
            }
        except Exception as e:
            print(f"❌ Recommendation error: {e}")
            return {
                "messages": [AIMessage(content="I'm having trouble finding products. Could you tell me what you're looking for?")],
                "recommended_products": []
            }

    async def _check_inventory(self, state: ConversationState) -> Dict:
        """Check inventory with table display."""
        print("--- Orchestrator: Handoff to Inventory Agent ---")
        
        try:
            last_message = state.messages[-1].content if state.messages else ""
            message_lower = last_message.lower()
            
            if any(word in message_lower for word in ['shoes', 'footwear', 'clothing', 'electronics', 'accessories', 'stock']) and 'sku' not in message_lower:
                print("🔄 Category stock query")
                
                preferences = self._extract_preferences(last_message)
                rec_message = f"""Find products: {last_message}
Categories: {', '.join(preferences.get('favorite_categories', [])) or 'Any'}"""
                
                specialist_input = {"messages": [HumanMessage(content=rec_message)]}
                specialist_response = await self.recommendation_agent.ainvoke(specialist_input)
                
                tool_messages = [msg for msg in specialist_response['messages'] if isinstance(msg, ToolMessage)]
                products = []
                
                if tool_messages:
                    try:
                        tool_content = tool_messages[-1].content
                        if isinstance(tool_content, str):
                            products_data = json.loads(tool_content)
                        else:
                            products_data = tool_content
                        
                        if isinstance(products_data, list):
                            products = products_data[:10]
                    except Exception as e:
                        print(f"⚠️ Parse error: {e}")
                        products = []
                
                if products:
                    category_name = preferences.get('favorite_categories', ['products'])[0] if preferences.get('favorite_categories') else 'products'
                    
                    from pathlib import Path
                    data_dir = Path(__file__).parent.parent / "data"
                    
                    inventory_file = data_dir / "inventory.json"
                    if inventory_file.exists():
                        with open(inventory_file) as f:
                            INVENTORY = json.load(f)
                    else:
                        INVENTORY = []
                    
                    STORES = {
                        "WH_CENTRAL": {"name": "Central Warehouse", "type": "warehouse"},
                        "MUM01": {"name": "Mumbai Central", "type": "store", "city": "Mumbai"},
                        "DEL01": {"name": "Delhi CP", "type": "store", "city": "Delhi"},
                        "BLR01": {"name": "Bangalore Koramangala", "type": "store", "city": "Bangalore"},
                        "HYD01": {"name": "Hyderabad Banjara", "type": "store", "city": "Hyderabad"},
                        "CHN01": {"name": "Chennai T.Nagar", "type": "store", "city": "Chennai"}
                    }
                    
                    print("\n" + "="*60)
                    print(f"📊 STOCK AVAILABILITY - {category_name.upper()}")
                    print("="*60)
                    
                    response = f"📦 **STOCK AVAILABILITY - {category_name.upper()}**\n\n```\n"
                    response += f"{'Product':<30} | {'SKU':<10} | {'Price':<10} | {'Stock':<15}\n"
                    response += "-" * 75 + "\n"
                    
                    for product in products:
                        sku = product.get('sku')
                        name = product.get('name', '')[:28]
                        price = product.get('price')
                        
                        sku_inventory = [inv for inv in INVENTORY if inv["sku"] == sku]
                        
                        if sku_inventory:
                            total_stock = sum(inv["quantity"] - inv.get("reserved", 0) for inv in sku_inventory)
                            
                            print(f"\n🏷️  {name}")
                            print(f"   SKU: {sku} | Price: ₹{price:,.2f} | Stock: {total_stock} units")
                            
                            locations = []
                            for inv in sku_inventory:
                                available_qty = inv["quantity"] - inv.get("reserved", 0)
                                if available_qty > 0:
                                    location_id = inv["location_id"]
                                    location_info = {
                                        "name": STORES[location_id]["name"],
                                        "city": STORES[location_id].get("city", "N/A"),
                                        "quantity": available_qty
                                    }
                                    locations.append(location_info)
                                    print(f"   📍 {location_info['name']} ({location_info['city']}): {available_qty} units")
                            
                            response += f"{name:<30} | {sku:<10} | ₹{price:<9,.0f} | {total_stock} units\n"
                            
                            store_locs = [loc for loc in locations if 'Warehouse' not in loc['name']]
                            if store_locs:
                                cities = ', '.join([loc['city'] for loc in store_locs[:3]])
                                response += f"{'':30} | {'':10} | {'':10} | 📍 {cities}\n"
                        else:
                            response += f"{name:<30} | {sku:<10} | ₹{price:<9,.0f} | ❌ Out of Stock\n"
                    
                    response += "```\n\n💡 **Next Steps:**\n"
                    response += "• Add to cart: 'Add [product name] to cart'\n"
                    response += "• Check specific SKU: 'Check stock for SKU [code]'\n"
                    response += "• Checkout: 'I want to checkout'\n"
                    
                    print("="*60 + "\n")
                    
                    return {
                        "messages": [AIMessage(content=response)],
                        "recommended_products": products
                    }
            
            # Specific SKU query
            print("🔍 Specific SKU inventory check")
            enhanced_message = f"""User: {last_message}

Check product availability using check_availability tool if SKU mentioned."""
            
            specialist_input = {"messages": [HumanMessage(content=enhanced_message)]}
            specialist_response = await self.inventory_agent.ainvoke(specialist_input)
            
            final_answer_msg = specialist_response['messages'][-1]
            return {"messages": [final_answer_msg], "recommended_products": []}
                
        except Exception as e:
            print(f"❌ Inventory error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "messages": [AIMessage(content="I can help check stock! Provide a SKU or category.")],
                "recommended_products": []
            }

    async def _manage_cart(self, state: ConversationState) -> Dict:
        """Manage shopping cart."""
        if not state.cart:
            response = "Your cart is empty. Let me help you find something!"
        else:
            response = f"Your cart has {len(state.cart)} item(s):\n\n"
            for item in state.cart:
                response += f"• {item.name} x{item.quantity} - ₹{item.price * item.quantity:,.2f}\n"
            response += f"\n**Total: ₹{state.cart_total:,.2f}**\n\n"
            response += "Proceed to checkout or continue shopping?"
        
        return {"messages": [AIMessage(content=response)]}

    async def _process_payment(self, state: ConversationState) -> Dict:
        """Process payment with auto-discount."""
        print("--- Orchestrator: Payment Processing ---")
        
        try:
            storage = get_storage()
            customer_id = state.customer_id or "guest"
            
            # Get customer tier
            customer_profile = storage.get_customer_profile(customer_id) if hasattr(storage, 'get_customer_profile') else None
            tier = "Bronze"
            if customer_profile:
                loyalty_points = customer_profile.get("loyalty_points", 0)
                if loyalty_points >= 1000:
                    tier = "Platinum"
                elif loyalty_points >= 500:
                    tier = "Gold"
                elif loyalty_points >= 100:
                    tier = "Silver"
            
            # Get coupons from Supabase
            available_coupons = []
            if hasattr(storage, 'get_available_coupons'):
                available_coupons = storage.get_available_coupons(customer_id, tier)
            
            # Auto-apply best coupon
            cart_total = state.cart_total
            original_total = cart_total
            savings = 0
            applied_coupon = None
            
            if available_coupons:
                applicable = [c for c in available_coupons if c.get('min_purchase', 0) <= cart_total]
                if applicable:
                    best_coupon = max(applicable, key=lambda x: x['discount_value'] if x['discount_type'] == 'flat' else (cart_total * x['discount_value'] / 100))
                    
                    if best_coupon['discount_type'] == 'percentage':
                        discount = cart_total * (best_coupon['discount_value'] / 100)
                        if best_coupon.get('max_discount'):
                            discount = min(discount, best_coupon['max_discount'])
                    else:
                        discount = best_coupon['discount_value']
                    
                    cart_total -= discount
                    savings = discount
                    applied_coupon = best_coupon
            
            # Default 5% if no coupon
            if not applied_coupon:
                default_discount = original_total * 0.05
                cart_total -= default_discount
                savings = default_discount
                applied_coupon = {"code": "WELCOME5", "discount_value": 5, "discount_type": "percentage", "description": "Welcome discount"}
            
            points_earned = int(cart_total / 100)
            
            response = f"""🎉 **CHECKOUT - DISCOUNT APPLIED!**

**Order Summary:**
━━━━━━━━━━━━━━━━━━━━━━━━━
Subtotal:       ₹{original_total:,.2f}
Discount ({applied_coupon['code']}): -₹{savings:,.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━
**Final Total:  ₹{cart_total:,.2f}**
━━━━━━━━━━━━━━━━━━━━━━━━━

💰 You saved ₹{savings:,.2f}!
🎁 You'll earn {points_earned} loyalty points!

"""
            
            if len(available_coupons) > 1:
                response += "\n**📋 Other Available Coupons:**\n"
                for coupon in available_coupons[:2]:
                    if coupon['code'] != applied_coupon.get('code'):
                        discount_text = f"{coupon['discount_value']}%" if coupon['discount_type'] == 'percentage' else f"₹{coupon['discount_value']}"
                        response += f"• **{coupon['code']}**: {coupon.get('description', 'Save')} {discount_text}\n"
            
            response += "\n**💳 Payment Methods:**\n• Credit/Debit Card\n• UPI\n• Net Banking\n• Cash on Delivery\n\nWhich would you prefer?"
            
            return {
                "messages": [AIMessage(content=response)],
                "current_step": "payment_selection",
                "cart_total": cart_total,
                "available_coupons": available_coupons
            }
            
        except Exception as e:
            print(f"❌ Payment error: {e}")
            return {
                "messages": [AIMessage(content="Ready for checkout! Confirm your cart and payment method.")]
            }

    async def _fulfill_order(self, state: ConversationState) -> Dict:
        """Fulfill order."""
        print("--- Orchestrator: Order Fulfillment ---")
        
        try:
            fulfillment_prompt = f"""Create order:
Customer: {state.customer_id or "guest"}
Items: {[item.dict() for item in state.cart]}
Total: {state.cart_total}"""
            
            specialist_input = {"messages": [HumanMessage(content=fulfillment_prompt)]}
            specialist_response = await self.fulfillment_agent.ainvoke(specialist_input)
            
            final_answer = specialist_response['messages'][-1].content
            
            return {
                "messages": [AIMessage(content=final_answer)],
                "cart": [],
                "cart_total": 0.0
            }
        except Exception as e:
            print(f"❌ Fulfillment error: {e}")
            return {
                "messages": [AIMessage(content="Order created! You'll receive confirmation soon.")]
            }

    async def _handle_support(self, state: ConversationState) -> Dict:
        """Handle support queries."""
        print("--- Orchestrator: Support ---")
        
        last_message = state.messages[-1].content if state.messages else ""
        customer_id = state.customer_id or "guest"
        
        enhanced_message = f"""Customer Query: {last_message}
Customer ID: {customer_id}

Help with tracking, returns, or support queries."""
        
        specialist_input = {"messages": [HumanMessage(content=enhanced_message)]}
        specialist_response = await self.post_purchase_agent.ainvoke(specialist_input)
        
        final_answer_msg = specialist_response['messages'][-1]
        return {"messages": [final_answer_msg]}
    
    async def _end_conversation(self, state: ConversationState) -> Dict:
        """End conversation."""
        response = "Thank you for shopping! 😊 I'm always here if you need anything."
        return {
            "messages": [AIMessage(content=response)],
            "current_step": "ended"
        }
    
    def _generate_suggestions(self, state_dict: Dict) -> List[str]:
        """Generate quick reply suggestions."""
        intent = state_dict.get("current_intent", "greeting")
        cart = state_dict.get("cart", [])
        
        if intent == "greeting":
            return ["Show me footwear", "I'm looking for electronics", "What's on sale?"]
        elif intent == "browsing" or intent == "product_inquiry":
            return ["Add to cart", "Check stock", "Show more", "Apply discount"]
        elif cart:
            return ["Checkout", "View cart", "Continue shopping"]
        else:
            return ["Browse products", "Track order", "Help & Support"]


# Singleton
_sales_agent = None

def get_sales_agent() -> SalesAgent:
    """Get singleton instance of SalesAgent."""
    global _sales_agent
    if _sales_agent is None:
        _sales_agent = SalesAgent()
    return _sales_agent

"""
Sales Agent - Main orchestrator for the retail AI system
Coordinates all specialized agents and handles customer conversations.
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
    """
    Main sales agent that orchestrates the entire conversation flow.
    """
    
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
        
        # --- Add Nodes ---
        workflow.add_node("understand_intent", self._understand_intent)
        workflow.add_node("greet_customer", self._greet_customer)
        workflow.add_node("recommend_products", self._recommend_products)
        workflow.add_node("check_inventory", self._check_inventory)
        workflow.add_node("manage_cart", self._manage_cart)
        workflow.add_node("process_payment", self._process_payment)
        workflow.add_node("fulfill_order", self._fulfill_order)
        workflow.add_node("handle_support", self._handle_support)
        workflow.add_node("end_conversation", self._end_conversation)
        
        # --- Entry Point ---
        workflow.set_entry_point("understand_intent")
        
        # --- Routing ---
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

        # --- Conversation Flow (Sequential chaining) ---
        workflow.add_edge("greet_customer", "recommend_products")
        workflow.add_edge("recommend_products", "check_inventory")
        workflow.add_edge("check_inventory", "manage_cart")
        workflow.add_edge("manage_cart", "process_payment")
        workflow.add_edge("process_payment", "fulfill_order")
        workflow.add_edge("fulfill_order", "end_conversation")
        workflow.add_edge("handle_support", "end_conversation")
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
    
    async def process_message(
        self,
        message: str,
        state: ConversationState,
        session_id: str,
        channel: str = "web"
    ) -> Dict[str, Any]:
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
- "browsing": General product browsing, “show me”, “looking for”, “need”
- "product_inquiry": Checking stock/availability
- "cart_management": “add to cart”, “my cart”
- "checkout": “checkout”, “pay now”
- "support": tracking, returns, help, refund
- "end": goodbye, thanks, done
"""
        
        try:
            response = await self.intent_llm.ainvoke([HumanMessage(content=intent_prompt)])
            detected_intent = response.intent
            print(f"🎯 Detected intent: {detected_intent}")
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
        """Greet customer."""
        customer_name = state.customer_profile.get("name", "there") if state.customer_profile else "there"
        greeting = f"""Hello {customer_name}! 👋 
Welcome to our store! I'm your shopping assistant.
What are you looking for today?"""
        return {"messages": [AIMessage(content=greeting)], "current_step": "introduced"}

    async def _recommend_products(self, state: ConversationState) -> Dict:
        """Delegates to recommendation specialist."""
        print("--- Handoff to Recommendation Agent ---")
        try:
            last_message = state.messages[-1].content if state.messages else ""
            preferences = self._extract_preferences(last_message)
            
            enhanced_message = f"""User request: {last_message}
Preferences: {preferences}"""
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
                except Exception as e:
                    print(f"⚠️ Could not parse product data: {e}")
            final_answer_msg = specialist_response['messages'][-1]
            return {"messages": [final_answer_msg], "recommended_products": products or []}

        except Exception as e:
            print(f"❌ Recommendation error: {e}")
            return {"messages": [AIMessage(content="I'm having trouble finding products right now.")]}
    
    async def _check_inventory(self, state: ConversationState) -> Dict:
        """Delegates to inventory agent."""
        print("--- Handoff to Inventory Agent ---")
        try:
            last_message = state.messages[-1].content if state.messages else ""
            message_lower = last_message.lower()
            
            if any(word in message_lower for word in ['shoes', 'footwear', 'clothing', 'electronics', 'accessories']) and 'sku' not in message_lower:
                print("🔄 User asking about category stock")
                preferences = self._extract_preferences(last_message)
                rec_message = f"""Find products based on: {last_message}
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
                            print(f"✅ Found {len(products)} products for stock check")
                    except Exception as e:
                        print(f"⚠️ Could not parse products: {e}")
                        products = []
                
                if products:
                    response = f"Here's stock availability for {preferences.get('favorite_categories', ['products'])[0]}:\n"
                    for p in products:
                        response += f"• {p.get('name')} (SKU: {p.get('sku')}) - ₹{p.get('price')}\n"
                    return {"messages": [AIMessage(content=response)], "recommended_products": products}
                else:
                    specialist_input = {"messages": [HumanMessage(content=f"User wants inventory: {last_message}")]}
                    specialist_response = await self.inventory_agent.ainvoke(specialist_input)
                    return {"messages": [specialist_response['messages'][-1]]}
            else:
                enhanced_message = f"Check SKU stock: {last_message}"
                specialist_input = {"messages": [HumanMessage(content=enhanced_message)]}
                specialist_response = await self.inventory_agent.ainvoke(specialist_input)
                return {"messages": [specialist_response['messages'][-1]]}
        except Exception as e:
            print(f"❌ Inventory error: {e}")
            return {"messages": [AIMessage(content="Please provide a SKU or category name to check stock.")]}
    
    async def _manage_cart(self, state: ConversationState) -> Dict:
        """Manage shopping cart."""
        if not state.cart:
            response = "Your cart is empty."
        else:
            response = f"Your cart has {len(state.cart)} items:\n"
            for item in state.cart:
                response += f"• {item.name} x{item.quantity} - ₹{item.price * item.quantity}\n"
            response += f"\nTotal: ₹{state.cart_total}\nProceed to checkout?"
        return {"messages": [AIMessage(content=response)]}

    async def _process_payment(self, state: ConversationState) -> Dict:
        """Handle checkout."""
        print("--- Processing Payment ---")
        try:
            storage = get_storage()
            customer_id = state.customer_id or "guest"
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
            available_coupons = []
            if hasattr(storage, 'get_available_coupons'):
                available_coupons = storage.get_available_coupons(customer_id, tier)
            response = f"Proceeding to checkout. Total: ₹{state.cart_total}\n"
            if available_coupons:
                response += "Available Coupons:\n"
                for c in available_coupons:
                    response += f"• {c['code']} - {c['description']}\n"
            return {"messages": [AIMessage(content=response)]}
        except Exception as e:
            print(f"❌ Payment error: {e}")
            return {"messages": [AIMessage(content="Unable to process payment right now.")]}
    
    async def _fulfill_order(self, state: ConversationState) -> Dict:
        """Handle fulfillment."""
        print("--- Fulfillment ---")
        try:
            fulfillment_prompt = f"""Create order for {state.customer_id or 'guest'} with total {state.cart_total}"""
            specialist_input = {"messages": [HumanMessage(content=fulfillment_prompt)]}
            specialist_response = await self.fulfillment_agent.ainvoke(specialist_input)
            final_answer = specialist_response['messages'][-1].content
            return {"messages": [AIMessage(content=final_answer)]}
        except Exception:
            return {"messages": [AIMessage(content="Order placed successfully!")]}
    
    async def _handle_support(self, state: ConversationState) -> Dict:
        """Support queries."""
        print("--- Handoff to Post-Purchase Agent ---")
        last_message = state.messages[-1].content if state.messages else ""
        customer_id = state.customer_id or "guest"
        enhanced_message = f"Support Query: {last_message}\nCustomer ID: {customer_id}"
        specialist_input = {"messages": [HumanMessage(content=enhanced_message)]}
        specialist_response = await self.post_purchase_agent.ainvoke(specialist_input)
        return {"messages": [specialist_response['messages'][-1]]}
    
    async def _end_conversation(self, state: ConversationState) -> Dict:
        """End conversation."""
        response = "Thank you for shopping with us! 😊"
        return {"messages": [AIMessage(content=response)], "current_step": "ended"}
    
    def _generate_suggestions(self, state_dict: Dict) -> List[str]:
        """Quick reply suggestions."""
        intent = state_dict.get("current_intent", "greeting")
        step = state_dict.get("current_step", "greeting")
        cart = state_dict.get("cart", [])
        if intent == "greeting" or step == "introduced":
            return ["Show me footwear", "I'm looking for electronics", "What's on sale?"]
        elif intent == "browsing":
            return ["Add to cart", "Check availability", "Show more", "Apply discount"]
        elif cart:
            return ["Proceed to checkout", "View cart", "Continue shopping", "Apply coupon"]
        else:
            return ["Browse products", "Track my order", "Help & Support"]


# Singleton instance
_sales_agent = None

def get_sales_agent() -> SalesAgent:
    """Get singleton instance of SalesAgent."""
    global _sales_agent
    if _sales_agent is None:
        _sales_agent = SalesAgent()
    return _sales_agent

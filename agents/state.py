"""
Conversation state management for LangGraph agents.
Defines the state structure and transitions using Pydantic for validation.
"""

from typing import List, Dict, Optional, Annotated, Literal
from datetime import datetime
from pydantic import BaseModel, Field

# --- MODIFIED: Import LangChain's native message types ---
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
# --- MODIFIED: Import the 'add_messages' reducer ---
from langgraph.graph.message import add_messages


### MODIFIED: CartItem still good ###
class CartItem(BaseModel):
    """Item in shopping cart."""
    sku: str
    name: str
    price: float
    quantity: int
    attributes: Optional[Dict] = Field(default_factory=dict) # size, color, etc.


### MODIFIED: Converted to Pydantic Model ###
class ConversationState(BaseModel):
    """
    Complete state of a conversation session.
    This is passed between all agents in the LangGraph workflow.
    """
    
    # ===== Session Info =====
    session_id: str
    customer_id: Optional[str] = None
    channel: str # "web", "whatsapp", "telegram", "kiosk", "voice"
    
    # ===== Conversation History =====
    ### MODIFIED: Use BaseMessage and the add_messages reducer ###
    messages: Annotated[List[BaseMessage], Field(json_schema_extra={"reducer": add_messages})] = Field(default_factory=list)
    
    # ===== Customer Context =====
    customer_profile: Optional[Dict] = Field(default_factory=dict)
    purchase_history: List[Dict] = Field(default_factory=list)
    
    # ===== Current Shopping Session =====
    ### MODIFIED: We can't use 'add' for a Pydantic list, this must be handled by nodes ###
    cart: List[CartItem] = Field(default_factory=list)
    cart_total: float = 0.0
    applied_discounts: List[Dict] = Field(default_factory=list)
    
    # ===== Conversation Flow =====
    current_intent: str = "greeting"
    current_step: str = "greeting"
    next_action: Optional[str] = "greet_customer"
    
    # ... (all other fields are correct) ...
    search_filters: Dict = Field(default_factory=dict) 
    recommended_products: List[Dict] = Field(default_factory=list)
    last_viewed_products: List[str] = Field(default_factory=list)
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None 
    fulfillment_type: Optional[str] = None
    delivery_address: Optional[Dict] = None
    selected_store: Optional[str] = None
    order_id: Optional[str] = None
    order_status: Optional[str] = None
    active_agent: str = "sales_agent" 
    agent_handoff_reason: Optional[str] = None
    pending_tasks: List[Dict] = Field(default_factory=list)
    channel_history: List[Dict] = Field(default_factory=list)
    context_preserved: bool = True 
    errors: List[Dict] = Field(default_factory=list)
    retry_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    session_duration: float = 0.0
    interaction_count: int = 0
    products_viewed: int = 0
    recommendations_given: int = 0
    conversion_likelihood: float = 0.0
    
    class Config:
        arbitrary_types_allowed = True

# ===== State Initialization (This is correct) =====

def create_initial_state(
    session_id: str,
    channel: str,
    customer_id: Optional[str] = None
) -> ConversationState:
    """Create a new conversation state."""
    
    now = datetime.now().isoformat()
    
    # This is not a node. It's a helper function to create
    # the initial, full state object *before* the graph runs.
    return ConversationState(
        session_id=session_id,
        customer_id=customer_id,
        channel=channel,
        channel_history=[{"channel": channel, "timestamp": now}],
        created_at=now,
        updated_at=now
    )

# ===== DELETED ALL HELPER FUNCTIONS =====
# All functions like `add_message`, `add_to_cart`, etc.,
# have been removed. Their logic belongs *inside* your
# agent's nodes, not in the state definition file.


### MODIFIED: Removed the deleted helper functions ###
__all__ = [
    "ConversationState",
    
    "create_initial_state",
    # We also export these so 'app.py' can use them
   
]
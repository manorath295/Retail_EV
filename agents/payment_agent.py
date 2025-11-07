"""
Payment Agent - Payment processing and validation
Provides a specialist agent that can use a toolkit of payment functions.
"""

import uuid
import random
from typing import Dict, List, Optional, Any, Literal
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
class PaymentMethod(str, Enum):
    """Supported payment methods."""
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    UPI = "upi"
    NET_BANKING = "net_banking"
    WALLET = "wallet"
    COD = "cod"
    EMI = "emi"

class PaymentStatus(str, Enum):
    """Payment status states."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"

# --- In-Memory Database Simulation ---
_transactions: Dict[str, Dict] = {}

# --- Constants ---
PAYMENT_METHODS_CONFIG = {
    PaymentMethod.CREDIT_CARD: {
        "name": "Credit Card", "icon": "💳", "processing_time": "Instant",
        "max_amount": 500000, "convenience_fee": 0
    },
    PaymentMethod.DEBIT_CARD: {
        "name": "Debit Card", "icon": "💳", "processing_time": "Instant",
        "max_amount": 200000, "convenience_fee": 0
    },
    PaymentMethod.UPI: {
        "name": "UPI (PhonePe/GPay/Paytm)", "icon": "📱", "processing_time": "Instant",
        "max_amount": 100000, "convenience_fee": 0
    },
    PaymentMethod.NET_BANKING: {
        "name": "Net Banking", "icon": "🏦", "processing_time": "2-5 minutes",
        "max_amount": 1000000, "convenience_fee": 0
    },
    PaymentMethod.WALLET: {
        "name": "Digital Wallet", "icon": "👛", "processing_time": "Instant",
        "max_amount": 50000, "convenience_fee": 0
    },
    PaymentMethod.COD: {
        "name": "Cash on Delivery", "icon": "💵", "processing_time": "On delivery",
        "max_amount": 10000, "convenience_fee": 50
    },
    PaymentMethod.EMI: {
        "name": "EMI (3/6/9/12 months)", "icon": "🔢", "processing_time": "Instant",
        "max_amount": 500000, "convenience_fee": 0, "min_amount": 3000
    }
}

# --- NEW: Initialize LLM (Module-level) ---
LLM = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.google_api_key,
    temperature=AgentConfig.TEMPERATURE
)

# --- Pydantic Schemas for Tool Arguments ---

class PaymentDetails(BaseModel):
    """Detailed information for a specific payment method."""
    card_number: Optional[str] = Field(default=None, description="16-digit credit/debit card number")
    expiry_month: Optional[int] = Field(default=None, description="Card expiry month (MM)")
    expiry_year: Optional[int] = Field(default=None, description="Card expiry year (YYYY)")
    cvv: Optional[str] = Field(default=None, description="3 or 4-digit CVV code")
    upi_vpa: Optional[str] = Field(default=None, description="UPI Virtual Payment Address (e.g., user@bank)")
    wallet_provider: Optional[str] = Field(default=None, description="Digital wallet provider (e.g., Paytm, PhonePe)")

class InitiatePaymentSchema(BaseModel):
    """Input schema for initiating a payment transaction."""
    order_id: str = Field(description="The unique ID for the order.")
    customer_id: str = Field(description="The customer's unique ID.")
    amount: float = Field(description="The final amount to be paid.")
    payment_method: PaymentMethod = Field(description="The payment method chosen by the user.")
    payment_details: Optional[PaymentDetails] = Field(default=None, description="Required details for the chosen payment method.")

class RefundSchema(BaseModel):
    """Input schema for initiating a refund."""
    transaction_id: str = Field(description="The original transaction ID to refund.")
    amount: Optional[float] = Field(default=None, description="Amount to refund. If None, a full refund is processed.")
    reason: str = Field(description="A brief reason for the refund.")


# --- Internal Helper Functions ---
# (These are not tools, just logic used by the tools)

def _calculate_final_amount(amount: float, payment_method: str) -> Dict:
    try:
        method = PaymentMethod(payment_method)
        config = PAYMENT_METHODS_CONFIG[method]
        convenience_fee = config["convenience_fee"]
        total = amount + convenience_fee
        return {"subtotal": amount, "convenience_fee": convenience_fee, "total": total}
    except (ValueError, KeyError):
        return {"subtotal": amount, "convenience_fee": 0, "total": amount}

def _validate_payment_method(payment_method: str, amount: float) -> Dict:
    try:
        method = PaymentMethod(payment_method)
        config = PAYMENT_METHODS_CONFIG[method]
        
        if amount > config["max_amount"]:
            return {"valid": False, "message": f"{config['name']} has a maximum limit of ₹{config['max_amount']:,.0f}"}
        
        if method == PaymentMethod.EMI and amount < config.get("min_amount", 0):
            return {"valid": False, "message": f"EMI is available for orders above ₹{config['min_amount']:,.0f}"}
        
        return {"valid": True, "message": "Payment method accepted"}
    except ValueError:
        return {"valid": False, "message": "Invalid payment method"}

def _calculate_emi_options(amount: float) -> List[Dict]:
    emi_plans = [
        {"tenure": 3, "interest_rate": 12},
        {"tenure": 6, "interest_rate": 13},
        {"tenure": 12, "interest_rate": 15}
    ]
    options = []
    for plan in emi_plans:
        monthly_rate = plan["interest_rate"] / 12 / 100
        emi = amount * monthly_rate * (1 + monthly_rate)**plan["tenure"] / ((1 + monthly_rate)**plan["tenure"] - 1)
        total = emi * plan["tenure"]
        options.append({
            "tenure": plan["tenure"],
            "emi_amount": round(emi, 2),
            "total_amount": round(total, 2)
        })
    return options

# --- Payment Tools ---

@tool
def get_available_payment_methods(amount: float) -> List[Dict]:
    """
    Get available payment methods based on the order's total amount.
    Use this to show the customer their options.
    """
    available = []
    for method, config in PAYMENT_METHODS_CONFIG.items():
        if amount > config["max_amount"]:
            continue
        if method == PaymentMethod.EMI and amount < config.get("min_amount", 0):
            continue
        
        available.append({
            "method": method.value,
            "name": config["name"],
            "icon": config["icon"],
            "convenience_fee": config["convenience_fee"],
        })
    return available

@tool(args_schema=InitiatePaymentSchema)
def initiate_payment(
    order_id: str,
    customer_id: str,
    amount: float,
    payment_method: str,
    payment_details: Optional[Dict] = None
) -> Dict:
    """
    Initiate a payment transaction after the user has selected a method.
    """
    # Convert Pydantic object to dict if needed
    if payment_details:
        if hasattr(payment_details, 'model_dump'):
            payment_details = payment_details.model_dump()
        elif hasattr(payment_details, 'dict'):
            payment_details = payment_details.dict()
    
    validation = _validate_payment_method(payment_method, amount)
    if not validation["valid"]:
        return {"success": False, "message": validation["message"]}
    
    transaction_id = f"TXN{uuid.uuid4().hex[:12].upper()}"
    final_amount = _calculate_final_amount(amount, payment_method)
    
    transaction = {
        "transaction_id": transaction_id, "order_id": order_id,
        "customer_id": customer_id, "amount": final_amount["total"],
        "payment_method": payment_method, "status": PaymentStatus.PENDING.value,
        "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
    }
    _transactions[transaction_id] = transaction
    
    result = {
        "success": True, "transaction_id": transaction_id,
        "status": PaymentStatus.PENDING.value, "amount": final_amount["total"]
    }
    
    if payment_method == PaymentMethod.UPI.value:
        vpa = payment_details.get("upi_vpa", "retailai@upi") if payment_details else "retailai@upi"
        result["upi_intent"] = f"upi://pay?pa={vpa}&pn=RetailAI&am={final_amount['total']}&tn={order_id}"
        result["message": "Scan QR code or use UPI app to pay"]
    
    elif payment_method in [PaymentMethod.CREDIT_CARD.value, PaymentMethod.DEBIT_CARD.value]:
        result["payment_url"] = f"https://payment.retailai.com/pay/{transaction_id}"
        result["message"] = "Redirecting to secure payment gateway..."
    
    elif payment_method == PaymentMethod.COD.value:
        transaction["status"] = PaymentStatus.COMPLETED.value
        result["status"] = PaymentStatus.COMPLETED.value
        result["message"] = "Cash on Delivery confirmed. Pay when you receive the order."
    
    elif payment_method == PaymentMethod.EMI.value:
        result["emi_options"] = _calculate_emi_options(final_amount["total"])
        result["message"] = "Select EMI tenure to proceed"
        
    else:
        result["payment_url"] = f"https://payment.retailai.com/pay/{transaction_id}"
        result["message"] = "Redirecting to payment page..."
        
    return result

@tool
def process_payment(transaction_id: str) -> Dict:
    """
    (Mock) Simulates processing a payment after the user has completed the action.
    In a real app, this would be triggered by a webhook.
    """
    if transaction_id not in _transactions:
        return {"success": False, "status": PaymentStatus.FAILED.value, "message": "Transaction not found"}
    
    transaction = _transactions[transaction_id]
    
    if random.random() < 0.9: # 90% success rate
        transaction["status"] = PaymentStatus.COMPLETED.value
        transaction["completed_at"] = datetime.now().isoformat()
        return {
            "success": True, "status": PaymentStatus.COMPLETED.value,
            "message": "Payment completed successfully",
            "transaction_id": transaction_id, "amount": transaction["amount"]
        }
    else:
        transaction["status"] = PaymentStatus.FAILED.value
        transaction["failure_reason"] = "Insufficient funds / Payment declined"
        return {
            "success": False, "status": PaymentStatus.FAILED.value,
            "message": "Payment failed. Please try again."
        }

@tool
def get_transaction_status(transaction_id: str) -> Optional[Dict]:
    """Get the current status of a transaction."""
    return _transactions.get(transaction_id)

@tool(args_schema=RefundSchema)
def initiate_refund(
    transaction_id: str, 
    amount: Optional[float] = None, 
    reason: str = ""
) -> Dict:
    """Initiate a refund for a completed transaction."""
    if transaction_id not in _transactions:
        return {"success": False, "message": "Transaction not found"}
    
    transaction = _transactions[transaction_id]
    
    if transaction["status"] != PaymentStatus.COMPLETED.value:
        return {"success": False, "message": "Only completed transactions can be refunded"}
    
    refund_amount = amount or transaction["amount"]
    
    if refund_amount > transaction["amount"]:
        return {"success": False, "message": "Refund amount cannot exceed transaction amount"}
    
    refund_id = f"REF{uuid.uuid4().hex[:12].upper()}"
    transaction["status"] = PaymentStatus.REFUNDED.value
    transaction["refund_id"] = refund_id
    transaction["refund_amount"] = refund_amount
    
    return {
        "success": True, "refund_id": refund_id, "amount": refund_amount,
        "estimated_days": 5, "message": f"Refund initiated. Amount will be credited in 5 business days.",
    }

# --- Exportable list of all tools in this file ---
payment_tools = [
    get_available_payment_methods,
    initiate_payment,
    process_payment,
    get_transaction_status,
    initiate_refund
]

# --- Build and Export Agent ---

### NEW: This is the function your SalesAgent will import ###
def get_payment_agent():
    """
    Builds and returns a compiled specialist agent for payment processing.
    """
    print("--- Initializing Payment Agent ---")
    
    # 1. Create the system prompt
    system_prompt = """You are a specialist payment processing assistant.
Your job is to help users select a payment method, initiate, and process payments.
Use your tools to get available methods, start a transaction, and check its status.
You do NOT handle pricing or discounts, only the payment itself.
Be secure, clear, and concise."""

    # 2. Create the pre-built agent
    agent = create_agent(
        model=LLM,
        tools=payment_tools,
        system_prompt=system_prompt,
        state_schema=MessagesState
    )
    return agent
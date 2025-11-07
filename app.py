"""
FastAPI Application for Retail AI Agent
Main API server with WebSocket support for real-time chat.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uuid
import json
from datetime import datetime

# NEW CODE
from agents import get_sales_agent, ConversationState, create_initial_state
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from config.settings import settings

# Initialize FastAPI app
app = FastAPI(
    title="Retail AI Sales Agent",
    description="Multi-channel AI sales agent with LangGraph orchestration",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize sales agent
sales_agent = get_sales_agent()

# ===== Request/Response Models =====

class ChatRequest(BaseModel):
    """Chat message request."""
    message: str
    session_id: Optional[str] = None
    customer_id: Optional[str] = None
    channel: str = "web"

class ChatResponse(BaseModel):
    """Chat message response."""
    response: str
    session_id: str
    suggestions: List[str]
    products: Optional[List[Dict]] = None
    cart_update: Optional[Dict] = None
    available_coupons: Optional[List[Dict]] = None


# ===== HTTP Endpoints =====

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Retail AI Sales Agent API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/products")
async def get_products(
    limit: int = 12,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None
):
    """Get products with optional filters."""
    try:
        from pathlib import Path
        import json
        
        data_dir = Path(__file__).parent / "data"
        products_file = data_dir / "products.json"
        
        if not products_file.exists():
            raise HTTPException(status_code=404, detail="Products file not found")
        
        with open(products_file) as f:
            all_products = json.load(f)
        
        # Apply filters
        filtered = all_products
        
        if category and category != "All":
            filtered = [p for p in filtered if p.get("category") == category]
        
        if min_price is not None:
            filtered = [p for p in filtered if p.get("price", 0) >= min_price]
        
        if max_price is not None:
            filtered = [p for p in filtered if p.get("price", 0) <= max_price]
        
        # Limit results
        filtered = filtered[:limit]
        
        return {
            "products": filtered,
            "total": len(filtered),
            "filters": {
                "category": category,
                "min_price": min_price,
                "max_price": max_price,
                "limit": limit
            }
        }
        
    except Exception as e:
        print(f"Products endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Process a chat message.
    This endpoint is STATELESS. It relies on the agent's checkpointer.
    """
    try:
        session_id = request.session_id or f"session_{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": session_id}}

        # We must pass all keys required by the ConversationState Pydantic model
        inputs = {
            "messages": [HumanMessage(content=request.message)],
            "customer_id": request.customer_id,
            "channel": request.channel,
            "session_id": session_id
        }
        
        # 'result' will be a dictionary returned by the graph
        result = await sales_agent.graph.ainvoke(inputs, config=config)
        
        # Extract response from result dictionary
        assistant_messages = [m for m in result["messages"] if hasattr(m, 'role') and m.role == "assistant"]
        response_text = assistant_messages[-1].content if assistant_messages else "How can I help you today?"
        
        # Generate suggestions
        suggestions = sales_agent._generate_suggestions(result)
        
        # Format and return the response
        response_data = ChatResponse(
            response=response_text,
            session_id=result["session_id"],
            suggestions=suggestions,
            products=result.get("recommended_products"),
            cart_update={"items": result.get("cart"), "total": result.get("cart_total")} if result.get("cart") else None,
            available_coupons=result.get("available_coupons", [])
        )
        
        return response_data
        
    except Exception as e:
        print(f"Chat endpoint error: {e}") 
        raise HTTPException(status_code=500, detail=str(e))


# ===== WebSocket Endpoint =====

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time chat.
    This is also STATELESS and relies on the agent's checkpointer.
    """
    await websocket.accept()
    
    config = {"configurable": {"thread_id": session_id}}
    
    await websocket.send_json({
        "type": "connected",
        "session_id": session_id,
        "message": "Connected to Retail AI Agent"
    })
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "")
            
            if not user_message:
                continue
                
            # Prepare inputs for the agent
            inputs = {
                "messages": [HumanMessage(content=user_message)],
                "session_id": session_id,
                "channel": "web"
            }
            
            # Stream the agent's response
            async for chunk in sales_agent.graph.astream(inputs, config=config, stream_mode="updates"):
                # (You can stream partial chunks here in a real app)
                pass 
            
            # Get the final state *after* the stream is done
            final_state = await sales_agent.graph.aget_state(config)
            
            # Extract the data to send back
            last_message = final_state["messages"][-1].content
            suggestions = sales_agent._generate_suggestions(final_state)
            
            # Send the final response
            await websocket.send_json({
                "type": "message",
                "response": last_message,
                "suggestions": suggestions,
                "products": final_state.get("recommended_products"),
                "cart_update": {"items": final_state.get("cart"), "total": final_state.get("cart_total")},
                "timestamp": datetime.now().isoformat()
            })
            
    except WebSocketDisconnect:
        print(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })


# ===== Startup/Shutdown Events =====

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    print("🚀 Starting Retail AI Sales Agent...")
    print(f"📍 Environment: {settings.app_env}")
    print(f"🤖 Model: {settings.gemini_model}")
    print("✅ Ready to serve!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    print("👋 Shutting down Retail AI Sales Agent...")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )

"""
Supabase Database Configuration
Handles all database connections and operations
"""

import os
from typing import Optional, Dict, List, Any
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class SupabaseDB:
    """Supabase database handler"""
    
    _instance: Optional['SupabaseDB'] = None
    _client: Optional[Client] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Supabase client"""
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            print("⚠️ Supabase credentials not found in .env file")
            print("💡 Chat history will be stored in memory only")
            self._client = None
            return
        
        try:
            self._client = create_client(supabase_url, supabase_key)
            print("✅ Supabase connected successfully")
        except Exception as e:
            print(f"❌ Failed to connect to Supabase: {e}")
            self._client = None
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to Supabase"""
        return self._client is not None
    
    # ========== CHAT HISTORY ==========
    
    def save_message(
        self,
        session_id: str,
        customer_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> bool:
        """Save a chat message to database"""
        if not self.is_connected:
            return False
        
        try:
            data = {
                "session_id": session_id,
                "customer_id": customer_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "created_at": datetime.now().isoformat()
            }
            
            self._client.table("chat_history").insert(data).execute()
            return True
        except Exception as e:
            print(f"Error saving message: {e}")
            return False
    
    def get_chat_history(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get chat history for a session"""
        if not self.is_connected:
            return []
        
        try:
            response = (
                self._client.table("chat_history")
                .select("*")
                .eq("session_id", session_id)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"Error fetching chat history: {e}")
            return []
    
    def get_customer_sessions(
        self,
        customer_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get all sessions for a customer"""
        if not self.is_connected:
            return []
        
        try:
            response = (
                self._client.table("chat_history")
                .select("session_id, created_at")
                .eq("customer_id", customer_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            # Group by session_id
            sessions = {}
            for msg in response.data:
                sid = msg["session_id"]
                if sid not in sessions:
                    sessions[sid] = {
                        "session_id": sid,
                        "last_message": msg["created_at"]
                    }
            
            return list(sessions.values())
        except Exception as e:
            print(f"Error fetching sessions: {e}")
            return []
    
    # ========== CUSTOMER PROFILE ==========
    
    def get_customer_profile(self, customer_id: str) -> Optional[Dict]:
        """Get customer profile with loyalty info"""
        if not self.is_connected:
            return None
        
        try:
            response = (
                self._client.table("customers")
                .select("*")
                .eq("customer_id", customer_id)
                .single()
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"Error fetching customer profile: {e}")
            return None
    
    def update_loyalty_points(
        self,
        customer_id: str,
        points_to_add: int
    ) -> bool:
        """Update customer loyalty points"""
        if not self.is_connected:
            return False
        
        try:
            # Get current points
            profile = self.get_customer_profile(customer_id)
            if not profile:
                return False
            
            current_points = profile.get("loyalty_points", 0)
            new_points = current_points + points_to_add
            
            # Update points
            self._client.table("customers").update({
                "loyalty_points": new_points,
                "updated_at": datetime.now().isoformat()
            }).eq("customer_id", customer_id).execute()
            
            return True
        except Exception as e:
            print(f"Error updating loyalty points: {e}")
            return False
    
    # ========== ORDERS ==========
    
    def save_order(self, order_data: Dict) -> bool:
        """Save order to database"""
        if not self.is_connected:
            return False
        
        try:
            self._client.table("orders").insert(order_data).execute()
            return True
        except Exception as e:
            print(f"Error saving order: {e}")
            return False
    
    def get_customer_orders(
        self,
        customer_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """Get customer orders"""
        if not self.is_connected:
            return []
        
        try:
            response = (
                self._client.table("orders")
                .select("*")
                .eq("customer_id", customer_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"Error fetching orders: {e}")
            return []
    
    # ========== COUPONS ==========
    
    def get_available_coupons(
        self,
        customer_id: str,
        tier: str = "Bronze"
    ) -> List[Dict]:
        """Get available coupons for customer based on tier"""
        if not self.is_connected:
            return []
        
        try:
            response = (
                self._client.table("coupons")
                .select("*")
                .eq("active", True)
                .lte("min_tier_required", self._tier_to_level(tier))
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"Error fetching coupons: {e}")
            return []
    
    def _tier_to_level(self, tier: str) -> int:
        """Convert tier name to numeric level"""
        tiers = {"Bronze": 0, "Silver": 1, "Gold": 2, "Platinum": 3}
        return tiers.get(tier, 0)


# Global instance
db = SupabaseDB()


# Fallback: In-memory storage if Supabase not connected
class InMemoryStorage:
    """Fallback storage when Supabase is not available"""
    
    def __init__(self):
        self.chat_history: Dict[str, List[Dict]] = {}
        self.customer_profiles: Dict[str, Dict] = {}
        self.orders: Dict[str, List[Dict]] = {}
    
    def save_message(self, session_id: str, customer_id: str, 
                     role: str, content: str, metadata: Optional[Dict] = None):
        """Save message to memory"""
        if session_id not in self.chat_history:
            self.chat_history[session_id] = []
        
        self.chat_history[session_id].append({
            "session_id": session_id,
            "customer_id": customer_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat()
        })
    
    def get_chat_history(self, session_id: str, limit: int = 50):
        """Get chat history from memory"""
        return self.chat_history.get(session_id, [])[-limit:]
    
    def get_customer_profile(self, customer_id: str):
        """Get customer profile from memory"""
        return self.customer_profiles.get(customer_id)
    
    def get_customer_orders(self, customer_id: str, limit: int = 10):
        """Get orders from memory"""
        return self.orders.get(customer_id, [])[-limit:]


# Global fallback storage
memory_storage = InMemoryStorage()


def get_storage():
    """Get appropriate storage backend"""
    return db if db.is_connected else memory_storage

"""
Centralized configuration management for Retail AI Agent.
Loads environment variables and provides typed settings.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os
from pathlib import Path

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # ===== Google Gemini =====
    google_api_key: str = Field(..., alias="GOOGLE_API_KEY")
    gemini_model: str = "gemini-2.0-flash"  # or "gemini-1.5-flash"
    
    # ===== Supabase =====
    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_key: str = Field(..., alias="SUPABASE_KEY")
    supabase_service_key: Optional[str] = Field(None, alias="SUPABASE_SERVICE_KEY")
    
    # ===== Twilio (WhatsApp) =====
    twilio_account_sid: Optional[str] = Field(None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(None, alias="TWILIO_AUTH_TOKEN")
    twilio_whatsapp_number: Optional[str] = Field(None, alias="TWILIO_WHATSAPP_NUMBER")
    
    # ===== Telegram =====
    telegram_bot_token: Optional[str] = Field(None, alias="TELEGRAM_BOT_TOKEN")
    
    # ===== Stripe Mock =====
    stripe_secret_key: str = Field("sk_test_mock", alias="STRIPE_SECRET_KEY")
    
    # ===== Application =====
    app_name: str = Field("Retail AI Sales Agent", alias="APP_NAME")
    app_env: str = Field("development", alias="APP_ENV")
    debug: bool = Field(True, alias="DEBUG")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    
    # ===== Server =====
    host: str = Field("0.0.0.0", alias="HOST")
    port: int = Field(8000, alias="PORT")
    
    # ===== Security =====
    secret_key: str = Field("change-me-in-production", alias="SECRET_KEY")
    session_timeout: int = Field(3600, alias="SESSION_TIMEOUT")  # 1 hour
    
    # ===== Ngrok =====
    ngrok_auth_token: Optional[str] = Field(None, alias="NGROK_AUTH_TOKEN")
    
    # ===== Paths =====
    data_dir: Path = PROJECT_ROOT / "data"
    logs_dir: Path = PROJECT_ROOT / "logs"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
try:
    settings = Settings()
except Exception as e:
    print(f"⚠️  Warning: Could not load .env file. Error: {e}")
    print("Using default settings. Create .env file for production.")
    # Create minimal settings for development
    settings = Settings(
        google_api_key="PLACEHOLDER",
        supabase_url="https://placeholder.supabase.co",
        supabase_key="PLACEHOLDER"
    )


# ===== Agent Configuration =====
class AgentConfig:
    """Configuration for AI agents."""
    
    # Model parameters
    TEMPERATURE = 0.7
    MAX_TOKENS = 2048
    TOP_P = 0.9
    
    # Agent behavior
    MAX_ITERATIONS = 10
    TOOL_TIMEOUT = 30  # seconds
    
    # Conversation
    MAX_HISTORY_LENGTH = 10
    CONTEXT_WINDOW = 8192
    
    # Personalization
    RECOMMENDATION_COUNT = 5
    MIN_SIMILARITY_SCORE = 0.6


# ===== Store Configuration =====
class StoreConfig:
    """Configuration for retail stores."""
    
    STORES = [
        {"id": "MUM01", "name": "Mumbai Central", "location": "Mumbai, MH"},
        {"id": "DEL01", "name": "Delhi Connaught Place", "location": "Delhi, DL"},
        {"id": "BLR01", "name": "Bangalore Koramangala", "location": "Bangalore, KA"},
        {"id": "HYD01", "name": "Hyderabad Banjara Hills", "location": "Hyderabad, TS"},
        {"id": "CHN01", "name": "Chennai T.Nagar", "location": "Chennai, TN"}
    ]
    
    WAREHOUSE_ID = "WH_CENTRAL"


# ===== Product Categories =====
class CategoryConfig:
    """Product categories for the retail store."""
    
    CATEGORIES = [
        "Footwear",
        "Clothing",
        "Accessories",
        "Electronics",
        "Home & Living",
        "Sports & Fitness",
        "Beauty & Personal Care"
    ]


# ===== Loyalty Tiers =====
class LoyaltyConfig:
    """Loyalty program configuration."""
    
    TIERS = {
        "Bronze": {"min_points": 0, "discount": 0},
        "Silver": {"min_points": 1000, "discount": 5},
        "Gold": {"min_points": 5000, "discount": 10},
        "Platinum": {"min_points": 15000, "discount": 15}
    }
    
    POINTS_PER_RUPEE = 1  # 1 point per ₹1 spent
    RUPEES_PER_POINT = 0.1  # 1 point = ₹0.10


# Export configurations
__all__ = [
    "settings",
    "AgentConfig",
    "StoreConfig",
    "CategoryConfig",
    "LoyaltyConfig",
    "PROJECT_ROOT"
]


if __name__ == "__main__":
    print("=== Retail AI Agent Configuration ===")
    print(f"App Name: {settings.app_name}")
    print(f"Environment: {settings.app_env}")
    print(f"Debug: {settings.debug}")
    print(f"Gemini Model: {AgentConfig.TEMPERATURE}")
    print(f"Stores: {len(StoreConfig.STORES)}")
    print(f"Categories: {len(CategoryConfig.CATEGORIES)}")

import os
import json
import logging
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class SecurityManager:
    """Handles API security and secrets management (Stage 13)."""
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.api_key = os.getenv("API_KEY", "your-secret-api-key")  # Default dev key

    def get_api_key(self) -> str:
        return self.api_key

    def verify_api_key(self, x_api_key: str) -> bool:
        """Validate the API key from request headers."""
        # Simple string comparison (constant time in prod recommended)
        return x_api_key == self.api_key

    def load_secure_config(self) -> dict:
        """Load config with env var overrides for secrets."""
        with open(self.config_path, "r") as f:
            cfg = json.load(f)
            
        # Override sensitive fields from ENV if present
        if os.getenv("PRIVATE_KEY"):
            cfg["private_key"] = os.getenv("PRIVATE_KEY")
        if os.getenv("RPC_ENDPOINT"):
            cfg["rpc_endpoint"] = os.getenv("RPC_ENDPOINT")
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            cfg["telegram_bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
            
        return cfg

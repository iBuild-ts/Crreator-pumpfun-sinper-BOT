import os
import logging
import json
import asyncio
from typing import Optional, Any
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

class RedisManager:
    """Singleton wrapper for Redis operations (Stage 14)."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisManager, cls).__new__(cls)
            cls._instance.client = None
            cls._instance.enabled = False
        return cls._instance

    async def connect(self):
        """Initialize connection to Redis."""
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logging.info("Redis URL not found. Running in memory-only mode.")
            return

        try:
            self.client = redis.from_url(redis_url, decode_responses=True)
            await self.client.ping()
            self.enabled = True
            logging.info("⚡ Redis Cache Connected.")
        except Exception as e:
            logging.warning(f"Failed to connect to Redis: {e}. Fallback to memory.")
            self.enabled = False

    async def get(self, key: str) -> Optional[str]:
        if not self.enabled: return None
        try:
            return await self.client.get(key)
        except Exception as e:
            logging.error(f"Redis GET failed: {e}")
            return None

    async def set(self, key: str, value: Any, ex: int = None):
        if not self.enabled: return
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            await self.client.set(key, value, ex=ex)
        except Exception as e:
            logging.error(f"Redis SET failed: {e}")

    async def exists(self, key: str) -> bool:
        if not self.enabled: return False
        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            logging.error(f"Redis EXISTS failed: {e}")
            return False

# Global instance
cache = RedisManager()

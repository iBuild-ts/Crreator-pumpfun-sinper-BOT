import asyncio
import json
import logging
import os
import redis.asyncio as redis
from typing import Callable, Optional
from dotenv import load_dotenv

load_dotenv()

class SwarmNode:
    """
    P2P Swarm Intelligence Node (Stage 17).
    Uses Redis Pub/Sub to share 'Alpha' and 'Threats' across bot instances.
    """
    CHANNEL_NAME = "swarm_intelligence"

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL")
        self.pub_client = None
        self.sub_client = None
        self.id = os.urandom(4).hex()
        self.callbacks = []
        
    async def connect(self):
        """Connect to the Swarm Bus."""
        if not self.redis_url:
            logging.warning("⚠️ Redis URL missing. Swarm Node disabled.")
            return

        try:
            # Publisher connection
            self.pub_client = redis.from_url(self.redis_url, decode_responses=True)
            # Subscriber connection (needs separate connection in Redis)
            self.sub_client = redis.from_url(self.redis_url, decode_responses=True)
            
            logging.info(f"🐝 Swarm Node {self.id} Connected to Hive.")
            
            # Start listening
            asyncio.create_task(self._listen())
        except Exception as e:
            logging.error(f"Swarm Connection Failed: {e}")

    async def broadcast(self, event_type: str, data: dict):
        """Broadcast a signal to the hive."""
        if not self.pub_client:
            return

        message = {
            "sender": self.id,
            "type": event_type,  # e.g., 'RUG_ALERT', 'ALPHA_LAUNCH'
            "payload": data,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        try:
            await self.pub_client.publish(self.CHANNEL_NAME, json.dumps(message))
            logging.debug(f"🐝 Broadcast {event_type} to Swarm.")
        except Exception as e:
            logging.error(f"Swarm Broadcast Error: {e}")

    def add_listener(self, callback: Callable[[dict], None]):
        self.callbacks.append(callback)

    async def _listen(self):
        """Subscribe and process messages from peers."""
        try:
            async with self.sub_client.pubsub() as pubsub:
                await pubsub.subscribe(self.CHANNEL_NAME)
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = json.loads(message["data"])
                        # Ignore self-messages
                        if data.get("sender") == self.id:
                            continue
                            
                        logging.info(f"🐝 Swarm Signal Received from {data['sender']}: {data['type']}")
                        
                        # Dispatch to callbacks
                        for cb in self.callbacks:
                            asyncio.create_task(cb(data))
                            
        except Exception as e:
            logging.error(f"Swarm Listener Error: {e}")

# Global instance
swarm = SwarmNode()

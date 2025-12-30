import asyncio
import logging
import json
from typing import Optional, Callable
import websockets
import os
from dotenv import load_dotenv

load_dotenv()

class GeyserStream:
    """
    Client for Solana Geyser gRPC/WebSocket plugins (Stage 15).
    Connects to high-performance streams (Helius/Triton) for sub-ms updates.
    """
    def __init__(self, callback: Callable[[dict], None]):
        self.endpoint = os.getenv("GEYSER_ENDPOINT")
        self.api_key = os.getenv("GEYSER_API_KEY")
        self.callback = callback
        self.running = False
        
    async def connect(self):
        """Establish streaming connection."""
        if not self.endpoint:
            logging.warning("⚠️ No Geyser Endpoint configured. Latency optimization inactive.")
            return

        full_url = f"{self.endpoint}?api-key={self.api_key}" if self.api_key else self.endpoint
        logging.info(f"🌩️ Connecting to Geyser Stream: {self.endpoint}")
        
        self.running = True
        while self.running:
            try:
                async with websockets.connect(full_url) as ws:
                    logging.info("⚡ Geyser Connected. Streaming blocks...")
                    
                    # Subscribe to program updates (e.g., PumpFun)
                    subscription = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "programSubscribe",
                        "params": [
                            "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", # PumpFun Program ID
                            {
                                "encoding": "jsonParsed",
                                "commitment": "processed" 
                            }
                        ]
                    }
                    await ws.send(json.dumps(subscription))
                    
                    async for msg in ws:
                        data = json.loads(msg)
                        # Dispatch to bot logic via callback
                        if "method" in data and data["method"] == "programNotification":
                            await self.callback(data["params"]["result"])
                            
            except Exception as e:
                logging.error(f"Geyser Stream Error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def stop(self):
        self.running = False

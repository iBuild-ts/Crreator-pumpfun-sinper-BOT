import asyncio
import logging
import json
import base64
import time
import os
from typing import List, Optional
import aiohttp
from solders.transaction import Transaction

# Jito Block Engine Endpoints
JITO_REGIONS = {
    "NY": "https://ny.mainnet.block-engine.jito.wtf",
    "AMS": "https://amsterdam.mainnet.block-engine.jito.wtf",
    "TKY": "https://tokyo.mainnet.block-engine.jito.wtf",
    "SLC": "https://saltlake.mainnet.block-engine.jito.wtf"
}

class FastBundleEngine:
    """
    Custom Jito Client for Ultra-Low Latency Bundling (Stage 15).
    Bypasses SDK overhead and sends to nearest region.
    """
    def __init__(self):
        self.region = os.getenv("JITO_REGION", "NY")
        self.url = f"{JITO_REGIONS.get(self.region, JITO_REGIONS['NY'])}/api/v1/bundles"
        self.auth_keypair = None # Should load from config if needed for auth

    async def send_bundle_fast(self, transactions: List[Transaction]) -> Optional[str]:
        """Serialize and POST bundle directly to Block Engine."""
        try:
            # 1. Serialize transactions to base58/base64
            # Jito usually expects base58 strings in JSON-RPC format
            encoded_txs = [base64.b64encode(bytes(tx)).decode('utf-8') for tx in transactions]
            
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendBundle",
                "params": [
                    encoded_txs
                ]
            }
            
            # 2. Direct HTTP/2 POST (aiohttp supports keep-alive)
            start = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.post(self.url, json=payload) as resp:
                    latency = (time.time() - start) * 1000
                    if resp.status == 200:
                        data = await resp.json()
                        bundle_id = data.get("result")
                        logging.info(f"🚄 Fast Bundle Sent ({latency:.2f}ms) -> {self.region}. ID: {bundle_id}")
                        return bundle_id
                    else:
                        err = await resp.text()
                        logging.error(f"Jito Fast Send Failed: {resp.status} - {err}")
                        return None
                        
        except Exception as e:
            logging.error(f"FastBundle Error: {e}")
            return None

import httpx
import json
import logging
import os
from typing import Dict, Optional

class IPFSLoader:
    """
    Decentralized Configuration Loader (Stage 18).
    Fetches bot settings from IPFS Gateway, removing reliance on local files.
    """
    def __init__(self, gateway_url: str = "https://ipfs.io/ipfs/"):
        self.gateway = gateway_url
        self.current_cid = os.getenv("CONFIG_CID", "QmYourConfigHashHere")  # Default or from Env

    async def fetch_config(self, cid: str = None) -> Optional[Dict]:
        """Download JSON config from IPFS."""
        target_cid = cid or self.current_cid
        url = f"{self.gateway}{target_cid}"
        
        logging.info(f"🐙 IPFS: Fetching config from {url}...")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    logging.info("✅ IPFS Config Loaded Successfully.")
                    return resp.json()
                else:
                    logging.error(f"IPFS Load Failed: {resp.status_code}")
                    return None
        except Exception as e:
            logging.error(f"IPFS Connection Error: {e}")
            return None

    async def update_cid(self, new_cid: str):
        """Update the tracked CID (simulated on-chain update)."""
        self.current_cid = new_cid
        # In a real DAO, this would verify a signature on-chain
        logging.info(f"🔗 Switched to new Config Head: {new_cid}")

# Global instance
ipfs_loader = IPFSLoader()

# signals.py
import aiohttp
import logging
from typing import Optional, Dict, Any

PUMPFUN_API_METADATA = "https://frontend-api.pump.fun/coins/{mint}"

async def fetch_token_metadata(mint: str) -> Optional[Dict[str, Any]]:
    """Fetch metadata for a token from Pump.fun frontend API."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(PUMPFUN_API_METADATA.format(mint=mint), timeout=5) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logging.warning(f"PumpFun Meta API HTTP {resp.status} for {mint}")
                    return None
        except Exception as e:
            logging.error(f"Failed to fetch metadata for {mint}: {e}")
            return None

async def get_token_signals(mint: str) -> Dict[str, Any]:
    """Extract signals like live stream status and social links."""
    metadata = await fetch_token_metadata(mint)
    signals = {
        "has_live_stream": False,
        "twitter": None,
        "telegram": None,
        "website": None
    }
    
    if metadata:
        # Check for live stream (Pump.fun API sometimes indicates this or we check external sources)
        # For now, we'll check if the 'video_url' or a specific 'is_live' flag exists
        signals["has_live_stream"] = metadata.get("is_live", False) or metadata.get("video_url") is not None
        signals["twitter"] = metadata.get("twitter")
        signals["telegram"] = metadata.get("telegram")
        signals["website"] = metadata.get("website")
        
    return signals

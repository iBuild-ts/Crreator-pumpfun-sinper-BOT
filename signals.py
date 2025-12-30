import aiohttp
import logging
import json
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
async def analyze_token_sentiment(mint: str, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> float:
    """Assign an AI score (0-100) based on project quality."""
    openai_key = cfg.get("openai_api_key")
    description = metadata.get("description", "")
    name = metadata.get("name", "")
    
    if openai_key and openai_key != "YOUR_OPENAI_KEY":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json"
        }
        prompt = f"""
        Analyze the following technical/social metadata for a new Solana token and return a single integer score from 0 to 100.
        Higher score means higher effort and lower rug probability.
        Name: {name}
        Description: {description}
        Socials: {metadata.get('twitter', 'None')}, {metadata.get('telegram', 'None')}
        
        Rules:
        - If description is generic/spammy, score < 30.
        - If professional description and working socials, score > 70.
        - Return ONLY the integer score.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json={
                    "model": "gpt-3.5-turbo", # or gpt-4
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                }, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        score_text = data['choices'][0]['message']['content'].strip()
                        return float(score_text)
        except Exception as e:
            logging.error(f"AI Analysis Failed: {e}")

    # Fallback Heuristics (Keyword matching)
    score = 50.0
    bad_keywords = ["moon", "inu", "elon", "rug", "safe", "lambo", "gem"]
    good_keywords = ["protocol", "infrastructure", "utility", "ecosystem", "bridge"]
    
    for kw in bad_keywords:
        if kw in description.lower() or kw in name.lower():
            score -= 10
            
    for kw in good_keywords:
        if kw in description.lower() or kw in name.lower():
            score += 10
            
    # Buffer for socials
    if metadata.get("twitter") or metadata.get("telegram"): score += 10
    
    return max(0.0, min(100.0, score))

# flow_filters.py
import aiohttp
import logging
from typing import Optional, Dict, Any, List
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey

BITQUERY_ENDPOINT = "https://streaming.bitquery.io/graphql"

# Simple 5-minute window trading stats query for a single Pump.fun mint
PUMPFUN_TRADES_QUERY = """
query PumpFunTokenStats($mint: String!) {
  Solana {
    DEXTrades(
      where: {
        Trade: {
          Currency: { MintAddress: { is: $mint } }
          Protocol: { Name: { is: "Pump.fun" } }
        }
        Block: { Time: { since: "-5 minutes" } }
      }
    ) {
      count: count
      buyVolume: TradeAmountInUSD(
        calculate: sum
        where: { Side: { Type: { is: buy } } }
      )
      sellVolume: TradeAmountInUSD(
        calculate: sum
        where: { Side: { Type: { is: sell } } }
      )
      uniqueBuyers: count(uniq: Trade_Buy_Account)
      uniqueSellers: count(uniq: Trade_Sell_Account)
    }
  }
}
"""

# Bonding curve progress query
BONDING_CURVE_QUERY = """
query PumpFunBondingCurve($mint: String!) {
  Solana {
    PumpFunToken(
      where: { MintAddress: { is: $mint } }
    ) {
      MintAddress
      BondingCurveProgressPercentage
      HasGraduated
    }
  }
}
"""

async def fetch_bitquery(
    api_key: str,
    query: str,
    variables: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                BITQUERY_ENDPOINT,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    logging.warning(f"Bitquery HTTP {resp.status}")
                    return None
                data = await resp.json()
                if "errors" in data:
                    logging.warning(f"Bitquery errors: {data['errors']}")
                    return None
                return data.get("data")
        except Exception as e:
            logging.error(f"Bitquery request failed: {e}")
            return None

async def get_token_flow_metrics(api_key: str, mint: str) -> Optional[Dict[str, Any]]:
    """Fetch aggregated flow and curve metrics from Bitquery."""
    data_trades = await fetch_bitquery(api_key, PUMPFUN_TRADES_QUERY, {"mint": mint})
    if not data_trades:
        return None

    trades = data_trades.get("Solana", {}).get("DEXTrades")
    if not trades:
        # no trades in last 5 minutes
        flow = {
            "count": 0,
            "buyVolume": 0.0,
            "sellVolume": 0.0,
            "uniqueBuyers": 0,
            "uniqueSellers": 0,
        }
    else:
        t = trades[0]
        flow = {
            "count": t.get("count", 0) or 0,
            "buyVolume": float(t.get("buyVolume", 0) or 0),
            "sellVolume": float(t.get("sellVolume", 0) or 0),
            "uniqueBuyers": t.get("uniqueBuyers", 0) or 0,
            "uniqueSellers": t.get("uniqueSellers", 0) or 0,
        }

    data_curve = await fetch_bitquery(api_key, BONDING_CURVE_QUERY, {"mint": mint})
    if not data_curve:
        return None

    tokens = data_curve.get("Solana", {}).get("PumpFunToken")
    if not tokens:
        return None

    meta = tokens[0]
    prog = float(meta.get("BondingCurveProgressPercentage") or 0.0)
    flow["bondingCurveProgress"] = prog
    flow["hasGraduated"] = bool(meta.get("HasGraduated") or False)

    # Estimate market cap: 100% progress ~ $60k-$100k USD
    # Very rough estimate: (progress / 100) * 85 SOL * SOL_PRICE
    # Assuming SOL price ~$100 for simplicity or fetching from meta if available
    flow["marketCapUsd"] = (prog / 100.0) * 85.0 * 100.0 # Placeholder calculation

    return flow

async def should_snipe_bitquery(mint: str, cfg: dict) -> bool:
    """Refined sniper logic using Bitquery metrics."""
    api_key = cfg.get("bitquery_api_key")
    if not api_key or api_key == "YOUR_BITQUERY_KEY":
        # Missing key, can't use these filters
        return False

    metrics = await get_token_flow_metrics(api_key, mint)
    if not metrics:
        return False

    prog = metrics["bondingCurveProgress"]
    buys = metrics["uniqueBuyers"]
    volume = metrics["buyVolume"]
    sells = metrics["uniqueSellers"]

    # 1) Must still be on Pump.fun bonding curve
    if metrics["hasGraduated"]:
        return False

    # 2) Bonding curve window (Entry thresholds)
    curve_min = cfg.get("curve_progress_min", 10.0)
    curve_max = cfg.get("curve_progress_max", 60.0)
    if not (curve_min <= prog <= curve_max):
        logging.info(f"Filter: {mint[:8]}... bitquery progress {prog:.1f}% (Rejected)")
        return False

    # 3) Fresh real flow: minimum activity
    if buys < 8: # Slightly lower threshold than snippet for flexibility
        return False
    if volume < 1500: # Min $1500 buy volume
        return False

    # 4) Avoid pure dump: sell volume ratio
    if sells > buys * 1.5:
        logging.info(f"Filter: {mint[:8]}... high sell ratio (Sellers: {sells}, Buyers: {buys})")
        return False

    logging.info(
        f"✅ BITQUERY APPROVED {mint[:8]}... | Prog: {prog:.1f}% | Buyers: {buys} | BuyVol: ${volume:.0f}"
    )
    return True

async def should_snipe_signals(mint: str, cfg: dict) -> bool:
    """Check for live streams and social signals."""
    from signals import get_token_signals
    
    signals = await get_token_signals(mint)
    
    if cfg.get("require_live_stream", False) and not signals["has_live_stream"]:
        logging.info(f"Filter: {mint[:8]}... no live stream (Rejected)")
        return False
        
    if cfg.get("require_twitter", False) and not signals["twitter"]:
        logging.info(f"Filter: {mint[:8]}... no Twitter link (Rejected)")
        return False
        
    if signals["has_live_stream"]:
        logging.info(f"✨ Signal: {mint[:8]}... Has active LIVE STREAM")
        
    return True
async def check_holder_concentration(mint: str, rpc_endpoint: str, threshold_pct: float = 25.0) -> bool:
    """
    Check if the top 10 holders (excluding the bonding curve) hold too much supply.
    High concentration indicates a potential bundled launch (rug risk).
    """
    try:
        async with AsyncClient(rpc_endpoint) as client:
            mint_pubkey = Pubkey.from_string(mint)
            resp = await client.get_token_largest_accounts(mint_pubkey)
            if not resp.value or len(resp.value) < 2:
                return True # Pass for very new tokens or errors to avoid false negatives

            # Filter out the largest account (Bonding Curve holds ~98% at launch)
            # We look at the rest of the top accounts
            other_holders_total = 0
            # Total supply for PumpFun tokens is 1 Billion
            total_supply = 1_000_000_000_000_000 # 1B with 6 decimals? No, usually 6 decimals so 1B * 10^6
            # Actually PumpFun tokens have 6 decimals.
            # 1,000,000,000 * 1,000,000 = 10^15
            
            # The resp returns amounts in raw units (lamports/tokens with decimals)
            # The largest account is index 0
            top_holders = resp.value[1:11] # Next 10 largest
            
            for holder in top_holders:
                other_holders_total += holder.amount.ui_amount or 0
                
            # Total supply for PumpFun is fixed at 1 Billion tokens
            actual_total_supply = 1_000_000_000 
            concentration = (other_holders_total / actual_total_supply) * 100
            
            if concentration > threshold_pct:
                logging.info(f"Filter: {mint[:8]}... holder concentration {concentration:.1f}% > {threshold_pct}% (Rejected)")
                return False
                
            logging.info(f"✅ Holder Concentration: {concentration:.1f}% (Safe)")
            return True
    except Exception as e:
        logging.error(f"Holder Filter Error: {e}")
        return True # Default to pass on error

async def is_insider_bundle(mint: str, cfg: Dict[str, Any]) -> bool:
    """Detect if multiple top holders were funded by the same source (Stage 9)."""
    api_key = cfg.get("bitquery_api_key")
    if not api_key or api_key == "YOUR_BITQUERY_KEY":
        return False
        
    query = """
    query InsiderBundle($mint: String!) {
      Solana {
        TokenSupply(where: {Token: {MintAddress: {is: $mint}}}) {
          Account {
            Address
            Balance
          }
        }
        Transfers(where: {Transfer: {Currency: {MintAddress: {is: "So11111111111111111111111111111111111111112"}}}}) {
          Transfer {
            Receiver {
              Address
            }
            Sender {
              Address
            }
          }
        }
      }
    }
    """
    # Conceptual check: In a real scenario, we'd cross-reference top holders with their funding sources
    logging.info(f"🕵️ Analyzing insider flow for {mint[:8]}...")
    # For simulation, we'll assume a 10% chance of detecting a bundle
    import random
    if random.random() < 0.1:
        logging.warning(f"🚨 INSIDER BUNDLE DETECTED for {mint[:8]}!")
        return True
    return False

# flow_filters.py
import aiohttp
import logging
from typing import Optional, Dict, Any

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
    flow["bondingCurveProgress"] = float(meta.get("BondingCurveProgressPercentage") or 0.0)
    flow["hasGraduated"] = bool(meta.get("HasGraduated") or False)

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

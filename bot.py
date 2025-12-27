import asyncio
import json
import logging
import time
import aiohttp
from typing import Dict, Any, Optional
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from blockchain import (
    PumpFunExecutor, 
    monitor_new_tokens, 
    get_sol_balance, 
    extract_token_data
)
from flow_filters import should_snipe_bitquery

PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# --- CONFIGURATION (Default values, will be overridden by config.json) ---
CONFIG = {
    "buy_amount_sol": 0.1,
    "max_slippage_bps": 1500,
    "take_profit_percent": 50.0,
    "stop_loss_percent": 20.0,
    "fee_limit_percent": 0.02,
    "curve_progress_min": 10.0,
    "curve_progress_max": 60.0,
    "min_activity_density": 2,
    "creator_blacklist": [] 
}

# Configure logging
logging.basicConfig(
    filename="sniper_trades.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

class TradingStats:
    def __init__(self, initial_capital: float, limit_pct: float):
        self.initial_capital = initial_capital
        self.total_fees_lamports = 0
        self.limit_pct = limit_pct

    def add_fee(self, fee_lamports: int):
        self.total_fees_lamports += fee_lamports
        logging.info(f"📊 Cumulative fees: {self.total_fees_lamports / 1e9:.6f} SOL")

    def is_budget_exceeded(self) -> bool:
        fee_sol = self.total_fees_lamports / 1e9
        limit = self.initial_capital * self.limit_pct
        if fee_sol >= limit:
            logging.error(f"⚠️ BUDGET EXCEEDED: {fee_sol:.6f}/{limit:.6f} SOL spent on fees.")
            return True
        return False

# Global state
candidate_queue = asyncio.Queue()
stats_tracker = None

# Filtering integrated into should_snipe

async def listen_new_tokens(ws_endpoint: str, program_id: str, queue: asyncio.Queue):
    """Subscribe to Pump.fun platform via SDK listener and queue new candidates."""
    async def pusher(event):
        # SDK event includes signature, mint, and creator (user)
        queue.put_nowait(event)
            
    await monitor_new_tokens(ws_endpoint, pusher)

async def should_snipe(executor: PumpFunExecutor, token_info: dict) -> bool:
    """Multi-layer filtering with Analytics API support and robust SDK fallback."""
    mint_address = token_info.get("mint")
    creator_address = token_info.get("creator") or token_info.get("user")
    api_base = CONFIG.get("analytics_api_base", "http://localhost:8000")
    
    if not mint_address or not creator_address:
        return False
        
    # 1. Immediate Blacklist Check (Zero latency)
    if creator_address in CONFIG.get("creator_blacklist", []):
        logging.info(f"Filter: {mint_address[:8]}... creator BLACKLISTED")
        return False

    # 2. Try Analytics API (Scored Risk & Creator Reputation)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{api_base}/tokens/{mint_address}", timeout=1.5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    risk = data.get("rug_risk", 100.0)
                    prog = data.get("bonding_curve_progress", 0.0)
                    
                    if risk > 65: # Threshold for rejection
                        logging.info(f"Filter: {mint_address[:8]}... API flagged high risk {risk:.1f}%")
                        return False
                        
                    if not (CONFIG["curve_progress_min"] <= prog <= CONFIG["curve_progress_max"]):
                        return False

                    logging.info(f"🚀 API APPROVED: {mint_address[:8]} | Risk: {risk:.1f}% | Progress: {prog:.1f}%")
                    return True
    except Exception as e:
        logging.debug(f"Analytics API fallback: {e}")

    # 3. Fallback: SDK/Local Filters (If API is down or token is too new for API)
    state = await executor.get_bonding_curve_state(Pubkey.from_string(mint_address))
    if not state: return False
    
    progress = state.get_progress()
    if not (CONFIG["curve_progress_min"] <= progress <= CONFIG["curve_progress_max"]):
        logging.info(f"Filter: {mint_address[:8]}... progress {progress:.1f}% (Rejected)")
        return False
            
    density = await executor.get_unique_buyers(Pubkey.from_string(mint_address), seconds=60)
    if density < CONFIG["min_activity_density"]:
        logging.info(f"Filter: {mint_address[:8]}... density {density} (Rejected)")
        return False
            
    logging.info(f"🛡️ SDK FALLBACK APPROVED: {mint_address[:8]} | Progress: {progress:.1f}% | Density: {density}")
    return True

async def manage_position(executor: PumpFunExecutor, mint_address: str, creator_address: str, entry_price: float):
    """Monitor position until TP/SL or Curve Completion conditions are met."""
    logging.info(f"🛰️ Monitoring position: {mint_address} (Entry: {entry_price:.8f} SOL)")
    mint_pubkey = Pubkey.from_string(mint_address)
    
    while True:
        try:
            state = await executor.get_bonding_curve_state(mint_pubkey)
            if not state:
                await asyncio.sleep(5)
                continue
                
            current_price = state.get_price_sol()
            profit_pct = ((current_price - entry_price) / entry_price) * 100
            
            if profit_pct >= CONFIG["take_profit_percent"]:
                logging.info(f"🎯 TP REACHED: {profit_pct:.1f}% on {mint_address}")
                break
                
            if profit_pct <= -CONFIG["stop_loss_percent"]:
                logging.info(f"📉 SL HIT: {profit_pct:.1f}% on {mint_address}")
                break
                
            if state.complete:
                logging.info(f"🏁 CURVE COMPLETE: {mint_address}")
                break
                
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Error managing position {mint_address}: {e}")
            await asyncio.sleep(10)

    # Exit Position
    sell_sig = await executor.sell_token(mint_address, creator_address)
    if sell_sig:
        logging.info(f"✅ Position Closed: {mint_address} | Sig: {sell_sig}")
        # Capture fee tracking
        await asyncio.sleep(3)
        tx = await executor.client.get_transaction(sell_sig, commitment=Confirmed, max_supported_transaction_version=0)
        if tx.value and tx.value.transaction.meta:
            stats_tracker.add_fee(tx.value.transaction.meta.fee)
    else:
        logging.error(f"❌ FAILED TO SELL: {mint_address}!")

async def sniper_main():
    """Main lifecycle for the sniper bot."""
    try:
        with open("config.json", "r") as f:
            user_cfg = json.load(f)
            CONFIG.update(user_cfg)
            
        wallet = Keypair.from_base58_string(CONFIG["main_private_key"])
        executor = PumpFunExecutor(CONFIG["rpc_endpoint"], CONFIG, wallet)
        
        sol_bal = await get_sol_balance(executor.client, wallet.pubkey())
        global stats_tracker
        stats_tracker = TradingStats(sol_bal, CONFIG.get("fee_limit_percent", 0.02))
        
        logging.info(f"🏁 SNIPER READY | Wallet: {wallet.pubkey()} | Bal: {sol_bal:.4f} SOL")

        token_queue = asyncio.Queue()
        
        # Start listener and trade supervisor
        asyncio.create_task(
            listen_new_tokens(CONFIG["ws_endpoint"], PUMP_FUN_PROGRAM_ID, token_queue)
        )
        
        while True:
            candidate = await token_queue.get()
            sig = candidate.get("signature")
            mint = candidate.get("mint")
            creator = candidate.get("creator") or candidate.get("user")
            
            if stats_tracker.is_budget_exceeded():
                token_queue.task_done()
                continue

            # Fallback for missing data
            if not mint or not creator:
                token_data = await extract_token_data(executor.client, sig)
                if token_data:
                    mint, creator = token_data["mint"], token_data["creator"]
                else:
                    token_queue.task_done()
                    continue

            # Step 1: SDK/Local Filters (Fast)
            if await should_snipe(executor, {"mint": mint, "creator": creator}):
                try:
                    # Step 2: Bitquery Deep Filter (Optional/Slower)
                    if not await should_snipe_bitquery(mint, CONFIG):
                        token_queue.task_done()
                        continue

                    state = await executor.get_bonding_curve_state(Pubkey.from_string(mint))
                    entry_price = state.get_price_sol() if state else 0.0
                    
                    logging.info(f"💰 Snipping {mint}...")
                    buy_sig = await executor.buy_token(mint, creator, CONFIG["buy_amount_sol"])
                    
                    if buy_sig:
                        logging.info(f"✅ Snipe execution successful: {buy_sig}")
                        # Manage position
                        asyncio.create_task(manage_position(executor, mint, creator, entry_price))
                except Exception as e:
                    logging.error(f"Snipe failed for {mint}: {e}")
            
            token_queue.task_done()
            await asyncio.sleep(0.1) # Small loop breather
        
    except Exception as e:
        logging.error(f"FATAL: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(sniper_main())
    except KeyboardInterrupt:
        logging.info("🛑 Bot stopped.")
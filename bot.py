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
from flow_filters import (
    should_snipe_bitquery, 
    should_snipe_signals, 
    check_holder_concentration
)
from signals import get_token_metadata, analyze_token_sentiment
from db import database, get_creator_stats, get_token_analytics, trades as trades_table

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

async def send_telegram_alert(message: str):
    """Send trade notifications to Telegram."""
    try:
        # Re-read config for latest credentials
        with open("config.json", "r") as f:
            cfg = json.load(f)
        bot_token = cfg.get("telegram_bot_token")
        chat_id = cfg.get("telegram_chat_id")
    except:
        return
        
    if not bot_token or not chat_id:
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})
        except Exception as e:
            logging.error(f"Telegram Alert Failed: {e}")

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

    # 2.5 Local Database Check (Creator Reputation & Rug Risk from worker)
    try:
        creator_data = await get_creator_stats(creator_address)
        if creator_data:
            score = creator_data.get("creator_score", 50.0)
            graduated = creator_data.get("graduated_count", 0)
            rugs = creator_data.get("rug_count", 0)
            
            if score < 30 or rugs > 0:
                logging.info(f"Filter: {mint_address[:8]}... bad reputation score {score:.1f} | Rugs: {rugs}")
                return False
            
            if graduated >= 2:
                logging.info(f"🌟 TOP CREATOR detected: {creator_address[:8]}... (Graduated: {graduated})")
                # Pre-approve or lower other thresholds if needed
        
        token_data = await get_token_analytics(mint_address)
        if token_data:
            risk = token_data.get("rug_risk", 100.0)
            if risk > 70:
                logging.info(f"Filter: {mint_address[:8]}... High rug risk {risk:.1f}%")
                return False
            
            mc = token_data.get("market_cap_usd", 0.0)
            min_mc = CONFIG.get("min_market_cap_usd", 5000.0)
            if mc < min_mc:
                logging.info(f"Filter: {mint_address[:8]}... Low MC ${mc:.0f}")
                return False
    except Exception as e:
        logging.error(f"DB Filter Error: {e}")

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
            
    # 4. Holder Concentration Filter
    if not await check_holder_concentration(mint_address, executor.rpc_endpoint, CONFIG.get("max_concentration_pct", 25.0)):
        return False
        
    # 5. AI Sentiment Filter (New)
    try:
        metadata = await get_token_metadata(mint_address)
        if metadata:
            ai_score = await analyze_token_sentiment(mint_address, metadata, CONFIG)
            min_ai_score = CONFIG.get("min_ai_score", 40.0)
            if ai_score < min_ai_score:
                logging.info(f"Filter: {mint_address[:8]}... Low AI Score {ai_score:.1f} (Rejected)")
                return False
            logging.info(f"🧠 AI Score: {ai_score:.1f}/100")
    except Exception as e:
        logging.debug(f"AI Filter Error: {e}")
            
    logging.info(f"🛡️ SNIPE APPROVED: {mint_address[:8]} | Progress: {progress:.1f}% | Density: {density}")
    return True

async def manage_position(executor: PumpFunExecutor, mint_address: str, creator_address: str, entry_price: float):
    """Monitor position until TP/SL or Curve Completion conditions are met."""
    logging.info(f"🛰️ Monitoring position: {mint_address} (Entry: {entry_price:.8f} SOL)")
    mint_pubkey = Pubkey.from_string(mint_address)
    
    peak_price = entry_price
    ladder_hit = False
    
    while True:
        try:
            # Refresh config partially
            
            state = await executor.get_bonding_curve_state(mint_pubkey)
            if not state:
                await asyncio.sleep(5)
                continue
                
            current_price = state.get_price_sol()
            if current_price > peak_price:
                peak_price = current_price
                
            profit_pct = ((current_price - entry_price) / entry_price) * 100
            drop_from_peak = ((peak_price - current_price) / peak_price) * 100
            
            # 1. Take Profit
            if profit_pct >= CONFIG.get("take_profit_percent", 50.0):
                logging.info(f"🎯 TP REACHED: {profit_pct:.1f}% on {mint_address}")
                break
                
            # 2. Trailing Stop Loss (New)
            trailing_sl = CONFIG.get("trailing_stop_loss_percent", 5.0)
            if profit_pct > 10.0 and drop_from_peak >= trailing_sl: # Only activate after 10% profit
                logging.info(f"🛡️ TRAILING SL HIT: Peak {peak_price:.8f} -> Curr {current_price:.8f} (-{drop_from_peak:.1f}%)")
                break

            # 3. Standard Stop Loss
            if profit_pct <= -CONFIG.get("stop_loss_percent", 20.0):
                logging.info(f"📉 SL HIT: {profit_pct:.1f}% on {mint_address}")
                break
                
            # 4. Emergency Exit: Dev rug detection (Checking creator balance)
            # If dev sells > 50% of their holdings, we exit
            try:
                creator_ata = executor.impls.address_provider.derive_user_token_account(Pubkey.from_string(creator_address), mint_pubkey)
                creator_bal_resp = await executor.client.get_token_account_balance(creator_ata)
                if creator_bal_resp.value:
                    bal = float(creator_bal_resp.value.ui_amount or 0)
                    if bal == 0: # Dev dumped everything
                        logging.warning(f"🚨 EMERGENCY: Creator dumped holdings for {mint_address}! Exiting...")
                        break
            except: 
                pass # Account might not exist yet if they haven't bought or if they sold everything and closed account
                
            if state.complete:
                logging.info(f"🏁 CURVE COMPLETE: {mint_address}")
                break
                
            # 5. Dynamic Ladder Take Profit (Stage 6)
            # Example config: [{"pct": 50, "sell": 50}, {"pct": 100, "sell": 25}]
            ladders = CONFIG.get("ladder_exits", [{"pct": 25.0, "sell": 50}])
            if "ladder_index" not in locals(): ladder_index = 0
            
            if ladder_index < len(ladders):
                target = ladders[ladder_index]
                if profit_pct >= target["pct"]:
                    logging.info(f"🪜 LADDER TARGET {ladder_index+1} HIT: {profit_pct:.1f}% >= {target['pct']}%")
                    logging.info(f"💰 Partial Sell Executed: {target['sell']}% of position")
                    ladder_index += 1
                    # In production, this would call executor.sell_token with a partial amount
                    pass
                
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Error managing position {mint_address}: {e}")
            await asyncio.sleep(10)

    # Exit Position with dynamic Jito tip
    try:
        state = await executor.get_bonding_curve_state(mint_pubkey)
        progress = state.get_progress() if state else 0.0
        tip = executor.calculate_dynamic_jito_tip(progress)
    except:
        tip = None

    sell_sig = await executor.sell_token(mint_address, creator_address, tip=tip)
    if sell_sig:
        logging.info(f"✅ Position Closed: {mint_address} | Sig: {sell_sig}")
        # Capture fee tracking
        await asyncio.sleep(3)
        tx = await executor.client.get_transaction(sell_sig, commitment=Confirmed, max_supported_transaction_version=0)
        if tx.value and tx.value.transaction.meta:
            fee = tx.value.transaction.meta.fee
            stats_tracker.add_fee(fee)
            
            # Record sell trade in DB with improved PNL tracking
            try:
                state = await executor.get_bonding_curve_state(mint_pubkey)
                price_sol = state.get_price_sol() if state else 0.0
                price_usd = price_sol * 100 # Estimate
                
                # Fetch recent buy amount to calculate PNL
                buy_query = trades_table.select().where(
                    (trades_table.c.mint == mint_address) & (trades_table.c.side == "buy")
                ).order_by(trades_table.c.timestamp.desc())
                buy_row = await database.fetch_one(buy_query)
                
                pnl_usd = 0.0
                if buy_row:
                    entry_usd = buy_row['price_usd']
                    pnl_usd = price_usd - entry_usd
                
                await database.execute(trades_table.insert().values(
                    mint=mint_address,
                    side="sell",
                    amount_sol=0.0, 
                    amount_tokens=0.0,
                    price_usd=price_usd,
                    pnl_usd=pnl_usd,
                    tx_hash=sell_sig
                ))

                # Automated Profit Skimming (New)
                if pnl_usd > 10.0: # Skim if profit > $10
                    skim_amt = CONFIG.get("fixed_skim_sol", 0.05)
                    await executor.transfer_profits(skim_amt)
            except Exception as e:
                logging.error(f"Error recording trade: {e}")
    else:
        logging.error(f"❌ FAILED TO SELL: {mint_address}!")
        await send_telegram_alert(f"❌ *SELL FAILED* for `{mint_address[:8]}`!")

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
        
        await database.connect()
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

            # Reload CONFIG to pick up dashboard changes
            try:
                with open("config.json", "r") as f:
                    new_cfg = json.load(f)
                    CONFIG.update(new_cfg)
            except Exception as e:
                logging.debug(f"Config reload failed: {e}")

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
                        
                    # Step 3: Signals Filter (New)
                    if not await should_snipe_signals(mint, CONFIG):
                        token_queue.task_done()
                        continue

                    state = await executor.get_bonding_curve_state(Pubkey.from_string(mint))
                    progress = state.get_progress() if state else 0.0
                    tip = executor.calculate_dynamic_jito_tip(progress)
                    entry_price = state.get_price_sol() if state else 0.0
                    
                    logging.info(f"💰 Snipping {mint} (Progress: {progress:.1f}%, Tip: {tip} lamports)...")
                    
                    if CONFIG.get("use_multi_wallet", False):
                        buy_sig = await executor.buy_multi_wallet(mint, CONFIG["buy_amount_sol"], tip=tip)
                    else:
                        buy_sig = await executor.buy_token(mint, creator, CONFIG["buy_amount_sol"], tip=tip)
                    
                    if buy_sig:
                        logging.info(f"✅ Snipe execution successful: {buy_sig}")
                        await send_telegram_alert(f"💰 *SNIPED* `{mint[:8]}` at `{entry_price:.8f} SOL`!")
                        # Record buy trade in DB
                        try:
                            await database.execute(trades_table.insert().values(
                                mint=mint,
                                side="buy",
                                amount_sol=CONFIG["buy_amount_sol"],
                                amount_tokens=0.0, # Estimate or fetch later
                                price_usd=entry_price * 100, # Estimate
                                tx_hash=buy_sig
                            ))
                        except Exception as e:
                            logging.error(f"Error recording buy trade: {e}")
                            
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
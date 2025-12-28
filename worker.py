# worker.py
import asyncio
import logging
import json
import os
from datetime import datetime, timedelta
from db import database, init_db, upsert_creator, add_token, tokens, creators, trades_stats
from blockchain import monitor_new_tokens
from flow_filters import get_token_flow_metrics

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - WORKER - %(levelname)s - %(message)s"
)

async def calculate_creator_score(address: str):
    """Refined scoring based on historical performance."""
    row = await database.fetch_one(creators.select().where(creators.c.creator_address == address))
    if not row: return 50.0
    
    launched = row['tokens_launched']
    rugs = row['rug_count']
    grads = row['graduated_count']
    
    if launched == 0: return 50.0
    
    rug_ratio = rugs / launched
    grad_ratio = grads / launched
    
    score = 50.0
    score -= (rug_ratio * 60.0)
    score += (grad_ratio * 30.0)
    
    # Frequency penalty
    days = (datetime.utcnow() - row['first_seen_at']).days + 1
    launch_rate = launched / days
    if launch_rate > 10: 
        score -= 15
    elif launch_rate > 5:
        score -= 5
        
    return max(0.0, min(100.0, score))

async def calculate_rug_risk(mint: str, creator_address: str, metrics: dict):
    """Calculates risk combining creator reputation and real-time flow."""
    c_row = await database.fetch_one(creators.select().where(creators.c.creator_address == creator_address))
    c_score = c_row['creator_score'] if c_row else 50.0
    
    # Base risk derived from creator score
    risk = 100.0 - (c_score * 0.7)
    
    prog = metrics.get('bondingCurveProgress', 0.0)
    buys = metrics.get('uniqueBuyers', 0)
    vol = metrics.get('buyVolume', 0.0)
    
    # Early stage risk (Suspiciously low activity)
    if prog < 10.0 and buys < 5:
        risk += 15.0
        
    # Liquidity/Dump risk
    sells = metrics.get('uniqueSellers', 0)
    if sells > buys * 1.5 and buys > 0:
        risk += 20.0
        
    # Market cap based risk
    mc = metrics.get('marketCapUsd', 0.0)
    if mc > 50000: # High MC tokens are generally safer from instant rug
        risk -= 10.0
        
    return max(0.0, min(100.0, risk))

async def process_new_token(event: dict):
    """Callback for new token launches."""
    mint = event.get('mint')
    creator = event.get('creator') or event.get('user')
    if not mint or not creator: return
    
    logging.info(f"✨ Ingesting new launch: {mint[:8]} by {creator[:8]}")
    
    try:
        await upsert_creator(creator)
        await add_token(mint, creator)
    except Exception as e:
        logging.error(f"Worker Ingestion Error: {e}")

async def enrichment_loop(api_key: str):
    """Continuous background worker to update active tokens."""
    logging.info("🕯️ Enrichment worker started.")
    while True:
        try:
            # Fetch active tokens (limit to reasonable set for dev)
            active = await database.fetch_all(
                tokens.select().where(tokens.c.status == 'active').limit(50)
            )
            
            for t in active:
                mint = t['mint']
                creator = t['creator_address']
                
                # Fetch fresh metrics from Bitquery
                metrics = await get_token_flow_metrics(api_key, mint)
                if metrics:
                    status = "active"
                    if metrics['has_graduated']: status = "graduated"
                    
                    # Compute risk
                    risk = await calculate_rug_risk(mint, creator, metrics)
                    
                    # Update Token Record
                    await database.execute(tokens.update().where(tokens.c.mint == mint).values(
                        bonding_curve_progress=metrics['bondingCurveProgress'],
                        has_graduated=metrics['has_graduated'],
                        unique_buyers_5m=metrics['uniqueBuyers'],
                        buy_volume_usd_5m=metrics['buyVolume'],
                        unique_sellers_5m=metrics['uniqueSellers'],
                        rug_risk=risk,
                        market_cap_usd=metrics.get('marketCapUsd', 0.0),
                        status=status
                    ))
                    
                    # Update Creator History
                    if status == "graduated":
                         await database.execute(creators.update().where(creators.c.creator_address == creator).values(
                             graduated_count=creators.c.graduated_count + 1
                         ))
                    
                    # Refresh score
                    new_score = await calculate_creator_score(creator)
                    await database.execute(creators.update().where(creators.c.creator_address == creator).values(
                        creator_score=new_score
                    ))
                
            await asyncio.sleep(30) # High frequency updates for sniping
        except Exception as e:
            logging.error(f"Worker Loop Error: {e}")
            await asyncio.sleep(10)

async def worker_main():
    init_db()
    
    if not os.path.exists("config.json"):
        logging.error("Missing config.json")
        return

    with open("config.json") as f:
        cfg = json.load(f)
    
    api_key = cfg.get("bitquery_api_key")
    if not api_key or api_key == "YOUR_BITQUERY_KEY":
        logging.warning("No Bitquery API key found. Worker will stay idle.")
        return

    await database.connect()
    try:
        logging.info(f"Worker connected to {database.url}")
        
        # Start listener and enrichment loop in parallel
        await asyncio.gather(
            monitor_new_tokens(cfg['ws_endpoint'], process_new_token),
            enrichment_loop(api_key)
        )
    finally:
        await database.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(worker_main())
    except KeyboardInterrupt:
        logging.info("🛑 Worker stopped.")

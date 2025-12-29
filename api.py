# api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from db import database, tokens, creators, trades
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import List, Dict

app = FastAPI(
    title="PumpFun Analytics API",
    description="Provides real-time creator scores and token risk metrics for the sniper bot."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CreatorResponse(BaseModel):
    creator_address: str
    tokens_launched: int
    rug_count: int
    graduated_count: int
    creator_score: float

class TokenResponse(BaseModel):
    mint: str
    creator_address: str
    bonding_curve_progress: float
    has_graduated: bool
    unique_buyers_5m: int
    buy_volume_usd_5m: float
    rug_risk: float
    market_cap_usd: float
    has_live_stream: bool
    twitter_link: Optional[str] = None
    telegram_link: Optional[str] = None

class TradeResponse(BaseModel):
    id: int
    mint: str
    side: str
    amount_sol: float
    price_usd: float
    timestamp: datetime
    tx_hash: str

class StatsResponse(BaseModel):
    total_trades: int
    win_rate: float
    total_pnl_usd: float
    roi_percent: float
    total_fees_sol: float
    active_positions: int

@app.on_event("startup")
async def startup():
    if not database.is_connected:
        await database.connect()

@app.on_event("shutdown")
async def shutdown():
    if database.is_connected:
        await database.disconnect()

@app.get("/creators/{address}", response_model=CreatorResponse)
async def get_creator(address: str):
    """Fetch historical performance and score for a token creator."""
    query = creators.select().where(creators.c.creator_address == address)
    row = await database.fetch_one(query)
    if not row:
        raise HTTPException(status_code=404, detail="Creator not found")
    return CreatorResponse(**dict(row))

@app.get("/tokens/{mint}", response_model=TokenResponse)
async def get_token(mint: str):
    """Fetch real-time risk scoring and volume metrics for a mint."""
    query = tokens.select().where(tokens.c.mint == mint)
    row = await database.fetch_one(query)
    if not row:
        raise HTTPException(status_code=404, detail="Token not found")
    return TokenResponse(**dict(row))

@app.get("/trades", response_model=List[TradeResponse])
async def get_trades(limit: int = 50):
    """Fetch recent trading history."""
    query = trades.select().order_by(trades.c.timestamp.desc()).limit(limit)
    rows = await database.fetch_all(query)
    return [TradeResponse(**dict(row)) for row in rows]

@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Compute aggregate performance stats."""
    all_trades = await database.fetch_all(trades.select())
    
    total_trades = len(all_trades)
    if total_trades == 0:
        return StatsResponse(
            total_trades=0,
            win_rate=0.0,
            total_pnl_usd=0.0,
            total_fees_sol=0.0,
            active_positions=0
        )
        
    # Basic math (this would be more complex in prod)
    buys = [t for t in all_trades if t['side'] == 'buy']
    sells = [t for t in all_trades if t['side'] == 'sell']
    
    total_pnl = sum([t['pnl_usd'] or 0.0 for t in sells])
    total_investment = sum([t['amount_sol'] * 100 for t in buys]) # Rough USD estimate
    roi = (total_pnl / total_investment * 100) if total_investment > 0 else 0.0
    
    wins = len([t for t in sells if (t['pnl_usd'] or 0.0) > 0])
    win_rate = (wins / len(sells)) * 100 if sells else 0.0
    
    # Active positions = buys without matching sells (simplistic)
    buy_mints = {t['mint'] for t in buys}
    sell_mints = {t['mint'] for t in sells}
    active_count = len(buy_mints - sell_mints)
    
    return StatsResponse(
        total_trades=total_trades,
        win_rate=win_rate,
        total_pnl_usd=total_pnl,
        roi_percent=roi,
        total_fees_sol=total_trades * 0.005, # Fixed estimate for now
        active_positions=active_count
    )

@app.get("/health")
async def health():
    return {"status": "ok", "db": database.is_connected}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

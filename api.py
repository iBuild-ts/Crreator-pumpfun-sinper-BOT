# api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from db import database, tokens, creators
from datetime import datetime
import uvicorn

app = FastAPI(
    title="PumpFun Analytics API",
    description="Provides real-time creator scores and token risk metrics for the sniper bot."
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

@app.get("/health")
async def health():
    return {"status": "ok", "db": database.is_connected}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

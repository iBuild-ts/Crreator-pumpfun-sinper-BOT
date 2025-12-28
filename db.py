# db.py
import os
from databases import Database
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, Float, Boolean, DateTime, ForeignKey
from datetime import datetime

# Default to SQLite for easy local setup, can be overridden by env var
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./analytics.db")

database = Database(DATABASE_URL)
metadata = MetaData()

creators = Table(
    "creators",
    metadata,
    Column("creator_address", String, primary_key=True),
    Column("first_seen_at", DateTime, default=datetime.utcnow),
    Column("last_seen_at", DateTime, default=datetime.utcnow),
    Column("tokens_launched", Integer, default=0),
    Column("rug_count", Integer, default=0),
    Column("graduated_count", Integer, default=0),
    Column("creator_score", Float, default=50.0),
)

tokens = Table(
    "tokens",
    metadata,
    Column("mint", String, primary_key=True),
    Column("creator_address", String, ForeignKey("creators.creator_address")),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("name", String),
    Column("symbol", String),
    Column("bonding_curve_progress", Float, default=0.0),
    Column("has_graduated", Boolean, default=False),
    Column("unique_buyers_5m", Integer, default=0),
    Column("buy_volume_usd_5m", Float, default=0.0),
    Column("unique_sellers_5m", Integer, default=0),
    Column("rug_risk", Float, default=50.0),
    Column("market_cap_usd", Float, default=0.0),
    Column("status", String, default="active"), # active, rugged, graduated
)

trades = Table(
    "trades",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("mint", String, ForeignKey("tokens.mint")),
    Column("side", String), # buy, sell
    Column("amount_sol", Float),
    Column("amount_tokens", Float),
    Column("price_usd", Float),
    Column("pnl_usd", Float, default=0.0),
    Column("timestamp", DateTime, default=datetime.utcnow),
    Column("tx_hash", String),
)

trades_stats = Table(
    "trades_stats",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("mint", String, ForeignKey("tokens.mint")),
    Column("window_start", DateTime),
    Column("window_end", DateTime),
    Column("unique_buyers", Integer),
    Column("unique_sellers", Integer),
    Column("buy_volume_usd", Float),
    Column("sell_volume_usd", Float),
)

# Sync engine for table creation
engine = create_engine(
    DATABASE_URL.replace("sqlite+aiosqlite://", "sqlite://") if DATABASE_URL.startswith("sqlite") else DATABASE_URL
)

def init_db():
    metadata.create_all(engine)

async def get_creator_stats(address: str):
    query = creators.select().where(creators.c.creator_address == address)
    return await database.fetch_one(query)

async def get_token_analytics(mint: str):
    query = tokens.select().where(tokens.c.mint == mint)
    return await database.fetch_one(query)

async def upsert_creator(address: str):
    # Check if exists
    row = await get_creator_stats(address)
    if not row:
        query = creators.insert().values(
            creator_address=address,
            tokens_launched=1
        )
    else:
        query = creators.update().where(creators.c.creator_address == address).values(
            tokens_launched=row['tokens_launched'] + 1,
            last_seen_at=datetime.utcnow()
        )
    await database.execute(query)

async def add_token(mint: str, creator: str, name: str = "", symbol: str = ""):
    query = tokens.insert().values(
        mint=mint,
        creator_address=creator,
        name=name,
        symbol=symbol
    )
    await database.execute(query)

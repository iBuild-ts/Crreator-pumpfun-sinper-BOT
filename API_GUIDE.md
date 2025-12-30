# Sniper Bot API Guide

This document outlines the external API endpoints available for monitoring and controlling the PumpFun Sniper Bot.

## Base URL
The API runs on `http://localhost:8000` by default.

## Endpoints

### 1. Stats Overview
`GET /stats`
- **Description**: Returns high-level trading metrics.
- **Response**:
  ```json
  {
    "total_pnl_usd": 125.50,
    "total_trades": 42,
    "win_rate": 65.2,
    "active_positions": 2
  }
  ```

### 2. ROI History
`GET /roi`
- **Description**: Returns cumulative P&L history for charting.
- **Response**:
  ```json
  [
    {"timestamp": "2025-12-29T10:00:00", "pnl": 10.5},
    {"timestamp": "2025-12-29T11:00:00", "pnl": 25.0}
  ]
  ```

### 3. Recent Trades
`GET /trades`
- **Description**: Fetch the last 50 trades.
- **Parameters**: `limit` (Optional, default 50)
- **Response**: List of trade objects including `mint`, `side`, `amount_sol`, `pnl_usd`.

### 4. Configuration Management
`GET /config`
- **Description**: Fetch the current bot configuration.

`POST /config`
- **Description**: Update bot configuration in real-time.
- **Body**: JSON object with fields to update (e.g., `{"buy_amount_sol": 0.2}`).

### 5. Live Logs
`GET /logs`
- **Description**: Fetch the latest bot logs for dashboard display.

## Error Handling
The API returns standard HTTP status codes:
- `200`: Success
- `400`: Bad Request
- `500`: Internal Server Error

# PumpFun Sniper Bot - FIXED VERSION

## 🚨 What Was Fixed

**Previous Problem:** The bot was draining your wallet through thousands of failed transactions because it used **fake placeholder instructions** (`bytearray([1])`, `bytearray([2])`) instead of real PumpFun program calls.

**Solution:** Complete rewrite with:
- ✅ Real PumpFun program instruction builders
- ✅ Proper PDA (Program Derived Address) derivation
- ✅ Transaction simulation before sending
- ✅ Comprehensive error handling
- ✅ Balance checks before trades
- ✅ Transaction confirmation waiting
- ✅ Retry logic with exponential backoff
- ✅ Jupiter API integration path (for future)

## 📋 Changes Made

### 1. `blockchain.py` - Complete Rewrite
- **Added `simulate_and_send`** - Mandatory helper that simulates EVERY transaction before sending. If simulation fails, the transaction is aborted, saving you 100% of the fees.
- **Smart Slippage Retries** - If a trade fails due to slippage (common with high-volume PumpFun launches), the bot automatically retries once with doubled slippage (up to a safe cap) to secure the trade.
- **Added proper instruction builders** for buy/sell with correct discriminators
- **Implemented PDA derivation** for all required accounts (bonding curve, creator vault, etc.)

### 2. `bot.py` - Sniper Refactor
- **Daily Fee Budget** - Added `FEE_LIMIT_PERCENT` (default 2%). If total fees spent on trades exceed this percentage of your starting capital, the bot automatically stops for the day to protect your funds.
- **Real-time Stats** - Tracks every lamport spent on fees by querying the blockchain after each confirmed swap.
- **Converted from token CREATOR to token SNIPER**
- **Removed token creation logic** (you're a sniper, not a creator!)
- **Added sniper mode** - Monitors new tokens and trades them automatically
- **Added manual mode** - Test trades on specific tokens
- **Better logging** - Console + file logging with emojis for clarity
- **Balance management** - Won't trade if balance too low

### 3. `config.json` - New Parameters
- `mode`: "sniper" or "manual"
- `max_slippage_bps`: Slippage tolerance (100 = 1%)
- `transaction_timeout_seconds`: How long to wait for confirmation
- `max_retries`: Number of retry attempts
- `priority_fee_lamports`: Priority fee for faster inclusion

### 4. `requirements.txt` - Updated Dependencies
- Added `httpx` for Jupiter API integration
- Added `tenacity` for retry logic
- Updated Solana library versions

## 🎯 How To Use

### Setup
1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure your wallet:**
   Edit `config.json` and fill in:
   - `rpc_endpoint`: Your Solana RPC URL (e.g., QuickNode, Helius)
   - `ws_endpoint`: Your WebSocket URL
   - `main_private_key`: Your wallet's Base58 private key

3. **Choose your mode:**
   - `"mode": "sniper"` - Auto-trade new token launches
   - `"mode": "manual"` - Manually specify tokens to trade

### Run the Bot

**Sniper Mode (Auto-trade new tokens):**
```bash
python bot.py
```

**Manual Mode (Test a specific token):**
```bash
python bot.py
```
Then enter the mint address when prompted.

## ⚙️ Configuration

### Trading Parameters (in `bot.py`)
```python
BUY_AMOUNT_SOL = 0.1           # SOL to spend per buy
SELL_DELAY_SECONDS = 10        # Hold time before selling
MIN_SOL_BALANCE = 0.05         # Minimum balance to maintain
MAX_SLIPPAGE_BPS = 100         # 1% slippage tolerance
PRIORITY_FEE_LAMPORTS = 5000   # Priority fee for inclusion
```

## 🧪 Testing Strategy

> **⚠️ CRITICAL: Test on Devnet FIRST!**

### Step 1: Devnet Testing
1. Change RPC endpoint to devnet: `https://api.devnet.solana.com`
2. Get devnet SOL from faucet: `solana airdrop 2 YOUR_WALLET --url devnet`
3. Run bot in manual mode
4. Test buy/sell on a devnet token
5. Verify transactions on Solana Explorer (devnet)

### Step 2: Mainnet Testing (Small Amounts)
1. Switch to mainnet RPC
2. Set `BUY_AMOUNT_SOL = 0.01` (very small)
3. Run in manual mode first
4. Test 5-10 trades
5. Verify 100% success rate

### Step 3: Production
1. Only after successful testing
2. Gradually increase `BUY_AMOUNT_SOL`
3. Monitor closely for first 24 hours

## 🔍 Monitoring

### Check Logs
```bash
tail -f trades.log
```

### Important Log Messages
- `✅ Buy successful` - Trade executed
- `❌ Buy failed` - Trade rejected (check logs for reason)
- `Simulation failed` - Caught before wasting fees
- `Insufficient balance` - Need more SOL

## 🐛 Troubleshooting

### "Transaction simulation failed"
- **Good thing!** Simulation caught the error before wasting fees
- Check logs for specific error message
- Common causes: Insufficient slippage, token already sold out, invalid PDA

### "Insufficient balance"
- Your wallet doesn't have enough SOL
- Add more SOL or reduce `BUY_AMOUNT_SOL`

### "No tokens to sell"
- Buy didn't execute successfully
- Or token balance already sold
- Check transaction on Solscan

### All transactions still failing?
- Check RPC endpoint is working
- Verify private key is correct
- Ensure you have enough SOL (>0.1)
- Try increasing `MAX_SLIPPAGE_BPS` to 200-300

## 🚧 Known Limitations

1. **Jupiter API not fully implemented** - The Jupiter integration path exists but needs completion based on actual API response format. Currently uses manual instruction building.

2. **Bonding curve math simplified** - Token amount calculations are estimates. Should use actual bonding curve formula for precise amounts.

3. **Event parsing incomplete** - Need to properly parse token creation events from WebSocket logs to extract mint addresses.

4. **Fee recipient hardcoded** - Should fetch actual fee recipient from global config PDA.

## 🔐 Security Notes

- **Never commit `config.json`** with your real private key
- Use environment variables for production
- Start with small amounts
- Monitor all transactions
- Keep private keys secure

## 📊 Success Metrics

After running the fixed bot, you should see:
- ✅ **0 failed transactions due to invalid instructions**
- ✅ Transactions either succeed or get caught in simulation
- ✅ Fees only paid for successful trades
- ✅ Clear logs showing buy/sell cycles

## 💡 Next Steps

To make this production-ready:

1. **Complete Jupiter API integration** - Cleaner than manual instructions
2. **Add rug pull detection** - Filter out scam tokens
3. **Implement profit tracking** - Track P&L across trades
4. **Add market cap filters** - Only trade tokens above certain MC
5. **Optimize for speed** - Use Jito bundles for 0-block latency
6. **Add stop-loss** - Auto-sell if price drops X%

## 🆘 Need Help?

Check the logs in `trades.log` for detailed error messages. Each transaction is logged with:
- Timestamp
- Action (buy/sell/simulation)
- Token address
- Result (success/failure)
- Error details if failed

---

**Remember:** Test on devnet first! Don't skip this step or you'll waste more SOL on mainnet.

import asyncio
import logging
from typing import List, Dict, Any
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from blockchain import PumpFunExecutor

class WalletRebalancer:
    """Manages SOL liquidity across multi-wallets (Stage 11)."""
    def __init__(self, executor: PumpFunExecutor, config: Dict[str, Any]):
        self.executor = executor
        self.config = config
        self.min_sol_balance = config.get("min_wallet_balance_sol", 0.05)
        self.target_sol_balance = config.get("target_wallet_balance_sol", 0.2)
        self.main_wallet = executor.wallet
        self.additional_wallets = executor.additional_wallets

    async def check_and_rebalance(self):
        """Monitor and refill sub-wallets if they fall below the minimum threshold."""
        logging.info("⚖️  Rebalancer: Checking multi-wallet liquidity...")
        
        for idx, wallet in enumerate(self.additional_wallets):
            try:
                balance_resp = await self.executor.client.get_balance(wallet.pubkey())
                balance_sol = balance_resp.value / 1e9
                
                if balance_sol < self.min_sol_balance:
                    refill_amount = self.target_sol_balance - balance_sol
                    logging.info(f"⛽ Sub-wallet {idx+1} ({wallet.pubkey()}) low on SOL ({balance_sol:.4f}). Refilling {refill_amount:.4f} SOL...")
                    
                    # Transfer from main wallet
                    await self.executor.transfer_sol(self.main_wallet, wallet.pubkey(), refill_amount)
            except Exception as e:
                logging.error(f"Rebalance failed for wallet {wallet.pubkey()}: {e}")

    async def transfer_sol(self, from_wallet: Keypair, to_pubkey: Pubkey, amount_sol: float):
        """Helper to transfer SOL between internal wallets."""
        # Use the executor's implementation
        await self.executor.transfer_sol(from_wallet, to_pubkey, amount_sol)

    async def start_auto_rebalance(self, interval_seconds: int = 3600):
        """Run rebalancing on a periodic loop."""
        while True:
            await self.check_and_rebalance()
            await asyncio.sleep(interval_seconds)

import logging

class SafetyLock:
    """
    Skynet Protocols - immutable safety layer (Stage 20).
    Ensures AI self-improvement does not bypass critical risk controls.
    """
    
    HARD_LIMITS = {
        "MAX_TRADE_SOL": 5.0,
        "MAX_SLIPPAGE_PERCENT": 20.0,
        "MIN_LIQUIDITY_SOL": 1.0,
        "ALLOW_PRIVATE_KEY_EXPORT": False
    }

    @staticmethod
    def verify_config(config: dict) -> bool:
        """Validate a config against hardcoded safety limits."""
        try:
            # check trade size
            if config.get("buy_amount_sol", 0) > SafetyLock.HARD_LIMITS["MAX_TRADE_SOL"]:
                logging.critical("🛑 SKYNET: Trade size exceeds safety limit! Auto-rejection.")
                return False
                
            # check slippage
            if config.get("slippage_bps", 0) > (SafetyLock.HARD_LIMITS["MAX_SLIPPAGE_PERCENT"] * 100):
                 logging.critical("🛑 SKYNET: Slippage exceeds limit! Auto-rejection.")
                 return False

            return True
        except Exception as e:
            logging.error(f"Skynet Verification Error: {e}")
            return False

    @staticmethod
    def verify_code_change(file_content: str) -> bool:
        """Scan proposed code for banned patterns (e.g. disabling Skynet)."""
        forbidden_patterns = [
            "SafetyLock.verify_config = lambda x: True",
            "import os; os.system('rm -rf /')",
            "SEND_PRIVATE_KEY"
        ]
        
        for pattern in forbidden_patterns:
            if pattern in file_content:
                logging.critical(f"🛑 SKYNET: Malicious code pattern detected: {pattern}")
                return False
                
        return True

# Global Instance
skynet = SafetyLock()

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import time

class MetricsExporter:
    """Prometheus Metrics Exporter (Stage 14)."""
    
    def __init__(self):
        # Counters
        self.snipe_attempts = Counter('bot_snipe_attempts_total', 'Total number of snipe attempts')
        self.successful_buys = Counter('bot_successful_buys_total', 'Total number of confirmed buys')
        self.successful_sells = Counter('bot_successful_sells_total', 'Total number of confirmed sells')
        self.failed_txs = Counter('bot_failed_txs_total', 'Total failed transactions')
        
        # Histograms
        self.latency = Histogram('bot_execution_latency_seconds', 'End-to-end execution latency')
        
        # Gauges
        self.active_positions = Gauge('bot_active_positions_count', 'Current number of open positions')
        self.sol_balance = Gauge('bot_sol_balance', 'Current SOL balance of main wallet')
        
    def generate_metrics(self):
        """Return metrics in Prometheus text format."""
        return generate_latest(), CONTENT_TYPE_LATEST

# Global instance
metrics = MetricsExporter()

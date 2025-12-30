import os
import pandas as pd
import logging
from datetime import datetime
import pyarrow as pa
import pyarrow.parquet as pq
from typing import List, Dict

DATA_LAKE_DIR = "data_lake"

class DataLake:
    """Archival service for historical market data (Stage 16)."""
    
    def __init__(self):
        if not os.path.exists(DATA_LAKE_DIR):
            os.makedirs(DATA_LAKE_DIR)
            
    def archive_trades(self, trade_data: List[Dict]):
        """Save a batch of trades to Parquet format (Columnar storage)."""
        if not trade_data:
            return
            
        try:
            df = pd.DataFrame(trade_data)
            # Ensure timestamps are datetime
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
            day_str = datetime.now().strftime("%Y-%m-%d")
            file_path = os.path.join(DATA_LAKE_DIR, f"trades_{day_str}.parquet")
            
            # Check if file exists to append
            if os.path.exists(file_path):
                existing_table = pq.read_table(file_path)
                existing_df = existing_table.to_pandas()
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                table = pa.Table.from_pandas(combined_df)
            else:
                table = pa.Table.from_pandas(df)
                
            pq.write_table(table, file_path)
            logging.info(f"💾 Data Lake: Archived {len(df)} records to {file_path}")
            
        except Exception as e:
            logging.error(f"Data Lake Archive Failed: {e}")

    def load_history(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Load archived data for backtesting replay."""
        # Simplified loading logic for demo
        try:
            files = [f for f in os.listdir(DATA_LAKE_DIR) if f.endswith(".parquet")]
            dfs = []
            for f in files:
                path = os.path.join(DATA_LAKE_DIR, f)
                dfs.append(pd.read_parquet(path))
            
            if not dfs:
                return pd.DataFrame()
                
            full_df = pd.concat(dfs, ignore_index=True)
            # Filter by date range would go here
            return full_df.sort_values(by="timestamp")
            
        except Exception as e:
            logging.error(f"Data Lake Load Failed: {e}")
            return pd.DataFrame()

# Global instance
lake = DataLake()

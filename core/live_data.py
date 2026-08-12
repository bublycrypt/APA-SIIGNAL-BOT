"""
Live market data fetcher using CCXT (crypto) and other sources.
Fetches real OHLC data for backtesting and live trading.
"""

from __future__ import annotations
import ccxt
import pandas as pd
from typing import Optional, List
from datetime import datetime, timedelta
import time
import os


class LiveDataFetcher:
    """Fetch live market data from crypto exchanges via CCXT."""
    
    def __init__(self, exchange_name: str = "binance", api_key: str = None, api_secret: str = None):
        """
        Initialize CCXT exchange connection.
        
        Args:
            exchange_name: Exchange to use (binance, kraken, coinbase, etc)
            api_key: Optional API key for authenticated endpoints
            api_secret: Optional API secret
        """
        self.exchange_name = exchange_name.lower()
        
        # Get exchange class
        if not hasattr(ccxt, self.exchange_name):
            raise ValueError(f"Exchange '{exchange_name}' not supported by CCXT. "
                           f"Supported: {', '.join(ccxt.exchanges)}")
        
        ExchangeClass = getattr(ccxt, self.exchange_name)
        
        # Initialize with credentials if provided
        config = {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"}
        }
        
        if api_key and api_secret:
            config["apiKey"] = api_key
            config["secret"] = api_secret
        
        self.exchange = ExchangeClass(config)
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
        since: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Fetch OHLC data for a symbol.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT', 'ETH/USDT')
            timeframe: Timeframe (1m, 5m, 15m, 1h, 4h, 1d, etc)
            limit: Number of candles to fetch (max ~500 per call)
            since: Unix timestamp to start from (optional)
        
        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        try:
            print(f"[{self.exchange_name.upper()}] Fetching {symbol} {timeframe} ({limit} candles)...")
            
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                limit=limit,
                since=since,
            )
            
            if not ohlcv:
                raise ValueError(f"No data returned for {symbol}")
            
            # Convert to DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            
            # Convert timestamp to datetime
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.set_index("timestamp")
            
            print(f"  ✓ Fetched {len(df)} candles ({df.index[0]} → {df.index[-1]})")
            
            return df
        
        except Exception as e:
            print(f"  ✗ Error fetching {symbol}: {e}")
            raise
    
    def fetch_multiple_timeframes(
        self,
        symbol: str,
        timeframes: List[str] = None,
        limit: int = 500,
    ) -> dict:
        """
        Fetch multiple timeframes for a symbol.
        
        Args:
            symbol: Trading pair
            timeframes: List of timeframes (e.g., ['5m', '1h', '4h'])
            limit: Candles per timeframe
        
        Returns:
            Dict mapping timeframe -> DataFrame
        """
        if timeframes is None:
            timeframes = ["5m", "1h", "4h"]
        
        data = {}
        for tf in timeframes:
            try:
                data[tf] = self.fetch_ohlc(symbol, timeframe=tf, limit=limit)
                time.sleep(0.1)  # Rate limit
            except Exception as e:
                print(f"  [Warn] Failed to fetch {tf}: {e}")
        
        return data
    
    def stream_latest(
        self,
        symbol: str,
        timeframe: str = "1h",
        callback=None,
        interval_seconds: int = 60,
    ):
        """
        Poll for latest OHLC candle and call callback.
        
        Args:
            symbol: Trading pair
            timeframe: Timeframe to monitor
            callback: Function to call with new candle (receives DataFrame row)
            interval_seconds: Poll interval
        """
        print(f"[STREAM] Starting live feed for {symbol} {timeframe}...")
        
        last_timestamp = None
        
        try:
            while True:
                df = self.fetch_ohlc(symbol, timeframe=timeframe, limit=10)
                
                # Get latest candle
                latest = df.iloc[-1]
                
                if last_timestamp is None or latest.name != last_timestamp:
                    print(f"[NEW] {symbol} {timeframe} @ {latest.name}")
                    last_timestamp = latest.name
                    
                    if callback:
                        callback(latest)
                
                time.sleep(interval_seconds)
        
        except KeyboardInterrupt:
            print(f"\n[STREAM] Stopped monitoring {symbol}")

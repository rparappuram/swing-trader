"""Data management for historical and live market data.

This module handles data loading with intelligent caching and validation:
- For backtest/optimization: Checks local files, validates date ranges, fetches if needed
- For live trading: Always fetches fresh data from Alpaca API
"""
import pandas as pd
import backtrader as bt
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
import logging


logger = logging.getLogger(__name__)


class DataManager:
    """Manages market data loading from parquet files or Alpaca API."""
    
    def __init__(self, daily_path: str = "data/daily", minute_path: str = "data/minute"):
        """Initialize data manager.
        
        Args:
            daily_path: Path to daily parquet files
            minute_path: Path to minute parquet files
        """
        self.daily_path = Path(daily_path)
        self.minute_path = Path(minute_path)
        self.alpaca_client = None
    
    def init_alpaca_client(self, api_key: str, secret_key: str):
        """Initialize Alpaca data client for live data fetching.
        
        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
        """
        self.alpaca_client = StockHistoricalDataClient(api_key, secret_key)
    
    def _check_file_exists(self, ticker: str, timeframe: str) -> bool:
        """Check if data file exists for ticker.
        
        Args:
            ticker: Stock ticker symbol
            timeframe: 'daily' or 'minute'
            
        Returns:
            True if file exists, False otherwise
        """
        path = self.daily_path if timeframe == 'daily' else self.minute_path
        file_path = path / f"{ticker}.parquet"
        return file_path.exists()
    
    def _check_date_range_coverage(self, ticker: str, timeframe: str,
                                   start_date: datetime, end_date: datetime) -> bool:
        """Check if local file has data covering the required date range.
        
        Args:
            ticker: Stock ticker symbol
            timeframe: 'daily' or 'minute'
            start_date: Required start date
            end_date: Required end date
            
        Returns:
            True if file covers the date range, False otherwise
        """
        path = self.daily_path if timeframe == 'daily' else self.minute_path
        file_path = path / f"{ticker}.parquet"
        
        if not file_path.exists():
            return False
        
        try:
            df = pd.read_parquet(file_path)
            if df.empty:
                return False
            
            # Check if data covers required range
            data_start = df.index.min()
            data_end = df.index.max()
            
            # Convert to datetime and ensure timezone-aware (UTC)
            if isinstance(data_start, pd.Timestamp):
                data_start = data_start.to_pydatetime()
                # Ensure timezone-aware (add UTC if naive)
                if data_start.tzinfo is None:
                    data_start = data_start.replace(tzinfo=timezone.utc)
            
            if isinstance(data_end, pd.Timestamp):
                data_end = data_end.to_pydatetime()
                # Ensure timezone-aware (add UTC if naive)
                if data_end.tzinfo is None:
                    data_end = data_end.replace(tzinfo=timezone.utc)
            
            # Ensure comparison dates are timezone-aware (UTC)
            compare_start = start_date if start_date.tzinfo else start_date.replace(tzinfo=timezone.utc)
            compare_end = end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)
            
            # Allow some flexibility (data can start a bit after and end a bit before)
            # but generally should cover the range
            has_coverage = (data_start <= compare_start + timedelta(days=5) and 
                          data_end >= compare_end - timedelta(days=5))
            
            if has_coverage:
                logger.info(f"Using cached {timeframe} data for {ticker}")
            else:
                logger.info(f"Cached {timeframe} data for {ticker} insufficient, fetching fresh data")
            
            return has_coverage
            
        except Exception as e:
            logger.warning(f"Error checking date range for {ticker}: {e}")
            return False
    
    def _fetch_from_alpaca(self, ticker: str, start_date: datetime, 
                          end_date: datetime, timeframe: str) -> pd.DataFrame:
        """Fetch data from Alpaca API.
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date
            end_date: End date
            timeframe: 'daily' or 'minute'
            
        Returns:
            DataFrame with OHLCV data
        """
        if not self.alpaca_client:
            raise RuntimeError("Alpaca client not initialized. Call init_alpaca_client first.")
        
        logger.info(f"Fetching {timeframe} data from Alpaca for {ticker}")
        
        # Create TimeFrame instance explicitly for proper typing
        if timeframe == 'daily':
            tf: TimeFrame = TimeFrame(1, TimeFrameUnit.Day)  # type: ignore[arg-type]
        else:
            tf: TimeFrame = TimeFrame(1, TimeFrameUnit.Minute)  # type: ignore[arg-type]
        
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=tf,
            start=start_date,
            end=end_date
        )
        
        bars = self.alpaca_client.get_stock_bars(request)
        df: pd.DataFrame = bars.df  # type: ignore[attr-defined]
        
        if df.empty:
            logger.warning(f"No data returned from Alpaca for {ticker}")
            return df
        
        # Reset index to get symbol and timestamp as columns, then set timestamp as index
        df = df.reset_index()
        df = df[df['symbol'] == ticker].set_index('timestamp')
        df = df[['open', 'high', 'low', 'close', 'volume']]
        
        return df
    
    def _load_from_file(self, ticker: str, timeframe: str,
                       start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Load data from local parquet file.
        
        Args:
            ticker: Stock ticker symbol
            timeframe: 'daily' or 'minute'
            start_date: Start date
            end_date: End date
            
        Returns:
            DataFrame with OHLCV data
        """
        path = self.daily_path if timeframe == 'daily' else self.minute_path
        file_path = path / f"{ticker}.parquet"
        
        logger.info(f"Loading {timeframe} data for {ticker}")
        
        df = pd.read_parquet(file_path)
        
        # Ensure index is timezone-aware (add UTC if naive)
        if df.index.tz is None:  # type: ignore[attr-defined]
            df.index = df.index.tz_localize('UTC')  # type: ignore[attr-defined]
        
        # Ensure comparison dates are timezone-aware (UTC)
        start_date_aware = start_date if start_date.tzinfo else start_date.replace(tzinfo=timezone.utc)
        end_date_aware = end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)
        
        # Filter by date range
        df = df[df.index >= start_date_aware]
        df = df[df.index <= end_date_aware]
        
        return df
    
    def get_data_for_backtest(self, ticker: str, start_date: datetime,
                              end_date: datetime, timeframe: str = 'daily') -> pd.DataFrame:
        """Get data for backtesting/optimization.
        
        This method:
        1. Checks if data file exists
        2. Validates date range coverage
        3. Loads from file if available, otherwise fetches from Alpaca
        4. Saves fetched data for future use
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date
            end_date: End date
            timeframe: 'daily' or 'minute'
            
        Returns:
            DataFrame with OHLCV data indexed by timestamp
        """
        # Check if file exists and covers date range
        file_exists = self._check_file_exists(ticker, timeframe)
        
        if file_exists:
            has_coverage = self._check_date_range_coverage(ticker, timeframe, 
                                                          start_date, end_date)
            if has_coverage:
                # Load from local file
                return self._load_from_file(ticker, timeframe, start_date, end_date)
        
        # Need to fetch from Alpaca
        if not file_exists:
            logger.info(f"No cached {timeframe} data for {ticker}, fetching from Alpaca")
        else:
            logger.info(f"Cached {timeframe} data insufficient for {ticker}, fetching from Alpaca")
        
        df = self._fetch_from_alpaca(ticker, start_date, end_date, timeframe)
        
        if not df.empty:
            # Save for future use
            self.save_data(ticker, df, timeframe)
        
        return df
    
    def get_data_for_live(self, ticker: str, days_back: int = 30) -> pd.DataFrame:
        """Get data for live trading (always fetches fresh from Alpaca).
        
        Args:
            ticker: Stock ticker symbol
            days_back: Number of days of historical data to fetch
            
        Returns:
            DataFrame with OHLCV data indexed by timestamp
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back + 10)  # Add buffer for weekends/holidays
        
        logger.info(f"Fetching live data for {ticker}")
        
        return self._fetch_from_alpaca(ticker, start_date, end_date, 'daily')
    
    def save_data(self, ticker: str, df: pd.DataFrame, timeframe: str):
        """Save data to parquet file.
        
        Args:
            ticker: Stock ticker symbol
            df: DataFrame with OHLCV data
            timeframe: 'daily' or 'minute'
        """
        path = self.daily_path if timeframe == 'daily' else self.minute_path
        path.mkdir(parents=True, exist_ok=True)
        
        file_path = path / f"{ticker}.parquet"
        df.to_parquet(file_path)
        logger.info(f"Cached {timeframe} data for {ticker}")
    
    def create_backtrader_feed(self, df: pd.DataFrame, ticker_name: str) -> bt.feeds.PandasData:
        """Create a backtrader data feed from DataFrame.
        
        Args:
            df: DataFrame with OHLCV data indexed by timestamp
            ticker_name: Name for the data feed
            
        Returns:
            Backtrader PandasData feed
        """
        # Ensure columns are lowercase
        df = df.copy()
        df.columns = [col.lower() for col in df.columns]
        
        # Create backtrader data feed
        # Type ignores needed due to incomplete backtrader type stubs
        data_feed = bt.feeds.PandasData(
            dataname=df,  # type: ignore[call-arg]
            datetime=None,  # type: ignore[call-arg]  # Use index as datetime
            open='open',  # type: ignore[call-arg]
            high='high',  # type: ignore[call-arg]
            low='low',  # type: ignore[call-arg]
            close='close',  # type: ignore[call-arg]
            volume='volume',  # type: ignore[call-arg]
            openinterest=-1  # type: ignore[call-arg]  # Not used
        )
        
        return data_feed

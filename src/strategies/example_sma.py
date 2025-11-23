"""Example SMA crossover strategy.

This demonstrates how to implement a strategy that works in both backtesting
and live trading. The strategy uses simple moving average crossovers for signals
and includes trailing stop functionality.
"""
import backtrader as bt
from .base_strategy import BaseStrategy


class SMAStrategy(BaseStrategy):
    """Simple Moving Average crossover strategy.
    
    Entry Signal: Fast SMA crosses above Slow SMA
    Exit Signal: Fast SMA crosses below Slow SMA, or trailing stop hit
    
    This strategy operates on daily bars only and uses trailing stops for
    risk management.
    """
    
    # Strategy configuration
    NAME = "SMAStrategy"
    
    # Optimization parameter ranges
    OPTIMIZE_PARAMS = {
        'fast_period': range(5, 31, 5),
        'slow_period': range(20, 51, 10),
        'trailing_stop_percent': [x / 10000 for x in range(200, 2001, 200)],  # 0.02 (2%) to 0.20 (20%)
    }
    
    # Default parameters (backtrader format)
    params = (
        ('tickers', ['SPY']),
        ('lookback_days', 30),
        ('position_percent', 1.0),  # Use 100% of available cash per position
        ('fast_period', 10),
        ('slow_period', 30),
        ('trailing_stop_percent', 0.001),  # 0.1% trailing stop
    )
    
    def __init__(self):
        """Initialize strategy indicators."""
        super().__init__()
        
        # Calculate SMAs on daily data
        # Type ignores needed due to incomplete backtrader type stubs
        self.fast_sma = bt.indicators.MovingAverageSimple(
            self.datas[0].close,  # type: ignore[arg-type]
            period=self.params.fast_period  # type: ignore[attr-defined]
        )
        self.slow_sma = bt.indicators.MovingAverageSimple(
            self.datas[0].close,  # type: ignore[arg-type]
            period=self.params.slow_period  # type: ignore[attr-defined]
        )
        
        # Track crossover
        self.crossover = bt.indicators.CrossOver(self.fast_sma, self.slow_sma)  # type: ignore[arg-type]
        
        # State tracking
        self.trailing_stop_set = False
    
    def next(self):
        """Generate trading signals based on SMA crossover."""
        # Check if we have an order pending
        if self.order:
            return
        
        # Check if we're in the market
        if not self.position:
            # Not in position - check for buy signal
            if self.crossover > 0:  # Fast SMA crossed above Slow SMA
                # Calculate position size
                size = self.get_position_size()
                self.log(f'BUY SIGNAL - Fast SMA: ${self.fast_sma[0]:,.2f}, '
                        f'Slow SMA: ${self.slow_sma[0]:,.2f}')
                self.place_buy_order(size=size)
                self.trailing_stop_set = False
        
        else:
            # In position - check for sell signal
            if self.crossover < 0:  # Fast SMA crossed below Slow SMA
                self.log(f'SELL SIGNAL - Fast SMA: ${self.fast_sma[0]:,.2f}, '
                        f'Slow SMA: ${self.slow_sma[0]:,.2f}')
                self.place_sell_order()
                self.trailing_stop_set = False
            
            # Set trailing stop if not already set
            elif not self.trailing_stop_set and self.params.trailing_stop_percent:  # type: ignore[attr-defined]
                self.set_trailing_stop(self.params.trailing_stop_percent)  # type: ignore[attr-defined]
                self.trailing_stop_set = True
    
    def get_position_size(self):
        """Calculate position size based on available cash.
        
        Returns:
            Number of shares to buy
        """
        cash = self.broker.getcash()
        price = self.datas[0].close[0]
        
        # Use percentage of available cash
        size = int((cash * self.params.position_percent) / price)  # type: ignore[attr-defined]
        
        return size
    
    def buy_signal(self) -> bool:
        """Check if buy signal is present.
        
        Returns:
            True if fast SMA is above slow SMA
        """
        return self.fast_sma[0] > self.slow_sma[0]
    
    def sell_signal(self) -> bool:
        """Check if sell signal is present.
        
        Returns:
            True if fast SMA is below slow SMA
        """
        return self.fast_sma[0] < self.slow_sma[0]

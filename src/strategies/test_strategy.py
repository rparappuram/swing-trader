"""Test strategy that always generates a buy signal.

This strategy is designed for integration testing to verify the live trading
pipeline works correctly. It always generates a buy signal on the first bar.
"""
import backtrader as bt
from .base_strategy import BaseStrategy


class AlwaysBuyStrategy(BaseStrategy):
    """Test strategy that always generates a buy signal.
    
    This is a minimal test strategy used for integration testing.
    It will always trigger a buy signal with a very small position size.
    """
    
    # Strategy configuration
    NAME = "AlwaysBuyStrategy"
    
    # Default parameters
    params = (
        ('tickers', ['SIRI']),
        ('lookback_days', 5),
        ('position_pct', 0.001),  # Not used, size always = 1
    )
    
    def __init__(self):
        """Initialize strategy."""
        super().__init__()
        self.signal_triggered = False
    
    def next(self):
        """Generate buy signal on first bar if not already in position."""
        # Only trigger once
        if self.signal_triggered:
            return
        
        # If we're not in the market, trigger buy signal
        if not self.position:
            self.log(f'TEST BUY SIGNAL - Position size: 1 share')
            self.place_buy_order(size=1)
            self.signal_triggered = True
    
    def get_position_size(self):
        """Always return 1 share for testing.
        
        Returns:
            1 (always buy exactly 1 share)
        """
        return 1
    
    def buy_signal(self) -> bool:
        """Always return True for testing.
        
        Returns:
            True (always buy for testing)
        """
        return not self.signal_triggered and not self.position
    
    def sell_signal(self) -> bool:
        """Never sell in this test strategy.
        
        Returns:
            False (never sell)
        """
        return False

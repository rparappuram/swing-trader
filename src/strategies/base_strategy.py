"""Base strategy class for swing trading.

This module provides the base class that all trading strategies must inherit from.
The key design principle is that strategy logic is defined once and used in both backtesting
and live trading, ensuring consistency across research and production.
"""
import backtrader as bt
from typing import Dict, Any, Optional


class BaseStrategy(bt.Strategy):
    """Abstract base class for all trading strategies.
    
    This class integrates with backtrader for backtesting/optimization while providing
    a clean interface that can be reused in live trading. Strategies operate on daily
    bars and should never access minute-level data directly.
    
    Key principles:
    - Strategy logic is defined once and works in both backtest and live modes
    - Strategies work with daily timeframe data only
    - Trailing stops are supported through broker implementation
    - All strategies must implement next() method for signal generation
    
    Attributes:
        params: Backtrader parameters tuple defining strategy parameters
    """
    
    # Default parameters - subclasses should override
    params = (
        ('tickers', []),  # List of tickers to trade
        ('position_pct', 1.0),  # Percentage of portfolio to allocate per position
        ('trailing_stop_percent', 0.01),  # Trailing stop percentage (optional)
    )
    
    def __init__(self):
        """Initialize strategy.
        
        Called by backtrader during strategy initialization. Subclasses should
        set up indicators and state variables here.
        """
        super().__init__()
        self.order = None  # Track pending orders
        self.entry_price = None  # Track entry price for position management
        self.trailing_stop_order_ids = set()  # Track IDs of trailing stop orders
        self.order_types = {}  # Map order ID -> order type for logging
        
    def next(self):
        """Process the next bar and generate trading signals.
        
        This is the core method where strategy logic lives. It's called by backtrader
        for each bar during backtesting and should be called manually in live trading
        after loading the latest data.
        
        Implementations should:
        1. Calculate indicators/signals
        2. Check for entry conditions (if not in position)
        3. Check for exit conditions (if in position)
        4. Place orders using buy() or sell() methods
        
        Note: This method should ONLY work with daily data. Never access minute bars.
        Note: Subclasses should override this method with their strategy logic.
        """
        pass
    
    def notify_order(self, order):
        """Notification of order status changes.
        
        Args:
            order: Backtrader order object
        """
        if order.status in [order.Submitted, order.Accepted]:
            # Order submitted/accepted - nothing to do
            return
        
        if order.status in [order.Completed]:
            # Check if this was a trailing stop order first
            is_trailing_stop = order.ref in self.trailing_stop_order_ids
            
            if order.isbuy():
                if is_trailing_stop:
                    self.log(f'TRAILING STOP HIT (BUY) - Price: ${order.executed.price:,.2f}, '
                            f'Cost: ${order.executed.value:,.2f}, Comm: ${order.executed.comm:.2f}')
                else:
                    self.log(f'BUY EXECUTED - Price: ${order.executed.price:,.2f}, '
                            f'Cost: ${order.executed.value:,.2f}, Comm: ${order.executed.comm:.2f}')
                self.entry_price = order.executed.price
                
            elif order.issell():
                if is_trailing_stop:
                    self.log(f'TRAILING STOP HIT (SELL) - Price: ${order.executed.price:,.2f}, '
                            f'Cost: ${order.executed.value:,.2f}, Comm: ${order.executed.comm:.2f}')
                else:
                    self.log(f'SELL EXECUTED - Price: ${order.executed.price:,.2f}, '
                            f'Cost: ${order.executed.value:,.2f}, Comm: ${order.executed.comm:.2f}')
                self.entry_price = None
            
            # Clean up order tracking
            if is_trailing_stop:
                self.trailing_stop_order_ids.discard(order.ref)
            self.order_types.pop(order.ref, None)
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')
            # Clean up tracking for canceled/rejected orders
            self.trailing_stop_order_ids.discard(order.ref)
            self.order_types.pop(order.ref, None)
        
        # Reset order reference
        self.order = None
    
    def notify_trade(self, trade):
        """Notification of closed trades.
        
        Args:
            trade: Backtrader trade object
        """
        if not trade.isclosed:
            return
        
        self.log(f'TRADE PROFIT - Gross: ${trade.pnl:+,.2f}, Net: ${trade.pnlcomm:+,.2f}')
    
    def log(self, txt, dt=None):
        """Logging function.
        
        Args:
            txt: Text to log
            dt: Datetime for log entry (uses current bar datetime if None)
        """
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} {txt}', flush=True)
    
    def buy_signal(self) -> bool:
        """Check if buy signal is present.
        
        Override this method in subclasses to define buy logic.
        
        Returns:
            True if buy signal is present, False otherwise
        """
        return False
    
    def sell_signal(self) -> bool:
        """Check if sell signal is present.
        
        Override this method in subclasses to define sell logic.
        
        Returns:
            True if sell signal is present, False otherwise
        """
        return False
    
    def get_position_size(self) -> Optional[int]:
        """Calculate position size for next trade.
        
        Override this method to implement custom position sizing logic.
        Default implementation returns None (use broker's default sizing).
        
        Returns:
            Number of shares to trade, or None for default sizing
        """
        return None
    
    def place_buy_order(self, exectype=None, price=None, size=None):
        """Place a buy order with optional trailing stop.
        
        Args:
            exectype: Order execution type (Market, Limit, Stop, etc.)
            price: Limit/Stop price (for Limit/Stop orders)
            size: Number of shares (None = use position sizing)
        """
        if self.order:
            return  # Prevent multiple pending orders
        
        # Calculate size if not provided
        if size is None:
            size = self.get_position_size()
        
        # Place the buy order
        if exectype and price:
            self.order = self.buy(exectype=exectype, price=price, size=size)
        else:
            self.order = self.buy(size=size)
        
        # Track order type
        if self.order:
            self.order_types[self.order.ref] = 'buy'
        
        self.log(f'BUY ORDER PLACED - Shares: {size or 0:,}')
    
    def place_sell_order(self, exectype=None, price=None, size=None):
        """Place a sell order.
        
        Args:
            exectype: Order execution type (Market, Limit, Stop, etc.)
            price: Limit/Stop price (for Limit/Stop orders)
            size: Number of shares (None = close entire position)
        """
        if self.order:
            return  # Prevent multiple pending orders
        
        # Close entire position if size not specified
        if size is None:
            size = self.position.size
        
        # Place the sell order
        if exectype and price:
            self.order = self.sell(exectype=exectype, price=price, size=size)
        else:
            self.order = self.sell(size=size)
        
        # Track order type
        if self.order:
            self.order_types[self.order.ref] = 'sell'
        
        self.log(f'SELL ORDER PLACED - Shares: {size or 0:,}')
    
    def set_trailing_stop(self, percent: float):
        """Set a trailing stop loss order.
        
        This should be called after entering a position. In backtesting with minute data,
        the broker will simulate the trailing stop behavior. In live trading, the broker
        will place an actual trailing stop order with Alpaca.
        
        For long positions: creates a sell stop order
        For short positions: creates a buy stop order
        
        Args:
            percent: Trailing stop percentage (e.g., 5.0 for 5%)
        """
        if not self.position:
            return
        
        # Calculate stop price based on entry
        if self.entry_price:
            trail_amount = self.entry_price * (percent / 100.0)
            trail_percent = percent / 100.0
            
            # Create a trailing stop order
            # Note: In backtest, this is a simple stop loss; real trailing stop would need broker support
            # For live trading, Alpaca handles this server-side
            import backtrader as bt
            
            position_size = abs(self.position.size)
            
            # For long positions (size > 0): sell stop below entry
            # For short positions (size < 0): buy stop above entry
            if self.position.size > 0:
                # Long position - set sell stop
                stop_price = self.entry_price * (1 - trail_percent)
                trailing_stop_order = self.sell(exectype=bt.Order.Stop, price=stop_price, size=position_size)
                direction = "SELL"
            else:
                # Short position - set buy stop
                stop_price = self.entry_price * (1 + trail_percent)
                trailing_stop_order = self.buy(exectype=bt.Order.Stop, price=stop_price, size=position_size)
                direction = "BUY"
            
            # Track this as a trailing stop order
            if trailing_stop_order:
                self.trailing_stop_order_ids.add(trailing_stop_order.ref)
                self.order_types[trailing_stop_order.ref] = 'trailing_stop'
            
            self.log(f'TRAILING STOP SET ({direction}) - {percent}% @ ${stop_price:,.2f}, Shares: {position_size:,}')

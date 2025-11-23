"""Type definitions for broker operations.

This module defines type-safe classes for orders, positions, accounts,
and other broker-related entities.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from datetime import datetime


class OrderSide(Enum):
    """Order side (buy or sell)."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(Enum):
    """Time in force for orders."""
    DAY = "day"
    GTC = "gtc"  # Good till cancelled
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill


class OrderStatus(Enum):
    """Order status."""
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    PENDING_CANCEL = "pending_cancel"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class OrderRequest:
    """Base class for order requests."""
    symbol: str
    qty: int
    side: OrderSide
    time_in_force: TimeInForce = TimeInForce.DAY
    
    def to_alpaca_side(self):
        """Convert to Alpaca OrderSide enum."""
        from alpaca.trading.enums import OrderSide as AlpacaOrderSide
        return AlpacaOrderSide.BUY if self.side == OrderSide.BUY else AlpacaOrderSide.SELL
    
    def to_alpaca_tif(self):
        """Convert to Alpaca TimeInForce enum."""
        from alpaca.trading.enums import TimeInForce as AlpacaTIF
        mapping = {
            TimeInForce.DAY: AlpacaTIF.DAY,
            TimeInForce.GTC: AlpacaTIF.GTC,
            TimeInForce.IOC: AlpacaTIF.IOC,
            TimeInForce.FOK: AlpacaTIF.FOK,
        }
        return mapping[self.time_in_force]


class MarketOrder(OrderRequest):
    """Market order request."""
    
    def __init__(self, symbol: str, qty: int, side: OrderSide, 
                 time_in_force: TimeInForce = TimeInForce.DAY):
        super().__init__(symbol, qty, side, time_in_force)
        self.order_type = OrderType.MARKET


class LimitOrder(OrderRequest):
    """Limit order request."""
    
    def __init__(self, symbol: str, qty: int, side: OrderSide, limit_price: float, 
                 time_in_force: TimeInForce = TimeInForce.DAY):
        super().__init__(symbol, qty, side, time_in_force)
        self.limit_price = limit_price
        self.order_type = OrderType.LIMIT


class StopOrder(OrderRequest):
    """Stop order request."""
    
    def __init__(self, symbol: str, qty: int, side: OrderSide, stop_price: float,
                 time_in_force: TimeInForce = TimeInForce.DAY):
        super().__init__(symbol, qty, side, time_in_force)
        self.stop_price = stop_price
        self.order_type = OrderType.STOP


class StopLimitOrder(OrderRequest):
    """Stop limit order request."""
    
    def __init__(self, symbol: str, qty: int, side: OrderSide, stop_price: float, 
                 limit_price: float, time_in_force: TimeInForce = TimeInForce.DAY):
        super().__init__(symbol, qty, side, time_in_force)
        self.stop_price = stop_price
        self.limit_price = limit_price
        self.order_type = OrderType.STOP_LIMIT


class TrailingStopOrder(OrderRequest):
    """Trailing stop order request.
    
    Note: trail_percent should be specified in DECIMAL format (0.05 = 5%).
    The broker will automatically convert to Alpaca's whole number format.
    """
    
    def __init__(self, symbol: str, qty: int, side: OrderSide,
                 trail_percent: Optional[float] = None,
                 trail_price: Optional[float] = None,
                 time_in_force: TimeInForce = TimeInForce.DAY):
        super().__init__(symbol, qty, side, time_in_force)
        
        if trail_percent is None and trail_price is None:
            raise ValueError("Either trail_percent or trail_price must be set")
        if trail_percent is not None and trail_price is not None:
            raise ValueError("Cannot set both trail_percent and trail_price")
        
        # Store in decimal format (0.05 = 5%)
        self.trail_percent = trail_percent
        self.trail_price = trail_price
        self.order_type = OrderType.TRAILING_STOP


@dataclass
class Order:
    """Represents an order (response from broker).
    
    Note: trail_percent is stored in DECIMAL format (0.05 = 5%), converted from
    Alpaca's whole number format for consistency with internal usage.
    """
    id: str
    symbol: str
    qty: int
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    filled_qty: int
    filled_avg_price: Optional[float]
    limit_price: Optional[float]
    stop_price: Optional[float]
    trail_percent: Optional[float]  # Decimal format: 0.05 = 5%
    trail_price: Optional[float]
    submitted_at: datetime
    filled_at: Optional[datetime]
    canceled_at: Optional[datetime]
    expired_at: Optional[datetime]
    failed_at: Optional[datetime]
    
    @classmethod
    def from_alpaca(cls, alpaca_order):
        """Create Order from Alpaca order object."""
        from alpaca.trading.enums import OrderSide as AlpacaOrderSide, OrderType as AlpacaOrderType
        
        # Map Alpaca side
        side = OrderSide.BUY if alpaca_order.side == AlpacaOrderSide.BUY else OrderSide.SELL
        
        # Map Alpaca order type
        order_type_mapping = {
            AlpacaOrderType.MARKET: OrderType.MARKET,
            AlpacaOrderType.LIMIT: OrderType.LIMIT,
            AlpacaOrderType.STOP: OrderType.STOP,
            AlpacaOrderType.STOP_LIMIT: OrderType.STOP_LIMIT,
            AlpacaOrderType.TRAILING_STOP: OrderType.TRAILING_STOP,
        }
        order_type = order_type_mapping.get(alpaca_order.type, OrderType.MARKET)
        
        # Map status
        status_str = str(alpaca_order.status).lower()
        try:
            status = OrderStatus(status_str)
        except ValueError:
            status = OrderStatus.NEW
        
        # PERCENTAGE CONVERSION: Alpaca whole number (5.0) → Internal decimal (0.05)
        # Convert from Alpaca's format to our internal decimal format
        trail_percent_decimal = None
        if alpaca_order.trail_percent is not None:
            trail_percent_decimal = float(alpaca_order.trail_percent) / 100
        
        return cls(
            id=alpaca_order.id,
            symbol=alpaca_order.symbol,
            qty=int(alpaca_order.qty),
            side=side,
            order_type=order_type,
            status=status,
            filled_qty=int(alpaca_order.filled_qty or 0),
            filled_avg_price=float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else None,
            limit_price=float(alpaca_order.limit_price) if alpaca_order.limit_price else None,
            stop_price=float(alpaca_order.stop_price) if alpaca_order.stop_price else None,
            trail_percent=trail_percent_decimal,
            trail_price=float(alpaca_order.trail_price) if alpaca_order.trail_price else None,
            submitted_at=alpaca_order.submitted_at,
            filled_at=alpaca_order.filled_at,
            canceled_at=alpaca_order.canceled_at,
            expired_at=alpaca_order.expired_at,
            failed_at=alpaca_order.failed_at,
        )


@dataclass
class Position:
    """Represents a position."""
    symbol: str
    qty: int
    side: OrderSide
    avg_entry_price: float
    current_price: float
    market_value: float
    cost_basis: float
    unrealized_pl: float
    unrealized_plpc: float
    
    @classmethod
    def from_alpaca(cls, alpaca_position):
        """Create Position from Alpaca position object."""
        qty = int(alpaca_position.qty)
        side = OrderSide.BUY if qty > 0 else OrderSide.SELL
        
        return cls(
            symbol=alpaca_position.symbol,
            qty=abs(qty),
            side=side,
            avg_entry_price=float(alpaca_position.avg_entry_price),
            current_price=float(alpaca_position.current_price),
            market_value=float(alpaca_position.market_value),
            cost_basis=float(alpaca_position.cost_basis),
            unrealized_pl=float(alpaca_position.unrealized_pl),
            unrealized_plpc=float(alpaca_position.unrealized_plpc),
        )


@dataclass
class Account:
    """Represents an account."""
    id: str
    account_number: str
    status: str
    currency: str
    cash: float
    portfolio_value: float
    buying_power: float
    equity: float
    last_equity: float
    long_market_value: float
    short_market_value: float
    initial_margin: float
    maintenance_margin: float
    daytrade_count: int
    daytrading_buying_power: float
    regt_buying_power: float
    
    @classmethod
    def from_alpaca(cls, alpaca_account):
        """Create Account from Alpaca account object."""
        return cls(
            id=alpaca_account.id,
            account_number=alpaca_account.account_number,
            status=alpaca_account.status,
            currency=alpaca_account.currency,
            cash=float(alpaca_account.cash),
            portfolio_value=float(alpaca_account.portfolio_value),
            buying_power=float(alpaca_account.buying_power),
            equity=float(alpaca_account.equity),
            last_equity=float(alpaca_account.last_equity),
            long_market_value=float(alpaca_account.long_market_value),
            short_market_value=float(alpaca_account.short_market_value),
            initial_margin=float(alpaca_account.initial_margin),
            maintenance_margin=float(alpaca_account.maintenance_margin),
            daytrade_count=alpaca_account.daytrade_count,
            daytrading_buying_power=float(alpaca_account.daytrading_buying_power),
            regt_buying_power=float(alpaca_account.regt_buying_power),
        )


@dataclass
class OrderResult:
    """Result of an order submission."""
    success: bool
    order: Optional[Order] = None
    error: Optional[str] = None
    
    @property
    def order_id(self) -> Optional[str]:
        """Get order ID if successful."""
        return self.order.id if self.order else None

"""Custom Alpaca broker for backtrader.

This broker integrates Alpaca's API for live trading while working within
the backtrader framework. It supports market, limit, stop, and trailing stop orders.
"""
import logging
from typing import List, Optional, Union

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest as AlpacaMarketOrderRequest,
    LimitOrderRequest as AlpacaLimitOrderRequest,
    StopOrderRequest as AlpacaStopOrderRequest,
    StopLimitOrderRequest as AlpacaStopLimitOrderRequest,
    TrailingStopOrderRequest as AlpacaTrailingStopOrderRequest,
)

from .types import (
    MarketOrder, LimitOrder, StopOrder, StopLimitOrder, TrailingStopOrder,
    OrderRequest, Order, Position, Account, OrderResult
)


logger = logging.getLogger(__name__)


class AlpacaBroker:
    """Custom broker implementation for Alpaca API.
    
    This broker handles order submission, position tracking, and account
    management through the Alpaca API. It's designed to work both in
    backtesting (as a backtrader broker) and live trading contexts.
    """
    
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        """Initialize Alpaca broker.
        
        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            paper: If True, use paper trading; otherwise use live trading
        """
        self.client = TradingClient(api_key, secret_key, paper=paper)
        self.paper = paper
        
    def submit_order(self, order: OrderRequest) -> OrderResult:
        """Submit an order (generic method for all order types).
        
        Args:
            order: Order request (MarketOrder, LimitOrder, etc.)
            
        Returns:
            OrderResult with success status and order details
        """
        try:
            if isinstance(order, MarketOrder):
                alpaca_request = AlpacaMarketOrderRequest(
                    symbol=order.symbol,
                    qty=order.qty,
                    side=order.to_alpaca_side(),
                    time_in_force=order.to_alpaca_tif()
                )
            elif isinstance(order, LimitOrder):
                alpaca_request = AlpacaLimitOrderRequest(
                    symbol=order.symbol,
                    qty=order.qty,
                    side=order.to_alpaca_side(),
                    time_in_force=order.to_alpaca_tif(),
                    limit_price=order.limit_price
                )
            elif isinstance(order, StopOrder):
                alpaca_request = AlpacaStopOrderRequest(
                    symbol=order.symbol,
                    qty=order.qty,
                    side=order.to_alpaca_side(),
                    time_in_force=order.to_alpaca_tif(),
                    stop_price=order.stop_price
                )
            elif isinstance(order, StopLimitOrder):
                alpaca_request = AlpacaStopLimitOrderRequest(
                    symbol=order.symbol,
                    qty=order.qty,
                    side=order.to_alpaca_side(),
                    time_in_force=order.to_alpaca_tif(),
                    stop_price=order.stop_price,
                    limit_price=order.limit_price
                )
            elif isinstance(order, TrailingStopOrder):
                alpaca_request = AlpacaTrailingStopOrderRequest(
                    symbol=order.symbol,
                    qty=order.qty,
                    side=order.to_alpaca_side(),
                    time_in_force=order.to_alpaca_tif(),
                    trail_percent=order.trail_percent,
                    trail_price=order.trail_price
                )
            else:
                return OrderResult(
                    success=False,
                    error=f"Unsupported order type: {type(order)}"
                )
            
            # Submit order to Alpaca
            alpaca_order = self.client.submit_order(alpaca_request)
            
            # Convert to our Order type
            result_order = Order.from_alpaca(alpaca_order)
            
            logger.info(f"{order.order_type.value.upper()} order submitted: "
                       f"{order.symbol} x{order.qty} {order.side.value.upper()}, "
                       f"Order ID: {result_order.id}")
            
            return OrderResult(success=True, order=result_order)
            
        except Exception as e:
            logger.error(f"Error submitting order: {e}")
            return OrderResult(success=False, error=str(e))
    
    def get_account(self) -> Account:
        """Get account information.
        
        Returns:
            Account object with balance, buying power, etc.
        """
        alpaca_account = self.client.get_account()
        return Account.from_alpaca(alpaca_account)
    
    def get_positions(self) -> List[Position]:
        """Get all open positions.
        
        Returns:
            List of Position objects
        """
        alpaca_positions = self.client.get_all_positions()
        return [Position.from_alpaca(pos) for pos in alpaca_positions]
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Position object or None if no position
        """
        try:
            alpaca_position = self.client.get_open_position(symbol)
            return Position.from_alpaca(alpaca_position)
        except Exception as e:
            logger.debug(f"No position for {symbol}: {e}")
            return None
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order object or None if not found
        """
        try:
            alpaca_order = self.client.get_order_by_id(order_id)
            return Order.from_alpaca(alpaca_order)
        except Exception as e:
            logger.debug(f"Order not found {order_id}: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def cancel_all_orders(self) -> bool:
        """Cancel all open orders.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.cancel_orders()
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return False
    
    def close_position(self, symbol: str) -> bool:
        """Close a position.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.close_position(symbol)
            logger.info(f"Position closed: {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}")
            return False
    
    def close_all_positions(self) -> bool:
        """Close all open positions.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.close_all_positions()
            logger.info("All positions closed")
            return True
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return False

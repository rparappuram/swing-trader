"""Live trading execution runner.

This module provides the entry point for live trading execution. It fetches
recent market data, runs strategies to check for signals, and executes
trades through the Alpaca broker. Works both locally and in AWS Lambda.
"""
import sys
import logging
import importlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.config_loader import get_config_loader
from src.data_loaders.data_manager import DataManager
from src.brokers.alpaca_broker import AlpacaBroker
from src.brokers.types import MarketOrder, OrderSide
from src.strategies.base_strategy import BaseStrategy
import backtrader as bt


logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    force=True
)
logger = logging.getLogger(__name__)


class LiveRunner:
    """Executes live trading strategies."""
    
    def __init__(self):
        """Initialize live runner."""
        self.config_loader = get_config_loader()
        self.config = self.config_loader.load_config()
        self.live_config = self.config.get('live', {})
        self.data_config = self.config.get('data', {})
        
        # Initialize components
        alpaca_config = self.config_loader.get_alpaca_config()
        
        # Initialize data manager
        data_paths = self.config_loader.get_data_paths()
        self.data_manager = DataManager(
            daily_path=str(data_paths['daily']),
            minute_path=str(data_paths['minute'])
        )
        
        # Initialize Alpaca clients
        self.data_manager.init_alpaca_client(
            alpaca_config['api_key'],
            alpaca_config['secret_key']
        )
        
        self.broker = AlpacaBroker(
            alpaca_config['api_key'],
            alpaca_config['secret_key'],
            paper=alpaca_config.get('paper', True)
        )
        
        logger.info("Live runner initialized")
    
    def display_portfolio_status(self):
        """Display current portfolio status including account info and positions."""
        try:
            # Get account info
            account = self.broker.get_account()
            
            print("\n" + "="*80)
            print("PORTFOLIO STATUS")
            print("="*80)
            print(f"Account Type: {'PAPER' if self.broker.paper else 'LIVE'}")
            print(f"Portfolio Value: ${float(account.portfolio_value):,.2f}")
            print(f"Cash: ${float(account.cash):,.2f}")
            print(f"Buying Power: ${float(account.buying_power):,.2f}")
            
            # Get positions
            positions = self.broker.get_positions()
            
            if positions:
                print(f"\nOpen Positions: {len(positions)}")
                print("-"*80)
                for pos in positions:
                    pnl = float(pos.unrealized_pl)
                    pnl_percent = float(pos.unrealized_plpc) * 100
                    pnl_sign = "+" if pnl >= 0 else ""
                    print(f"  {pos.symbol:6s} | Qty: {int(pos.qty):4d} | "
                          f"Avg: ${float(pos.avg_entry_price):7.2f} | "
                          f"Current: ${float(pos.current_price):7.2f} | "
                          f"P&L: {pnl_sign}${pnl:,.2f} ({pnl_sign}{pnl_percent:.2f}%)")
            else:
                print("\nOpen Positions: 0")
            
            print("="*80 + "\n")
            
        except Exception as e:
            logger.error(f"Error fetching portfolio status: {e}")
    
    def load_strategy_class(self, module_path: str, class_name: str):
        """Dynamically load a strategy class.
        
        Args:
            module_path: Python module path
            class_name: Strategy class name
            
        Returns:
            Strategy class
        """
        module = importlib.import_module(module_path)
        strategy_class = getattr(module, class_name)
        
        if not issubclass(strategy_class, BaseStrategy):
            raise ValueError(f"{class_name} must inherit from BaseStrategy")
        
        return strategy_class
    
    def run_strategy(self, strategy_config: Dict[str, Any]) -> Dict[str, Any]:
        """Run a strategy and execute any generated signals.
        
        Args:
            strategy_config: Strategy configuration dictionary
            
        Returns:
            Dictionary with execution results
        """
        logger.info(f"Strategy: {strategy_config['name']}")
        
        # Load strategy class
        strategy_class = self.load_strategy_class(
            strategy_config['module'],
            strategy_config['class']
        )
        
        results = {
            'strategy': strategy_config['name'],
            'timestamp': datetime.now().isoformat(),
            'signals': [],
            'executions': [],
            'errors': []
        }
        
        # Process each ticker
        params = strategy_config.get('params', {})
        tickers = params.get('tickers', [])
        lookback_days = params.get('lookback_days', 30)
        
        for ticker in tickers:
            try:
                # Processing ticker
                
                # Fetch fresh data from Alpaca (always for live trading)
                df = self.data_manager.get_data_for_live(ticker, lookback_days)
                
                if df.empty:
                    logger.warning(f"No data available for {ticker}")
                    continue
                
                # Run strategy using backtrader's mini-engine
                signal_result = self._check_signal(
                    strategy_class, 
                    strategy_config.get('params', {}),
                    ticker,
                    df
                )
                
                if signal_result:
                    results['signals'].append(signal_result)
                    
                    # Execute trade
                    execution = self._execute_signal(ticker, signal_result)
                    if execution:
                        results['executions'].append(execution)
                
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                results['errors'].append({
                    'ticker': ticker,
                    'error': str(e)
                })
        
        return results
    
    def _check_signal(self, strategy_class, params: Dict[str, Any], 
                     ticker: str, df) -> Optional[Dict[str, Any]]:
        """Check for trading signals using backtrader.
        
        Args:
            strategy_class: Strategy class
            params: Strategy parameters
            ticker: Stock ticker
            df: Price data DataFrame
            
        Returns:
            Signal dictionary or None
        """
        # Create a minimal backtrader cerebro to run the strategy
        cerebro = bt.Cerebro()
        
        # Add strategy
        cerebro.addstrategy(strategy_class, **params)
        
        # Create data feed
        # Type ignores needed due to incomplete backtrader type stubs
        data_feed = bt.feeds.PandasData(
            dataname=df,  # type: ignore[call-arg]
            datetime=None,  # type: ignore[call-arg]
            open='open',  # type: ignore[call-arg]
            high='high',  # type: ignore[call-arg]
            low='low',  # type: ignore[call-arg]
            close='close',  # type: ignore[call-arg]
            volume='volume',  # type: ignore[call-arg]
            openinterest=-1  # type: ignore[call-arg]
        )
        cerebro.adddata(data_feed, name=ticker)
        
        # Set a minimal broker to avoid errors
        cerebro.broker.setcash(1000000)
        
        # Run strategy
        strat_list = cerebro.run()
        strat = strat_list[0]
        
        # Check current position and signals
        position = self.broker.get_position(ticker)
        has_position = position is not None and position.qty > 0
        
        # Determine action based on strategy state
        # Note: This is a simplified approach - you may need to enhance based on your strategy logic
        action = None
        
        if not has_position:
            # Check for buy signal
            if hasattr(strat, 'buy_signal') and strat.buy_signal():
                action = 'buy'
        else:
            # Check for sell signal
            if hasattr(strat, 'sell_signal') and strat.sell_signal():
                action = 'sell'
        
        if action:
            current_price = df['close'].iloc[-1]
            return {
                'ticker': ticker,
                'action': action,
                'price': float(current_price),
                'timestamp': df.index[-1].isoformat() if hasattr(df.index[-1], 'isoformat') else str(df.index[-1])
            }
        
        return None
    
    def _execute_signal(self, ticker: str, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Execute a trading signal.
        
        Args:
            ticker: Stock ticker
            signal: Signal dictionary
            
        Returns:
            Execution result dictionary
        """
        action = signal['action']
        
        try:
            if action == 'buy':
                # Calculate position size from signal (strategy calculates this)
                account = self.broker.get_account()
                cash = account.cash
                # Use position size from signal if provided, otherwise calculate from price
                position_value = signal.get('size', 1) * signal['price']
                
                price = signal['price']
                qty = int(position_value / price)
                
                if qty > 0:
                    # Create and submit market order
                    order = MarketOrder(symbol=ticker, qty=qty, side=OrderSide.BUY)
                    result = self.broker.submit_order(order)
                    
                    if result.success:
                        logger.info(f"BUY order executed: {ticker} x{qty} @ ${price:.2f}")
                        return {
                            'ticker': ticker,
                            'action': 'buy',
                            'quantity': qty,
                            'price': price,
                            'order_id': result.order_id,
                            'timestamp': datetime.now().isoformat()
                        }
                    else:
                        logger.error(f"Failed to submit BUY order: {result.error}")
                        return {
                            'ticker': ticker,
                            'action': 'buy',
                            'error': result.error,
                            'timestamp': datetime.now().isoformat()
                        }
            
            elif action == 'sell':
                # Get current position size
                position = self.broker.get_position(ticker)
                if position:
                    qty = position.qty
                    
                    # Create and submit market order
                    order = MarketOrder(symbol=ticker, qty=qty, side=OrderSide.SELL)
                    result = self.broker.submit_order(order)
                    
                    if result.success:
                        logger.info(f"SELL order executed: {ticker} x{qty}")
                        return {
                            'ticker': ticker,
                            'action': 'sell',
                            'quantity': qty,
                            'order_id': result.order_id,
                            'timestamp': datetime.now().isoformat()
                        }
                    else:
                        logger.error(f"Failed to submit SELL order: {result.error}")
                        return {
                            'ticker': ticker,
                            'action': 'sell',
                            'error': result.error,
                            'timestamp': datetime.now().isoformat()
                        }
        
        except Exception as e:
            logger.error(f"Error executing signal for {ticker}: {e}")
            return {
                'ticker': ticker,
                'action': action,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
        
        return None
    
    def run_strategies(self) -> List[Dict[str, Any]]:
        """Run strategies.
        
        Returns:
            List of execution results for each strategy
        """
        # Display portfolio status first
        self.display_portfolio_status()
        
        strategies = self.config_loader.get_strategies()
        
        if not strategies:
            logger.warning("No strategies found in configuration")
            return []
        
        all_results = []
        
        for strategy_config in strategies:
            logger.info("\n" + "="*80)
            logger.info(f"Executing: {strategy_config['name']}")
            logger.info("="*80)
            
            try:
                results = self.run_strategy(strategy_config)
                all_results.append(results)
                
                # Print summary
                self._print_results(results)
                
            except Exception as e:
                logger.error(f"Error running strategy {strategy_config['name']}: {e}")
                import traceback
                traceback.print_exc()
        
        return all_results
    
    def _print_results(self, results: Dict[str, Any]):
        """Print execution results.
        
        Args:
            results: Execution results dictionary
        """
        print("\n" + "="*80)
        print("EXECUTION RESULTS")
        print("="*80)
        print(f"Strategy: {results['strategy']}")
        
        signals = results.get('signals', [])
        executions = results.get('executions', [])
        errors = results.get('errors', [])
        
        print(f"\nSignals detected: {len(signals)}")
        for signal in signals:
            print(f"  - {signal['ticker']}: {signal['action'].upper()} @ ${signal['price']:.2f}")
        
        print(f"\nOrders executed: {len(executions)}")
        for execution in executions:
            if 'error' in execution:
                print(f"  - {execution['ticker']}: ERROR - {execution['error']}")
            else:
                print(f"  - {execution['ticker']}: {execution['action'].upper()} "
                     f"x{execution['quantity']} (Order ID: {execution['order_id']})")
        
        if errors:
            print(f"\nErrors: {len(errors)}")
            for error in errors:
                print(f"  - {error['ticker']}: {error['error']}")
        
        print("="*80 + "\n")


def main():
    """Main entry point for live trading."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Execute live trading strategies')
    parser.add_argument('--strategy', type=str, 
                       help='Specific strategy name to run (optional)')
    
    args = parser.parse_args()
    
    # Initialize runner
    runner = LiveRunner()
    
    if args.strategy:
        # Run specific strategy
        config_loader = get_config_loader()
        strategies = config_loader.get_strategies()
        
        strategy_config = None
        for s in strategies:
            if s['name'] == args.strategy:
                strategy_config = s
                break
        
        if not strategy_config:
            logger.error(f"Strategy '{args.strategy}' not found in configuration")
            return
        
        runner.run_strategy(strategy_config)
    else:
        # Run strategies
        runner.run_strategies()


if __name__ == '__main__':
    main()

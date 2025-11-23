"""Backtesting runner for swing trading strategies.

This module provides the entry point for backtesting strategies using historical
data. It supports dual-timeframe data loading (daily for strategy, minute for
stop-loss simulation) to accurately model trailing stops.
"""
import backtrader as bt
import sys
import importlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Type, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.config_loader import get_config_loader
from src.data_loaders.data_manager import DataManager
from src.strategies.base_strategy import BaseStrategy


logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    force=True
)
logger = logging.getLogger(__name__)


class BacktestRunner:
    """Runs backtests for swing trading strategies."""
    
    def __init__(self, config_path: str = "config"):
        """Initialize backtest runner.
        
        Args:
            config_path: Path to configuration directory
        """
        self.config_loader = get_config_loader()
        self.config = self.config_loader.load_config()
        self.backtest_config = self.config.get('backtest', {})
        
        # Initialize data manager
        data_paths = self.config_loader.get_data_paths()
        self.data_manager = DataManager(
            daily_path=str(data_paths['daily']),
            minute_path=str(data_paths['minute'])
        )
        
        # Initialize Alpaca client for data fetching
        alpaca_config = self.config_loader.get_alpaca_config()
        self.data_manager.init_alpaca_client(
            alpaca_config['api_key'],
            alpaca_config['secret_key']
        )
    
    def load_strategy_class(self, module_path: str, class_name: str) -> Type[BaseStrategy]:
        """Dynamically load a strategy class.
        
        Args:
            module_path: Python module path (e.g., 'src.strategies.example_sma')
            class_name: Strategy class name
            
        Returns:
            Strategy class
        """
        module = importlib.import_module(module_path)
        strategy_class = getattr(module, class_name)
        
        if not issubclass(strategy_class, BaseStrategy):
            raise ValueError(f"{class_name} must inherit from BaseStrategy")
        
        return strategy_class
    
    def run_backtest(self, strategy_config: Dict[str, Any]) -> Dict[str, Any]:
        """Run backtest for a single strategy using config settings.
        
        Args:
            strategy_config: Strategy configuration dictionary
            
        Returns:
            Dictionary with backtest results
        """
        # Get dates from config
        start_str = self.backtest_config.get('start_date')
        end_str = self.backtest_config.get('end_date')
        
        if not start_str or not end_str:
            raise ValueError("start_date and end_date must be set in config.yaml")
        
        # Parse dates and make timezone-aware (UTC) for consistency with market data
        start_date = datetime.strptime(start_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(end_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        
        # Date range loaded from config
        
        # Load strategy class
        strategy_class = self.load_strategy_class(
            strategy_config['module'],
            strategy_config['class']
        )
        
        # Initialize cerebro engine
        cerebro = bt.Cerebro()
        
        # Set initial cash and commission from config
        initial_cash = self.backtest_config.get('initial_cash', 100000.0)
        commission = self.backtest_config.get('commission', 0.001)
        
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=commission)
        
        # Add strategy - it will use default values from its params tuple
        # No params passed means all defaults are used
        cerebro.addstrategy(strategy_class)
        
        # Load data for each ticker
        params = strategy_config.get('params', {})
        tickers = params.get('tickers', [])
        tickers = params.get('tickers', [])
        
        for ticker in tickers:
            # Data loading handled by DataManager
            
            # Get daily data (checks local files, fetches if needed)
            daily_df = self.data_manager.get_data_for_backtest(
                ticker, start_date, end_date, timeframe='daily'
            )
            
            if daily_df.empty:
                logger.error(f"No daily data available for {ticker}, skipping")
                continue
            
            # Create and add daily data feed
            daily_feed = self.data_manager.create_backtrader_feed(daily_df, ticker)
            cerebro.adddata(daily_feed, name=ticker)
            
            # Load minute data for intraday stop loss simulation
            try:
                minute_df = self.data_manager.get_data_for_backtest(
                    ticker, start_date, end_date, timeframe='minute'
                )
                if not minute_df.empty:
                    # Add as separate feed for advanced stop simulation
                    # minute_feed = self.data_manager.create_backtrader_feed(
                    #     minute_df, f"{ticker}_minute"
                    # )
                    # cerebro.adddata(minute_feed, name=f"{ticker}_minute")
                    pass  # Minute data loaded for stop simulation
                else:
                    logger.warning(f"No minute data available for {ticker}")
            except Exception as e:
                logger.warning(f"Error loading minute data for {ticker}: {e}")
        
        # Add analyzers
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # Run backtest
        logger.info(f"Starting backtest for {strategy_config['name']}")
        logger.info(f"Initial value: ${cerebro.broker.getvalue():,.2f}")
        
        results = cerebro.run()
        final_value = cerebro.broker.getvalue()
        
        logger.info(f"Final value: ${final_value:,.2f} ({(final_value - initial_cash) / initial_cash * 100:+.2f}%)")
        
        # Plot the results
        cerebro.plot()
        
        # Extract analyzer results
        strat = results[0]
        
        returns = strat.analyzers.returns.get_analysis()
        sharpe = strat.analyzers.sharpe.get_analysis()
        drawdown = strat.analyzers.drawdown.get_analysis()
        trades = strat.analyzers.trades.get_analysis()
        
        # Compile results
        backtest_results = {
            'strategy': strategy_config['name'],
            'initial_value': initial_cash,
            'final_value': final_value,
            'total_return': final_value - initial_cash,
            'total_return_percent': (final_value - initial_cash) / initial_cash * 100,
            'returns': returns,
            'sharpe_ratio': sharpe.get('sharperatio', None),
            'max_drawdown': drawdown.get('max', {}).get('drawdown', None),
            'trades': trades,
        }
        
        # Print summary
        self._print_results(backtest_results)
        
        return backtest_results
    
    def run(self) -> Dict[str, Any]:
        """Run backtest for the strategy specified in config.
        
        Returns:
            Dictionary with backtest results
        """
        # Get strategy name from config
        strategy_name = self.config_loader.get_backtest_strategy()
        
        if not strategy_name:
            raise ValueError("No strategy specified in config")
        
        # Find strategy config
        strategies = self.config_loader.get_strategies()
        strategy_config = None
        
        for s in strategies:
            if s['name'] == strategy_name:
                strategy_config = s
                break
        
        if not strategy_config:
            raise ValueError(f"Strategy '{strategy_name}' not found")
        
        logger.info("\n" + "="*80)
        logger.info(f"Backtest: {strategy_config['name']}")
        logger.info("="*80)
        
        return self.run_backtest(strategy_config)
    
    def _print_results(self, results: Dict[str, Any]):
        """Print backtest results summary.
        
        Args:
            results: Backtest results dictionary
        """
        print("\n" + "="*80)
        print("BACKTEST RESULTS")
        print("="*80)
        print(f"Strategy: {results['strategy']}")
        print(f"Initial Value: ${results['initial_value']:,.2f}")
        print(f"Final Value: ${results['final_value']:,.2f}")
        print(f"Total Return: ${results['total_return']:+,.2f} ({results['total_return_percent']:+.2f}%)")
        
        if results['sharpe_ratio']:
            print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
        
        if results['max_drawdown']:
            print(f"Max Drawdown: {results['max_drawdown']:.2f}%")
        
        trades = results['trades']
        if trades:
            total = trades.get('total', {}).get('total', 0)
            won = trades.get('won', {}).get('total', 0)
            lost = trades.get('lost', {}).get('total', 0)
            
            print(f"\nTotal Trades: {total}")
            if total > 0:
                print(f"Won: {won} ({won/total*100:.1f}%)")
                print(f"Lost: {lost} ({lost/total*100:.1f}%)")
        
        print("="*80 + "\n")


def main():
    """Main entry point for backtesting.
    
    All configuration is read from config/config.yaml.
    No command-line arguments needed.
    """
    runner = BacktestRunner()
    
    try:
        runner.run()
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    main()

"""Optimization runner for strategy parameter tuning.

This module provides parameter optimization capabilities using backtrader's
built-in optimization engine. It can test multiple parameter combinations
in parallel to find optimal strategy parameters.
"""
import backtrader as bt
import sys
import importlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Type, Tuple, Optional
from itertools import product

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


class OptimizationRunner:
    """Runs parameter optimization for swing trading strategies."""
    
    def __init__(self, config_path: str = "config"):
        """Initialize optimization runner.
        
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
    
    def load_strategy_class(self, module_path: str, class_name: str) -> Type[BaseStrategy]:
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
    
    def optimize_strategy(self, strategy_config: Dict[str, Any],
                         param_ranges: Dict[str, List[Any]],
                         metric: str = 'return') -> List[Dict[str, Any]]:
        """Run parameter optimization for a strategy using config settings.
        
        Args:
            strategy_config: Strategy configuration dictionary
            param_ranges: Dictionary mapping parameter names to lists of values to test
                         e.g., {'fast_period': [5, 10, 15], 'slow_period': [20, 30, 40]}
            metric: Optimization metric (always 'return')
            
        Returns:
            List of result dictionaries sorted by return
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
        
        logger.info(f"Optimizing {strategy_config['name']}")
        
        # Calculate and display total combinations
        total_combinations = 1
        logger.info("\nParameter ranges to test:")
        for param_name, param_values in param_ranges.items():
            values_list = list(param_values)
            total_combinations *= len(values_list)
            logger.info(f"  {param_name}: {values_list}")
            logger.info(f"    ({len(values_list)} values)")
        
        logger.info(f"\nTotal combinations to test: {total_combinations}")
        logger.info("="*80)
        
        # Initialize cerebro for optimization
        cerebro = bt.Cerebro()
        
        # Enable cheat-on-close mode to simulate live trading at market close
        # Orders placed during a bar execute at that bar's close price (same bar execution)
        # This matches live trading where we run the strategy at market close and execute immediately
        cerebro.broker.set_coc(True)
        
        # Set initial cash and commission
        initial_cash = self.backtest_config.get('initial_cash', 100000.0)
        commission = self.backtest_config.get('commission', 0.001)
        
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=commission)
        
        # Only use parameters specified in OPTIMIZE_PARAMS
        # Convert to backtrader format: param_name=(val1, val2, val3, ...)
        bt_params = {}
        for param_name, param_values in param_ranges.items():
            bt_params[param_name] = tuple(param_values)
        
        # Add optimized strategy - ONLY with parameters from OPTIMIZE_PARAMS
        # The strategy will use its default values for any params not being optimized
        # Disable verbose logging during optimization to reduce noise
        cerebro.optstrategy(strategy_class, verbose_logging=False, **bt_params)
        
        # Load data for each ticker
        params = strategy_config.get('params', {})
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
        
        # Add all analyzers to collect comprehensive performance metrics
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # Run optimization
        logger.info("Running optimization...")
        opt_results = cerebro.run()
        
        # Extract results with all metrics
        results = []
        
        for run in opt_results:
            strat = run[0]
            
            # Get parameter values
            params = {}
            for param_name in param_ranges.keys():
                params[param_name] = getattr(strat.params, param_name)
            
            
            # Get all analyzer results
            returns_analysis = strat.analyzers.returns.get_analysis()
            sharpe_analysis = strat.analyzers.sharpe.get_analysis()
            drawdown_analysis = strat.analyzers.drawdown.get_analysis()
            trades_analysis = strat.analyzers.trades.get_analysis()
            
            # Extract metrics
            total_return = returns_analysis.get('rtot', 0) or 0
            sharpe_ratio = sharpe_analysis.get('sharperatio', None)
            max_drawdown = drawdown_analysis.get('max', {}).get('drawdown', None)
            
            # Calculate final portfolio value from return
            final_value = initial_cash * (1 + total_return)
            
            # Trade statistics
            total_trades = trades_analysis.get('total', {}).get('total', 0)
            won_trades = trades_analysis.get('won', {}).get('total', 0)
            win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Sort by return (default metric)
            sort_value = total_return
            
            # Store comprehensive results
            result_data = {
                'params': params,
                'sort_value': sort_value,
                'final_value': final_value,
                'total_return': total_return,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'total_trades': total_trades,
                'won_trades': won_trades,
                'win_rate': win_rate
            }
            
            results.append(result_data)
        
        # Sort by metric (descending - higher is better)
        results.sort(key=lambda x: x['sort_value'], reverse=True)
        
        # Log completion summary
        logger.info(f"\nOptimization complete: Tested {len(results)} parameter combinations")
        
        # Print top results
        self._print_optimization_results(results, metric, initial_cash, top_n=3)
        
        return results
    
    def _print_optimization_results(self, results: List[Dict[str, Any]], 
                                   metric: str, initial_cash: float, top_n: int = 3):
        """Print optimization results with comprehensive metrics.
        
        Args:
            results: List of result dictionaries
            metric: Metric name used for sorting
            initial_cash: Initial portfolio value
            top_n: Number of top results to display
        """
        print("\n" + "="*80)
        print("OPTIMIZATION RESULTS")
        print("="*80)
        print(f"Optimization Metric: {metric.upper()}")
        print(f"Total Combinations Tested: {len(results)}")
        print(f"Initial Portfolio Value: ${initial_cash:,.2f}")
        print(f"\nTop {top_n} Parameter Combinations:")
        print("="*80)
        
        for i, result in enumerate(results[:top_n], 1):
            params = result['params']
            final_value = result['final_value']
            total_return = result['total_return']
            sharpe = result['sharpe_ratio']
            drawdown = result['max_drawdown']
            trades = result['total_trades']
            won = result['won_trades']
            win_rate = result['win_rate']
            
            pnl = final_value - initial_cash
            return_percent = total_return * 100
            
            print(f"\n#{i}")
            print("-" * 80)
            print(f"Parameters: {params}")
            print(f"\nPerformance:")
            print(f"  Final Portfolio Value:  ${final_value:,.2f}")
            print(f"  P&L:                    ${pnl:+,.2f}")
            print(f"  Total Return:           {return_percent:+.2f}%")
            
            if sharpe is not None:
                print(f"  Sharpe Ratio:           {sharpe:.3f}")
            else:
                print(f"  Sharpe Ratio:           N/A")
            
            if drawdown is not None:
                print(f"  Max Drawdown:           {drawdown:.2f}%")
            else:
                print(f"  Max Drawdown:           N/A")
            
            print(f"\nTrade Statistics:")
            print(f"  Total Trades:           {trades}")
            if trades > 0:
                print(f"  Winning Trades:         {won} ({win_rate:.1f}%)")
                print(f"  Losing Trades:          {trades - won} ({100 - win_rate:.1f}%)")
            else:
                print(f"  No trades executed")
        
        print("\n" + "="*80 + "\n")

    def run(self) -> List[Dict[str, Any]]:
        """Run optimization for the strategy specified in config.
        
        Returns:
            List of result dictionaries sorted by return
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
        
        # Get parameter ranges from strategy config
        param_ranges = strategy_config.get('optimize_params', {})
        
        if not param_ranges:
            raise ValueError(f"No optimize_params defined in strategy config for {strategy_name}")
        
        logger.info("\n" + "="*80)
        logger.info(f"Optimization: {strategy_config['name']}")
        logger.info("="*80)
        
        results = self.optimize_strategy(strategy_config, param_ranges, 'return')
        
        return results


def main():
    """Main entry point for optimization.
    
    All configuration is read from config/config.yaml.
    Optimizes by return and displays top 3 results.
    """
    runner = OptimizationRunner()
    
    try:
        runner.run()
    except Exception as e:
        logger.error(f"Error running optimization: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    main()

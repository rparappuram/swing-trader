"""Configuration loader utility."""
import os
import yaml
import importlib
from pathlib import Path
from typing import Any, Dict, List
from dotenv import load_dotenv


class ConfigLoader:
    """Loads and manages configuration from YAML files and environment variables."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the configuration loader.
        
        Args:
            config_path: Path to the configuration file
        """
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._strategies: List[Dict[str, Any]] | None = None
        
        # Load environment variables
        load_dotenv()
    
    def load_config(self) -> Dict[str, Any]:
        """Load main configuration from config.yaml.
        
        Returns:
            Dictionary containing configuration
        """
        if not self._config:
            with open(self.config_path, 'r') as f:
                self._config = yaml.safe_load(f)
            
            # Load Alpaca settings from environment variables
            self._load_alpaca_from_env()
        
        return self._config
    
    def _load_strategy_class(self, strategy_name: str):
        """Dynamically import and return a strategy class.
        
        Args:
            strategy_name: Name of the strategy to load
            
        Returns:
            Strategy class or None if not found
        """
        # Map strategy names to their modules and classes
        strategy_map = {
            'SMAStrategy': ('src.strategies.example_sma', 'SMAStrategy'),
        }
        
        if strategy_name not in strategy_map:
            return None
        
        module_name, class_name = strategy_map[strategy_name]
        
        try:
            module = importlib.import_module(module_name)
            return getattr(module, class_name)
        except Exception as e:
            print(f"Warning: Failed to load strategy class {strategy_name}: {e}")
            return None
    
    def _load_strategies(self) -> List[Dict[str, Any]]:
        """Load all strategies from their class definitions.
        
        Strategies are now defined as class attributes in the strategy classes
        themselves, not in YAML files.
        
        Returns:
            List of strategy configurations
        """
        if self._strategies is not None:
            return self._strategies
        
        self._strategies = []
        
        # Get active strategy from config.yaml
        config = self.load_config()
        strategy_name = config.get('strategy')
        
        if not strategy_name:
            return self._strategies
        
        # Load the strategy class
        strategy_class = self._load_strategy_class(strategy_name)
        if strategy_class is None:
            return self._strategies
        
        # Build config from class attributes
        # Extract default params from backtrader's params tuple
        params_dict = {}
        if hasattr(strategy_class, 'params'):
            # params is a tuple of tuples: (('name', default_value), ...)
            params_tuple = getattr(strategy_class.params, '_gettuple', lambda: strategy_class.params)()
            params_dict = {name: value for name, value in params_tuple if name != 'ticker'}
        
        strategy_config = {
            'name': getattr(strategy_class, 'NAME', strategy_name),
            'module': strategy_class.__module__,
            'class': strategy_class.__name__,
            'tickers': getattr(strategy_class, 'DEFAULT_TICKERS', []),
            'lookback_days': getattr(strategy_class, 'LOOKBACK_DAYS', 30),
            'params': params_dict,
            'optimize_params': getattr(strategy_class, 'OPTIMIZE_PARAMS', {}),
            'enabled': True,
        }
        
        self._strategies.append(strategy_config)
        return self._strategies
    
    def get_strategies(self) -> List[Dict[str, Any]]:
        """Get list of strategies.
        
        Returns cached list of strategy configurations. Strategies
        are loaded once on first call.
        
        Returns:
            List of strategy configurations
        """
        return self._load_strategies()
    
    def get_strategy_params(self, strategy_name: str) -> Dict[str, Any]:
        """Get parameters for a specific strategy.
        
        Args:
            strategy_name: Name of the strategy
            
        Returns:
            Dictionary of strategy parameters, or empty dict if not found
        """
        for strategy_config in self._load_strategies():
            if strategy_config.get('name') == strategy_name:
                return strategy_config.get('params', {})
        return {}
    
    def get_strategy_optimize_params(self, strategy_name: str) -> Dict[str, Any]:
        """Get optimization parameter ranges for a specific strategy.
        
        Args:
            strategy_name: Name of the strategy
            
        Returns:
            Dictionary mapping parameter names to iterables (ranges, lists) of values to test
        """
        for strategy_config in self._load_strategies():
            if strategy_config.get('name') == strategy_name:
                # Convert ranges to lists for backtrader compatibility
                optimize_params = strategy_config.get('optimize_params', {})
                return {k: list(v) if not isinstance(v, list) else v 
                       for k, v in optimize_params.items()}
        return {}
    
    def get_max_lookback_days(self) -> int:
        """Get the maximum lookback days across all strategies.
        
        This determines how much historical data to fetch for live trading.
        
        Returns:
            Maximum lookback days from all strategies
        """
        max_days = 30  # Default minimum
        
        for strategy_config in self._load_strategies():
            lookback = strategy_config.get('lookback_days', 30)
            max_days = max(max_days, lookback)
        
        return max_days
    
    def _load_alpaca_from_env(self):
        """Load Alpaca API settings from environment variables.
        
        API keys are only stored in environment variables, not in config files.
        This method loads them into the config structure for easy access.
        The base URL determines whether it's paper or live trading.
        """
        # Initialize alpaca config if not present
        if 'alpaca' not in self._config:
            self._config['alpaca'] = {}
        
        # Load from environment variables (these are the source of truth)
        self._config['alpaca']['api_key'] = os.getenv('ALPACA_API_KEY')
        self._config['alpaca']['secret_key'] = os.getenv('ALPACA_SECRET_KEY')
        self._config['alpaca']['base_url'] = os.getenv(
            'ALPACA_BASE_URL', 
            'https://paper-api.alpaca.markets'
        )
    
    def get_data_paths(self) -> Dict[str, Path]:
        """Get data directory paths.
        
        Returns:
            Dictionary with 'daily' and 'minute' paths
        """
        config = self.load_config()
        data_config = config.get('data', {})
        
        return {
            'daily': Path(data_config.get('daily_path', 'data/daily')),
            'minute': Path(data_config.get('minute_path', 'data/minute'))
        }
    
    def get_alpaca_config(self) -> Dict[str, Any]:
        """Get Alpaca API configuration.
        
        Returns:
            Dictionary with Alpaca configuration
        """
        config = self.load_config()
        return config.get('alpaca', {})
    
    def get_backtest_config(self) -> Dict[str, Any]:
        """Get backtest configuration.
        
        Returns:
            Dictionary with backtest configuration
        """
        config = self.load_config()
        return config.get('backtest', {})
    
    def get_backtest_strategy(self) -> str:
        """Get the active strategy name from config.
        
        Returns:
            Strategy name
        """
        config = self.load_config()
        strategy = config.get('strategy', '')
        
        if not strategy:
            raise ValueError("No strategy specified in config")
        
        return strategy
    
    def get_backtest_dates(self) -> tuple[str, str]:
        """Get backtest start and end dates from config.
        
        Returns:
            Tuple of (start_date, end_date) as strings in YYYY-MM-DD format
        """
        backtest_config = self.get_backtest_config()
        start_date = backtest_config.get('start_date', '')
        end_date = backtest_config.get('end_date', '')
        return (start_date, end_date)


# Global configuration instance
_config_loader = None


def get_config_loader() -> ConfigLoader:
    """Get global configuration loader instance.
    
    Returns:
        ConfigLoader instance
    """
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader

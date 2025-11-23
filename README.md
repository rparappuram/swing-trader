# Swing Trading System

A production-ready algorithmic trading system for swing trading strategies using Alpaca Markets. The system supports backtesting, parameter optimization, and live trading with a unified codebase.

## 🎯 Key Features

- **Config-Driven Architecture**: All configuration in YAML files - no command-line arguments needed
- **Unified Strategy Code**: Write strategy logic once, use in backtesting, optimization, and live trading
- **Intelligent Data Management**: Automatic caching with validation - fetches only missing data
- **Type-Safe Broker Interface**: Strongly-typed order submission with proper enums and dataclasses
- **Alpaca Integration**: Full support for paper and live trading via Alpaca Markets API
- **AWS Lambda Ready**: Can run live trading as a serverless function

## 📁 Project Structure

```
swing-trader/
├── config/
│   ├── config.yaml              # Main system configuration
│   └── strategies/              # Strategy-specific configs
│       └── sma_strategy.yaml    # Example: SMA crossover strategy
├── data/
│   ├── daily/                   # Cached daily price data (parquet files)
│   └── minute/                  # Cached minute price data (parquet files)
├── src/
│   ├── brokers/
│   │   ├── alpaca_broker.py     # Alpaca broker implementation
│   │   └── types.py             # Order types, enums, response types
│   ├── data_loaders/
│   │   └── data_manager.py      # Smart data loading with caching
│   ├── runners/
│   │   ├── backtest.py          # Backtesting runner
│   │   ├── optimize.py          # Parameter optimization runner
│   │   └── live.py              # Live trading runner
│   ├── strategies/
│   │   ├── base_strategy.py     # Abstract base class for all strategies
│   │   └── example_sma.py       # Example: SMA crossover strategy
│   └── utils/
│       └── config_loader.py     # Configuration management
├── .env                         # Environment variables (API keys)
└── requirements.txt             # Python dependencies
```

## 🚀 Getting Started

### Prerequisites

- Python 3.11 or higher
- Alpaca Markets account (paper or live)
- API keys from Alpaca Markets

### Installation

1. **Clone the repository**
```bash
cd swing-trader
```

2. **Create virtual environment**
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**

Create a `.env` file in the project root:
```bash
# Alpaca API Credentials
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here

# Paper trading (default)
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# For live trading, use:
# ALPACA_BASE_URL=https://api.alpaca.markets
```

5. **Configure your strategy**

Edit `config/config.yaml` to set your active strategy:
```yaml
# Active strategy (must match name in strategy config)
strategy: "SMAStrategy"

backtest:
  start_date: "2023-01-01"
  end_date: "2023-12-31"
  initial_cash: 100000.0
  commission: 0.001
```

## 🎮 Usage

### Backtesting

Run a backtest using the configured strategy and date range:

```bash
python src/runners/backtest.py
```

**Configuration**: Edit `config/config.yaml`
- `strategy`: Name of strategy to test
- `backtest.start_date`: Backtest start date
- `backtest.end_date`: Backtest end date
- `backtest.initial_cash`: Starting capital
- `backtest.commission`: Commission rate (e.g., 0.001 = 0.1%)

**Output**:
- Strategy performance metrics (return, Sharpe ratio, drawdown)
- Trade analysis (win rate, number of trades)
- Console logging of all trades

### Parameter Optimization

Optimize strategy parameters to find the best combination:

```bash
python src/runners/optimize.py
```

**Configuration**: 
- Uses same dates and strategy from `config/config.yaml`
- Parameter ranges defined in strategy config (e.g., `config/strategies/sma_strategy.yaml`)

```yaml
# In strategy config file
optimize_params:
  fast_period: [5, 10, 15, 20]
  slow_period: [20, 30, 40, 50]
  trailing_stop_percent: [3.0, 5.0, 7.0]
```

**Output**:
- Best parameter combination
- Performance metrics for each tested combination
- Sorted by optimization metric (default: Sharpe ratio)

### Live Trading

Execute live trading with the configured strategy:

```bash
python src/runners/live.py
```

**What it does**:
1. Fetches fresh market data from Alpaca
2. Runs strategy logic to check for signals
3. Executes trades through Alpaca API
4. Logs all actions and results

**Configuration**: Edit `config/config.yaml`
- `strategy`: Active strategy name
- `live.max_positions`: Maximum concurrent positions
- `live.position_size`: Position size as % of portfolio

**Important**: Set `ALPACA_BASE_URL` in `.env` to control paper vs live trading

## 📝 Creating a Strategy

### 1. Create Strategy Class

Create a new file in `src/strategies/`:

```python
import backtrader as bt
from .base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    """My custom strategy."""
    
    params = (
        ('param1', 10),
        ('param2', 20),
    )
    
    def __init__(self):
        super().__init__()
        # Initialize indicators
        self.indicator = bt.indicators.SMA(
            self.datas[0].close,  # type: ignore[arg-type]
            period=self.params.param1  # type: ignore[attr-defined]
        )
    
    def next(self):
        """Strategy logic - called for each bar."""
        if not self.position:
            # Entry logic
            if self.indicator[0] > self.datas[0].close[0]:
                size = self.get_position_size()
                self.place_buy_order(size=size)
        else:
            # Exit logic
            if self.indicator[0] < self.datas[0].close[0]:
                self.place_sell_order()
```

### 2. Create Strategy Config

Create `config/strategies/my_strategy.yaml`:

```yaml
name: "MyStrategy"
module: "src.strategies.my_strategy"
class: "MyStrategy"
enabled: true

tickers:
  - "SPY"

lookback_days: 60

params:
  param1: 10
  param2: 20

optimize_params:
  param1: [5, 10, 15, 20]
  param2: [10, 20, 30, 40]
```

### 3. Activate Strategy

Edit `config/config.yaml`:

```yaml
strategy: "MyStrategy"
```

### 4. Test Your Strategy

```bash
# Backtest
python src/runners/backtest.py

# Optimize
python src/runners/optimize.py

# Live trade
python src/runners/live.py
```

## 🔧 Configuration Reference

### Main Config (`config/config.yaml`)

```yaml
# Active strategy
strategy: "SMAStrategy"

# Data storage paths
data:
  daily_path: "data/daily"
  minute_path: "data/minute"

# Backtesting settings
backtest:
  start_date: "2023-01-01"
  end_date: "2023-12-31"
  initial_cash: 100000.0
  commission: 0.001

# Live trading settings
live:
  max_positions: 5
  position_size: 0.2
```

### Strategy Config (`config/strategies/*.yaml`)

```yaml
name: "StrategyName"           # Unique strategy identifier
module: "src.strategies.file"  # Python module path
class: "ClassName"             # Strategy class name
enabled: true                  # Enable/disable strategy

tickers:                       # List of tickers to trade
  - "SPY"
  - "QQQ"

lookback_days: 60              # Days of historical data needed

params:                        # Strategy parameters
  parameter_name: value

optimize_params:               # Parameter ranges for optimization
  parameter_name: [val1, val2, val3]
```

## 📊 Data Management

The system uses intelligent data caching:

### Backtesting/Optimization
- Checks if local parquet files exist
- Validates date range coverage
- Loads from cache if available
- Fetches from Alpaca only if needed
- Saves fetched data for future use

### Live Trading
- Always fetches fresh data from Alpaca
- No caching (ensures latest prices)

### Data Storage
- Daily data: `data/daily/{ticker}.parquet`
- Minute data: `data/minute/{ticker}.parquet`
- Format: Parquet (efficient, compressed)

## 🔐 Broker Integration

### Order Types

```python
from src.brokers.types import (
    MarketOrder, LimitOrder, StopOrder, 
    StopLimitOrder, TrailingStopOrder,
    OrderSide, TimeInForce
)

# Market order
order = MarketOrder(
    symbol="SPY",
    qty=10,
    side=OrderSide.BUY
)

# Limit order
order = LimitOrder(
    symbol="SPY",
    qty=10,
    side=OrderSide.BUY,
    limit_price=450.00,
    time_in_force=TimeInForce.DAY
)

# Submit order
result = broker.submit_order(order)
if result.success:
    print(f"Order ID: {result.order_id}")
```

### Account Information

```python
# Get account details
account = broker.get_account()
print(f"Cash: ${account.cash}")
print(f"Portfolio Value: ${account.portfolio_value}")

# Get positions
positions = broker.get_positions()
for pos in positions:
    print(f"{pos.symbol}: {pos.qty} shares @ ${pos.avg_entry_price}")
```

## 🧪 Testing

### Manual Testing

```bash
# Test backtest runner
python src/runners/backtest.py

# Test optimization
python src/runners/optimize.py

# Test live runner (paper trading recommended)
python src/runners/live.py
```

### Verify Data Loading

```python
from src.data_loaders.data_manager import DataManager
from datetime import datetime

dm = DataManager()
dm.init_alpaca_client(api_key, secret_key)

# Test data fetch
df = dm.get_data_for_backtest(
    "SPY",
    datetime(2023, 1, 1),
    datetime(2023, 12, 31),
    "daily"
)
print(df.head())
```

## 📈 Example Strategy: SMA Crossover

The included SMA strategy demonstrates:
- Fast/Slow moving average crossover signals
- Trailing stop loss for risk management
- Position sizing based on available capital
- Proper parameter configuration

**Entry**: Fast SMA crosses above Slow SMA  
**Exit**: Fast SMA crosses below Slow SMA OR trailing stop hit  
**Risk Management**: 5% trailing stop

## ☁️ AWS Lambda Deployment

The system includes a Lambda handler for serverless live trading:

```python
# src/lambda_handler.py
def lambda_handler(event, context):
    """AWS Lambda entry point for live trading."""
    # Automatically runs live trading
    # Can be triggered on schedule (e.g., daily at market close)
```

**Setup**:
1. Package code and dependencies
2. Set environment variables in Lambda console
3. Configure EventBridge trigger for scheduling
4. Set appropriate IAM permissions

## 🛠️ Development

### Type Checking

The codebase uses type hints with special handling for backtrader:

```python
# Type ignores needed for backtrader's dynamic systems
self.sma = bt.indicators.SMA(
    self.datas[0].close,  # type: ignore[arg-type]
    period=self.params.period  # type: ignore[attr-defined]
)
```

### Adding New Indicators

```python
def __init__(self):
    super().__init__()
    
    # Moving averages
    self.sma = bt.indicators.SMA(self.data, period=20)  # type: ignore[arg-type]
    self.ema = bt.indicators.EMA(self.data, period=20)  # type: ignore[arg-type]
    
    # Oscillators  
    self.rsi = bt.indicators.RSI(self.data, period=14)  # type: ignore[arg-type]
    self.macd = bt.indicators.MACD(self.data)  # type: ignore[arg-type]
    
    # Volatility
    self.atr = bt.indicators.ATR(self.data, period=14)  # type: ignore[arg-type]
    self.bbands = bt.indicators.BollingerBands(self.data)  # type: ignore[arg-type]
```

## 🔒 Security Notes

- **Never commit `.env` file** - contains API keys
- Use paper trading for testing
- Start with small position sizes in live trading
- Monitor live trades closely
- Set appropriate risk limits

## 📋 Common Issues

### "No strategy specified in config"
- Ensure `strategy` field is set in `config/config.yaml`
- Verify strategy name matches config file name

### "Strategy not found or not enabled"
- Check `enabled: true` in strategy config
- Verify strategy config file exists in `config/strategies/`

### "Alpaca client not initialized"
- Check `.env` file exists and has correct API keys
- Verify environment variables are loaded

### Data not loading
- Check internet connection
- Verify Alpaca API keys are valid
- Check date ranges are valid (no future dates)

### Type errors with backtrader
- Add `# type: ignore[arg-type]` or `# type: ignore[attr-defined]` comments
- These are due to incomplete backtrader type stubs, not actual errors

## 📚 Additional Resources

- [Alpaca Markets Documentation](https://alpaca.markets/docs/)
- [Backtrader Documentation](https://www.backtrader.com/docu/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)

## 📄 License

This project is for educational and personal use. Use at your own risk. Trading involves substantial risk of loss.

## ⚠️ Disclaimer

This software is provided for educational purposes only. Trading stocks and other securities involves risk of loss. Past performance does not guarantee future results. The authors and contributors are not responsible for any financial losses incurred through the use of this software.

Always test thoroughly in paper trading before using real money. Never invest more than you can afford to lose.

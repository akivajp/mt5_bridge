# MT5 Bridge API

## Overview
`mt5-bridge` is a FastAPI service and CLI tool that mediates market data access and order execution between a MetaTrader 5 terminal and external applications. 

- **Server**: Runs on Windows (where MT5 is installed) and exposes a REST API.
- **Client**: Runs on any platform (Windows, Linux, macOS) and communicates with the Server to fetch data or execute trades.

## Prerequisites
- Python 3.11+
- **Server Mode**: Windows environment with MetaTrader 5 terminal installed.
- **Client Mode**: Any OS.

## Installation

### From PyPI (Recommended)

You can install `mt5-bridge` directly from PyPI:

```bash
pip install mt5-bridge
```

Once installed, you can run the `mt5-bridge` command directly.

### From Source (Development)

This project uses [uv](https://github.com/astral-sh/uv) for package management.

```bash
# Install dependencies
uv sync
```

On Linux/macOS, the `MetaTrader5` package will be skipped automatically, allowing you to use the client functionality without issues.

## Usage

The package installs a CLI command `mt5-bridge`.

### 1. Start the Server (Windows Only)

On your Windows machine with MT5:

```powershell
# Default (localhost:8000)
uv run mt5-bridge server

# Custom host/port
uv run mt5-bridge server --host 0.0.0.0 --port 8000
```

> **Note**: If you are using WSL, please checkout this repository on the **Windows file system** (e.g., `C:\Work\mt5-bridge`) and run the command from PowerShell/Command Prompt. Running Windows Python directly against a directory inside WSL (UNC path like `\\wsl.localhost\Ubuntu\...`) often causes `DLL load failed` errors with libraries like NumPy.


Additional options:
- `--mt5-path "C:\Path\To\terminal64.exe"`: proper initialization
- `--no-utc`: Disable Server Time -> UTC conversion

### 2. Use the Client (Any Platform)

From another machine (or the same one), use the client command to interact with the server.

```bash
# Check connection health
uv run mt5-bridge client --url http://192.168.1.10:8000 health

# Get server version
uv run mt5-bridge client --url http://192.168.1.10:8000 version

# Get historical rates (M1, last 1000 bars) for XAUUSD
uv run mt5-bridge client --url http://192.168.1.10:8000 rates XAUUSD

# Get historical rates by date range (M1, 2026-01-01 to 2026-01-15)
uv run mt5-bridge client --url http://192.168.1.10:8000 rates_range XAUUSD --timeframe M1 --start 2026-01-01 --end 2026-01-15

# Get historical tick data from a specific date (count-based)
uv run mt5-bridge client --url http://192.168.1.10:8000 ticks_from XAUUSD --start 2026-01-01 --count 1000 --flags ALL

# Get historical tick data within a date range
uv run mt5-bridge client --url http://192.168.1.10:8000 ticks_range XAUUSD --start "2026-01-01 10:00:00" --end "2026-01-01 10:05:00" --flags TRADE

# Get latest tick
uv run mt5-bridge client --url http://192.168.1.10:8000 tick XAUUSD

# Get market depth (Level 2)
uv run mt5-bridge client --url http://192.168.1.10:8000 book XAUUSD

# Get account information
uv run mt5-bridge client --url http://192.168.1.10:8000 account

# List open positions (optional filters: --symbols XAUUSD,BTCUSD --magic 123456)
uv run mt5-bridge client --url http://192.168.1.10:8000 positions

# Get historical deals (optional filters: --position 123456 --ticket 789012 --start 2026-01-01 --end 2026-01-02)
uv run mt5-bridge client --url http://192.168.1.10:8000 history_deals

# Send order
uv run mt5-bridge client --url http://192.168.1.10:8000 order XAUUSD BUY 0.01 --sl 2000.0 --tp 2050.0

# Close position
uv run mt5-bridge client --url http://192.168.1.10:8000 close 12345678

# Modify position
uv run mt5-bridge client --url http://192.168.1.10:8000 modify 12345678 --sl 2005.0
```

### JSON API

You can also access the API directly via generic HTTP clients (curl, Postman, specific libraries).

- `GET /health`
- `GET /version` (**v1.8.1+**)
- `GET /rates/{symbol}?timeframe=M1&count=1000`
- `GET /rates_range/{symbol}?timeframe=M1&start=2026-01-01&end=2026-01-15`
- `GET /tick/{symbol}`
- `GET /book/{symbol}` (**v1.6.0+**)
- `GET /ticks_from/{symbol}?start=2026-01-01&count=1000&flags=ALL` (**v1.5.0+**)
- `GET /ticks_range/{symbol}?start=2026-01-01&end=2026-01-02&flags=ALL` (**v1.5.0+**)
- `GET /account`
- `GET /positions?symbols=XAUUSD,BTCUSD&magic=123456` (**v1.7.0+** now includes `time_msc`)
- `GET /history/deals?position=123456&ticket=789012&start=2026-01-01&end=2026-01-02` (**v1.8.0+**)
- `POST /order`
- `POST /close`
- `POST /modify`

### Historical Tick Data (v1.5.0+)

The tick data endpoints support the following tick type flags:

| Flag | Description |
|------|-------------|
| `ALL` | All ticks |
| `INFO` | Ticks with Bid/Ask changes |
| `TRADE` | Ticks with Last/Volume changes (actual trades) |

The response includes:
- `time`: Timestamp in seconds (UTC)
- `time_msc`: Millisecond-precision timestamp (UTC)
- `bid`, `ask`, `last`, `volume`: Price and volume information
- `flags`: Tick change flags

## Architecture
- `mt5_bridge/main.py`: CLI entry point and FastAPI server definition.
- `mt5_bridge/mt5_handler.py`: Wrapper for MetaTrader5 package (guarded imports).
- `mt5_bridge/client.py`: HTTP client implementation.

## MCP (Copilot CLI) Integration
- Purpose: expose the MT5 Bridge API to Copilot CLI (MCP).
- Run MCP server:
  - `python mt5_bridge/mcp_server.py --api-base http://localhost:8000`

## License
MIT License.

# MT5 Bridge API

## Overview
`mt5_bridge` is a FastAPI service that mediates HTTP-based market data access and order execution between a MetaTrader 5 terminal and external applications. Run it on the same Windows environment as MetaTrader 5, and call the REST endpoints from your research or inference pipeline (for example, `trading_brain`) to reuse data retrieval and trade submission logic.

## Architecture
- `mt5_bridge/main.py`: FastAPI entry point that bootstraps the server and defines endpoints.
- `mt5_bridge/mt5_handler.py`: Wrapper around the official MetaTrader5 Python package that encapsulates connection setup, data retrieval, order placement, and position management.

## Prerequisites
1. A MetaTrader 5 terminal installed and logged in to the target broker account.
2. Windows environment (the official MetaTrader5 Python package is Windows-only).
3. Python 3.9+ is recommended.

## Dependencies
Only the packages strictly required by the bridge are listed in `requirements.txt`.

```bash
pip install -r requirements.txt
```

Key packages:
- `MetaTrader5` (Windows only)
- `fastapi`
- `uvicorn[standard]`
- `pydantic`

## Getting Started
1. Launch your MetaTrader 5 terminal and ensure it is connected to the intended account.
2. Install the dependencies in your Windows Python environment.
3. From the repository root (or inside `mt5_bridge/`), run:

```bash
python -m uvicorn mt5_bridge.main:app --host 0.0.0.0 --port 8000
```

You can also start the server by calling `uvicorn.run` at the bottom of `main.py`.

When invoking `main.py` directly, use the CLI flags to adjust host/port (defaults: `0.0.0.0:8000`).

```powershell
python mt5_bridge/main.py --host 0.0.0.0 --port 9000
```

## API Reference
All endpoints return JSON. On errors the service responds with HTTP 500 and a payload containing `detail`.

### GET `/health`
- Purpose: Check MT5 connection status.
- Example response:
```json
{"status": "ok", "mt5_connected": true}
```

### GET `/rates/{symbol}`
- Query parameters: `timeframe` (for example `M1`, `H1`, `W1`, `MN1`), `count` (number of bars, default 1000).
- Description: Fetch the latest bars for the specified symbol from MT5 and return them in ascending timestamp order.
- Fields per bar: `time`, `open`, `high`, `low`, `close`, `tick_volume`, `spread`, `real_volume`.

### GET `/tick/{symbol}`
- Description: Retrieve the current tick information.
- Response fields: `time`, `bid`, `ask`, `last`, `volume`.

### GET `/positions`
- Description: List all open positions in the account.
- Fields per position: `ticket`, `symbol`, `type` (`BUY`/`SELL`), `volume`, `price_open`, `sl`, `tp`, `price_current`, `profit`, `time`.

### POST `/order`
- Request body:
```json
{
  "symbol": "XAUUSD",
  "type": "BUY",
  "volume": 0.01,
  "sl": 0.0,
  "tp": 0.0,
  "comment": "Optional text"
}
```
- Description: Submit a market order. Returns `{ "status": "ok", "ticket": <id> }` on success.

### POST `/close`
- Request body:
```json
{
  "ticket": 12345678
}
```
- Description: Close the specified ticket via the opposite side. Returns `{ "status": "ok" }` on success.

### POST `/modify`
- Request body:
```json
{
  "ticket": 12345678,
  "sl": 1.095,
  "tp": 1.115,
  "update_sl": true,
  "update_tp": false
}
```
- Description: Update stop-loss and/or take-profit levels for an existing position. Only the fields with `update_* = true` are changed. Omitting `sl`/`tp` or passing `null` clears the respective level. Returns `{ "status": "ok" }` on success.

## Configuration and Extension Tips
- Customize the host/port via Uvicorn arguments. Make sure the Windows firewall allows inbound traffic so external clients (for example, `trading_brain` on Linux) can reach the server.
- When adding new endpoints, keep the abstraction layer in `mt5_handler` and avoid calling the MetaTrader5 API directly from the FastAPI layer. This keeps the codebase modular and easier to reuse.
- If you change the API surface, update this README and notify downstream consumers.

## MCP (Copilot CLI) Integration
- Purpose: expose the HTTP API to Copilot CLI (MCP) over HTTP.
- Requirements: `pip install -r requirements.txt` (includes `fastmcp` and `httpx`).
- Env: optional `MT5_BRIDGE_BASE_URL` (default `http://localhost:8000`).
- Run MCP server (HTTP listener, defaults host `0.0.0.0`, port `8001`):
  - `python mcp_server.py --api-base http://localhost:8000 --host 0.0.0.0 --port 8001`
- Copilot CLI: add this MCP server as an HTTP source (e.g., `copilot mcp add http http://localhost:8001`). Tool names mirror the HTTP endpoints: `get_rates`, `get_tick`, `list_positions`, `send_order`, `close_position`, `modify_position`, `health`.

## Support and Donations
- <a href="https://github.com/sponsors/akivajp" style="vertical-align: middle;"><img src="https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png" alt="GitHub Sponsors" height="32" /></a> GitHub Sponsors: [https://github.com/sponsors/akivajp](https://github.com/sponsors/akivajp)
- <a href="https://buymeacoffee.com/akivajp" style="vertical-align: middle;"><img src="https://github.githubassets.com/assets/buy_me_a_coffee-63ed78263f6e.svg" alt="Buy Me a Coffee" height="32" /></a> Buy Me a Coffee: [https://buymeacoffee.com/akivajp](https://buymeacoffee.com/akivajp)

If you prefer another support option, open an Issue or Discussion. Even small contributions are greatly appreciated.

## License
This project is licensed under the MIT License. See `LICENSE` for details.

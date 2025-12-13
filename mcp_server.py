"""
MCP server bridging Copilot CLI to MT5 Bridge.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Literal

import httpx
from fastmcp import FastMCP

BASE_URL = os.getenv("MT5_BRIDGE_BASE_URL", "http://localhost:8000")

mcp = FastMCP(
    "mt5-bridge",
    instructions=(
        "Tools proxy the mt5_bridge FastAPI for chart data and trading. "
        "Set MT5_BRIDGE_BASE_URL if the API is not at http://localhost:8000."
    ),
)

def _request(
    method: str,
    path: str,
    *,
    json: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    # Single HTTP request wrapper with consistent error reporting / 一貫したエラーハンドリング付きのHTTPラッパー
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            response = client.request(method, path, json=json, params=params)
            response.raise_for_status()
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            return response.text
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise RuntimeError(f"MT5 Bridge error {exc.response.status_code}: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to reach MT5 Bridge: {exc}") from exc


@mcp.tool()
def health() -> Dict[str, Any]:
    """Check MT5 Bridge health / ブリッジのヘルスを確認"""
    return _request("GET", "/health")


@mcp.tool()
def get_rates(symbol: str, timeframe: str = "M1", count: int = 100) -> List[Dict[str, Any]]:
    """Fetch OHLCV bars / OHLCVバーを取得"""
    return _request("GET", f"/rates/{symbol}", params={"timeframe": timeframe, "count": count})


@mcp.tool()
def get_tick(symbol: str) -> Dict[str, Any]:
    """Fetch latest tick / 最新ティックを取得"""
    return _request("GET", f"/tick/{symbol}")


@mcp.tool()
def list_positions() -> List[Dict[str, Any]]:
    """List open positions / オープンポジション一覧"""
    return _request("GET", "/positions")


@mcp.tool()
def send_order(
    symbol: str,
    side: Literal["BUY", "SELL"],
    volume: float,
    sl: float = 0.0,
    tp: float = 0.0,
    comment: str = "",
) -> Dict[str, Any]:
    """Submit market order / 成行注文を送信"""
    payload = {"symbol": symbol, "type": side, "volume": volume, "sl": sl, "tp": tp, "comment": comment}
    return _request("POST", "/order", json=payload)


@mcp.tool()
def close_position(ticket: int) -> Dict[str, Any]:
    """Close position by ticket / チケット指定で決済"""
    return _request("POST", "/close", json={"ticket": ticket})


@mcp.tool()
def modify_position(
    ticket: int,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    update_sl: bool = False,
    update_tp: bool = False,
) -> Dict[str, Any]:
    """Update SL/TP for a position / ポジションのSL/TPを更新"""
    payload = {"ticket": ticket, "sl": sl, "tp": tp, "update_sl": update_sl, "update_tp": update_tp}
    return _request("POST", "/modify", json=payload)


if __name__ == "__main__":
    import argparse

    # Parse CLI args so operator can set API base URL and MCP listen address /
    # APIベースURLとMCP待受アドレスをCLI引数で設定
    parser = argparse.ArgumentParser(description="Run MT5 Bridge MCP over HTTP")
    parser.add_argument("--api-base", default=BASE_URL, help="MT5 Bridge API base URL (default: env MT5_BRIDGE_BASE_URL or http://localhost:8000)")
    parser.add_argument("--host", default="0.0.0.0", help="MCP listen host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="MCP listen port (default: 8001)")
    args = parser.parse_args()

    # Override BASE_URL from CLI / CLI指定でBASE_URLを上書き
    #global BASE_URL
    BASE_URL = args.api_base

    # Start MCP HTTP server; prefer run_http, otherwise use run(transport="http") /
    # MCPのHTTPサーバーを起動。run_httpが無い場合はtransport="http"でrunを利用
    if hasattr(mcp, "run_http"):
        mcp.run_http(host=args.host, port=args.port)
    elif hasattr(mcp, "run"):
        # Some fastmcp versions default transport to stdio; force HTTP explicitly /
        # 一部バージョンはデフォルトtransportがstdioのためHTTPを明示
        mcp.run(host=args.host, port=args.port, transport="http")
    else:
        raise SystemExit("FastMCP does not provide run_http or run; please upgrade fastmcp")

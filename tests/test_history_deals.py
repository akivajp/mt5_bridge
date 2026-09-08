import pytest
from unittest.mock import patch, MagicMock
from typing import Generator
from mt5_bridge.client import BridgeClient
from mt5_bridge.main import parse_datetime

def test_parse_datetime() -> None:
    """日付文字列およびタイムスタンプ文字列のパース処理をテストします。"""
    # 数値形式のタイムスタンプ文字列のパース
    assert parse_datetime("1704067200") == 1704067200
    
    # 日付文字列（UTC）のパース
    # 2024-01-01 00:00:00 UTC は 1704067200 になるはず
    assert parse_datetime("2024-01-01 00:00:00") == 1704067200


@patch("httpx.get")
def test_client_get_history_deals(mock_get: MagicMock) -> None:
    """BridgeClient の get_history_deals が正しく HTTP GET リクエストを送信し、結果を取得できるかテストします。"""
    # レスポンスのモック設定
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {
            "ticket": 12345,
            "order": 67890,
            "time": 1704067200,
            "time_msc": 1704067200000,
            "type": "BUY",
            "entry": "IN",
            "position_id": 111,
            "volume": 0.1,
            "price": 2000.0,
            "commission": -0.5,
            "swap": 0.0,
            "profit": 10.0,
            "comment": "test trade",
            "magic": 123456,
            "symbol": "XAUUSD"
        }
    ]
    mock_get.return_value = mock_resp

    # クライアントの初期化と実行
    client = BridgeClient("http://localhost:8000")
    result = client.get_history_deals(
        position=111,
        ticket=12345,
        start=1704067200,
        end=1704067300
    )

    # 正しいURLとパラメータでGETリクエストが送信されたことを検証
    mock_get.assert_called_once_with(
        "http://localhost:8000/history/deals",
        params={
            "position": 111,
            "ticket": 12345,
            "start": 1704067200,
            "end": 1704067300
        },
        timeout=30.0
    )
    
    # 戻り値の検証
    assert len(result) == 1
    assert result[0]["ticket"] == 12345
    assert result[0]["symbol"] == "XAUUSD"
    assert result[0]["profit"] == 10.0


@patch("httpx.get")
def test_client_get_version(mock_get: MagicMock) -> None:
    """BridgeClient.get_version が正しく HTTP GET リクエストを送信し、結果を取得できるかテストします。"""
    # レスポンスのモック設定
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"version": "1.9.0"}
    mock_get.return_value = mock_resp

    # クライアントの初期化と実行
    client = BridgeClient("http://localhost:8000")
    result = client.get_version()

    # 正しいURLでGETリクエストが送信されたことを検証
    mock_get.assert_called_once_with(
        "http://localhost:8000/version",
        timeout=5.0
    )
    assert result == {"version": "1.9.0"}


def test_api_version() -> None:
    """FastAPI サーバーの /version エンドポイントが正しく機能するかテストします。"""
    from fastapi.testclient import TestClient
    from mt5_bridge.main import app

    client = TestClient(app)
    response = client.get("/version")
    
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data["version"] == "1.9.0" or data["version"] == "unknown"


def test_api_health() -> None:
    """FastAPI サーバーの /health エンドポイントがバージョン情報を含むかテストします。"""
    from fastapi.testclient import TestClient
    from mt5_bridge.main import app

    client = TestClient(app)
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"
    assert "version" in data
    assert data["version"] == "1.9.0" or data["version"] == "unknown"


@patch("httpx.get")
def test_client_get_tick_url_encode(mock_get: MagicMock) -> None:
    """特殊文字（# や /）を含むシンボル名で呼び出した際、正しくURLエンコードされるかを検証します。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "time": 1704067200,
        "time_msc": 1704067200000,
        "bid": 2000.0,
        "ask": 2000.5,
        "last": 2000.0,
        "volume": 1
    }
    mock_get.return_value = mock_resp

    client = BridgeClient("http://localhost:8000")
    
    # スラッシュ (/) と シャープ (#) を含むシンボル名
    symbol_with_special = "XAU/USD#test"
    result = client.get_tick(symbol_with_special)

    # 期待されるエンコードされた URL
    # "XAU/USD#test" -> "XAU%2FUSD%23test"
    expected_encoded_symbol = "XAU%2FUSD%23test"
    mock_get.assert_called_once_with(
        f"http://localhost:8000/tick/{expected_encoded_symbol}",
        timeout=5.0
    )
    assert result is not None
    assert result["bid"] == 2000.0

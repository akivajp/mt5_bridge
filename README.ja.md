# MT5 Bridge API

## 概要
`mt5-bridge`はMetaTrader 5ターミナルと外部アプリケーションの間で市場データの取得や注文実行を仲介するためのFastAPIサービス兼CLIツールです。

- **サーバー機能**: MetaTrader 5がインストールされたWindows環境で動作し、REST API機能を提供します。
- **クライアント機能**: Windows、Linux、macOSなど任意のOSで動作し、サーバーと通信してデータの取得や注文を行います。

## 前提条件
- Python 3.11以上
- **サーバーモード**: MetaTrader 5ターミナルがインストールされたWindows環境。
- **クライアントモード**: 任意のOS環境。

## インストール (uv)

本プロジェクトはパッケージ管理に [uv](https://github.com/astral-sh/uv) を使用しています。

```bash
# 依存関係のインストール
uv sync
```

LinuxやmacOS環境では、Windows専用の `MetaTrader5` パッケージは自動的にスキップされ、クライアント機能のみが利用可能な状態でインストールされます。

## 使い方

インストールすると `mt5-bridge` コマンドが利用可能になります。

### 1. サーバーの起動 (Windowsのみ)

MT5がインストールされているWindowsマシンで実行します:

```powershell
# デフォルト設定 (localhost:8000) で起動
uv run mt5-bridge server

# ホストやポートを指定
uv run mt5-bridge server --host 0.0.0.0 --port 8000
```

> **注意**: WSL上のディレクトリ（`\\wsl.localhost\...`）にあるソースコードをWindows側のPythonで直接実行すると、NumPyなどのライブラリ読み込み時（DLLロード）にエラーが発生する場合があります。サーバー機能を利用する際は、必ず**Windows側のローカルフォルダ**（例: `C:\Work\mt5-bridge`）にリポジトリを配置して実行してください。


主なオプション:
- `--mt5-path "C:\Path\To\terminal64.exe"`: MT5のパスを明示的に指定して初期化
- `--no-utc`: サーバー時間をUTCに変換せず、そのまま返す（デフォルトはUTC変換有効）

### 2. クライアントの利用 (任意のプラットフォーム)

別のマシン（または同一マシン）からクライアントコマンドでサーバーを操作できます。

```bash
# サーバーのヘルスチェック
uv run mt5-bridge client --url http://192.168.1.10:8000 health

# サーバーのバージョン取得
uv run mt5-bridge client --url http://192.168.1.10:8000 version

# 利用可能なシンボル一覧の取得
uv run mt5-bridge client --url http://192.168.1.10:8000 symbols

# 過去レートの取得 (M1, 最新1000本) - シンボル: XAUUSD
uv run mt5-bridge client --url http://192.168.1.10:8000 rates XAUUSD

# 最新ティックの取得
uv run mt5-bridge client --url http://192.168.1.10:8000 tick XAUUSD

# 板情報 (Level 2) の取得
uv run mt5-bridge client --url http://192.168.1.10:8000 book XAUUSD

# 口座情報の取得
uv run mt5-bridge client --url http://192.168.1.10:8000 account

# 保有ポジションの一覧表示 (オプション: --symbols XAUUSD,BTCUSD --magic 123456)
uv run mt5-bridge client --url http://192.168.1.10:8000 positions

# 取引履歴（約定履歴）の取得 (オプション: --position 123456 --ticket 789012 --start 2025-01-01 --end 2025-01-02)
uv run mt5-bridge client --url http://192.168.1.10:8000 history_deals

# 指定期間のレート取得 (タイムスタンプまたは日時文字列)
uv run mt5-bridge client --url http://192.168.1.10:8000 rates_range XAUUSD --timeframe M1 --start 2025-01-01 --end 2025-01-02

# 過去ティックデータ取得 (指定日時から件数指定)
uv run mt5-bridge client --url http://192.168.1.10:8000 ticks_from XAUUSD --start 2025-01-01 --count 1000 --flags ALL

# 過去ティックデータ取得 (日時範囲指定)
uv run mt5-bridge client --url http://192.168.1.10:8000 ticks_range XAUUSD --start "2025-01-01 10:00:00" --end "2025-01-01 10:05:00" --flags TRADE

# 新規注文 (例: XAUUSD 0.01ロット 買い, SL 2000.0, TP 2050.0)
uv run mt5-bridge client --url http://192.168.1.10:8000 order XAUUSD BUY 0.01 --sl 2000.0 --tp 2050.0

# ポジション決済 (チケット番号指定)
uv run mt5-bridge client --url http://192.168.1.10:8000 close 12345678

# ポジション変更 (SL/TP更新)
uv run mt5-bridge client --url http://192.168.1.10:8000 modify 12345678 --sl 2005.0
```

### JSON API

汎用的なHTTPクライアントやライブラリから直接APIを利用することも可能です。

- `GET /health`
- `GET /version` (**v1.8.1~**)
- `GET /symbols` (**v1.7.2~**)
- `GET /rates/{symbol}?timeframe=M1&count=1000`
- `GET /rates_range/{symbol}?timeframe=M1&start=2025-01-01&end=2025-01-02`
- `GET /tick/{symbol}`
- `GET /book/{symbol}` (**v1.6.0~**)
- `GET /ticks_from/{symbol}?start=2025-01-01&count=1000&flags=ALL` (**v1.5.0~**)
- `GET /ticks_range/{symbol}?start=2025-01-01&end=2025-01-02&flags=ALL` (**v1.5.0~**)
- `GET /account`
- `GET /positions?symbols=XAUUSD,BTCUSD&magic=123456` (**v1.7.0~** で `time_msc` を追加)
- `GET /history/deals?position=123456&ticket=789012&start=2025-01-01&end=2025-01-02` (**v1.8.0~**)
- `POST /order`
- `POST /close`
- `POST /modify`

### ティックデータについて (v1.5.0~)

履歴ティックデータ機能では、以下のフラグを使用してティックの種類を指定できます:

| フラグ | 説明 |
|--------|------|
| `ALL` | すべてのティック |
| `INFO` | Bid/Askの変更を含むティック |
| `TRADE` | Last/Volumeの変更を含むティック（実約定） |

レスポンスには以下のフィールドが含まれます:
- `time`: 秒単位のタイムスタンプ (UTC)
- `time_msc`: ミリ秒単位のタイムスタンプ（高精度、UTC）
- `bid`, `ask`, `last`, `volume`: 価格・出来高情報
- `flags`: ティック変更フラグ

## 構成
- `mt5_bridge/main.py`: CLIエントリポイントおよびFastAPIサーバー定義。
- `mt5_bridge/mt5_handler.py`: MetaTrader5パッケージのラッパー（条件付きインポートにより非Windows環境でもエラーになりません）。
- `mt5_bridge/client.py`: HTTPクライアントの実装。

## MCP (Copilot CLI) 連携
- 目的: MT5 Bridge APIをCopilot CLI (MCP) として公開します。
- 実行方法:
  - `python mt5_bridge/mcp_server.py --api-base http://localhost:8000`

## サポート・寄付
- <a href="https://github.com/sponsors/akivajp" style="vertical-align: middle;"><img src="https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png" alt="GitHub Sponsors" height="32" /></a> GitHub Sponsors: [https://github.com/sponsors/akivajp](https://github.com/sponsors/akivajp)
- <a href="https://buymeacoffee.com/akivajp" style="vertical-align: middle;"><img src="https://github.githubassets.com/assets/buy_me_a_coffee-63ed78263f6e.svg" alt="Buy Me a Coffee" height="32" /></a> Buy Me a Coffee: [https://buymeacoffee.com/akivajp](https://buymeacoffee.com/akivajp)

上記以外の支援方法を希望される場合は Issue や Discussions でご相談ください。
少額の寄付・サポートはいつでも大歓迎です。お気持ちだけでも大きな励みになります。

## ライセンス
本プロジェクトは MIT License の下で提供されます。詳細は `LICENSE` を参照してください。

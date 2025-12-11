# MT5 Bridge API

## 概要
`mt5_bridge`はMetaTrader 5ターミナルと外部アプリケーションの間でHTTP経由のデータ取得および注文実行を仲介するFastAPIサービスです。MetaTrader 5が稼働するWindows環境上で本APIを立ち上げ、学習・推論パイプライン（例: `trading_brain`）からはRESTエンドポイントを呼び出すだけで価格データ取得や注文送信を再利用できます。

## 構成
- `mt5_bridge/main.py`: FastAPIエントリポイント。サーバー起動とエンドポイント定義を担当。
- `mt5_bridge/mt5_handler.py`: MetaTrader5公式Pythonパッケージを使って端末と通信するラッパー。接続初期化、価格取得、注文、決済をカプセル化。

## 前提条件
1. MetaTrader 5ターミナルがインストールされ、対象ブローカー口座にログイン済みであること。
2. 本サービスはWindows上でのみ稼働可能です（MetaTrader5公式PythonがWindows限定のため）。
3. Python 3.9+ を推奨。

## 依存パッケージ
`mt5_bridge/requirements.txt`に、ブリッジ単体で必要なパッケージのみを列挙しています。

```bash
pip install -r mt5_bridge/requirements.txt
```

主な依存:
- `MetaTrader5` (Windows限定)
- `fastapi`
- `uvicorn[standard]`
- `pydantic`

## 起動方法
1. MetaTrader 5ターミナルを起動し、対象口座に接続された状態にします。
2. WindowsのPython環境で依存パッケージをインストールします。
3. リポジトリルートまたは`mt5_bridge/`ディレクトリ内で以下を実行します。

```bash
python -m uvicorn mt5_bridge.main:app --host 0.0.0.0 --port 8000
```

`main.py`末尾の`uvicorn.run`を使って直接起動することも可能です。

## APIリファレンス
共通: 全エンドポイントはJSONを返し、エラー時はHTTP 500で`detail`を含むレスポンスを返します。

### GET `/health`
- 内容: MT5接続状態チェック。
- レスポンス例:
```json
{"status": "ok", "mt5_connected": true}
```

### GET `/rates/{symbol}`
- クエリ: `timeframe` (例: `M1`, `H1`, `W1`, `MN1`), `count` (取得バー数、既定1000)。
- 説明: 指定シンボルの最新バーをMT5から取得し、時刻昇順に返却。
- レスポンスの各要素: `time`, `open`, `high`, `low`, `close`, `tick_volume`, `spread`, `real_volume`。

### GET `/tick/{symbol}`
- 説明: 現在のティック情報を取得。
- レスポンス: `time`, `bid`, `ask`, `last`, `volume`。

### GET `/positions`
- 説明: 口座内の全オープンポジションを一覧で返却。
- 各要素: `ticket`, `symbol`, `type` (`BUY`/`SELL`), `volume`, `price_open`, `sl`, `tp`, `price_current`, `profit`, `time`。

### POST `/order`
- リクエストボディ:
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
- 説明: 成行注文を送信。成功時 `{ "status": "ok", "ticket": <id> }` を返却。

### POST `/close`
- リクエストボディ:
```json
{
  "ticket": 12345678
}
```
- 説明: 指定チケットのポジションを反対売買で決済。成功時 `{ "status": "ok" }`。

### POST `/modify`
- リクエストボディ:
```json
{
  "ticket": 12345678,
  "sl": 1.095,
  "tp": 1.115,
  "update_sl": true,
  "update_tp": false
}
```
- 説明: 既存ポジションのストップロス／テイクプロフィットを更新。`update_*` が `true` のフィールドのみ書き換え、`sl`/`tp` を省略または `null` にすると該当レベルをクリア。成功時 `{ "status": "ok" }`。

## 設定・拡張のヒント
- 接続先ポート/ホストはサーバー起動引数で変更できます。外部クライアント（例: Linux上の`trading_brain`）から到達できるよう、Windowsファイアウォールで該当ポートを許可してください。
- エンドポイントを追加する際は`mt5_handler`に必ず薄いラッパーを用意し、FastAPI層から直接MetaTrader5 APIを呼び出さない方針にすると、将来的なサブモジュール化・単体利用が容易になります。
- API仕様を変更した場合は、本READMEのエンドポイント定義を更新し、依存リポジトリにも周知してください。

## サポート・寄付
- <a href="https://github.com/sponsors/akivajp" style="vertical-align: middle;"><img src="https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png" alt="GitHub Sponsors" height="32" /></a> GitHub Sponsors: [https://github.com/sponsors/akivajp](https://github.com/sponsors/akivajp)
- <a href="https://buymeacoffee.com/akivajp" style="vertical-align: middle;"><img src="https://github.githubassets.com/assets/buy_me_a_coffee-63ed78263f6e.svg" alt="Buy Me a Coffee" height="32" /></a>
Buy Me a Coffee: [https://buymeacoffee.com/akivajp](https://buymeacoffee.com/akivajp)

上記以外の支援方法を希望される場合は Issue や Discussions でご相談ください。
少額の寄付・サポートはいつでも大歓迎です。お気持ちだけでも大きな励みになります。

## ライセンス
本プロジェクトは MIT License の下で提供されます。詳細は `LICENSE` を参照してください。

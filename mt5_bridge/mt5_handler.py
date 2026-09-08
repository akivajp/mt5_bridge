import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conditional import for MetaTrader5
if sys.platform == 'win32':
    try:
        import MetaTrader5 as mt5
    except ImportError:
        mt5 = None
        logger.warning("MetaTrader5 package not found")
else:
    mt5 = None

import pandas as pd
from datetime import datetime, timezone, timedelta
import logging
from typing import Optional, Dict, List, Union



class MT5Handler:
    # サーバータイムゾーンオフセットとして現実的に取りうる範囲 (秒)。
    # 実在するブローカーのサーバー時間は概ね UTC-12 ～ UTC+14 に収まる。
    _MIN_OFFSET_SEC = -12 * 3600
    _MAX_OFFSET_SEC = 14 * 3600
    # 再推定時に許容するオフセットの変動幅 (秒)。
    # サーバーのタイムゾーンが変わるのは夏時間切り替え時のみで、その幅は最大1時間。
    _MAX_OFFSET_DRIFT_SEC = 3600

    def __init__(
        self,
        program_path: Optional[str] = None,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        use_utc: bool = True,
        offset_ttl_hours: float = 6.0
    ):
        self.connected = False
        self.program_path = program_path
        self.login = login
        self.password = password
        self.server = server
        self.use_utc = use_utc
        self._server_offset_sec: Optional[int] = None
        # offsetキャッシュのTTL管理(長期間起動で古いoffsetが使われ続け、
        # 夏時間切り替えやMT5端末再接続後のサーバー時刻変動に追従できなくなる問題の対策)
        self._offset_updated_at: Optional[datetime] = None
        self._offset_ttl_sec: float = offset_ttl_hours * 3600.0

    def initialize(self) -> bool:
        """
        Initialize connection to MetaTrader 5 terminal.
        """
        # If path is specified, use it
        init_args = {}
        if self.program_path:
            init_args["path"] = self.program_path
            
        if mt5 is None:
            logger.error("MetaTrader5 is not available on this platform (Windows only).")
            self.connected = False
            return False

        if not mt5.initialize(**init_args):
            logger.error("initialize() failed, error code = %s", mt5.last_error())
            self.connected = False
            return False
            
        # If login credentials are provided, try to login
        if self.login and self.password and self.server:
            authorized = mt5.login(
                login=self.login,
                password=self.password,
                server=self.server
            )
            if not authorized:
                logger.error("failed to connect at account #%d, error code: %s", self.login, mt5.last_error())
                self.connected = False
                return False
            logger.info("MT5 login successful")

        logger.info("MT5 initialized successfully")
        self.connected = True
        return True

    def check_connection(self) -> bool:
        """
        Check if connection is still alive using terminal_info.
        Attempt to reconnect if lost.
        """
        if not mt5.terminal_info():
            self.connected = False
            logger.warning("Connection lost. Attempting to reconnect...")
            return self.initialize()
        
        self.connected = True
        return True

    def shutdown(self):
        """
        Shutdown connection to MetaTrader 5.
        """
        mt5.shutdown()
        self.connected = False
        logger.info("MT5 connection shutdown")

    def _is_plausible_offset(self, offset_sec: int) -> bool:
        """
        推定されたサーバータイムゾーンオフセットが妥当かどうかを判定する。

        市場クローズ中は symbol_info_tick() が直前の営業終了時のティックを返し続けるため、
        オフセットが「真の値 - 市場停止からの経過時間」として大幅に誤推定される。
        以下の2条件で明らかに不正な推定値を弾く。

        1. 実在するタイムゾーンの範囲 (UTC-12 ～ UTC+14) に収まっていること
        2. 既にオフセットが確定している場合、その変動幅が1時間以内であること

        Args:
            offset_sec: 推定されたオフセット (秒)

        Returns:
            妥当と判断できる場合 True
        """
        if not (self._MIN_OFFSET_SEC <= offset_sec <= self._MAX_OFFSET_SEC):
            return False
        if self._server_offset_sec is not None:
            if abs(offset_sec - self._server_offset_sec) > self._MAX_OFFSET_DRIFT_SEC:
                return False
        return True

    def _update_server_offset(self, symbol: str):
        """
        Estimate server timezone offset relative to UTC using the given symbol's tick time.
        Offset = ServerTime - UTC.
        """
        if self._server_offset_sec is not None and self._offset_updated_at is not None:
            # TTL内ならキャッシュ使用。TTL超過で再計算(古いoffsetの永続キャッシュ問題を回避)。
            if datetime.now(timezone.utc) - self._offset_updated_at < timedelta(seconds=self._offset_ttl_sec):
                return
            logger.info("Server timezone offset cache expired (TTL=%ds), recalculating...", int(self._offset_ttl_sec))

        # Ensure symbol is selected to get fresh tick
        if not mt5.symbol_select(symbol, True):
            logger.warning(f"Failed to select symbol {symbol} for offset calculation")

        tick = mt5.symbol_info_tick(symbol)
        server_ts = 0
        
        if tick is not None:
            server_ts = int(tick.time)
        else:
            logger.warning(f"Tick not available for {symbol}, trying last rate for offset")
            # Try to fetch just 1 bar of M1 to guess time
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1)
            if rates is not None and len(rates) > 0:
                server_ts = int(rates[0]['time'])
            else:
                logger.error(f"Could not determine server time for {symbol} (no tick, no rates)")
                return

        # Use simple utc timestamp
        utc_ts = datetime.now(timezone.utc).timestamp()
        
        diff = server_ts - utc_ts
        # Round to nearest 15 minutes (900s) to handle latency and candle close lag
        rounded_diff = int(round(diff / 900) * 900)

        # 市場クローズ中の誤推定を採用しないよう妥当性を検証する。
        # 棄却時は _offset_updated_at を更新しないため、次回呼び出しで再試行され、
        # 市場再開後は速やかに正しいオフセットへ復帰する。
        if not self._is_plausible_offset(rounded_diff):
            if self._server_offset_sec is None:
                logger.error(
                    f"Implausible server timezone offset {rounded_diff}s discarded "
                    f"(using {symbol}, raw_diff={diff:.1f}s); market may be closed. "
                    f"Time correction is disabled until a valid offset is obtained."
                )
            else:
                logger.warning(
                    f"Implausible server timezone offset {rounded_diff}s discarded "
                    f"(using {symbol}, raw_diff={diff:.1f}s); "
                    f"keeping previous offset {self._server_offset_sec}s."
                )
            return

        self._server_offset_sec = rounded_diff
        self._offset_updated_at = datetime.now(timezone.utc)
        logger.info(f"Server timezone offset estimated: {self._server_offset_sec}s (using {symbol}, raw_diff={diff:.1f}s)")

    def _apply_time_correction(self, ts: int) -> int:
        """Convert server timestamp to UTC if use_utc is True."""
        if not self.use_utc:
            return ts
        # If offset not yet calculated, we can't correct yet (or assume 0)
        # We rely on _update_server_offset being called before or during.
        return int(ts - (self._server_offset_sec or 0))

    def _apply_time_correction_msc(self, ts_msc: int) -> int:
        """
        ミリ秒精度のサーバータイムスタンプをUTCへ変換する。

        MT5が返す time_msc は time と同じくサーバー時間基準であるため、
        秒精度側と同一のオフセットをミリ秒スケールで適用しないと、
        time と time_msc の間にサーバーのタイムゾーン分のズレが生じてしまう。

        Args:
            ts_msc: サーバー時間基準のミリ秒タイムスタンプ

        Returns:
            UTC基準のミリ秒タイムスタンプ。use_utc=False の場合は入力をそのまま返す。
        """
        if not self.use_utc:
            return ts_msc
        # time_msc が未設定(0)のレコードは補正すると負値になるため対象外とする
        if ts_msc == 0:
            return 0
        return int(ts_msc - (self._server_offset_sec or 0) * 1000)

    def get_rates(self, symbol: str, timeframe_str: str, num_bars: int) -> Optional[List[Dict]]:
        """
        Get historical rates for a symbol.
        
        Args:
            symbol: Symbol name (e.g., "XAUUSD")
            timeframe_str: Timeframe string (e.g., "M1", "H1")
            num_bars: Number of bars to fetch
            
        Returns:
            List of dictionaries containing rate data, or None if failed.
        """
        if not self.connected:
            if not self.initialize():
                return None

        # Map timeframe string to MT5 constant
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": getattr(mt5, "TIMEFRAME_W1", None),
            "MN1": getattr(mt5, "TIMEFRAME_MN1", None),
        }
        
        mt5_tf = tf_map.get(timeframe_str)
        if mt5_tf is None:
            logger.error(f"Invalid timeframe: {timeframe_str}")
            return None

        # Copy rates from current time backwards
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, num_bars)
        
        if self.use_utc and self._server_offset_sec is None:
            self._update_server_offset(symbol)
        
        if rates is None:
            logger.error(f"Failed to get rates for {symbol}")
            return None
            
        # Convert to list of dicts (handling numpy types)
        # rates is a numpy record array
        result = []
        for rate in rates:
            result.append({
                "time": self._apply_time_correction(int(rate['time'])),
                "open": float(rate['open']),
                "high": float(rate['high']),
                "low": float(rate['low']),
                "close": float(rate['close']),
                "tick_volume": int(rate['tick_volume']),
                "spread": int(rate['spread']),
                "real_volume": int(rate['real_volume'])
            })
            
        return result

    def get_rates_range(self, symbol: str, timeframe_str: str, date_from: datetime, date_to: datetime) -> Optional[List[Dict]]:
        """
        Get historical rates for a symbol within a date range.
        
        Args:
            symbol: Symbol name
            timeframe_str: Timeframe string
            date_from: Start date (datetime)
            date_to: End date (datetime)
            
        Returns:
            List of dictionaries containing rate data.
        """
        if not self.connected:
            if not self.initialize():
                return None

        # Map timeframe string to MT5 constant
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": getattr(mt5, "TIMEFRAME_W1", None),
            "MN1": getattr(mt5, "TIMEFRAME_MN1", None),
        }
        
        mt5_tf = tf_map.get(timeframe_str)
        if mt5_tf is None:
            logger.error(f"Invalid timeframe: {timeframe_str}")
            return None

        # copy_rates_range はサーバー時間を受け取ることを期待するため、
        # UTC -> ServerTime の逆変換を適用する
        if self.use_utc and self._server_offset_sec is None:
            self._update_server_offset(symbol)
        
        offset = self._server_offset_sec or 0
        server_from = datetime.fromtimestamp(date_from.timestamp() + offset)
        server_to = datetime.fromtimestamp(date_to.timestamp() + offset)

        rates = mt5.copy_rates_range(symbol, mt5_tf, server_from, server_to)
        
        if rates is None:
            logger.error(f"Failed to get rates range for {symbol} ({mt5.last_error()})")
            return None
            
        result = []
        for rate in rates:
            result.append({
                "time": self._apply_time_correction(int(rate['time'])),
                "open": float(rate['open']),
                "high": float(rate['high']),
                "low": float(rate['low']),
                "close": float(rate['close']),
                "tick_volume": int(rate['tick_volume']),
                "spread": int(rate['spread']),
                "real_volume": int(rate['real_volume'])
            })
            
        return result

    def get_tick(self, symbol: str) -> Optional[Dict]:
        """
        Get latest tick data.
        """
        if not self.connected:
            if not self.initialize():
                return None
                
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Failed to get tick for {symbol}")
            return None
            
        if self.use_utc and self._server_offset_sec is None:
            self._update_server_offset(symbol)

        return {
            "time": self._apply_time_correction(int(tick.time)),
            "time_msc": self._apply_time_correction_msc(int(tick.time_msc)),
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "last": float(tick.last),
            "volume": int(tick.volume)
        }

    def get_ticks_from(
        self,
        symbol: str,
        date_from: datetime,
        count: int,
        flags: str = "ALL"
    ) -> Optional[List[Dict]]:
        """
        指定日時から指定件数の過去ティックデータを取得する。
        
        Args:
            symbol: シンボル名 (例: "XAUUSD")
            date_from: 開始日時 (datetime, UTC推奨)
            count: 取得するティック数
            flags: ティックの種類 ("ALL", "INFO", "TRADE")
                   - ALL: すべてのティック
                   - INFO: Bid/Ask変更のティック
                   - TRADE: Last/Volume変更のティック
            
        Returns:
            ティックデータの辞書リスト、またはエラー時None
        """
        if not self.connected:
            if not self.initialize():
                return None
        
        # フラグのマッピング
        flag_map = {
            "ALL": mt5.COPY_TICKS_ALL,
            "INFO": mt5.COPY_TICKS_INFO,
            "TRADE": mt5.COPY_TICKS_TRADE,
        }
        mt5_flags = flag_map.get(flags.upper(), mt5.COPY_TICKS_ALL)
        
        # UTC -> ServerTime の逆変換を適用
        if self.use_utc and self._server_offset_sec is None:
            self._update_server_offset(symbol)
        
        offset = self._server_offset_sec or 0
        server_from = datetime.fromtimestamp(date_from.timestamp() + offset)
        
        ticks = mt5.copy_ticks_from(symbol, server_from, count, mt5_flags)
        
        if ticks is None:
            logger.error(f"Failed to get ticks from {symbol}: {mt5.last_error()}")
            return None
        
        if len(ticks) == 0:
            logger.warning(f"No ticks returned for {symbol} from {date_from}")
            return []
        
        # numpy配列を辞書リストに変換
        result = []
        for tick in ticks:
            result.append({
                "time": self._apply_time_correction(int(tick['time'])),
                "time_msc": self._apply_time_correction_msc(int(tick['time_msc'])),  # ミリ秒精度のタイムスタンプ (UTC)
                "bid": float(tick['bid']),
                "ask": float(tick['ask']),
                "last": float(tick['last']),
                "volume": int(tick['volume']),
                "flags": int(tick['flags']),  # ティック変更フラグ
            })
        
        return result

    def get_ticks_range(
        self,
        symbol: str,
        date_from: datetime,
        date_to: datetime,
        flags: str = "ALL"
    ) -> Optional[List[Dict]]:
        """
        指定日時範囲の過去ティックデータを取得する。
        
        Args:
            symbol: シンボル名 (例: "XAUUSD")
            date_from: 開始日時 (datetime, UTC推奨)
            date_to: 終了日時 (datetime, UTC推奨)
            flags: ティックの種類 ("ALL", "INFO", "TRADE")
            
        Returns:
            ティックデータの辞書リスト、またはエラー時None
        """
        if not self.connected:
            if not self.initialize():
                return None
        
        # フラグのマッピング
        flag_map = {
            "ALL": mt5.COPY_TICKS_ALL,
            "INFO": mt5.COPY_TICKS_INFO,
            "TRADE": mt5.COPY_TICKS_TRADE,
        }
        mt5_flags = flag_map.get(flags.upper(), mt5.COPY_TICKS_ALL)
        
        # UTC -> ServerTime の逆変換を適用
        if self.use_utc and self._server_offset_sec is None:
            self._update_server_offset(symbol)
        
        offset = self._server_offset_sec or 0
        server_from = datetime.fromtimestamp(date_from.timestamp() + offset)
        server_to = datetime.fromtimestamp(date_to.timestamp() + offset)
        
        ticks = mt5.copy_ticks_range(symbol, server_from, server_to, mt5_flags)
        
        if ticks is None:
            logger.error(f"Failed to get ticks range for {symbol}: {mt5.last_error()}")
            return None
        
        if len(ticks) == 0:
            logger.warning(f"No ticks returned for {symbol} in range {date_from} to {date_to}")
            return []
        
        # numpy配列を辞書リストに変換
        result = []
        for tick in ticks:
            result.append({
                "time": self._apply_time_correction(int(tick['time'])),
                "time_msc": self._apply_time_correction_msc(int(tick['time_msc'])),  # ミリ秒精度のタイムスタンプ (UTC)
                "bid": float(tick['bid']),
                "ask": float(tick['ask']),
                "last": float(tick['last']),
                "volume": int(tick['volume']),
                "flags": int(tick['flags']),  # ティック変更フラグ
            })
        
        return result

    def get_account_info(self) -> Optional[Dict]:
        """
        Get account information (balance, equity, etc.).
        """
        if not self.connected:
            if not self.initialize():
                return None
                
        account_info = mt5.account_info()
        if account_info is None:
            logger.error(f"Failed to get account info: {mt5.last_error()}")
            return None
            
        return {
            "login": int(account_info.login),
            "balance": float(account_info.balance),
            "equity": float(account_info.equity),
            "margin": float(account_info.margin),
            "margin_free": float(account_info.margin_free),
            "margin_level": float(account_info.margin_level),
            "leverage": int(account_info.leverage),
            "currency": str(account_info.currency),
            "server": str(account_info.server)
        }

    def get_positions(
        self,
        symbols: Optional[List[str]] = None,
        magic: Optional[int] = None,
    ) -> Optional[List[Dict]]:
        """
        Get current open positions with optional filtering.
        
        Args:
            symbols: If provided, only return positions for these symbols.
            magic: If provided, only return positions with this magic number.
        
        Returns:
            List of position dictionaries, or None if failed.
        """
        if not self.connected:
            if not self.initialize():
                return None
                
        positions = mt5.positions_get()
        if positions is None:
            return []
            
        result = []
        for pos in positions:
            # magic number フィルタ
            pos_magic = int(getattr(pos, "magic", 0))
            if magic is not None and pos_magic != magic:
                continue
            
            # symbol フィルタ
            pos_symbol = pos.symbol
            if symbols is not None and pos_symbol not in symbols:
                continue
            
            result.append({
                "ticket": int(pos.ticket),
                "symbol": pos_symbol,
                "type": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": float(pos.volume),
                "price_open": float(pos.price_open),
                # deep-trader 側で「自分のポジだけ」を安全に識別するために必要
                "comment": str(getattr(pos, "comment", "")),
                "magic": pos_magic,
                "sl": float(pos.sl),
                "tp": float(pos.tp),
                "price_current": float(pos.price_current),
                "profit": float(pos.profit),
                "time": self._apply_time_correction(int(pos.time)),
                "time_msc": self._apply_time_correction_msc(int(getattr(pos, "time_msc", 0)))
            })
            
        return result

    def get_history_deals(
        self,
        position: Optional[int] = None,
        ticket: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Optional[List[Dict]]:
        """
        Get historical deals (completed transactions) with filters.
        """
        if not self.connected:
            if not self.initialize():
                return None

        # Determine timezone offset
        if self.use_utc and self._server_offset_sec is None:
            symbols = mt5.symbols_get()
            if symbols and len(symbols) > 0:
                self._update_server_offset(symbols[0].name)
            else:
                self._update_server_offset("XAUUSDz")

        if position is not None:
            deals = mt5.history_deals_get(position=position)
        elif ticket is not None:
            deals = mt5.history_deals_get(ticket=ticket)
        elif date_from is not None and date_to is not None:
            offset = self._server_offset_sec or 0
            server_from = datetime.fromtimestamp(date_from.timestamp() + offset, tz=timezone.utc)
            server_to = datetime.fromtimestamp(date_to.timestamp() + offset, tz=timezone.utc)
            deals = mt5.history_deals_get(server_from, server_to)
        else:
            # Default to last 24 hours
            import datetime as dt
            offset = self._server_offset_sec or 0
            now_ts = datetime.now(timezone.utc).timestamp()
            server_from = datetime.fromtimestamp(now_ts - 86400 + offset, tz=timezone.utc)
            server_to = datetime.fromtimestamp(now_ts + offset, tz=timezone.utc)
            deals = mt5.history_deals_get(server_from, server_to)

        if deals is None:
            logger.error(f"Failed to get history deals: {mt5.last_error()}")
            return None

        result = []
        for deal in deals:
            result.append({
                "ticket": int(deal.ticket),
                "order": int(deal.order),
                "time": self._apply_time_correction(int(deal.time)),
                "time_msc": self._apply_time_correction_msc(int(deal.time_msc)),
                "type": "BUY" if deal.type == 0 else "SELL" if deal.type == 1 else str(deal.type),
                "entry": "IN" if deal.entry == 0 else "OUT" if deal.entry == 1 else "INOUT" if deal.entry == 2 else str(deal.entry),
                "position_id": int(deal.position_id),
                "volume": float(deal.volume),
                "price": float(deal.price),
                "commission": float(deal.commission),
                "swap": float(deal.swap),
                "profit": float(deal.profit),
                "comment": str(getattr(deal, "comment", "")),
                "magic": int(deal.magic),
                "symbol": str(deal.symbol)
            })

        return result

    def send_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "",
        magic: int = 123456,
    ) -> tuple[Optional[int], Optional[str]]:
        """
        Send a market order.
        
        Args:
            symbol: Symbol to trade.
            order_type: "BUY" or "SELL".
            volume: Lot size.
            sl: Stop Loss price.
            tp: Take Profit price.
            comment: Order comment.
            
        Returns:
            Order ticket if successful, None otherwise.
        """
        if not self.connected:
            if not self.initialize():
                message = "MT5 に接続できませんでした"
                return None, message
                
        # Get current price for filling request
        tick = self.get_tick(symbol)
        if tick is None:
            message = f"{symbol} のティック情報を取得できません"
            logger.error(message)
            return None, message
            
        action = mt5.TRADE_ACTION_DEAL
        mt5_type = mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL
        price = tick['ask'] if order_type == "BUY" else tick['bid']
        
        base_request = {
            "action": action,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,  # Slippage tolerance
            "magic": magic,   # Magic number
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }

        # filling の切り替えは「filling 起因の失敗」のときだけ行う。
        # 例: Invalid stops(10016) は filling を変えても解決しないので、総当たりしない。
        invalid_fill_retcode = getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030)

        # まずはデフォルト（type_filling未指定）を試し、
        # 「Unsupported filling mode / Invalid filling」等の場合のみ filling を変えて再試行する。
        fillings = [
            None,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_RETURN,
        ]
        last_error: Optional[str] = None
        for filling in fillings:
            request = dict(base_request)
            if filling is not None:
                request["type_filling"] = filling
            filling_label = "default" if filling is None else str(filling)
            result = mt5.order_send(request)
            if result is None:
                # result=None は通信/端末側の問題の可能性が高く、filling を変えても改善しないことが多い
                error_code = mt5.last_error()
                last_error = f"order_send returned None with filling={filling_label} (error={error_code}). Request: {request}"
                logger.error(last_error)
                break
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Order sent successfully: {result.order} (filling={filling_label})")
                return result.order, None
            last_error = f"filling={filling_label} {result.retcode} で失敗: {result.comment}"
            logger.warning("Order send failed: %s", last_error)

            # filling 起因の失敗（Unsupported/Invalid filling）のときだけ次の filling を試す。
            # それ以外（例: Invalid stops）は即座に中断して返す。
            if int(result.retcode) == int(invalid_fill_retcode) or "filling" in str(result.comment).lower():
                continue
            break
        message = last_error or "すべての filling モードで発注に失敗しました"
        return None, message

    def close_position(self, ticket: int) -> tuple[bool, str]:
        """
        Close an existing position.
        Returns: (success, message)
        """
        if not self.connected:
            if not self.initialize():
                return False, "Failed to connect to MT5"
                
        # Get position details to know volume and symbol
        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            logger.error(f"Position {ticket} not found")
            return False, f"Position {ticket} not found"
            
        pos = positions[0]
        symbol = pos.symbol
        volume = pos.volume
        
        # Determine opposite type
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        
        # Get current price
        tick = self.get_tick(symbol)
        if tick is None:
            return False, f"Failed to get tick for {symbol}"
            
        price = tick['bid'] if order_type == mt5.ORDER_TYPE_SELL else tick['ask']
        
        base_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
        }

        # filling の切り替えは「filling 起因の失敗」のときだけ行う。
        invalid_fill_retcode = getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030)

        fillings = [
            None,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_RETURN,
        ]
        last_error: Optional[str] = None
        for filling in fillings:
            request = dict(base_request)
            if filling is not None:
                request["type_filling"] = filling
            filling_label = "default" if filling is None else str(filling)
            result = mt5.order_send(request)
            if result is None:
                error_code = mt5.last_error()
                last_error = f"order_send returned None with filling={filling_label} (error={error_code})"
                logger.error(last_error)
                continue
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info("Position %s closed successfully (filling=%s)", ticket, filling_label)
                return True, "Success"
            last_error = f"filling={filling_label} {result.retcode} で失敗: {result.comment}"
            logger.warning("Close position failed: %s", last_error)

            # filling 起因の失敗（Unsupported/Invalid filling）のときだけ次の filling を試す。
            # それ以外（例: Invalid stops）は即座に中断して返す。
            if int(result.retcode) == int(invalid_fill_retcode) or "filling" in str(result.comment).lower():
                continue
            break

        message = last_error or "Close position failed"
        return False, message

    def modify_position(self, ticket: int, sl: Optional[float], tp: Optional[float], update_sl: bool, update_tp: bool) -> tuple[bool, str]:
        """Adjust stop loss / take profit for an existing position."""

        if not update_sl and not update_tp:
            return False, "Nothing to update"

        if not self.connected:
            if not self.initialize():
                return False, "Failed to connect to MT5"

        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            logger.error(f"Position {ticket} not found")
            return False, f"Position {ticket} not found"

        pos = positions[0]
        symbol = pos.symbol
        action = getattr(mt5, "TRADE_ACTION_SLTP", None)
        if action is None:
            logger.error("MT5 does not support TRADE_ACTION_SLTP")
            return False, "TRADE_ACTION_SLTP not available"

        sl_value = float(pos.sl or 0.0)
        tp_value = float(pos.tp or 0.0)

        if update_sl:
            sl_value = 0.0 if sl is None else float(sl)

        if update_tp:
            tp_value = 0.0 if tp is None else float(tp)

        request = {
            "action": action,
            "position": ticket,
            "symbol": symbol,
            "sl": sl_value,
            "tp": tp_value,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error("Modify position failed: result is None")
            return False, "order_send returned None"

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            error_msg = f"{result.comment} ({result.retcode})"
            logger.error(f"Modify position failed: {error_msg}")
            return False, error_msg

        logger.info(f"Protection updated for ticket {ticket}")
        return True, "Success"

    def get_market_book(self, symbol: str) -> Optional[List[Dict]]:
        """
        Get market depth (Level 2) data for a symbol.
        Automatically handles subscription.
        """
        if not self.connected:
            if not self.initialize():
                return None

        # Ensure symbol is selected
        if not mt5.symbol_select(symbol, True):
            logger.error(f"Failed to select symbol {symbol}")
            return None

        # Subscribe to market book (must be done to use MarketBookGet)
        if not mt5.market_book_add(symbol):
            logger.error(f"Failed to subscribe to market book for {symbol}: {mt5.last_error()}")
            return None

        # Retrieve the book
        items = mt5.market_book_get(symbol)
        if items is None:
            # Note: Sometimes it returns None if the book is not yet populated
            return []

        result = []
        for item in items:
            result.append({
                "type": "BUY" if item.type == mt5.BOOK_TYPE_BUY else 
                        "SELL" if item.type == mt5.BOOK_TYPE_SELL else 
                        "BUY_LIMIT" if item.type == mt5.BOOK_TYPE_BUY_LIMIT else
                        "SELL_LIMIT" if item.type == mt5.BOOK_TYPE_SELL_LIMIT else "OTHER",
                "price": float(item.price),
                "volume": float(item.volume),
                #"volume_real": float(item.volume_real)
                "volume_dbl": float(item.volume_dbl)
            })
        
        return result

    def get_symbols(self) -> List[str]:
        """Get list of all available symbols in the terminal."""
        if not self.connected:
            self.initialize()
        
        symbols = mt5.symbols_get()
        if symbols is None:
            return []
        return [s.name for s in symbols]

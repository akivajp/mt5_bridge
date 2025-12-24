import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import logging
from typing import Optional, Dict, List, Union

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MT5Handler:
    def __init__(self):
        self.connected = False

    def initialize(self) -> bool:
        """
        Initialize connection to MetaTrader 5 terminal.
        """
        if not mt5.initialize():
            logger.error("initialize() failed, error code = %s", mt5.last_error())
            self.connected = False
            return False
        
        logger.info("MT5 initialized successfully")
        self.connected = True
        return True

    def shutdown(self):
        """
        Shutdown connection to MetaTrader 5.
        """
        mt5.shutdown()
        self.connected = False
        logger.info("MT5 connection shutdown")

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
        
        if rates is None:
            logger.error(f"Failed to get rates for {symbol}")
            return None
            
        # Convert to list of dicts (handling numpy types)
        # rates is a numpy record array
        result = []
        for rate in rates:
            result.append({
                "time": int(rate['time']),
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
            
        return {
            "time": int(tick.time),
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "last": float(tick.last),
            "volume": int(tick.volume)
        }

    def get_positions(self) -> Optional[List[Dict]]:
        """
        Get current open positions.
        """
        if not self.connected:
            if not self.initialize():
                return None
                
        positions = mt5.positions_get()
        if positions is None:
            return []
            
        result = []
        for pos in positions:
            result.append({
                "ticket": int(pos.ticket),
                "symbol": pos.symbol,
                "type": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": float(pos.volume),
                "price_open": float(pos.price_open),
                "sl": float(pos.sl),
                "tp": float(pos.tp),
                "price_current": float(pos.price_current),
                "profit": float(pos.profit),
                "time": int(pos.time)
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
        
        request = {
            "action": action,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20, # Slippage tolerance
            "magic": 123456, # Magic number
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result is None:
            message = "order_send の戻り値が None でした"
            logger.error(message)
            return None, message

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            message = f"{result.retcode} で失敗: {result.comment}"
            logger.error(f"Order send failed: {message}")
            return None, message
            
        logger.info(f"Order sent successfully: {result.order}")
        return result.order, None

    def close_position(self, ticket: int) -> (bool, str):
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
        
        request = {
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
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result is None:
            logger.error("Close position failed: result is None")
            return False, "Order send failed (result is None)"
            
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            error_msg = f"{result.comment} ({result.retcode})"
            logger.error(f"Close position failed: {error_msg}")
            return False, error_msg
            
        logger.info(f"Position {ticket} closed successfully")
        return True, "Success"

    def modify_position(self, ticket: int, sl: Optional[float], tp: Optional[float], update_sl: bool, update_tp: bool) -> (bool, str):
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

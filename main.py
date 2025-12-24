#!/usr/bin/env python3

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import argparse
import os
import sys

# Add project root to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mt5_bridge.mt5_handler import MT5Handler

app = FastAPI(title="MT5 Bridge API")
mt5_handler = MT5Handler()

class Rate(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    real_volume: int

class Tick(BaseModel):
    time: int
    bid: float
    ask: float
    last: float
    volume: int

class Position(BaseModel):
    ticket: int
    symbol: str
    type: str
    volume: float
    price_open: float
    sl: float
    tp: float
    price_current: float
    profit: float
    time: int

@app.on_event("startup")
async def startup_event():
    """Initialize MT5 connection on startup."""
    if not mt5_handler.initialize():
        print("WARNING: Failed to initialize MT5 on startup. Will retry on first request.")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown MT5 connection."""
    mt5_handler.shutdown()

@app.get("/health")
def health_check():
    return {"status": "ok", "mt5_connected": mt5_handler.connected}

@app.get("/rates/{symbol}", response_model=List[Rate])
def get_rates(
    symbol: str, 
    timeframe: str = Query(..., description="Timeframe (e.g., M1, H1)"), 
    count: int = Query(1000, description="Number of bars")
):
    rates = mt5_handler.get_rates(symbol, timeframe, count)
    if rates is None:
        raise HTTPException(status_code=500, detail=f"Failed to get rates for {symbol}")
    return rates

@app.get("/tick/{symbol}", response_model=Tick)
def get_tick(symbol: str):
    tick = mt5_handler.get_tick(symbol)
    if tick is None:
        raise HTTPException(status_code=500, detail=f"Failed to get tick for {symbol}")
    return tick

@app.get("/positions", response_model=List[Position])
def get_positions():
    positions = mt5_handler.get_positions()
    if positions is None:
        raise HTTPException(status_code=500, detail="Failed to get positions")
    return positions

class OrderRequest(BaseModel):
    symbol: str
    type: str # "BUY" or "SELL"
    volume: float
    sl: float = 0.0
    tp: float = 0.0
    comment: str = ""

class CloseRequest(BaseModel):
    ticket: int

class ModifyRequest(BaseModel):
    ticket: int
    sl: Optional[float] = None
    tp: Optional[float] = None
    update_sl: bool = False
    update_tp: bool = False

@app.post("/order")
def send_order(order: OrderRequest):
    ticket, error = mt5_handler.send_order(
        order.symbol, 
        order.type, 
        order.volume, 
        order.sl, 
        order.tp, 
        order.comment
    )
    if ticket is None:
        detail = error or "Failed to send order"
        raise HTTPException(status_code=500, detail=detail)
    return {"status": "ok", "ticket": ticket}

@app.post("/close")
def close_position(req: CloseRequest):
    success, message = mt5_handler.close_position(req.ticket)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to close position: {message}")
    return {"status": "ok"}

@app.post("/modify")
def modify_position(req: ModifyRequest):
    success, message = mt5_handler.modify_position(
        req.ticket,
        req.sl,
        req.tp,
        req.update_sl,
        req.update_tp,
    )
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to modify position: {message}")
    return {"status": "ok"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MT5 Bridge API server")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    args = parser.parse_args()

    # Parse CLI args for server host/port / サーバーのホストとポートをCLI引数から取得
    uvicorn.run(app, host=args.host, port=args.port)

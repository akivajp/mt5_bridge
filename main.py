from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
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

@app.post("/order")
def send_order(order: OrderRequest):
    ticket = mt5_handler.send_order(
        order.symbol, 
        order.type, 
        order.volume, 
        order.sl, 
        order.tp, 
        order.comment
    )
    if ticket is None:
        raise HTTPException(status_code=500, detail="Failed to send order")
    return {"status": "ok", "ticket": ticket}

@app.post("/close")
def close_position(req: CloseRequest):
    success = mt5_handler.close_position(req.ticket)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to close position")
    return {"status": "ok"}

if __name__ == "__main__":
    # Run the server
    # Host 0.0.0.0 allows access from other machines (e.g. Linux/WSL)
    uvicorn.run(app, host="0.0.0.0", port=8000)

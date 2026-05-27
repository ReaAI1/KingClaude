"""
Smoke-test: verify all core modules import cleanly.
Run with: python tests/check_imports.py
"""
import sys
import os

# Make sure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import INITIAL_CAPITAL, TRADING_PAIRS, WEB_PORT
from src.database import Database
from src.indicators import ema, rsi, adx
from src.ml_engine import MLEngine
from src.signals import generate_signal, Signal
from src.portfolio import Portfolio
from src.trader import TradingEngine
from src.web.server import app

print("All imports OK")
print(f"  Capital: ${INITIAL_CAPITAL:,.0f} | Pairs: {len(TRADING_PAIRS)} | Port: {WEB_PORT}")

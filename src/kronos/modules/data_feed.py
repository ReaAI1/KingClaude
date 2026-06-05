"""DATA — Market data feed module.

Fetches live prices every 5 s and refreshes OHLCV candles on schedule.
Publishes:
  prices.update   {coin: price, ...}
  candles.update  {coin: str, tf: str, bars: list}
  htf.update      {coin: str, tf: str, bars: list}
  chart.update    {bars: list}
"""
import time

from src import config as cfg
from src.api import get_prices, get_candles
from src.kronos.base import KronosModule
from src.kronos.bus import KronosEventBus


class DataFeed(KronosModule):
    PRICE_INTERVAL = 5      # seconds between price fetches
    CHART_INTERVAL = 300    # 5 min
    FULL_INTERVAL  = 900    # 15 min

    def __init__(self, bus: KronosEventBus):
        super().__init__("DATA", bus)
        self._last_full  = 0.0
        self._last_chart = 0.0

    def _run_loop(self):
        # Initial full load
        self._full_candle_refresh()

        while not self._stop_evt.is_set():
            try:
                # Prices — every 5 s
                prices = get_prices(cfg.HL_REST_URL)
                if prices:
                    self.publish("prices.update", prices)
                    self.heartbeat(
                        f"{len(prices)} prices — BTC ${prices.get('BTC', 0):,.0f}"
                    )

                # Candle refresh schedule
                now = time.time()
                if now - self._last_full > self.FULL_INTERVAL:
                    self._full_candle_refresh()
                elif now - self._last_chart > self.CHART_INTERVAL:
                    self._chart_refresh()

            except Exception as exc:
                self.set_error(str(exc))
                time.sleep(10)
                continue

            time.sleep(self.PRICE_INTERVAL)

    def _full_candle_refresh(self):
        for coin in cfg.TRADING_PAIRS:
            if self._stop_evt.is_set():
                return
            try:
                bars = get_candles(cfg.HL_REST_URL, coin, cfg.PRIMARY_TF, cfg.CANDLE_LOOKBACK)
                if bars:
                    self.publish("candles.update", {"coin": coin, "tf": cfg.PRIMARY_TF, "bars": bars})

                htf = get_candles(cfg.HL_REST_URL, coin, cfg.HTF_TF, cfg.HTF_LOOKBACK)
                if htf:
                    self.publish("htf.update", {"coin": coin, "tf": cfg.HTF_TF, "bars": htf})
            except Exception as exc:
                self.set_error(f"{coin}: {exc}")
            time.sleep(0.4)

        self._chart_refresh()
        self._last_full = time.time()
        self.heartbeat(f"Full candle refresh — {len(cfg.TRADING_PAIRS)} coins")

    def _chart_refresh(self):
        try:
            chart = get_candles(cfg.HL_REST_URL, cfg.CHART_COIN, cfg.CHART_TF, cfg.CHART_BARS)
            if chart:
                self.publish("chart.update", {"bars": chart})
        except Exception as exc:
            self.set_error(f"chart: {exc}")
        self._last_chart = time.time()

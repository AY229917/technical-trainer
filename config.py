"""初期値。画面の設定から上書きできる。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DB_PATH = DATA / "market.sqlite"
SETTINGS_PATH = DATA / "settings.json"
LOG_PATH = DATA / "app.log"

API_URL = "https://api.hyperliquid.xyz/info"


@dataclass
class Settings:
    save_top: int = 100
    show_top: int = 30
    volume_mult: float = 2.0
    rsi_period: int = 14
    rsi_low: float = 30.0
    rsi_high: float = 70.0
    rci_short: int = 9
    rci_mid: int = 26
    rci_long: int = 52
    rci_line: float = 80.0
    stoch_k: int = 14
    stoch_d: int = 3
    stoch_slow: int = 3
    stoch_low: float = 20.0
    stoch_high: float = 80.0
    adx_period: int = 14
    adx_line: float = 25.0
    bb_period: int = 20
    bb_mult: float = 2.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    ichi_tenkan: int = 9
    ichi_kijun: int = 26
    ichi_span: int = 52
    pivot_bars: int = 5
    price_pct: float = 3.0
    pole_bars: int = 10
    pole_pct: float = 8.0
    ma_short_d: int = 5
    ma_mid_d: int = 25
    ma_long_d: int = 75
    ma_short_w: int = 13
    ma_mid_w: int = 26
    ma_long_w: int = 52
    ma_short_m: int = 6
    ma_mid_m: int = 12
    ma_long_m: int = 36

    def ma_periods(self, timeframe: str) -> tuple[int, int, int]:
        if timeframe == "1w":
            return self.ma_short_w, self.ma_mid_w, self.ma_long_w
        if timeframe == "1M":
            return self.ma_short_m, self.ma_mid_m, self.ma_long_m
        return self.ma_short_d, self.ma_mid_d, self.ma_long_d


def load_settings() -> Settings:
    DATA.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        save_settings(Settings())
    raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    base = Settings()
    for key, value in raw.items():
        if hasattr(base, key):
            current = getattr(base, key)
            setattr(base, key, type(current)(value))
    base.save_top = min(200, max(30, int(base.save_top)))
    base.show_top = min(base.save_top, max(5, int(base.show_top)))
    return base


def save_settings(settings: Settings) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

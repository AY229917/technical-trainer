"""Hyperliquidの公開API。日足と出来高順位だけを取る。"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request

from config import API_URL

DAY_MS = 86_400_000


class RateLimiter:
    def __init__(self, per_minute: int = 1000) -> None:
        self.per_minute = per_minute
        self.events: list[tuple[float, int]] = []

    def take(self, weight: int) -> None:
        while True:
            now = time.time()
            self.events = [(t, w) for t, w in self.events if now - t < 60]
            used = sum(w for _, w in self.events)
            if used + weight <= self.per_minute:
                self.events.append((now, weight))
                return
            time.sleep(0.4)


LIMITER = RateLimiter()


def post_info(payload: dict, weight: int) -> object:
    body = json.dumps(payload).encode()
    last_error: Exception | None = None
    for attempt in range(4):
        LIMITER.take(weight)
        req = urllib.request.Request(
            API_URL, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as res:
                return json.loads(res.read().decode())
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Hyperliquidへの接続に失敗しました: {last_error}")


def fetch_ranking() -> list[tuple[str, float]]:
    data = post_info({"type": "metaAndAssetCtxs"}, weight=20)
    meta, ctxs = data
    rows: list[tuple[str, float]] = []
    for asset, ctx in zip(meta["universe"], ctxs):
        if asset.get("isDelisted"):
            continue
        name = str(asset["name"])
        if ":" in name:
            continue
        volume = float(ctx.get("dayNtlVlm") or 0)
        if volume <= 0:
            continue
        rows.append((name, volume))
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows


def fetch_daily(coin: str, start_ms: int) -> list[dict]:
    end_ms = int(time.time() * 1000)
    # 重量は返ってくる本数で増える。長い履歴は後から正確な重量を足す。
    LIMITER.take(20)
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": "1d",
            "startTime": start_ms,
            "endTime": end_ms,
        },
    }
    data = post_info(payload, weight=0)
    if not isinstance(data, list):
        return []
    extra = math.ceil(len(data) / 60) if data else 0
    if extra:
        LIMITER.take(extra)
    rows = []
    for candle in data:
        high = float(candle["h"])
        low = float(candle["l"])
        if high < low:
            continue
        rows.append(
            {
                "open_time": int(candle["t"]),
                "open": float(candle["o"]),
                "high": high,
                "low": low,
                "close": float(candle["c"]),
                "volume": float(candle["v"]),
            }
        )
    rows.sort(key=lambda row: row["open_time"])
    return rows

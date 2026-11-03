"""日足の集計、状態の文章、更新。"""

from __future__ import annotations

import threading
import traceback
from datetime import datetime, timedelta, timezone

from config import LOG_PATH, Settings, load_settings
from db import (
    DAY_MS,
    connect,
    init_db,
    insert_ranking,
    last_open_time,
    latest_ranking,
    load_candles,
    saved_coins,
    upsert_candles,
)
from hl import fetch_daily, fetch_ranking
from indicators import (
    cross_down,
    cross_up,
    dmi,
    donchian_mid,
    ema,
    rci,
    rsi,
    sma,
    stdev,
    stochastic,
)
from patterns import detect, fib_retracement

JST = timezone(timedelta(hours=9))
_lock = threading.Lock()
STATUS = {
    "running": False,
    "message": "まだ更新していません",
    "current": 0,
    "total": 0,
    "error": "",
    "finished_at": "",
}


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def closed_bars(rows: list[dict], now_ms: int | None = None) -> list[dict]:
    now_ms = now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    bars = []
    for row in rows:
        if row["open_time"] + DAY_MS > now_ms:
            continue
        if row["high"] < row["low"]:
            continue
        bars.append(
            {
                "time": int(row["open_time"] // 1000),
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
        )
    return bars


def _week_start(ts: int) -> int:
    dt = datetime.fromtimestamp(ts, timezone.utc)
    monday = dt - timedelta(days=dt.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(monday.timestamp())


def _month_start(ts: int) -> int:
    dt = datetime.fromtimestamp(ts, timezone.utc)
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp())


def _next_month(ts: int) -> int:
    dt = datetime.fromtimestamp(ts, timezone.utc)
    year = dt.year + (1 if dt.month == 12 else 0)
    month = 1 if dt.month == 12 else dt.month + 1
    return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())


def resample(daily: list[dict], timeframe: str) -> list[dict]:
    if timeframe == "1d":
        return daily
    groups: dict[int, list[dict]] = {}
    for bar in daily:
        key = _week_start(bar["time"]) if timeframe == "1w" else _month_start(bar["time"])
        groups.setdefault(key, []).append(bar)
    now = int(datetime.now(timezone.utc).timestamp())
    bars = []
    for key in sorted(groups):
        chunk = groups[key]
        complete_at = key + 7 * 86400 if timeframe == "1w" else _next_month(key)
        if complete_at > now:
            continue
        bars.append(
            {
                "time": key,
                "open": chunk[0]["open"],
                "high": max(item["high"] for item in chunk),
                "low": min(item["low"] for item in chunk),
                "close": chunk[-1]["close"],
                "volume": sum(item["volume"] for item in chunk),
            }
        )
    return bars


def _num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _price(value: float) -> str:
    abs_value = abs(value)
    digits = 2 if abs_value >= 100 else 4 if abs_value >= 1 else 6
    return f"{value:,.{digits}f}"


def _plot(times: list[int], values: list[float | None], step: int) -> list[dict]:
    points = []
    last_time = times[-1]
    for i, value in enumerate(values):
        if value is None:
            continue
        when = times[i] if i < len(times) else last_time + step * (i - len(times) + 1)
        points.append({"time": when, "value": value})
    return points


def _shift_plot(values: list[float | None], shift: int) -> list[float | None]:
    out: list[float | None] = [None] * (len(values) + max(shift, 0))
    for i, value in enumerate(values):
        j = i + shift
        if value is not None and 0 <= j < len(out):
            out[j] = value
    return out


def analyze(bars: list[dict], settings: Settings, timeframe: str) -> dict:
    if len(bars) < 2:
        return {"items": [], "badges": [], "overlays": {}, "panes": {}, "patterns": [], "markers": []}
    short_n, mid_n, long_n = settings.ma_periods(timeframe)
    closes = [bar["close"] for bar in bars]
    highs = [bar["high"] for bar in bars]
    lows = [bar["low"] for bar in bars]
    volumes = [bar["volume"] for bar in bars]
    times = [bar["time"] for bar in bars]
    step = times[-1] - times[-2] if len(times) > 1 else 86400
    last = len(bars) - 1
    prev = last - 1

    sma_s, sma_m, sma_l = sma(closes, short_n), sma(closes, mid_n), sma(closes, long_n)
    vol_ma = sma(volumes, mid_n)
    tenkan = donchian_mid(highs, lows, settings.ichi_tenkan)
    kijun = donchian_mid(highs, lows, settings.ichi_kijun)
    span_b_src = donchian_mid(highs, lows, settings.ichi_span)
    span_a_src: list[float | None] = [None] * len(bars)
    for i in range(len(bars)):
        if tenkan[i] is not None and kijun[i] is not None:
            span_a_src[i] = (tenkan[i] + kijun[i]) / 2
    shift = settings.ichi_kijun
    span_a = _shift_plot(span_a_src, shift)
    span_b = _shift_plot(span_b_src, shift)
    bb_mid = sma(closes, settings.bb_period)
    bb_sd = stdev(closes, settings.bb_period)
    bb_up2, bb_dn2, bb_up1, bb_dn1, bb_up3, bb_dn3 = [], [], [], [], [], []
    width = []
    for i in range(len(bars)):
        if bb_mid[i] is None or bb_sd[i] is None:
            for bucket in (bb_up2, bb_dn2, bb_up1, bb_dn1, bb_up3, bb_dn3, width):
                bucket.append(None)
            continue
        sd = bb_sd[i]
        mid = bb_mid[i]
        bb_up1.append(mid + sd)
        bb_dn1.append(mid - sd)
        bb_up2.append(mid + settings.bb_mult * sd)
        bb_dn2.append(mid - settings.bb_mult * sd)
        bb_up3.append(mid + 3 * sd)
        bb_dn3.append(mid - 3 * sd)
        width.append((bb_up2[-1] - bb_dn2[-1]) / mid if mid else None)

    ema_fast = ema(closes, settings.macd_fast)
    ema_slow = ema(closes, settings.macd_slow)
    macd_vals: list[float | None] = [None] * len(bars)
    for i in range(len(bars)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_vals[i] = ema_fast[i] - ema_slow[i]
    macd_filled = [value if value is not None else 0.0 for value in macd_vals]
    signal_raw = ema(macd_filled, settings.macd_signal)
    signal = [
        None if macd_vals[i] is None or signal_raw[i] is None else signal_raw[i]
        for i in range(len(bars))
    ]
    hist = [
        None if macd_vals[i] is None or signal[i] is None else macd_vals[i] - signal[i]
        for i in range(len(bars))
    ]
    rsi_vals = rsi(closes, settings.rsi_period)
    rci_s = rci(closes, settings.rci_short)
    rci_m = rci(closes, settings.rci_mid)
    rci_l = rci(closes, settings.rci_long)
    stoch_k, stoch_d = stochastic(highs, lows, closes, settings.stoch_k, settings.stoch_d, settings.stoch_slow)
    plus_di, minus_di, adx = dmi(highs, lows, closes, settings.adx_period)

    items: list[dict] = []
    markers: list[dict] = []

    def add(name: str, state: str, value: str, text: str, mark: bool = False) -> None:
        items.append({"name": name, "state": state, "value": value, "text": text})
        if mark and state in {"発生", "確定"}:
            markers.append(
                {
                    "time": times[last],
                    "position": "aboveBar" if "上" in text or "好転" in text else "belowBar",
                    "text": name,
                }
            )

    if sma_m[last] is None:
        add("移動平均", "本数不足", "—", f"中期線には{mid_n}本必要です")
    else:
        side = "上" if closes[last] > sma_m[last] else "下"
        add("移動平均", "点灯", _price(sma_m[last]), f"終値が{mid_n}本線の{side}")
        if sma_s[prev] is not None and sma_s[last] is not None and sma_m[prev] is not None:
            if cross_up(sma_s[prev], sma_m[prev], sma_s[last], sma_m[last]):
                add("移動平均 短期と中期", "発生", _price(sma_s[last]), "短期が中期を上抜け", True)
            elif cross_down(sma_s[prev], sma_m[prev], sma_s[last], sma_m[last]):
                add("移動平均 短期と中期", "発生", _price(sma_s[last]), "短期が中期を下抜け", True)
        if sma_l[prev] is not None and sma_m[prev] is not None and sma_l[last] is not None:
            if cross_up(sma_m[prev], sma_l[prev], sma_m[last], sma_l[last]):
                add("移動平均 中期と長期", "発生", _price(sma_m[last]), "中期が長期を上抜け", True)
            elif cross_down(sma_m[prev], sma_l[prev], sma_m[last], sma_l[last]):
                add("移動平均 中期と長期", "発生", _price(sma_m[last]), "中期が長期を下抜け", True)

    if vol_ma[last] in (None, 0):
        add("出来高", "本数不足", "—", f"平均には{mid_n}本必要です")
    else:
        ratio = volumes[last] / vol_ma[last]
        if ratio >= settings.volume_mult:
            add("出来高", "点灯", f"{ratio:.2f}倍", "出来高急増")
        else:
            add("出来高", "数値のみ", f"{ratio:.2f}倍", "平均に対する倍率")

    if None in (tenkan[last], kijun[last]) or last < shift or span_a[last] is None or span_b[last] is None:
        add("一目均衡表", "本数不足", "—", "三役の判定に必要な本数が足りません")
    else:
        cloud_top = max(span_a[last], span_b[last])
        cloud_bottom = min(span_a[last], span_b[last])
        above_cloud = closes[last] > cloud_top
        below_cloud = closes[last] < cloud_bottom
        bull = tenkan[last] > kijun[last] and above_cloud and closes[last] > closes[last - shift]
        bear = tenkan[last] < kijun[last] and below_cloud and closes[last] < closes[last - shift]
        if bull:
            add("一目均衡表", "点灯", _price(kijun[last]), "三役好転", True)
        elif bear:
            add("一目均衡表", "点灯", _price(kijun[last]), "三役逆転", True)
        else:
            parts = []
            if tenkan[last] > kijun[last]:
                parts.append("転換線が基準線の上")
            elif tenkan[last] < kijun[last]:
                parts.append("転換線が基準線の下")
            if above_cloud:
                parts.append("終値が雲の上")
            elif below_cloud:
                parts.append("終値が雲の下")
            else:
                parts.append("終値が雲の中")
            add("一目均衡表", "数値のみ", "、".join(parts), "三役は揃っていません")

    if bb_up2[last] is None:
        add("ボリンジャーバンド", "本数不足", "—", f"{settings.bb_period}本必要です")
    else:
        if closes[last] > bb_up2[last]:
            add("ボリンジャーバンド", "点灯", _price(bb_up2[last]), "上方への行き過ぎ")
        elif closes[last] < bb_dn2[last]:
            add("ボリンジャーバンド", "点灯", _price(bb_dn2[last]), "下方への行き過ぎ")
        else:
            add("ボリンジャーバンド", "数値のみ", _price(bb_mid[last]), "±2σの内側")
        ready = [value for value in width[max(0, last - 120) : last] if value is not None]
        if ready and width[prev] is not None and width[last] is not None:
            if width[prev] <= min(ready) and width[last] > width[prev]:
                add("ボリンジャーバンド", "点灯", _num(width[last] * 100), "収縮のあとの拡大")

    if macd_vals[last] is None or signal[last] is None or macd_vals[prev] is None or signal[prev] is None:
        add("MACD", "本数不足", "—", "12、26、9の計算に必要な本数が足りません")
    else:
        zero = "ゼロより上" if macd_vals[last] > 0 else "ゼロより下"
        add("MACD", "数値のみ", _num(macd_vals[last], 4), zero)
        if cross_up(macd_vals[prev], signal[prev], macd_vals[last], signal[last]):
            add("MACD", "発生", _num(macd_vals[last], 4), "MACDがシグナルを上抜け", True)
        elif cross_down(macd_vals[prev], signal[prev], macd_vals[last], signal[last]):
            add("MACD", "発生", _num(macd_vals[last], 4), "MACDがシグナルを下抜け", True)

    if rsi_vals[last] is None or rsi_vals[prev] is None:
        add("RSI", "本数不足", "—", f"{settings.rsi_period}本必要です")
    else:
        if rsi_vals[last] <= settings.rsi_low and rsi_vals[last] > rsi_vals[prev]:
            add("RSI", "点灯", _num(rsi_vals[last]), "売られ過ぎ圏からの回復")
        elif rsi_vals[last] >= settings.rsi_high and rsi_vals[last] < rsi_vals[prev]:
            add("RSI", "点灯", _num(rsi_vals[last]), "買われ過ぎ圏からの反落")
        else:
            add("RSI", "数値のみ", _num(rsi_vals[last]), f"{settings.rsi_period}本")

    if rci_s[last] is None or rci_s[prev] is None:
        add("RCI", "本数不足", "—", f"短期には{settings.rci_short}本必要です")
    else:
        line = settings.rci_line
        if rci_s[prev] <= -line and rci_s[last] > rci_s[prev]:
            add("RCI", "点灯", _num(rci_s[last]), "短期が売られ過ぎ圏から上向き。反発候補")
        elif rci_s[prev] >= line and rci_s[last] < rci_s[prev]:
            add("RCI", "点灯", _num(rci_s[last]), "短期が買われ過ぎ圏から下向き。反落候補")
        else:
            add("RCI", "数値のみ", _num(rci_s[last]), "短期")
        if rci_m[last] is not None and rci_l[last] is not None and rci_m[prev] is not None and rci_l[prev] is not None:
            if rci_m[last] > rci_m[prev] and rci_l[last] > rci_l[prev]:
                add("RCI 中期と長期", "数値のみ", _num(rci_m[last]), "中期と長期が上向き")
            elif rci_m[last] < rci_m[prev] and rci_l[last] < rci_l[prev]:
                add("RCI 中期と長期", "数値のみ", _num(rci_m[last]), "中期と長期が下向き")

    if stoch_k[last] is None or stoch_d[last] is None or stoch_k[prev] is None or stoch_d[prev] is None:
        add("ストキャスティクス", "本数不足", "—", "14、3、3の計算に必要な本数が足りません")
    else:
        low_zone = stoch_k[last] < settings.stoch_low and stoch_d[last] < settings.stoch_low
        high_zone = stoch_k[last] > settings.stoch_high and stoch_d[last] > settings.stoch_high
        if low_zone and cross_up(stoch_k[prev], stoch_d[prev], stoch_k[last], stoch_d[last]):
            add("ストキャスティクス", "点灯", _num(stoch_k[last]), "売られ過ぎ圏からの上抜け")
        elif high_zone and cross_down(stoch_k[prev], stoch_d[prev], stoch_k[last], stoch_d[last]):
            add("ストキャスティクス", "点灯", _num(stoch_k[last]), "買われ過ぎ圏からの下抜け")
        else:
            add("ストキャスティクス", "数値のみ", _num(stoch_k[last]), "%K")

    if adx[last] is None or plus_di[last] is None or minus_di[last] is None:
        add("DMI / ADX", "本数不足", "—", f"{settings.adx_period}本必要です")
    elif adx[last] >= settings.adx_line:
        way = "上昇方向" if plus_di[last] > minus_di[last] else "下降方向"
        add("DMI / ADX", "点灯", _num(adx[last]), f"トレンドあり。{way}")
    else:
        add("DMI / ADX", "数値のみ", _num(adx[last]), "トレンドなし")

    if sma_m[last] not in (None, 0):
        gap = (closes[last] - sma_m[last]) / sma_m[last] * 100
        add("移動平均乖離率", "数値のみ", f"{gap:+.2f}%", f"{mid_n}本線からの乖離")
    else:
        add("移動平均乖離率", "本数不足", "—", f"{mid_n}本必要です")

    pattern_hits = detect(bars, settings)
    fib = fib_retracement(bars, settings)
    if fib:
        pattern_hits.append(fib)
    for hit in pattern_hits:
        add(hit["name"], hit["state"], hit.get("value", "—"), hit["text"], mark=hit["state"] == "確定")

    badges = [item["text"] for item in items if item["state"] in {"点灯", "発生", "確定"}]

    def series(values: list[float | None]) -> list[dict]:
        return [{"time": times[i], "value": value} for i, value in enumerate(values) if value is not None]

    cloud_a = _shift_plot(span_a_src, shift)
    cloud_b = _shift_plot(span_b_src, shift)
    overlays = {
        "sma_short": series(sma_s),
        "sma_mid": series(sma_m),
        "sma_long": series(sma_l),
        "bb_mid": series(bb_mid),
        "bb_up1": series(bb_up1),
        "bb_dn1": series(bb_dn1),
        "bb_up2": series(bb_up2),
        "bb_dn2": series(bb_dn2),
        "bb_up3": series(bb_up3),
        "bb_dn3": series(bb_dn3),
        "tenkan": series(tenkan),
        "kijun": series(kijun),
        "span_a": _plot(times, cloud_a, step),
        "span_b": _plot(times, cloud_b, step),
        "chikou": [
            {"time": times[i - shift], "value": closes[i]}
            for i in range(shift, len(bars))
        ],
    }
    panes = {
        "macd": series(macd_vals),
        "signal": series(signal),
        "hist": [
            {"time": times[i], "value": value, "color": "#3ddc97" if value >= 0 else "#ff5d73"}
            for i, value in enumerate(hist)
            if value is not None
        ],
        "rsi": series(rsi_vals),
        "rci_short": series(rci_s),
        "rci_mid": series(rci_m),
        "rci_long": series(rci_l),
        "stoch_k": series(stoch_k),
        "stoch_d": series(stoch_d),
        "adx": series(adx),
        "plus_di": series(plus_di),
        "minus_di": series(minus_di),
    }
    return {
        "items": items,
        "badges": badges,
        "overlays": overlays,
        "panes": panes,
        "patterns": [
            {key: hit[key] for key in ("name", "state", "text", "lines", "color", "span") if key in hit}
            for hit in pattern_hits
        ],
        "markers": markers[-12:],
        "periods": {"short": short_n, "mid": mid_n, "long": long_n},
    }


def coin_payload(coin: str, timeframe: str, rank: int | None, volume_24h: float | None, recorded_at: str | None) -> dict:
    settings = load_settings()
    with connect() as conn:
        rows = load_candles(conn, coin)
    daily = closed_bars(rows)
    bars = resample(daily, timeframe)
    result = analyze(bars, settings, timeframe)
    judged = datetime.fromtimestamp(bars[-1]["time"], timezone.utc).strftime("%Y-%m-%d") if bars else ""
    return {
        "coin": coin,
        "timeframe": timeframe,
        "rank": rank,
        "volume_24h": volume_24h,
        "recorded_at": recorded_at,
        "judged_on": judged,
        "candles": bars,
        **result,
    }


def ranking_payload() -> dict:
    settings = load_settings()
    with connect() as conn:
        recorded, rows = latest_ranking(conn, settings.show_top)
        stored = {row["coin"]: load_candles(conn, row["coin"]) for row in rows} if recorded else {}
    if not recorded:
        return {"recorded_at": None, "items": [], "status": dict(STATUS)}
    items = []
    for row in rows:
        daily = closed_bars(stored[row["coin"]])
        badges = analyze(daily, settings, "1d")["badges"] if len(daily) >= 2 else []
        items.append({**row, "badges": badges[:8], "badge_count": len(badges)})
    return {"recorded_at": recorded, "items": items, "status": dict(STATUS)}


def _set_status(**kwargs) -> None:
    with _lock:
        STATUS.update(kwargs)


def update_market() -> None:
    _set_status(running=True, message="出来高順位を取得しています", current=0, total=0, error="")
    try:
        init_db()
        settings = load_settings()
        ranked = fetch_ranking()
        top = ranked[: settings.save_top]
        recorded_at = datetime.now(timezone.utc).isoformat()
        with connect() as conn:
            insert_ranking(
                conn,
                recorded_at,
                [(coin, index + 1, volume) for index, (coin, volume) in enumerate(top)],
            )
            known = saved_coins(conn)
        targets = []
        seen = set()
        for coin, _volume in top:
            if coin not in seen:
                targets.append(coin)
                seen.add(coin)
        for coin in known:
            if coin not in seen:
                targets.append(coin)
                seen.add(coin)
        _set_status(total=len(targets), message="日足を保存しています")
        failures = []
        for index, coin in enumerate(targets, start=1):
            _set_status(current=index, message=f"{coin} の日足を保存しています")
            try:
                with connect() as conn:
                    last = last_open_time(conn, coin)
                start = 0 if last is None else max(0, last - 5 * DAY_MS)
                rows = fetch_daily(coin, start)
                with connect() as conn:
                    upsert_candles(conn, coin, rows)
            except Exception as exc:  # noqa: BLE001
                failures.append(coin)
                log(f"{coin} の取得に失敗: {exc}")
        message = "更新しました"
        if failures:
            message = f"更新しました。失敗 {len(failures)} 銘柄: {', '.join(failures[:8])}"
        _set_status(
            running=False,
            message=message,
            finished_at=datetime.now(JST).isoformat(timespec="minutes"),
            error="",
        )
        log(message)
    except Exception as exc:  # noqa: BLE001
        log(traceback.format_exc())
        _set_status(running=False, message="更新に失敗しました", error=str(exc))


def start_update() -> bool:
    with _lock:
        if STATUS["running"]:
            return False
        STATUS["running"] = True
        STATUS["message"] = "開始しています"
        STATUS["error"] = ""
    threading.Thread(target=update_market, daemon=True).start()
    return True

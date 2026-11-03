"""確定足のテクニカル計算。"""

from __future__ import annotations

import math


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        return out
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period or period <= 0:
        return out
    k = 2 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def stdev(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = sum(window) / period
        var = sum((v - mean) ** 2 for v in window) / period
        out[i] = math.sqrt(var)
    return out


def wilder(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period or period <= 0:
        return out
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def rsi(closes: list[float], period: int) -> list[float | None]:
    gains = [0.0] * len(closes)
    losses = [0.0] * len(closes)
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains[i] = max(change, 0.0)
        losses[i] = max(-change, 0.0)
    avg_gain = wilder(gains[1:], period)
    avg_loss = wilder(losses[1:], period)
    out: list[float | None] = [None] * len(closes)
    for i in range(period, len(closes)):
        gain = avg_gain[i - 1]
        loss = avg_loss[i - 1]
        if gain is None or loss is None:
            continue
        if loss == 0:
            out[i] = 100.0
        else:
            rs = gain / loss
            out[i] = 100 - (100 / (1 + rs))
    return out


def _average_ranks(values: list[float], higher_is_first: bool) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=higher_is_first)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = rank
        i = j + 1
    return ranks


def rci(closes: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    denom = period * (period * period - 1)
    if denom <= 0:
        return out
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        price_rank = _average_ranks(window, higher_is_first=True)
        diff_sq = 0.0
        for age, rank in enumerate(price_rank):
            time_rank = period - age
            diff_sq += (time_rank - rank) ** 2
        out[i] = (1 - 6 * diff_sq / denom) * 100
    return out


def stochastic(
    highs: list[float], lows: list[float], closes: list[float], k_period: int, d_period: int, slow: int
) -> tuple[list[float | None], list[float | None]]:
    raw: list[float | None] = [None] * len(closes)
    for i in range(k_period - 1, len(closes)):
        hh = max(highs[i - k_period + 1 : i + 1])
        ll = min(lows[i - k_period + 1 : i + 1])
        if hh == ll:
            raw[i] = 50.0
        else:
            raw[i] = (closes[i] - ll) / (hh - ll) * 100
    filled = [value if value is not None else 0.0 for value in raw]
    slow_k_raw = sma(filled, slow)
    slow_k: list[float | None] = [
        None if raw[i] is None or slow_k_raw[i] is None else slow_k_raw[i] for i in range(len(raw))
    ]
    d_filled = [value if value is not None else 0.0 for value in slow_k]
    d_raw = sma(d_filled, d_period)
    d_line: list[float | None] = [
        None if slow_k[i] is None or d_raw[i] is None else d_raw[i] for i in range(len(slow_k))
    ]
    return slow_k, d_line


def dmi(
    highs: list[float], lows: list[float], closes: list[float], period: int
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    size = len(closes)
    tr = [0.0] * size
    plus_dm = [0.0] * size
    minus_dm = [0.0] * size
    for i in range(1, size):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    smooth_tr = wilder(tr[1:], period)
    smooth_plus = wilder(plus_dm[1:], period)
    smooth_minus = wilder(minus_dm[1:], period)
    plus_di: list[float | None] = [None] * size
    minus_di: list[float | None] = [None] * size
    dx: list[float] = [0.0] * size
    dx_ready = [False] * size
    for i in range(period, size):
        tr_v = smooth_tr[i - 1]
        p_v = smooth_plus[i - 1]
        m_v = smooth_minus[i - 1]
        if tr_v in (None, 0) or p_v is None or m_v is None:
            continue
        plus_di[i] = 100 * p_v / tr_v
        minus_di[i] = 100 * m_v / tr_v
        denom = plus_di[i] + minus_di[i]
        if denom:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / denom
            dx_ready[i] = True
    adx: list[float | None] = [None] * size
    start = None
    for i in range(size):
        if dx_ready[i]:
            start = i
            break
    if start is None or start + period > size:
        return plus_di, minus_di, adx
    seed_at = start + period - 1
    if seed_at >= size:
        return plus_di, minus_di, adx
    prev = sum(dx[start : seed_at + 1]) / period
    adx[seed_at] = prev
    for i in range(seed_at + 1, size):
        prev = (prev * (period - 1) + dx[i]) / period
        adx[i] = prev
    return plus_di, minus_di, adx


def donchian_mid(highs: list[float], lows: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(highs)
    for i in range(period - 1, len(highs)):
        out[i] = (max(highs[i - period + 1 : i + 1]) + min(lows[i - period + 1 : i + 1])) / 2
    return out


def cross_up(prev_a: float, prev_b: float, a: float, b: float) -> bool:
    return prev_a <= prev_b and a > b


def cross_down(prev_a: float, prev_b: float, a: float, b: float) -> bool:
    return prev_a >= prev_b and a < b

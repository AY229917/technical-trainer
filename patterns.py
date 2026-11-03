"""山と谷から、直近のチャートパターンを探す。"""

from __future__ import annotations

from config import Settings


def pivots(highs: list[float], lows: list[float], wing: int) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    ph: list[tuple[int, float]] = []
    pl: list[tuple[int, float]] = []
    for i in range(wing, len(highs) - wing):
        if highs[i] == max(highs[i - wing : i + wing + 1]) and highs[i] > max(highs[i - wing : i] + highs[i + 1 : i + wing + 1]):
            ph.append((i, highs[i]))
        if lows[i] == min(lows[i - wing : i + wing + 1]) and lows[i] < min(lows[i - wing : i] + lows[i + 1 : i + wing + 1]):
            pl.append((i, lows[i]))
    return ph, pl


def _near(a: float, b: float, pct: float) -> bool:
    base = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / base * 100 <= pct


def _between(points: list[tuple[int, float]], left: int, right: int) -> list[tuple[int, float]]:
    return [point for point in points if left < point[0] < right]


def _slope(p1: tuple[int, float], p2: tuple[int, float]) -> float:
    gap = p2[0] - p1[0]
    if gap == 0:
        return 0.0
    return (p2[1] - p1[1]) / gap


def _line_at(p1: tuple[int, float], p2: tuple[int, float], index: int) -> float:
    return p1[1] + _slope(p1, p2) * (index - p1[0])


def _last_close_break(closes: list[float], start: int, level_fn, up: bool) -> tuple[str, int] | None:
    """start の次の足から、終値が境界の外に出たか、否定されたかを見る。"""
    for i in range(start + 1, len(closes)):
        level = level_fn(i)
        if up and closes[i] > level:
            return "確定", i
        if not up and closes[i] < level:
            return "確定", i
    return None


# 同じ区間に似た形が重なったとき、より条件の多い型を残す。
_GROUPS = {
    "ダブルボトム": ("底", 1),
    "トリプルボトム": ("底", 2),
    "逆ヘッド＆ショルダー": ("底", 3),
    "ダブルトップ": ("天井", 1),
    "トリプルトップ": ("天井", 2),
    "ヘッド＆ショルダー": ("天井", 3),
    "上昇フラッグ": ("保ち合い", 1),
    "下降フラッグ": ("保ち合い", 1),
    "上昇レクタングル": ("保ち合い", 1),
    "下降レクタングル": ("保ち合い", 1),
    "上昇ペナント": ("保ち合い", 2),
    "下降ペナント": ("保ち合い", 2),
    "上昇三角保ち合い": ("保ち合い", 2),
    "下降三角保ち合い": ("保ち合い", 2),
    "上昇ウェッジ": ("保ち合い", 3),
    "下降ウェッジ": ("保ち合い", 3),
}


def detect(bars: list[dict], settings: Settings) -> list[dict]:
    if len(bars) < settings.pivot_bars * 2 + 10:
        return []
    highs = [bar["high"] for bar in bars]
    lows = [bar["low"] for bar in bars]
    closes = [bar["close"] for bar in bars]
    times = [bar["time"] for bar in bars]
    ph, pl = pivots(highs, lows, settings.pivot_bars)
    window = 180
    ph = [point for point in ph if point[0] >= len(bars) - window]
    pl = [point for point in pl if point[0] >= len(bars) - window]
    found: list[dict] = []
    found.extend(_doubles(pl, ph, closes, times, settings, bottom=True))
    found.extend(_doubles(ph, pl, closes, times, settings, bottom=False))
    found.extend(_triples(pl, ph, closes, times, settings, bottom=True))
    found.extend(_triples(ph, pl, closes, times, settings, bottom=False))
    found.extend(_head_shoulders(ph, pl, closes, times, settings, inverse=False))
    found.extend(_head_shoulders(pl, ph, closes, times, settings, inverse=True))
    found.extend(_channels(ph, pl, closes, times, highs, lows, settings))
    found.extend(_flags(bars, settings))
    found = _keep_distinct(found)
    found.sort(key=lambda item: item["at"], reverse=True)
    active = [item for item in found if item["state"] == "形成中"][:1]
    confirmed = [item for item in found if item["state"] == "確定"][:3]
    return active + confirmed


def _keep_distinct(found: list[dict]) -> list[dict]:
    ranked = sorted(
        found,
        key=lambda item: (_GROUPS.get(item["name"], ("", 0))[1], item["at"]),
        reverse=True,
    )
    kept: list[dict] = []
    for item in ranked:
        if any(_same_span(item, other) for other in kept):
            continue
        kept.append(item)
    return kept


def _same_span(left: dict, right: dict) -> bool:
    group_left = _GROUPS.get(left["name"])
    group_right = _GROUPS.get(right["name"])
    if not group_left or not group_right or group_left[0] != group_right[0]:
        return False
    start = max(left["start"], right["start"])
    end = min(left["end"], right["end"])
    if end < start:
        return False
    shorter = max(1, min(left["end"] - left["start"], right["end"] - right["start"]))
    return end - start >= shorter * 0.5


def _pack(name: str, state: str, text: str, at: int, lines: list[list[tuple[int, float]]], times: list[int]) -> dict:
    drawn = []
    indexes: list[int] = []
    for line in lines:
        points = []
        for index, price in line:
            indexes.append(index)
            if 0 <= index < len(times):
                points.append({"time": times[index], "value": price})
        drawn.append({"points": points})
    start = min(indexes) if indexes else at
    end = max(indexes) if indexes else at
    return {
        "name": name,
        "state": state,
        "text": text,
        "at": at,
        "start": start,
        "end": max(end, at),
        "lines": drawn,
    }


def _doubles(main, other, closes, times, settings: Settings, bottom: bool) -> list[dict]:
    name = "ダブルボトム" if bottom else "ダブルトップ"
    out = []
    for right in range(len(main) - 1, 0, -1):
        i2, p2 = main[right]
        for left in range(right - 1, -1, -1):
            i1, p1 = main[left]
            gap = i2 - i1
            if gap < 5:
                continue
            if gap > 60:
                break
            if not _near(p1, p2, settings.price_pct):
                continue
            mids = _between(other, i1, i2)
            if not mids:
                continue
            neck = max(mids, key=lambda point: point[1]) if bottom else min(mids, key=lambda point: point[1])
            extreme = min(p1, p2) if bottom else max(p1, p2)
            state = "形成中"
            at = i2
            failed = False
            for i in range(i2 + 1, len(closes)):
                if bottom and closes[i] < extreme:
                    failed = True
                    break
                if not bottom and closes[i] > extreme:
                    failed = True
                    break
                if bottom and closes[i] > neck[1]:
                    state, at = "確定", i
                    break
                if not bottom and closes[i] < neck[1]:
                    state, at = "確定", i
                    break
            if failed:
                continue
            if state == "形成中" and i2 < len(closes) - 40:
                continue
            verb = "上抜け" if bottom else "下抜け"
            text = f"境界を終値で{verb}" if state == "確定" else "形はある。終値はまだ境界の内側"
            out.append(
                _pack(
                    name,
                    state,
                    text,
                    at,
                    [[(i1, p1), (i2, p2)], [(i1, neck[1]), (max(at, i2), neck[1])]],
                    times,
                )
            )
            return out
    return out


def _triples(main, other, closes, times, settings: Settings, bottom: bool) -> list[dict]:
    name = "トリプルボトム" if bottom else "トリプルトップ"
    out = []
    for k in range(len(main) - 1, 1, -1):
        i3, p3 = main[k]
        for j in range(k - 1, 0, -1):
            i2, p2 = main[j]
            if i3 - i2 > 80:
                break
            for i in range(j - 1, -1, -1):
                i1, p1 = main[i]
                if i3 - i1 > 120:
                    break
                if i2 - i1 < 5 or i3 - i2 < 5:
                    continue
                if not (_near(p1, p2, settings.price_pct) and _near(p2, p3, settings.price_pct)):
                    continue
                left_mids = _between(other, i1, i2)
                right_mids = _between(other, i2, i3)
                if not left_mids or not right_mids:
                    continue
                if bottom:
                    neck = max(left_mids + right_mids, key=lambda point: point[1])[1]
                    extreme = min(p1, p2, p3)
                else:
                    neck = min(left_mids + right_mids, key=lambda point: point[1])[1]
                    extreme = max(p1, p2, p3)
                state, at = "形成中", i3
                failed = False
                for idx in range(i3 + 1, len(closes)):
                    if bottom and closes[idx] < extreme:
                        failed = True
                        break
                    if not bottom and closes[idx] > extreme:
                        failed = True
                        break
                    if bottom and closes[idx] > neck:
                        state, at = "確定", idx
                        break
                    if not bottom and closes[idx] < neck:
                        state, at = "確定", idx
                        break
                if failed or (state == "形成中" and i3 < len(closes) - 40):
                    continue
                verb = "上抜け" if bottom else "下抜け"
                text = f"境界を終値で{verb}" if state == "確定" else "3つの点がそろっている。終値はまだ境界の内側"
                out.append(
                    _pack(
                        name,
                        state,
                        text,
                        at,
                        [[(i1, p1), (i3, p3)], [(i1, neck), (max(at, i3), neck)]],
                        times,
                    )
                )
                return out
    return out


def _head_shoulders(peaks, troughs, closes, times, settings: Settings, inverse: bool) -> list[dict]:
    name = "逆ヘッド＆ショルダー" if inverse else "ヘッド＆ショルダー"
    out = []
    for mid in range(len(peaks) - 2, 0, -1):
        left, head, right = peaks[mid - 1], peaks[mid], peaks[mid + 1]
        if inverse:
            if not (head[1] < left[1] and head[1] < right[1]):
                continue
        elif not (head[1] > left[1] and head[1] > right[1]):
            continue
        if not _near(left[1], right[1], settings.price_pct):
            continue
        left_gap = head[0] - left[0]
        right_gap = right[0] - head[0]
        if min(left_gap, right_gap) < 5:
            continue
        if max(left_gap, right_gap) / min(left_gap, right_gap) > 2:
            continue
        arm_pits = _between(troughs, left[0], right[0])
        left_pits = [point for point in arm_pits if point[0] < head[0]]
        right_pits = [point for point in arm_pits if point[0] > head[0]]
        if not left_pits or not right_pits:
            continue
        pit_l = min(left_pits, key=lambda point: point[1]) if not inverse else max(left_pits, key=lambda point: point[1])
        pit_r = min(right_pits, key=lambda point: point[1]) if not inverse else max(right_pits, key=lambda point: point[1])
        slope = _slope(pit_l, pit_r)
        sloping_down = slope < 0

        def level(index: int, pit_l=pit_l, slope=slope) -> float:
            return pit_l[1] + slope * (index - pit_l[0])

        state, at = "形成中", right[0]
        for i in range(right[0] + 1, len(closes)):
            if inverse:
                if closes[i] > level(i):
                    state, at = "確定", i
                    break
                if closes[i] < head[1]:
                    state = ""
                    break
            else:
                use = pit_r[1] if sloping_down else level(i)
                if closes[i] < use:
                    state, at = "確定", i
                    break
                if closes[i] > head[1]:
                    state = ""
                    break
        if not state or (state == "形成中" and right[0] < len(closes) - 40):
            continue
        text = "ネックラインを終値で抜けた" if state == "確定" else "形はある。終値はまだネックラインの内側"
        if not inverse and sloping_down and state == "確定":
            text = "右の谷を終値で下抜け"
        out.append(
            _pack(
                name,
                state,
                text,
                at,
                [[left, head, right], [pit_l, (max(at, right[0]), level(max(at, right[0])))]],
                times,
            )
        )
        return out
    return out


def _channels(ph, pl, closes, times, highs, lows, settings: Settings) -> list[dict]:
    if len(ph) < 2 or len(pl) < 2:
        return []
    highs_p = ph[-3:]
    lows_p = pl[-3:]
    top1, top2 = highs_p[-2], highs_p[-1]
    bot1, bot2 = lows_p[-2], lows_p[-1]
    if abs(top2[0] - bot2[0]) > 80 or min(top2[0], bot2[0]) < len(closes) - 120:
        return []
    top_flat = _near(top1[1], top2[1], settings.price_pct)
    bot_flat = _near(bot1[1], bot2[1], settings.price_pct)
    top_slope = _slope(top1, top2)
    bot_slope = _slope(bot1, bot2)
    span = max(top2[0], bot2[0]) - min(top1[0], bot1[0])
    if span < 10:
        return []
    end = len(closes) - 1
    top_now = _line_at(top1, top2, end)
    bot_now = _line_at(bot1, bot2, end)
    if top_now <= bot_now:
        return []

    name = ""
    if top_flat and bot_slope > 0 and not bot_flat:
        name = "上昇三角保ち合い"
    elif bot_flat and top_slope < 0 and not top_flat:
        name = "下降三角保ち合い"
    elif top_flat and bot_flat:
        name = ""
    elif top_slope > 0 and bot_slope > 0 and top_slope < bot_slope:
        name = "上昇ウェッジ"
    elif top_slope < 0 and bot_slope < 0 and top_slope < bot_slope:
        name = "下降ウェッジ"

    touches_top = len(highs_p) if top_flat or name.endswith("ウェッジ") else 2
    if name.startswith("上昇三角") and len(highs_p) < 3:
        name = ""
    if name.startswith("下降三角") and len(lows_p) < 3:
        name = ""

    results = []
    if name:
        state, text, at = _boundary_state(closes, top1, top2, bot1, bot2, name)
        if state:
            results.append(
                _pack(
                    name,
                    state,
                    text,
                    at,
                    [[top1, (at, _line_at(top1, top2, at))], [bot1, (at, _line_at(bot1, bot2, at))]],
                    times,
                )
            )
    if top_flat and bot_flat and len(highs_p) >= 2 and len(lows_p) >= 2:
        rising = closes[end] >= closes[max(0, end - 20)]
        rect = "上昇レクタングル" if rising else "下降レクタングル"
        up = rect.startswith("上昇")
        level = max(top1[1], top2[1]) if up else min(bot1[1], bot2[1])
        state, at = "形成中", end
        for i in range(max(top2[0], bot2[0]) + 1, len(closes)):
            if up and closes[i] > level:
                state, at = "確定", i
                break
            if not up and closes[i] < level:
                state, at = "確定", i
                break
        text = "箱の外へ終値で抜けた" if state == "確定" else "上下がほぼ水平。終値はまだ箱の内側"
        results.append(
            _pack(
                rect,
                state,
                text,
                at,
                [[(min(top1[0], bot1[0]), max(top1[1], top2[1])), (at, max(top1[1], top2[1]))],
                 [(min(top1[0], bot1[0]), min(bot1[1], bot2[1])), (at, min(bot1[1], bot2[1]))]],
                times,
            )
        )
    return results


def _boundary_state(closes, top1, top2, bot1, bot2, name: str) -> tuple[str, str, int]:
    start = max(top2[0], bot2[0])
    end = len(closes) - 1
    if start < len(closes) - 50 and all(
        _line_at(bot1, bot2, i) <= closes[i] <= _line_at(top1, top2, i) for i in range(start, min(start + 3, len(closes)))
    ):
        pass
    broke = None
    for i in range(start + 1, len(closes)):
        upper = _line_at(top1, top2, i)
        lower = _line_at(bot1, bot2, i)
        if closes[i] > upper:
            broke = ("上", i)
            break
        if closes[i] < lower:
            broke = ("下", i)
            break
    if broke:
        side, at = broke
        if "ウェッジ" in name:
            text = f"終値が{side}側へ抜けた"
        else:
            text = f"終値が{side}側へ抜けた"
        return "確定", text, at
    if start < len(closes) - 45:
        return "", "", end
    return "形成中", "上下の線の内側で、終値はまだ抜けていない", end


def _flags(bars: list[dict], settings: Settings) -> list[dict]:
    closes = [bar["close"] for bar in bars]
    highs = [bar["high"] for bar in bars]
    lows = [bar["low"] for bar in bars]
    times = [bar["time"] for bar in bars]
    if len(bars) < settings.pole_bars + 8:
        return []
    results = []
    for length in range(5, 15):
        end = len(bars) - 1
        cons_start = end - length
        pole_start = cons_start - settings.pole_bars
        if pole_start < 0:
            continue
        base = closes[pole_start]
        if base == 0:
            continue
        move = (closes[cons_start] - base) / base * 100
        if abs(move) < settings.pole_pct:
            continue
        up = move > 0
        cons_high = max(highs[cons_start:end])
        cons_low = min(lows[cons_start:end])
        mid = (cons_high + cons_low) / 2
        if mid == 0 or (cons_high - cons_low) / mid * 100 > abs(move) * 0.75:
            continue
        # 保ち合いの傾き。フラッグは逆か横、ペナントは幅が狭まる。
        early_range = max(highs[cons_start : cons_start + 2]) - min(lows[cons_start : cons_start + 2])
        late_range = max(highs[end - 2 : end]) - min(lows[end - 2 : end])
        pennant = late_range < early_range * 0.7
        drift = closes[end - 1] - closes[cons_start]
        if pennant:
            name = "上昇ペナント" if up else "下降ペナント"
        else:
            if up and drift > abs(move) / 100 * base * 0.25:
                continue
            if not up and drift < -abs(move) / 100 * base * 0.25:
                continue
            name = "上昇フラッグ" if up else "下降フラッグ"
        level_up = max(highs[cons_start:end])
        level_down = min(lows[cons_start:end])
        state, at = "形成中", end
        if up and closes[end] > level_up:
            state = "確定"
        elif not up and closes[end] < level_down:
            state = "確定"
        text = "保ち合いの外へ終値で抜けた" if state == "確定" else "急な動きのあとの保ち合い。終値はまだ内側"
        results.append(
            _pack(
                name,
                state,
                text,
                at,
                [[(cons_start, level_up), (end, level_up)], [(cons_start, level_down), (end, level_down)]],
                times,
            )
        )
        break
    return results


_FIB_RATIOS = (
    (0.0, "#d0d7e2", 2, 0),
    (0.236, "#8eb6de", 1, 2),
    (0.382, "#3dbe8b", 1, 2),
    (0.5, "#e2b656", 1, 2),
    (0.618, "#d98a62", 1, 2),
    (0.786, "#c084fc", 1, 2),
    (1.0, "#d0d7e2", 2, 0),
)


def _ratio_text(ratio: float) -> str:
    return f"{ratio:.3f}".rstrip("0").rstrip(".")


def _price_text(value: float) -> str:
    digits = 2 if abs(value) >= 100 else 4 if abs(value) >= 1 else 6
    return f"{value:,.{digits}f}"


def _zigzag(highs: list[float], lows: list[float], wing: int) -> list[tuple[int, float, str]]:
    peaks, troughs = pivots(highs, lows, wing)
    points = [(index, price, "h") for index, price in peaks] + [(index, price, "l") for index, price in troughs]
    points.sort()
    zigzag: list[tuple[int, float, str]] = []
    for index, price, kind in points:
        if not zigzag or zigzag[-1][2] != kind:
            zigzag.append((index, price, kind))
            continue
        if kind == "h" and price >= zigzag[-1][1]:
            zigzag[-1] = (index, price, kind)
        elif kind == "l" and price <= zigzag[-1][1]:
            zigzag[-1] = (index, price, kind)
    return zigzag


def fib_retracement(bars: list[dict], settings: Settings) -> dict | None:
    """直近の山と谷を 0 と 1 にして、戻りの位置を引く。"""
    if len(bars) < settings.pivot_bars * 2 + 10:
        return None
    highs = [bar["high"] for bar in bars]
    lows = [bar["low"] for bar in bars]
    times = [bar["time"] for bar in bars]
    zigzag = _zigzag(highs, lows, settings.pivot_bars)
    start = end = None
    for right in range(len(zigzag) - 1, 0, -1):
        left, right_point = zigzag[right - 1], zigzag[right]
        gap = right_point[0] - left[0]
        base = max(abs(left[1]), abs(right_point[1]), 1e-12)
        move = abs(right_point[1] - left[1]) / base * 100
        if gap >= 5 and move >= 2:
            start, end = left, right_point
            break
    if start is None or end is None:
        return None
    rising = end[1] > start[1]
    lines = []
    for ratio, color, width, style in _FIB_RATIOS:
        price = end[1] + (start[1] - end[1]) * ratio
        lines.append(
            {
                "points": [
                    {"time": times[start[0]], "value": price},
                    {"time": times[-1], "value": price},
                ],
                "name": f"フィボナッチ {_ratio_text(ratio)}　{_price_text(price)}",
                "color": color,
                "width": width,
                "style": style,
                "label": ratio == 0.618,
            }
        )
    lines.append(
        {
            "points": [
                {"time": times[start[0]], "value": start[1]},
                {"time": times[end[0]], "value": end[1]},
            ],
            "name": "フィボナッチ 計測した山と谷",
            "color": "#9aa8bd",
            "width": 1,
            "style": 0,
        }
    )
    if rising:
        text = f"谷から山。0 が山、1 が谷。間の数値はその幅の位置です"
    else:
        text = f"山から谷。0 が谷、1 が山。間の数値はその幅の位置です"
    return {
        "name": "フィボナッチ",
        "state": "目安",
        "text": text,
        "color": "#d0d7e2",
        "span": [times[start[0]], times[end[0]]],
        "lines": lines,
        "value": f"{_price_text(start[1])} → {_price_text(end[1])}",
    }

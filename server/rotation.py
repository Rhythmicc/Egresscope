"""二级地区感知的出口轮换（组合节点池 / "xx智能"策略组）。

节点名通常只精确到一级（国家），二级地区（城市）由外部机制判定：名称启发式
预填、出口 IP GeoIP 探测、管理员手动纠正。轮换行为是固定的单一策略：

    同国家同地区的健康节点间轮换 → 同国家跨地区轮换 → 绝不跨国家。

本模块是纯逻辑（无 I/O），便于单测；地区解析器作为参数注入。
"""

from __future__ import annotations

import re
from typing import Any, Callable

# 城市（二级地区）词表：中文词按子串匹配；拉丁词（机场码、城市名）按词边界匹配，
# 避免 common words 误判（如 research ≠ 西雅图、history ≠ 伊斯坦布尔）。
CITY_HINTS: dict[str, tuple[str, ...]] = {
    "香港": ("香港", "hong kong", "hkg"),
    "东京": ("东京", "tokyo", "nrt"),
    "大阪": ("大阪", "osaka", "kix"),
    "首尔": ("首尔", "seoul", "icn"),
    "新加坡": ("新加坡", "singapore", "sin"),
    "台北": ("台北", "taipei", "tpe"),
    "洛杉矶": ("洛杉矶", "los angeles", "lax"),
    "圣何塞": ("圣何塞", "san jose", "sjc"),
    "西雅图": ("西雅图", "seattle", "sea"),
    "旧金山": ("旧金山", "san francisco", "sfo"),
    "纽约": ("纽约", "new york", "nyc"),
    "芝加哥": ("芝加哥", "chicago", "ord"),
    "达拉斯": ("达拉斯", "dallas", "dfw"),
    "凤凰城": ("凤凰城", "phoenix", "phx"),
    "法兰克福": ("法兰克福", "frankfurt", "fra"),
    "巴黎": ("巴黎", "paris", "cdg"),
    "伦敦": ("伦敦", "london", "city of london", "lhr"),
    "阿姆斯特丹": ("阿姆斯特丹", "amsterdam", "ams"),
    "悉尼": ("悉尼", "sydney", "syd"),
    "墨尔本": ("墨尔本", "melbourne", "mel"),
    "莫斯科": ("莫斯科", "moscow", "svo"),
    "迪拜": ("迪拜", "dubai", "dxb"),
    "曼谷": ("曼谷", "bangkok", "bkk"),
    "吉隆坡": ("吉隆坡", "kuala lumpur", "kul"),
    "马尼拉": ("马尼拉", "manila", "mnl"),
    "孟买": ("孟买", "mumbai", "bom"),
    "伊斯坦布尔": ("伊斯坦布尔", "istanbul", "ist"),
    "米兰": ("米兰", "milan", "mxp"),
    "圣保罗": ("圣保罗", "sao paulo", "gru"),
    "马德里": ("马德里", "madrid", "mad"),
    "都柏林": ("都柏林", "dublin", "dub"),
    "胡志明": ("胡志明", "ho chi minh", "sgn"),
    "河内": ("河内", "hanoi", "han"),
    "雅加达": ("雅加达", "jakarta", "cgk"),
    "柏林": ("柏林", "berlin", "ber"),
    "阿什本": ("阿什本", "ashburn", "iad"),
    "圣克拉拉": ("圣克拉拉", "santa clara", "svc"),
    "丹佛": ("丹佛", "denver", "den"),
    "亚特兰大": ("亚特兰大", "atlanta", "atl"),
    "迈阿密": ("迈阿密", "miami", "mia"),
    "波士顿": ("波士顿", "boston", "bos"),
    "休斯顿": ("休斯顿", "houston", "iah"),
    "波特兰": ("波特兰", "portland", "pdx"),
    "盐湖城": ("盐湖城", "salt lake city", "slc"),
    "拉斯维加斯": ("拉斯维加斯", "las vegas", "las"),
    "多伦多": ("多伦多", "toronto", "yyz"),
    "温哥华": ("温哥华", "vancouver", "yvr"),
    "蒙特利尔": ("蒙特利尔", "montreal", "yul"),
    "新德里": ("新德里", "new delhi", "del"),
    "班加罗尔": ("班加罗尔", "bangalore", "blr"),
    "釜山": ("釜山", "busan", "pus"),
    "华沙": ("华沙", "warsaw", "waw"),
    "苏黎世": ("苏黎世", "zurich", "zrh"),
    "维也纳": ("维也纳", "vienna", "vie"),
    "布拉格": ("布拉格", "prague", "prg"),
    "斯德哥尔摩": ("斯德哥尔摩", "stockholm", "arn"),
    "赫尔辛基": ("赫尔辛基", "helsinki", "hel"),
    "哥本哈根": ("哥本哈根", "copenhagen", "cph"),
    "奥斯陆": ("奥斯陆", "oslo", "osl"),
    "布鲁塞尔": ("布鲁塞尔", "brussels", "bru"),
    "里斯本": ("里斯本", "lisbon", "lis"),
    "布加勒斯特": ("布加勒斯特", "bucharest", "otp"),
    "基辅": ("基辅", "kyiv", "kbp"),
    "圣彼得堡": ("圣彼得堡", "saint petersburg", "led"),
    "墨西哥城": ("墨西哥城", "mexico city", "mex"),
    "布宜诺斯艾利斯": ("布宜诺斯艾利斯", "buenos aires", "eze"),
    "圣地亚哥": ("圣地亚哥", "santiago", "scl"),
    "约翰内斯堡": ("约翰内斯堡", "johannesburg", "jnb"),
    "特拉维夫": ("特拉维夫", "tel aviv", "tlv"),
    "多哈": ("多哈", "doha", "doh"),
}

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_TOKEN_PATTERN = r"(?<![a-z0-9]){token}(?![a-z0-9])"


def _latin_matches(hint: str, lowered: str) -> bool:
    pattern = _LATIN_TOKEN_PATTERN.format(token=re.escape(hint.casefold()))
    return bool(re.search(pattern, lowered))


def city_of(name: str) -> str | None:
    """从节点名启发式识别二级地区（城市）；识别不到返回 None。"""
    lowered = name.casefold()
    for city, hints in CITY_HINTS.items():
        for hint in hints:
            if _CJK_RE.search(hint):
                if hint.casefold() in lowered:
                    return city
            elif _latin_matches(hint, lowered):
                return city
    return None


# GeoIP 返回英文城市名 → 归一化为词表里的中文城市键，避免 "Los Angeles" 与 "洛杉矶"
# 被当成两个地区。
_ENGLISH_CITY_INDEX: dict[str, str] = {
    hint.casefold(): city
    for city, hints in CITY_HINTS.items()
    for hint in hints
    if not _CJK_RE.search(hint)
}


def normalize_city(value: str | None) -> str | None:
    """把 GeoIP/名称给出的城市字符串归一化为稳定地区键。"""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for city, hints in CITY_HINTS.items():
        if any(hint == text or hint.casefold() == text.casefold() for hint in hints):
            return city
    lowered = text.casefold()
    return _ENGLISH_CITY_INDEX.get(lowered) or text


def classify(name: str, country_of: Callable[[str], str | None], region_of: Callable[[str], str | None]) -> dict[str, str | None]:
    return {"name": name, "country": country_of(name), "region": region_of(name)}


def pool_profiles(names: list[str], country_of: Callable[[str], str | None], region_of: Callable[[str], str | None]) -> list[dict[str, str | None]]:
    return [classify(name, country_of, region_of) for name in names]


def countries(pool: list[dict[str, str | None]]) -> list[str]:
    result: list[str] = []
    for profile in pool:
        country = profile.get("country")
        if country and country not in result:
            result.append(country)
    return sorted(result)


def regions_for(pool: list[dict[str, str | None]], country: str | None) -> list[str]:
    result: list[str] = []
    for profile in pool:
        if profile.get("country") != country:
            continue
        region = profile.get("region") or "默认"
        if region not in result:
            result.append(region)
    return sorted(result)


def _alive(health: dict[str, Any], name: str) -> bool:
    record = health.get(name)
    if record is None:
        return True
    return bool(record.get("alive", True))


def _provider_of(pool: list[dict[str, str | None]], name: str) -> str:
    for profile in pool:
        if profile.get("name") == name:
            return str(profile.get("provider") or "")
    return ""


# 轮换因素（用户可按优先级启用）。有序逐级生效：先按最高优先级因素排序，平局再看下一级。
FACTOR_DEFAULT_PREFS = ["usage_balance", "region_health", "region_latency", "node_delay", "diversity"]

FACTOR_LABELS: dict[str, str] = {
    "usage_balance": "用量均衡",
    "region_health": "地区健康",
    "region_latency": "地区延迟",
    "node_delay": "节点延迟",
    "diversity": "多样性",
}


def _tiered_best(candidates: list[str], prefs: list[str], keys: dict[str, Callable[[str], Any]]) -> str:
    """按 ``prefs``（高优先级在前）逐级稳定排序，返回最优候选。

    低优先级因素先排序、高优先级最后排序：稳定排序保证高优先级因素主导，
    平局时保留上一级因素的顺序。``keys`` 为 {因素: 候选 → 排序键}，键为升序最优。
    """
    ordered = list(candidates)
    for factor in reversed(prefs):
        key = keys.get(factor)
        if key is not None:
            ordered.sort(key=key)
    return ordered[0] if ordered else ""


def _stable_names(pool: list[dict[str, str | None]], country: str | None, region: str | None) -> list[str]:
    return sorted(
        profile["name"] for profile in pool
        if profile.get("country") == country and (profile.get("region") or "默认") == region
    )


def choose_rotation(
    pool: list[dict[str, str | None]],
    current: dict[str, str] | None,
    health: dict[str, Any],
    rotate_due: bool,
    cross_due: bool,
    prefs: list[str] | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    """为“智能”组挑选下一个出口（单国家内）。

    ``pool`` 是该国家内的节点；``current`` = {country, region, node}；
    ``health`` = {name: {"alive": bool}}。``rotate_due``/``cross_due`` 表示
    同地区轮换与跨地区轮换是否到期（3 天/手动）。绝不跨国家。

    ``prefs``：启用因素的有序优先级列表（高优先级在前），空/None 用默认顺序；
    ``usage``：{provider: 本月累计字节}，供“用量均衡”因素使用。
    """
    prefs = prefs or FACTOR_DEFAULT_PREFS
    usage = usage or {}
    if not pool:
        return {"country": None, "region": None, "node": None, "reason": "节点池为空", "crossed": False}

    known_countries = countries(pool)
    country = (current or {}).get("country") or known_countries[0]
    if country not in known_countries:
        country = known_countries[0]
    known_regions = regions_for(pool, country) or ["默认"]
    region = (current or {}).get("region") or known_regions[0]
    if region not in known_regions:
        region = known_regions[0]
    current_node = (current or {}).get("node") or ""

    same_region = _stable_names(pool, country, region)
    alive_region = [name for name in same_region if _alive(health, name)]
    alive_country = sorted(
        profile["name"] for profile in pool
        if profile.get("country") == country and _alive(health, profile["name"])
    )

    def provider_of(name: str) -> str:
        return _provider_of(pool, name)

    def delay_of(name: str) -> int | float:
        record = health.get(name) or {}
        value = record.get("delay")
        return value if isinstance(value, int) else float("inf")

    def usage_of(name: str) -> int:
        return usage.get(provider_of(name), 0)

    # 同地区内节点级排序键
    node_keys: dict[str, Callable[[str], Any]] = {
        "usage_balance": usage_of,
        "node_delay": delay_of,
        "diversity": lambda n: 0 if provider_of(n) != provider_of(current_node) else 1,
    }

    def region_stats(r: str) -> dict[str, Any]:
        names = _stable_names(pool, country, r)
        alive = [n for n in names if _alive(health, n)]
        delays = [delay_of(n) for n in alive if delay_of(n) != float("inf")]
        return {
            "ratio": (len(alive) / len(names)) if names else 0.0,
            "delay": (sum(delays) / len(delays)) if delays else float("inf"),
            "usage": min((usage_of(n) for n in alive), default=0),
        }

    def cross_target() -> str:
        healthy = [r for r in regions_for(pool, country) if _first_alive(_stable_names(pool, country, r), health)]
        candidates = [r for r in healthy if r != region] or healthy
        region_keys: dict[str, Callable[[str], Any]] = {
            "usage_balance": lambda r: region_stats(r)["usage"],
            "region_health": lambda r: -region_stats(r)["ratio"],
            "region_latency": lambda r: region_stats(r)["delay"],
            "diversity": lambda r: 0 if r != region else 1,
        }
        return _tiered_best(candidates, prefs, region_keys)

    def result(node: str, target_region: str | None, reason: str, crossed: bool) -> dict[str, Any]:
        profile = next((item for item in pool if item["name"] == node), None)
        return {
            "country": country,
            "region": (profile.get("region") or "默认") if profile else (target_region or "默认"),
            "node": node,
            "reason": reason,
            "crossed": crossed,
        }

    # 当前节点失效/消失：同地区换最优，无则跨地区。
    if current_node not in alive_region:
        if alive_region:
            target = _tiered_best(alive_region, prefs, node_keys)
            reason = "当前节点不可用，同地区切换其他提供商" if provider_of(target) != provider_of(current_node) else "当前节点不可用，同地区内切换"
            return result(target, region, reason, False)
        if alive_country:
            target_region = cross_target()
            target = _first_alive(_stable_names(pool, country, target_region), health)
            return result(target, target_region, "当前地区无可用节点，跨地区切换", True)
        return result(current_node or same_region[0], region, "国家内无可用节点，保持现状", False)

    # 同地区健康节点间轮换（到期）：排除当前节点，按因素选最优。
    if rotate_due and len(alive_region) > 1:
        candidates = [n for n in alive_region if n != current_node] or alive_region
        target = _tiered_best(candidates, prefs, node_keys)
        reason = "同地区切换至其他提供商" if provider_of(target) != provider_of(current_node) else "同地区健康节点轮换"
        return result(target, region, reason, False)

    # 跨地区轮换（3 天/手动）：排除当前地区，按因素选最优。
    if cross_due and alive_country:
        target_region = cross_target()
        if target_region != region:
            target = _first_alive(_stable_names(pool, country, target_region), health)
            return result(target, target_region, "跨地区轮换", True)

    return {"country": country, "region": region, "node": current_node, "reason": "保持当前出口", "crossed": False}


def _first_alive(names: list[str], health: dict[str, Any]) -> str:
    for name in names:
        if _alive(health, name):
            return name
    return names[0] if names else ""


def first_alive_in(pool: list[dict[str, str | None]], country: str | None, region: str | None, health: dict[str, Any]) -> str:
    """返回指定国家+地区内第一个可用节点（供 AI 建议地区后落地选择）。"""
    return _first_alive(_stable_names(pool, country, region), health)

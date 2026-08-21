"""GeoIP 出口地区解析：离线 GeoLite2 (.mmdb) 优先，在线服务兜底。

入口 server 地址往往落在国内，不能用来判地区；调用方应先通过 mihomo 混合端口
把请求走目标节点的真实出口，再拿到的出口 IP 交给本模块解析国家 + 城市。
"""

from __future__ import annotations

import gzip
import ipaddress
import os
from pathlib import Path
from typing import Any

import httpx

# ISO 3166-1 alpha-2 → 面板使用的一级地区（中文）名，与 REGION_HINTS 保持一致。
COUNTRY_CODES: dict[str, str] = {
    "US": "美国",
    "JP": "日本",
    "HK": "香港",
    "SG": "新加坡",
    "GB": "英国",
    "TW": "台湾",
    "DE": "德国",
    "KR": "韩国",
    "FR": "法国",
    "CA": "加拿大",
    "AU": "澳大利亚",
    "NL": "荷兰",
    "RU": "俄罗斯",
    "TH": "泰国",
    "VN": "越南",
    "MY": "马来西亚",
    "PH": "菲律宾",
    "IN": "印度",
    "TR": "土耳其",
    "IT": "意大利",
    "BR": "巴西",
    "ES": "西班牙",
    "IE": "爱尔兰",
    "ID": "印度尼西亚",
    "AE": "阿联酋",
}

# 中文国家名 → 国旗 emoji，由 ISO 码按区域指示符推导，避免手写 25 份旗面。
def _country_flag(iso: str) -> str:
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso if "A" <= c <= "Z")


COUNTRY_FLAGS: dict[str, str] = {chinese: _country_flag(iso) for iso, chinese in COUNTRY_CODES.items()}
# 产品约定：台湾出口统一用 🇨🇳 标记（与订阅商口径一致），覆盖 ISO 推导的 🇹🇼。
COUNTRY_FLAGS["台湾"] = "🇨🇳"

# 英文全称国家名 → 中文（在线服务可能返回完整英文名；ISO 码走 COUNTRY_CODES）。
_ENGLISH_COUNTRY: dict[str, str] = {
    "united states": "美国",
    "united kingdom": "英国",
    "hong kong": "香港",
    "taiwan": "台湾",
    "germany": "德国",
    "japan": "日本",
    "singapore": "新加坡",
    "south korea": "韩国",
    "korea": "韩国",
    "france": "法国",
    "canada": "加拿大",
    "australia": "澳大利亚",
    "netherlands": "荷兰",
    "russia": "俄罗斯",
    "thailand": "泰国",
    "vietnam": "越南",
    "malaysia": "马来西亚",
    "philippines": "菲律宾",
    "india": "印度",
    "turkey": "土耳其",
    "italy": "意大利",
    "brazil": "巴西",
    "spain": "西班牙",
    "ireland": "爱尔兰",
    "indonesia": "印度尼西亚",
    "united arab emirates": "阿联酋",
}


def normalize_country(value: str | None) -> str:
    """把 ISO 码 / 英文全称 / 中文统一归一化为面板使用的中文一级地区名。"""
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if len(text) == 2 and text.upper() in COUNTRY_CODES:
        return COUNTRY_CODES[text.upper()]
    if text in COUNTRY_CODES.values():
        return text
    return _ENGLISH_COUNTRY.get(text.casefold(), text)


DEFAULT_ONLINE_SERVICE = "https://ipwho.is/{ip}"
# 兜底顺序：多源降低免费服务限流风险；ip-api.com 免费档走 http。
ONLINE_SERVICES = (
    "https://ipwho.is/{ip}",
    "http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,query",
    "https://ipapi.co/{ip}/json/",
)


def _load_mmdb_reader(path: str) -> Any | None:
    try:
        import maxminddb  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return maxminddb.open_database(path)
    except Exception:
        return None


class GeoIPResolver:
    """离线 .mmdb 优先，在线 HTTP 服务兜底；两者都可配置、都可缺省。

    离线库路径可被 Web 上传替换，通过 :meth:`reload` 让新库即时生效。
    """

    def __init__(self, mmdb_path: str = "", online_service: str = "") -> None:
        self._mmdb_path = mmdb_path
        self._reader: Any | None = None
        self._online_service = (online_service or DEFAULT_ONLINE_SERVICE).strip()
        if self._mmdb_path:
            self._reader = _load_mmdb_reader(self._mmdb_path)

    def reload(self) -> bool:
        self._reader = _load_mmdb_reader(self._mmdb_path) if self._mmdb_path else None
        return self._reader is not None

    def mmdb_status(self) -> dict[str, Any]:
        path = self._mmdb_path
        if not path:
            return {"enabled": False, "path": "", "size": 0, "modifiedAt": None}
        import os

        try:
            stat = os.stat(path)
            return {
                "enabled": self._reader is not None,
                "path": path,
                "size": stat.st_size,
                "modifiedAt": int(stat.st_mtime),
            }
        except OSError:
            return {"enabled": False, "path": path, "size": 0, "modifiedAt": None}

    def resolve(self, ip: str) -> dict[str, str] | None:
        """返回 {"country": 中文一级, "city": 英文城市}；都解析不到返回 None。"""
        try:
            address = ipaddress.ip_address(ip.split("%", 1)[0])
        except ValueError:
            return None
        if not address.is_global:
            return None
        text = str(address)

        offline = self._resolve_offline(text)
        if offline:
            return offline
        return self._resolve_online(text)

    def _resolve_offline(self, ip: str) -> dict[str, str] | None:
        if self._reader is None:
            return None
        try:
            record = self._reader.get(ip)
        except Exception:
            return None
        if not isinstance(record, dict):
            return None
        country_iso = str((record.get("country") or {}).get("iso_code") or "")
        city_names = (record.get("city") or {}).get("names") or {}
        city = str(city_names.get("en") or city_names.get("zh-CN") or "")
        country = COUNTRY_CODES.get(country_iso.upper(), country_iso)
        if not country and not city:
            return None
        return {"country": country or country_iso, "city": city}

    def _resolve_online(self, ip: str) -> dict[str, str] | None:
        # 多源依次尝试，避免单一免费服务限流导致地区解析全失败。
        services = [self._online_service] if self._online_service and "{ip}" in self._online_service else []
        services.extend([item for item in ONLINE_SERVICES if item not in services])
        for service in services:
            if "{ip}" not in service:
                continue
            payload = self._fetch_json(service.format(ip=ip))
            if not isinstance(payload, dict):
                continue
            # 优先用 ISO 码映射为中文一级地区，避免各服务英文全称口径不一。
            iso = str(payload.get("country_code") or payload.get("countryCode") or "")
            if len(iso) == 2:
                country = COUNTRY_CODES.get(iso.upper(), iso.upper())
            else:
                country = normalize_country(
                    str(payload.get("country_name") or payload.get("country") or "")
                )
            city = str(payload.get("city") or "")
            if country or city:
                return {"country": country, "city": city}
        return None

    @staticmethod
    def _fetch_json(url: str) -> Any | None:
        try:
            response = httpx.get(url, timeout=httpx.Timeout(8, connect=4), follow_redirects=False, trust_env=False)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None


def install_mmdb_from_url(url: str, dest_path: str) -> dict[str, Any]:
    """下载（可选 .gz 压缩）并校验安装 GeoLite2 mmdb，原子替换到 ``dest_path``。

    默认源为 jsDelivr 托管的 wp-statistics/GeoLite2-City 镜像（``.mmdb.gz``），
    定时更新、无需 API key。安装后调用 :meth:`GeoIPResolver.reload` 即时生效。
    """
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, follow_redirects=True, timeout=httpx.Timeout(180, connect=15), trust_env=False) as response:
        response.raise_for_status()
        chunks: list[bytes] = []
        for chunk in response.iter_bytes():
            chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        raise ValueError("下载内容为空")
    if url.rstrip().lower().endswith(".gz") or raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except OSError as exc:
            raise ValueError("下载的 .gz 文件无法解压") from exc
    try:
        import maxminddb  # type: ignore[import-not-found]
    except ImportError:
        maxminddb = None
    temporary = dest.with_suffix(".mmdb.tmp")
    temporary.write_bytes(raw)
    if maxminddb is not None:
        try:
            probe = maxminddb.open_database(str(temporary))
            probe.close()
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise ValueError("下载的文件不是有效的 MaxMind GeoIP 数据库") from exc
    os.replace(temporary, dest)
    os.chmod(dest, 0o600)
    return {"path": str(dest), "size": len(raw)}

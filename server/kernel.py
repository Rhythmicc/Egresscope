"""mihomo 内核（二进制）的 Web 化管理：版本检查、下载、SHA256 校验、暂存、切换、回滚。

面板把二进制暂存到共享 bin 目录（默认 data_dir/mihomo-bin，部署时挂载给 mihomo
容器），通过 ``mihomo-current`` 符号链接标记当前版本；mihomo 容器入口脚本优先
exec 该链接，否则用镜像内置二进制。切换后需重启 mihomo 容器生效。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any

import httpx

RELEASE_REPO = "MetaCubeX/mihomo"
GITHUB_API = "https://api.github.com"
RELEASE_URL = f"{GITHUB_API}/repos/{RELEASE_REPO}/releases"
VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+$")


def detect_arch(machine: str | None = None) -> str:
    raw = (machine or platform.machine()).lower()
    if raw in ("x86_64", "amd64"):
        return "amd64"
    if raw in ("aarch64", "arm64"):
        return "arm64"
    if raw.startswith("arm") and "v7" in raw:
        return "armv7"
    return raw or "amd64"


def normalize_version(version: str) -> str:
    version = version.strip().lstrip("v")
    if not VERSION_RE.match(version):
        raise ValueError(f"版本号格式不正确：{version}")
    return f"v{version}"


def version_key(version: str) -> tuple[int, int, int]:
    parts = str(version).lstrip("v").split(".")
    return tuple(int(item) for item in parts[:3]) + (0,) * (3 - len(parts))


def asset_name(arch: str, version: str) -> str:
    return f"mihomo-linux-{arch}-{normalize_version(version)}.gz"


def binary_name(version: str) -> str:
    return f"mihomo-{normalize_version(version)}"


def checksum_name(version: str) -> str:
    return f"sha256-{normalize_version(version)}.txt"


class KernelManager:
    """面板侧内核管理：GitHub 版本探测 + 下载校验 + 暂存/切换/回滚。"""

    def __init__(self, bin_dir: str | Path) -> None:
        self.bin_dir = Path(bin_dir)

    # ---- 状态 ----

    def staged(self) -> list[dict[str, Any]]:
        if not self.bin_dir.exists():
            return []
        result: list[dict[str, Any]] = []
        for path in sorted(self.bin_dir.iterdir()):
            if not path.is_file() or not path.name.startswith("mihomo-v"):
                continue
            stat = path.stat()
            result.append({"version": path.name[len("mihomo-"):], "size": stat.st_size, "modifiedAt": int(stat.st_mtime)})
        return result

    def current_version(self) -> str | None:
        current = self.bin_dir / "mihomo-current"
        try:
            return current.resolve().name[len("mihomo-"):] if current.exists() else None
        except OSError:
            return None

    def status(self, running_version: str | None) -> dict[str, Any]:
        current = self.current_version()
        staged = self.staged()
        return {
            "runningVersion": running_version,
            "arch": detect_arch(),
            "current": current,
            "pendingRestart": bool(current and running_version and version_key(current) != version_key(running_version)),
            "staged": staged,
            "binDir": str(self.bin_dir),
        }

    # ---- GitHub ----

    async def fetch_latest(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=8), follow_redirects=False, trust_env=False, headers={"Accept": "application/vnd.github+json", "User-Agent": "Egresscope/0.2"}) as client:
            response = await client.get(f"{RELEASE_URL}/latest")
            response.raise_for_status()
            payload = response.json()
        return {
            "version": str(payload.get("tag_name") or ""),
            "publishedAt": str(payload.get("published_at") or ""),
            "htmlUrl": str(payload.get("html_url") or ""),
            "assets": [
                {"name": str(asset.get("name") or ""), "size": int(asset.get("size") or 0),
                 "url": str(asset.get("browser_download_url") or "")}
                for asset in payload.get("assets") or []
            ],
        }

    def _checksum_asset(self, assets: list[dict[str, Any]], version: str) -> tuple[str, str] | None:
        wanted = checksum_name(version)
        for asset in assets:
            name = str(asset.get("name") or "").lower()
            if name == wanted or name in ("sha256sums.txt", "sha256.txt") or name.endswith(".sha256"):
                return name, str(asset.get("url") or "")
        return None

    async def _download(self, url: str, max_bytes: int = 40 * 1024 * 1024) -> bytes:
        body = bytearray()
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10), follow_redirects=True, trust_env=False, headers={"User-Agent": "Egresscope/0.2"}) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise ValueError("内核压缩包超过 40 MiB 上限")
        return bytes(body)

    async def download_and_stage(
        self,
        version: str,
        arch: str | None = None,
        latest: dict[str, Any] | None = None,
        confirm_unverified: bool = False,
    ) -> dict[str, Any]:
        normalized = normalize_version(version)
        arch = arch or detect_arch()
        if latest is None:
            latest = await self.fetch_latest()
        assets = latest.get("assets") or []
        asset = next((item for item in assets if item.get("name") == asset_name(arch, normalized)), None)
        if asset is None:
            raise ValueError(f"GitHub 发布中没有 {asset_name(arch, normalized)}")
        archive = await self._download(str(asset["url"]))
        try:
            binary = gzip.decompress(archive)
        except OSError as exc:
            raise ValueError("内核压缩包解压失败") from exc
        digest = hashlib.sha256(binary).hexdigest()
        expected = ""
        checksum_asset = self._checksum_asset(assets, normalized)
        if checksum_asset:
            try:
                checksum_body = await self._download(str(checksum_asset[1]), max_bytes=2 * 1024 * 1024)
                expected = self._parse_checksum(checksum_body.decode("utf-8", "replace"), asset_name(arch, normalized))
            except Exception:
                expected = ""
        if expected:
            if digest != expected.strip().lower():
                raise ValueError(f"SHA256 校验失败：期望 {expected}，实际 {digest}")
        elif not confirm_unverified:
            raise ValueError(f"未找到官方校验文件，实际 SHA256 为 {digest}；确认来源可信后再试")
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        target = self.bin_dir / binary_name(normalized)
        temporary = self.bin_dir / f"{target.name}.tmp"
        temporary.write_bytes(binary)
        os.chmod(temporary, 0o755)
        os.replace(temporary, target)
        return {"version": normalized, "sha256": digest, "verified": bool(expected), "size": len(binary), "arch": arch}

    @staticmethod
    def _parse_checksum(content: str, asset: str) -> str:
        for line in content.splitlines():
            parts = line.split()
            if not parts:
                continue
            if len(parts) >= 2 and parts[1].strip().replace("/*", "") == asset:
                return parts[0].strip()
            if len(parts) == 1 and len(parts[0]) == 64:
                return parts[0]
        return ""

    def apply(self, version: str) -> dict[str, Any]:
        normalized = normalize_version(version)
        target = self.bin_dir / binary_name(normalized)
        if not target.is_file():
            raise ValueError(f"暂存中没有版本 {normalized}，请先下载")
        current = self.bin_dir / "mihomo-current"
        temporary = self.bin_dir / "mihomo-current.tmp"
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target.name)
        os.replace(temporary, current)
        return {"version": normalized, "pendingRestart": True}

    def rollback(self) -> dict[str, Any]:
        current = self.bin_dir / "mihomo-current"
        if not current.exists():
            raise ValueError("当前没有已应用的暂存内核")
        previous = None
        for item in sorted(self.staged(), key=lambda entry: version_key(entry["version"]), reverse=True):
            if item["version"] != self.current_version():
                previous = item["version"]
                break
        if previous is None:
            current.unlink(missing_ok=True)
            return {"version": None, "pendingRestart": True}
        return self.apply(previous)

    def delete(self, version: str) -> None:
        normalized = normalize_version(version)
        if normalized == self.current_version():
            raise ValueError("不能删除当前已应用的版本")
        target = self.bin_dir / binary_name(normalized)
        target.unlink(missing_ok=True)

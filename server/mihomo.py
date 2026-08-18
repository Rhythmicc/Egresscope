from __future__ import annotations

import asyncio
from urllib.parse import quote

import httpx


class MihomoClient:
    """Small controller adapter; domain services should not depend on httpx directly."""

    def __init__(self, controller_url: str, controller_secret: str) -> None:
        self.controller_url = controller_url
        self.controller_secret = controller_secret
        self.client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        headers = {"Authorization": f"Bearer {self.controller_secret}"} if self.controller_secret else {}
        self.client = httpx.AsyncClient(base_url=self.controller_url, headers=headers, timeout=8)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()

    async def get(self, path: str) -> dict:
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.get(path)
        response.raise_for_status()
        return response.json()

    async def select(self, group: str, name: str) -> None:
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.put(f"/proxies/{quote(group, safe='')}", json={"name": name})
        response.raise_for_status()

    async def test_delay(self, name: str, url: str = "https://www.gstatic.com/generate_204", timeout_ms: int = 5000) -> int | None:
        """Re-run the delay test for one proxy or group and return its reported delay."""
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.get(
            f"/proxies/{quote(name, safe='')}/delay",
            params={"url": url, "timeout": timeout_ms},
        )
        response.raise_for_status()
        try:
            return int(response.json().get("delay") or 0) or None
        except (ValueError, TypeError):
            return None

    async def reload_config(self, payload: str) -> None:
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.put("/configs?force=true", json={"payload": payload})
        response.raise_for_status()

    async def refresh_rule_provider(self, provider: str) -> None:
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.put(f"/providers/rules/{quote(provider, safe='')}")
        response.raise_for_status()

    async def delete(self, path: str) -> None:
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.delete(path)
        response.raise_for_status()

    async def close_connections(self, connection_ids: list[str]) -> tuple[int, int]:
        semaphore = asyncio.Semaphore(16)

        async def close_one(connection_id: str) -> bool:
            async with semaphore:
                try:
                    await self.delete(f"/connections/{quote(connection_id, safe='')}")
                    return True
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        return False
                    raise

        results = await asyncio.gather(*(close_one(item) for item in connection_ids), return_exceptions=True)
        return sum(result is True for result in results), sum(isinstance(result, Exception) for result in results)

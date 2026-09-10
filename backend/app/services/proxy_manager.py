"""
Proxy Manager (Phase 3 — Task 3.5).

Nguyên tắc: mỗi clone bám cố định 1 IP. Đổi IP liên tục còn đáng ngờ hơn
là dùng mãi một IP sạch. Chỉ xoay proxy khi proxy đó dính sự cố.
"""
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.clone_account import CloneAccount, Proxy
from app.models.enums import ProxyStatus


class NoProxyAvailable(Exception):
    """Pool đã cạn proxy khả dụng."""


class ProxyManager:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def available_proxies(self, user_id: str | None = None) -> list[Proxy]:
        """Proxy dùng được: chưa gán, chưa blacklist, thuộc user hoặc pool chung."""
        stmt = select(Proxy).where(Proxy.status == ProxyStatus.AVAILABLE.value)
        if user_id is not None:
            stmt = stmt.where(
                or_(Proxy.owner_user_id.is_(None), Proxy.owner_user_id == user_id)
            )
        result = await self.db.execute(stmt.order_by(Proxy.created_at.asc()))
        return list(result.scalars().all())

    async def get_proxy_for_clone(self, clone_id: str) -> Proxy | None:
        result = await self.db.execute(
            select(Proxy).where(Proxy.assigned_to_clone_id == clone_id)
        )
        return result.scalars().first()

    async def assign_proxy(self, clone: CloneAccount) -> Proxy:
        """Gán proxy trống đầu tiên cho clone.

        Raises:
            NoProxyAvailable: khi pool đã hết.
        """
        existing = await self.get_proxy_for_clone(clone.id)
        if existing is not None:
            return existing

        candidates = await self.available_proxies(clone.user_id)
        if not candidates:
            raise NoProxyAvailable(
                "Hết proxy khả dụng trong pool — hãy thêm proxy trước khi chạy clone."
            )

        proxy = candidates[0]
        proxy.status = ProxyStatus.ASSIGNED.value
        proxy.assigned_to_clone_id = clone.id
        proxy.assigned_at = utcnow()
        clone.proxy_address = proxy.address
        await self.db.flush()
        return proxy

    async def blacklist_proxy(self, proxy: Proxy, reason: str) -> Proxy:
        proxy.status = ProxyStatus.BLACKLISTED.value
        proxy.blacklisted_at = utcnow()
        proxy.blacklist_reason = reason
        proxy.assigned_to_clone_id = None
        proxy.is_healthy = False
        await self.db.flush()
        return proxy

    async def rotate_proxy(self, clone: CloneAccount, reason: str) -> Proxy:
        """Blacklist proxy đang dùng rồi gán proxy mới cho clone."""
        old = await self.get_proxy_for_clone(clone.id)
        if old is not None:
            await self.blacklist_proxy(old, reason)
        clone.proxy_address = None
        await self.db.flush()
        return await self.assign_proxy(clone)

    async def release_proxy(self, clone: CloneAccount) -> None:
        """Trả proxy về pool khi clone bị xoá (không blacklist — proxy vẫn tốt)."""
        proxy = await self.get_proxy_for_clone(clone.id)
        if proxy is None:
            return
        proxy.assigned_to_clone_id = None
        proxy.assigned_at = None
        if proxy.status == ProxyStatus.ASSIGNED.value:
            proxy.status = ProxyStatus.AVAILABLE.value
        await self.db.flush()

    async def record_health(self, proxy: Proxy, healthy: bool) -> Proxy:
        proxy.is_healthy = healthy
        proxy.last_health_check = utcnow()
        if not healthy and proxy.status != ProxyStatus.BLACKLISTED.value:
            proxy.status = ProxyStatus.DEAD.value
        await self.db.flush()
        return proxy

    async def pool_overview(self, user_id: str | None = None) -> dict:
        stmt = select(Proxy)
        if user_id is not None:
            stmt = stmt.where(
                or_(Proxy.owner_user_id.is_(None), Proxy.owner_user_id == user_id)
            )
        proxies = list((await self.db.execute(stmt)).scalars().all())
        counts: dict[str, int] = {}
        for proxy in proxies:
            counts[proxy.status] = counts.get(proxy.status, 0) + 1
        return {"total": len(proxies), "by_status": counts}


async def check_proxy_health(address: str, timeout_seconds: float = 10.0) -> bool:
    """Ping Facebook qua proxy để xem IP còn sống không.

    Dùng httpx (đã có sẵn trong requirements) thay vì aiohttp để bớt phụ thuộc.
    Mọi lỗi mạng đều quy về 'không khoẻ' — im lặng bỏ qua sẽ nguy hiểm hơn.
    """
    try:
        import httpx

        async with httpx.AsyncClient(
            proxy=address, timeout=timeout_seconds, follow_redirects=True
        ) as client:
            response = await client.get("https://www.facebook.com/")
            return response.status_code < 400
    except Exception:
        return False

"""破局平台接口客户端。

基于 httpx 异步封装，负责调用破局平台抓包接口。所有请求统一携带
Authorization 请求头（MVP 手动配置 Token）。

异常处理（对齐技术方案 7.3）：
- 401/403 → PojuAuthError（Token 失效，不重试）
- 超时/网络错误 → PojuNetworkError（指数退避重试，最多 3 次）
- 其它非 2xx → PojuApiError（业务错误）
- 调用 status='pending' 的接口 → PojuNotAvailable（降级）

⚠️ 接口 URL/字段为占位（见 endpoints.py），真实接口定义明确后需替换
   响应字段映射逻辑。当前实现对响应做基本健壮性解析，字段缺失时返回
   空结构而非崩溃，便于真实接口接入后渐进完善。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.poju.auth import TokenManager
from app.poju.endpoints import ENDPOINTS, PojuEndpoint
from app.poju.exceptions import (
    PojuApiError,
    PojuAuthError,
    PojuNetworkError,
    PojuNotAvailable,
)

logger = logging.getLogger(__name__)

# 网络错误最大重试次数
MAX_RETRIES = 3
# 单次请求超时（秒）
DEFAULT_TIMEOUT = 30.0


class PojuClient:
    """破局平台接口异步客户端。"""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_manager = TokenManager(token)
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def _request(
        self,
        endpoint: PojuEndpoint,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """统一请求封装：鉴权检查、异常映射、网络重试。

        Args:
            endpoint: 接口端点定义。
            params: 查询参数。
            json: 请求体。

        Returns:
            解析后的 JSON 响应（dict 或 list）。

        Raises:
            PojuNotAvailable: 接口 pending/未开放。
            PojuAuthError: Token 失效（401/403）。
            PojuNetworkError: 网络超时/连接错误（重试耗尽）。
            PojuApiError: 其它非 2xx 业务错误。
        """
        if endpoint.status == "pending":
            raise PojuNotAvailable(f"接口「{endpoint.name}」待确认/未开放，暂不可用")

        url = f"{self.base_url}{endpoint.path}"
        headers = self.token_manager.get_headers()
        client = await self._get_client()

        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.request(
                    endpoint.method, url, params=params, json=json, headers=headers
                )
                # 鉴权失败不重试
                if response.status_code in (401, 403):
                    raise PojuAuthError(
                        f"破局 Token 失效（HTTP {response.status_code}），请到接口配置更新"
                    )
                # 其它非 2xx 为业务错误，不重试
                if response.status_code >= 400:
                    raise PojuApiError(
                        f"破局接口业务错误（HTTP {response.status_code}）: "
                        f"{response.text[:200]}"
                    )
                # 解析 JSON，空响应返回 None
                if not response.content:
                    return None
                return response.json()
            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "破局接口超时（第 %d/%d 次）: %s", attempt, MAX_RETRIES, endpoint.path
                )
            except httpx.NetworkError as exc:
                last_exc = exc
                logger.warning(
                    "破局接口网络错误（第 %d/%d 次）: %s",
                    attempt,
                    MAX_RETRIES,
                    endpoint.path,
                )
            except (PojuAuthError, PojuApiError, PojuNotAvailable):
                # 这些异常不重试，直接上抛
                raise
            # 指数退避：1s, 2s, 4s
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** (attempt - 1))

        raise PojuNetworkError(
            f"破局接口网络错误（重试 {MAX_RETRIES} 次后失败）: {endpoint.path} - {last_exc}"
        )

    # ------------------------------------------------------------------
    # 读接口
    # ------------------------------------------------------------------

    async def fetch_checkin_records(self, camp_id: int | None = None) -> list[dict[str, Any]]:
        """拉取学员打卡记录（读接口，志愿者看板数据来源）。

        ⚠️ 响应字段映射为占位：返回标准化字典列表，字段含义待真实接口定义明确后调整。
        当前预期字段：poju_student_id, poju_checkin_id, nickname, content,
        images, submitted_at, stars, day_number, checkin_date。

        Args:
            camp_id: 行动营本地 ID（用于过滤，若接口支持）。

        Returns:
            标准化打卡记录字典列表；接口返回空或异常时返回空列表。
        """
        endpoint = ENDPOINTS["fetch_checkins"]
        params = {"camp_id": camp_id} if camp_id is not None else None
        try:
            data = await self._request(endpoint, params=params)
        except PojuAuthError:
            raise
        except (PojuApiError, PojuNetworkError):
            # 读接口失败返回空列表，调用方据 last_synced_at 判断
            logger.warning("拉取打卡记录失败，返回空列表")
            return []
        if not data:
            return []
        if isinstance(data, dict) and "list" in data:
            data = data["list"]
        if not isinstance(data, list):
            return []
        return [self._normalize_checkin(item) for item in data]

    def _normalize_checkin(self, item: dict[str, Any]) -> dict[str, Any]:
        """将接口返回的原始打卡记录标准化。

        字段映射为占位，真实接口字段名明确后在此统一适配。
        """
        return {
            "poju_student_id": str(item.get("student_id") or item.get("poju_student_id") or ""),
            "poju_checkin_id": str(item.get("checkin_id") or item.get("id") or ""),
            "nickname": item.get("nickname") or item.get("name") or "",
            "content": item.get("content") or item.get("text") or "",
            "images": item.get("images") or [],
            "submitted_at": item.get("submitted_at") or item.get("created_at"),
            "stars": item.get("stars"),
            "day_number": item.get("day_number"),
            "checkin_date": item.get("checkin_date") or item.get("date"),
        }

    async def verify_token(self) -> bool:
        """校验 Token 有效性（调用一次读接口验证）。

        Returns:
            True 表示 Token 有效；False 或抛 PojuAuthError 表示失效。
        """
        try:
            await self.fetch_checkin_records()
            return True
        except PojuAuthError:
            return False

    # ------------------------------------------------------------------
    # 写接口
    # ------------------------------------------------------------------

    async def submit_grade(
        self,
        student_id: str,
        checkin_id: str,
        stars: int,
        comment: str,
    ) -> bool:
        """给学员作业打分和评价（写接口，已验证）。

        Args:
            student_id: 破局学员唯一标识。
            checkin_id: 破局打卡记录唯一标识。
            stars: 星级 1-3。
            comment: 评语。

        Returns:
            True 表示同步成功。

        Raises:
            PojuAuthError / PojuApiError / PojuNetworkError: 同步失败（调用方需保留本地数据并支持重试）。
        """
        endpoint = ENDPOINTS["submit_grade"]
        payload = {
            "student_id": student_id,
            "checkin_id": checkin_id,
            "stars": stars,
            "comment": comment,
        }
        await self._request(endpoint, json=payload)
        logger.info("作业打分同步成功 student=%s checkin=%s stars=%d", student_id, checkin_id, stars)
        return True

    async def submit_checkin(
        self,
        content: str,
        images: list[str] | None = None,
    ) -> bool:
        """提交学员打卡（写接口，待确认）。

        ⚠️ 该接口 status='pending'，当前调用会抛 PojuNotAvailable，
        强制降级为手动提交。真实接口确认后更新 endpoints.py 状态即可启用。

        Raises:
            PojuNotAvailable: 接口待确认，不可用。
        """
        endpoint = ENDPOINTS["submit_checkin"]
        payload = {"content": content, "images": images or []}
        await self._request(endpoint, json=payload)
        logger.info("学员打卡提交成功")
        return True

    async def close(self) -> None:
        """关闭底层 httpx 客户端，释放连接。"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

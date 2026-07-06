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

日志约定（DEBUG 排查用）：
- ``logger.info``：所有破局接口的请求/响应（脱敏后）
- ``logger.warning``：单页失败、重试
- ``logger.error``：未捕获异常
- 响应体在超过 4KB 时截断到前 4KB，便于人工阅读
- Authorization / Cookie 头只在请求时打印 key 名，不打 value
"""

from __future__ import annotations

import asyncio
import json
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
# 响应体打印最大字节数（防止日志爆炸）
RESPONSE_LOG_MAX_BYTES = 4096


def _truncate_for_log(value: Any, limit: int = RESPONSE_LOG_MAX_BYTES) -> str:
    """把任意响应值截短到 limit 字节，便于日志输出。"""
    try:
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = repr(value)[: limit * 2]
    if len(text.encode("utf-8")) > limit:
        b = text.encode("utf-8")[:limit]
        return b.decode("utf-8", errors="ignore") + f"…(truncated, total {len(text)} chars)"
    return text


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

        除统一鉴权/异常映射外，会把每个请求 URL / method / body / 响应码 /
        响应体（截断）打到 INFO 级日志，便于排查"0 条"等数据问题。

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
        # 脱敏：只打印 Authorization 头名，不打 token
        try:
            header_keys = sorted(self.token_manager.get_headers().keys())
        except Exception:  # noqa: BLE001
            header_keys = ["authorization"]
        logger.info(
            "破局请求 → %s %s headers=%s params=%s json=%s",
            endpoint.method,
            url,
            header_keys,
            _truncate_for_log(params) if params else None,
            _truncate_for_log(json) if json else None,
        )

        client = await self._get_client()

        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.request(
                    endpoint.method,
                    url,
                    params=params,
                    json=json,
                    headers=self.token_manager.get_headers(),
                )
                # 鉴权失败不重试
                if response.status_code in (401, 403):
                    logger.warning(
                        "破局鉴权失败（%d）: %s %s body=%s",
                        response.status_code,
                        endpoint.method,
                        url,
                        _truncate_for_log(response.text),
                    )
                    raise PojuAuthError(
                        f"破局 Token 失效（HTTP {response.status_code}），请到接口配置更新"
                    )
                # 其它非 2xx 为业务错误，不重试
                if response.status_code >= 400:
                    logger.warning(
                        "破局业务错误（%d）: %s %s body=%s",
                        response.status_code,
                        endpoint.method,
                        url,
                        _truncate_for_log(response.text),
                    )
                    raise PojuApiError(
                        f"破局接口业务错误（HTTP {response.status_code}）: "
                        f"{response.text[:200]}"
                    )
                # 解析 JSON，空响应返回 None
                if not response.content:
                    logger.info(
                        "破局响应 ← %d %s %s (空 body)",
                        response.status_code,
                        endpoint.method,
                        url,
                    )
                    return None
                # 日志：响应码 + body 顶部预览（截断到 4KB）
                logger.info(
                    "破局响应 ← %d %s %s body=%s",
                    response.status_code,
                    endpoint.method,
                    url,
                    _truncate_for_log(response.text),
                )
                body = response.json()
                # 业务码识别：部分破局端点 HTTP 200 但用 body.code 表达鉴权/业务错误。
                # 已识别到的 code：401（请登录）/ 403 / 500（业务异常）。
                # 注意：query-people 的真实响应 code=200，但 PagesTool 调用其它端点
                # 可能仍按 HTTP 状态码表达错误；两者各自识别一次。
                if isinstance(body, dict):
                    biz_code = body.get("code")
                    biz_msg = body.get("msg") or body.get("message")
                    # 业务码若是 401/403 等鉴权失败 → 转抛 PojuAuthError
                    if biz_code in (401, 403):
                        logger.warning(
                            "破局业务鉴权失败（code=%s）: %s %s msg=%s",
                            biz_code,
                            endpoint.method,
                            url,
                            biz_msg,
                        )
                        raise PojuAuthError(
                            f"破局 Token 失效（业务码 {biz_code}），请到接口配置更新"
                        )
                    # 业务码若是 5xx → 视为业务错误
                    if isinstance(biz_code, int) and 500 <= biz_code < 600:
                        logger.warning(
                            "破局业务异常（code=%s）: %s %s msg=%s",
                            biz_code,
                            endpoint.method,
                            url,
                            biz_msg,
                        )
                        raise PojuApiError(
                            f"破局业务异常（code={biz_code}）: {biz_msg or '无 msg'}"
                        )
                return body
            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "破局接口超时（第 %d/%d 次）: %s - %s",
                    attempt,
                    MAX_RETRIES,
                    endpoint.path,
                    exc,
                )
            except httpx.NetworkError as exc:
                last_exc = exc
                logger.warning(
                    "破局接口网络错误（第 %d/%d 次）: %s - %s",
                    attempt,
                    MAX_RETRIES,
                    endpoint.path,
                    exc,
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

        Raises:
            PojuAuthError: Token 失效（401/403），上抛。
            PojuApiError: 业务错误（4xx/5xx），上抛（修复 BUG-PJU-001：不再静默吞）。
            PojuNetworkError: 网络错误，上抛。
            PojuNotAvailable: 接口 pending/未开放，上抛。
        """
        endpoint = ENDPOINTS["fetch_checkins"]
        params = {"camp_id": camp_id} if camp_id is not None else None
        # 注意：不再静默吞 PojuNetworkError/PojuApiError，
        # 否则 verify_token 在网络错时永远返回 True（假阳性）。
        data = await self._request(endpoint, params=params)
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

    async def fetch_volunteer_people(
        self,
        action_id: str,
        *,
        page_size: int = 50,
        max_pages: int = 100,
        user_number: str = "",
        wechat_name: str = "",
    ) -> tuple[list[dict[str, Any]], list[str], int]:
        """拉取某 actionId 下志愿者看板的全部学员（query-people）。

        ⚠️ 此接口由破局按 POST + body 返回分页结果 (pageNum / pageSize /
        total / records)。本期志愿者通常带教 30 人左右，page_size=50 一般
        一页就够；max_pages 默认 100 足以覆盖人工带教规模（5000 人封顶）。

        错误处理（与对齐 PRD：失败不阻断已有数据展示）：
        - PojuAuthError（401/403）→ 立刻上抛（统一异常处理器接管为 401）。
        - 其它任意一页网络/业务错 → 跳过该页，把 (page, error) 追加到
          ``errors`` 列表，继续翻页；不停、不抛。
        - total <= 0 或 records 为空 → 直接结束。

        Args:
            action_id: 破局行动营 UUID（来自 camp.poju_action_id）。
            page_size: 每页条数，默认 50。
            max_pages: 最大翻页次数（防御性上限），默认 100。
            user_number: 可选筛选。
            wechat_name: 可选筛选。

        Returns:
            (records_normalized, errors, pages_fetched)：
              - records_normalized：标准化学员字典列表（字段名对齐 Student ORM）。
              - errors：失败分页的明细字符串列表，UI 可直接展示。
              - pages_fetched：实际成功遍历的页数（含后续跳过错误页）。

        Raises:
            PojuAuthError: Token 失效，上抛。
            PojuNotAvailable: 接口 pending，上抛。
            ValueError: action_id 为空。
        """
        if not action_id or not action_id.strip():
            raise ValueError("action_id 不能为空")

        endpoint = ENDPOINTS["query_people"]
        all_records: list[dict[str, Any]] = []
        errors: list[str] = []
        pages_fetched = 0

        page = 1
        total: Optional[int] = None
        while True:
            if page > max_pages:
                logger.warning(
                    "query-people 翻页超上限 %d (action_id=%s)，停止",
                    max_pages,
                    action_id,
                )
                errors.append(f"翻页超过最大页数 {max_pages}，请检查 pageSize 配置")
                break

            payload = {
                "pageNum": page,
                "pageSize": page_size,
                "filters": {
                    "userNumber": user_number or "",
                    "wechatName": wechat_name or "",
                    "actionId": action_id,
                },
            }
            try:
                resp = await self._request(endpoint, json=payload)
                pages_fetched += 1
            except PojuAuthError:
                # 立刻上抛，统一异常处理器映射为 401
                raise
            except (PojuApiError, PojuNetworkError, PojuNotAvailable) as exc:
                # 单页失败：跳过该页，继续翻页
                logger.warning(
                    "query-people 第 %d 页失败(action_id=%s): %s",
                    page,
                    action_id,
                    exc,
                )
                errors.append(f"第 {page} 页失败：{exc}")
                page += 1
                continue

            data = self._extract_people_payload(resp)
            if total is None:
                total = data["total"]
            records = data["records"]
            if not records:
                # 多数情况下 records 为空就表示翻完了
                break
            all_records.extend(self._normalize_people(r) for r in records)
            page += 1
            # 翻到 total 用完为止：total=30, pageSize=50 时第 1 页就够
            if total is not None and total <= page_size * (page - 1):
                break

        return all_records, errors, pages_fetched

    @staticmethod
    def _extract_people_payload(resp: Any) -> dict[str, Any]:
        """从 query-people 响应中剥出 {total, records}。

        兼容以下响应形态（按顺序探测，第一个命中即返回）：
        1. ``{"code":200,"data":{"total":N,"records":[...]}}``  ← 当前已知
        2. ``{"code":200,"data":{"pageSize":N,"pageNum":P,"total":N,"records":[...]}}``  ← 同 1
        3. ``{"total":N,"records":[...]}}``  ← 平铺
        4. ``{"pageSize":N,"pageNum":P,"total":N,"records":[...]}}``  ← 同 3
        5. ``{"code":200,"msg":"...","data":{...records...}}``  ← code 字段名兼容
        6. 任何 dict 含 records 键 → 视为 records 列表（不验 total）

        任意非 dict 响应（如 list/空）一律视为空数据。

        探测结果每次都打到 INFO 日志（透出字段名），便于排查
        "接口通了但 0 条" 类 bug。
        """
        def _to_int(v: Any) -> int:
            if v is None or v == "":
                return 0
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0

        if not isinstance(resp, dict):
            logger.info(
                "query-people: 响应非 dict 类型 (type=%s)，视为空数据", type(resp).__name__
            )
            return {"total": 0, "records": []}

        # 拆出内层 payload：支持 data 嵌套或平铺
        payload: Any = resp
        if "data" in resp and isinstance(resp["data"], dict):
            payload = resp["data"]
            logger.info(
                "query-people: 检测到 data 嵌套结构，外层 keys=%s",
                sorted(resp.keys()),
            )
        else:
            logger.info(
                "query-people: 未检测到 data 嵌套，使用顶层 keys=%s 作为 payload",
                sorted(resp.keys()),
            )

        if not isinstance(payload, dict):
            logger.info(
                "query-people: payload 非 dict (type=%s)，视为空数据",
                type(payload).__name__,
            )
            return {"total": 0, "records": []}

        # total 字段兼容
        total = 0
        for key in ("total", "totalCount", "totalNum", "count", "size"):
            if key in payload:
                total = _to_int(payload[key])
                if total > 0:
                    logger.info("query-people: total 字段命中 key=%r value=%d", key, total)
                    break

        # records 字段兼容（兼容多个常见别名）
        records_raw: Any = []
        for key in ("records", "list", "rows", "items", "data", "result"):
            if key in payload and isinstance(payload[key], list):
                records_raw = payload[key]
                logger.info(
                    "query-people: records 字段命中 key=%r 长度=%d",
                    key,
                    len(records_raw),
                )
                break
        else:
            # 没命中 records 同义词且非空 dict → 直接遍历顶层所有 list 字段，挑最长的
            lists = [
                (k, v) for k, v in payload.items() if isinstance(v, list)
            ]
            if lists:
                k, records_raw = max(lists, key=lambda kv: len(kv[1]))
                logger.info(
                    "query-people: 未找到标准 records 字段，回退用顶层最大 list: key=%r 长度=%d",
                    k,
                    len(records_raw),
                )
            else:
                logger.info(
                    "query-people: payload 内找不到任何 list 字段，返回空 data 字段 keys=%s",
                    sorted(payload.keys()),
                )

        if not isinstance(records_raw, list):
            records_raw = []

        return {"total": total, "records": records_raw}

    @staticmethod
    def _normalize_people(item: dict[str, Any]) -> dict[str, Any]:
        """把 query-people 单条记录标准化为 Student ORM 同名字段。

        缺失字段返回 None；目标表对应列均 nullable，缺失即跳过，
        不阻断整条 upsert。可空字段缺失时不视为"该条无效"。
        """
        def _s(v: Any) -> Optional[str]:
            """去空白字符串 + 转 str；空字符串归 None。"""
            if v is None:
                return None
            s = str(v).strip()
            return s or None

        def _i(v: Any) -> Optional[int]:
            """尽量转 int；失败回 None（不阻断整条）。"""
            if v is None or v == "":
                return None
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        return {
            # 唯一键：破局 user UUID
            "poju_student_id": _s(item.get("id")),
            # 最小字段（与历史同步对齐）
            "nickname": _s(item.get("fullName")) or _s(item.get("wechatName")),
            "wechat": _s(item.get("wechatId")),
            # 档案全字段
            "full_name": _s(item.get("fullName")),
            "wechat_id": _s(item.get("wechatId")),
            "wechat_name": _s(item.get("wechatName")),
            "phone": _s(item.get("phone")),
            "user_name": _s(item.get("userName")),
            "user_number": _s(item.get("userNumber")),
            "leader_name": _s(item.get("leaderName")),
            "leader_user_name": _s(item.get("leaderUserName")),
            "leader_wechat_id": _s(item.get("leaderWechatId")),
            "volunteer_name": _s(item.get("volunteerName")),
            "volunteer_user_name": _s(item.get("volunteerUserName")),
            "volunteer_wechat_id": _s(item.get("volunteerWechatId")),
            "data_officer_name": _s(item.get("dataOfficerName")),
            "data_officer_user_name": _s(item.get("dataOfficerUserName")),
            "data_officer_wechat_id": _s(item.get("dataOfficerWechatId")),
            "clock_in_count": _i(item.get("clockInCount")),
            "camp_days": _i(item.get("campDays")),
        }

    async def verify_token(self) -> bool:
        """校验 Token 有效性（调用一次读接口验证）。

        Returns:
            True: Token + base_url 均可连通。
            False: Token 失效（401/403）、网络错、业务错或接口 pending 均视为无效。

        Raises:
            不抛任何 Poju 异常；调用方只看 True/False。
        """
        try:
            await self.fetch_checkin_records()
            return True
        except (
            PojuAuthError,
            PojuApiError,
            PojuNetworkError,
            PojuNotAvailable,
        ):
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

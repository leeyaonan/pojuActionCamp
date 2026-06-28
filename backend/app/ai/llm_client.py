"""大模型客户端封装。

按技术方案 6.2 实现，统一封装 anthropic / openai SDK：

- ``__init__`` 按 provider 初始化对应 SDK 客户端。
- ``chat`` 非流式调用：传 ``response_schema`` 时强制结构化输出并 Pydantic 校验，
  anthropic 用 tool_use 强制 JSON，openai 用 ``response_format=json_schema``。
  校验失败按指数退避重试，最多 3 次。
- ``chat_stream`` 流式异步生成器，yield 增量文本。
- 超时与异常统一抛 ``LLMError``（对应错误码 3001）。
- ``get_llm_client(settings)`` 工厂，缓存单例。

说明：
- anthropic SDK 与 openai SDK 均为同步客户端，这里用 ``anyio.to_thread.run_sync``
  把同步调用包到线程中执行，避免阻塞 asyncio 事件循环；流式则把同步迭代器
  的逐块产出经队列回传到事件循环后 yield。
- 配置项来自 ``settings``（app/config.py 提供）：``llm_provider`` / ``llm_api_key``
  / ``llm_model`` / ``llm_timeout``。
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Optional, Type

import anyio
from pydantic import BaseModel, ValidationError

from app.core.exceptions import LLMError as _CoreLLMError

logger = logging.getLogger(__name__)

# 默认重试与退避参数（技术方案 6.2：指数退避，最多 3 次）
_MAX_RETRIES = 3
_BASE_BACKOFF = 1.0  # 秒，指数退避基数：1s, 2s, 4s ...


class LLMError(_CoreLLMError):
    """大模型调用异常（继承自 core.LLMError，code=3001, http_status=502）。

    兼容旧 API：``raise LLMError(msg, cause=e)`` 中 ``cause`` 仅作属性存根，
    不参与 HTTP 响应序列化。如需溯源，使用 ``raise ... from e``。
    """

    def __init__(self, message: str, *, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.cause = cause


class LLMClient:
    """统一大模型客户端。

    Parameters
    ----------
    provider:
        ``"anthropic"`` 或 ``"openai"``。
    api_key:
        对应 provider 的 API Key。
    model:
        模型名，如 ``claude-sonnet-4-6``、``gpt-4o``。
    timeout:
        请求超时秒数。
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        timeout: int = 60,
    ) -> None:
        self.provider = provider.lower()
        self.model = model
        self.timeout = timeout

        if self.provider == "anthropic":
            try:
                import anthropic  # type: ignore
            except ImportError as e:  # pragma: no cover
                raise LLMError("未安装 anthropic SDK，请 pip install anthropic") from e
            self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        elif self.provider == "openai":
            try:
                import openai  # type: ignore
            except ImportError as e:  # pragma: no cover
                raise LLMError("未安装 openai SDK，请 pip install openai") from e
            self._client = openai.OpenAI(api_key=api_key, timeout=timeout)
        else:
            raise LLMError(f"不支持的 llm_provider: {provider}")

    # ------------------------------------------------------------------ #
    # 非流式：chat
    # ------------------------------------------------------------------ #
    async def chat(
        self,
        system: str,
        messages: list[dict],
        response_schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.7,
    ) -> BaseModel | str:
        """非流式调用大模型。

        Parameters
        ----------
        system:
            系统提示词。
        messages:
            对话消息列表，``[{"role": "user"|"assistant", "content": "..."}]``。
        response_schema:
            若提供，则强制结构化输出并以此 Pydantic 模型校验。
        temperature:
            采样温度。

        Returns
        -------
        BaseModel | str
            传入 schema 时返回校验后的 Pydantic 模型实例；否则返回纯文本。

        Raises
        ------
        LLMError
            超时、网络异常或结构化校验重试耗尽时抛出。
        """
        last_err: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if response_schema is not None:
                    raw = await self._chat_structured(system, messages, response_schema, temperature)
                    return raw  # 已是校验后的 BaseModel 实例
                text = await self._chat_text(system, messages, temperature)
                return text
            except ValidationError as e:
                # 结构化输出校验失败 → 重试
                last_err = e
                logger.warning(
                    "LLM 结构化输出校验失败(第 %d/%d 次): %s", attempt, _MAX_RETRIES, e
                )
            except LLMError as e:
                # 超时 / 网络类错误 → 重试
                last_err = e
                logger.warning(
                    "LLM 调用失败(第 %d/%d 次): %s", attempt, _MAX_RETRIES, e
                )
            except Exception as e:  # SDK 抛出的其它异常
                last_err = e
                logger.warning(
                    "LLM 调用异常(第 %d/%d 次): %s", attempt, _MAX_RETRIES, e
                )

            # 未到末次则退避等待
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BASE_BACKOFF * (2 ** (attempt - 1)))

        raise LLMError(
            f"LLM 调用失败，已重试 {_MAX_RETRIES} 次: {last_err}", cause=last_err
        )

    # ------------------------------------------------------------------ #
    # 流式：chat_stream
    # ------------------------------------------------------------------ #
    async def chat_stream(
        self,
        system: str,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """流式调用大模型，异步生成器，逐块 yield 增量文本。

        流式不强制结构化输出（结构化场景请用 chat）。
        超时或异常抛 LLMError。
        """
        try:
            if self.provider == "anthropic":
                async for chunk in self._stream_anthropic(system, messages, temperature):
                    yield chunk
            else:
                async for chunk in self._stream_openai(system, messages, temperature):
                    yield chunk
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"LLM 流式调用失败: {e}", cause=e) from e

    # ------------------------------------------------------------------ #
    # 纯文本调用
    # ------------------------------------------------------------------ #
    async def _chat_text(
        self, system: str, messages: list[dict], temperature: float
    ) -> str:
        if self.provider == "anthropic":
            resp = await anyio.to_thread.run_sync(
                lambda: self._client.messages.create(
                    model=self.model,
                    system=system,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=4096,
                )
            )
            # 提取文本块
            return "".join(
                block.text for block in resp.content if getattr(block, "type", None) == "text"
            )
        else:
            resp = await anyio.to_thread.run_sync(
                lambda: self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, *messages],
                    temperature=temperature,
                )
            )
            return resp.choices[0].message.content or ""

    # ------------------------------------------------------------------ #
    # 结构化输出
    # ------------------------------------------------------------------ #
    async def _chat_structured(
        self,
        system: str,
        messages: list[dict],
        schema: Type[BaseModel],
        temperature: float,
    ) -> BaseModel:
        """强制结构化输出并用 Pydantic 校验。

        - anthropic：用 tool_use 强制返回 JSON，从 tool_input 提取后校验。
        - openai：用 ``response_format={"type": "json_schema", ...}`` 约束。
        校验失败抛 ValidationError（由上层 chat 重试）。
        """
        schema_json = schema.model_json_schema()

        if self.provider == "anthropic":
            tool_name = "return_result"
            result = await anyio.to_thread.run_sync(
                lambda: self._client.messages.create(
                    model=self.model,
                    system=system,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=4096,
                    tools=[
                        {
                            "name": tool_name,
                            "description": "返回结构化结果，必须严格符合 schema",
                            "input_schema": _json_schema_to_input_schema(schema_json),
                        }
                    ],
                    tool_choice={"type": "tool", "name": tool_name},
                )
            )
            # 从 tool_use 块提取 input
            data: Any = None
            for block in result.content:
                if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                    data = block.input
                    break
            if data is None:
                raise ValidationError.from_exception_data(
                    "未在响应中找到 tool_use 块", []
                )
            return schema.model_validate(data)

        else:
            # openai json_schema 结构化输出
            resp = await anyio.to_thread.run_sync(
                lambda: self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, *messages],
                    temperature=temperature,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema.__name__,
                            "schema": _json_schema_to_strict(schema_json),
                            "strict": True,
                        },
                    },
                )
            )
            content = resp.choices[0].message.content or ""
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise ValidationError.from_exception_data(
                    f"响应非合法 JSON: {e}", []
                ) from e
            return schema.model_validate(data)

    # ------------------------------------------------------------------ #
    # 流式实现
    # ------------------------------------------------------------------ #
    async def _stream_anthropic(
        self, system: str, messages: list[dict], temperature: float
    ) -> AsyncIterator[str]:
        with self._client.messages.stream(
            model=self.model,
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=4096,
        ) as stream:
            # SDK 的 stream 是同步迭代器，包到线程里逐块经队列回传
            queue: asyncio.Queue = asyncio.Queue()
            sentinel = object()

            def _produce() -> None:
                try:
                    for text in stream.text_stream:
                        queue.put_nowait(text)
                except Exception as e:  # noqa: BLE001
                    queue.put_nowait(e)
                finally:
                    queue.put_nowait(sentinel)

            asyncio.get_running_loop().run_in_executor(None, _produce)
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item

    async def _stream_openai(
        self, system: str, messages: list[dict], temperature: float
    ) -> AsyncIterator[str]:
        stream = await anyio.to_thread.run_sync(
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, *messages],
                temperature=temperature,
                stream=True,
            )
        )
        # openai 流式迭代器是同步的，逐块取回
        for chunk in await anyio.to_thread.run_sync(lambda: list(stream)):
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


# --------------------------------------------------------------------- #
# JSON Schema 适配工具
# --------------------------------------------------------------------- #
def _json_schema_to_input_schema(schema: dict) -> dict:
    """把 Pydantic 生成的 json_schema 适配为 anthropic tool input_schema。

    Pydantic 的 json_schema 已是标准 JSON Schema，直接返回即可。
    这里做一次深拷贝避免外部改动影响缓存。
    """
    return json.loads(json.dumps(schema))


def _json_schema_to_strict(schema: dict) -> dict:
    """把 Pydantic json_schema 适配为 openai strict json_schema。

    openai strict 模式要求：
    - 所有 object 的 ``additionalProperties`` 为 false；
    - 所有属性加入 required；
    - 顶层有 ``type``；
    - 不允许 ``$ref``（需内联展开）。
    这里做递归内联与属性补全。
    """
    import copy

    defs = schema.get("$defs") or schema.get("definitions") or {}
    schema = copy.deepcopy(schema)
    schema.pop("$defs", None)
    schema.pop("definitions", None)
    schema = _inline_refs(schema, defs)

    def _walk(node: Any) -> Any:
        if isinstance(node, list):
            return [_walk(x) for x in node]
        if not isinstance(node, dict):
            return node
        node = {k: _walk(v) for k, v in node.items()}
        if node.get("type") == "object":
            node.setdefault("additionalProperties", False)
            props = node.get("properties", {})
            if props:
                node["required"] = list(props.keys())
        return node

    return _walk(schema)


def _inline_refs(node: Any, defs: dict) -> Any:
    """递归把 ``$ref`` 替换为 defs 中对应的真实 schema（深拷贝）。"""
    import copy

    if isinstance(node, list):
        return [_inline_refs(x, defs) for x in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        ref = node["$ref"]
        # 形如 #/$defs/Foo 或 #/definitions/Foo
        key = ref.rsplit("/", 1)[-1]
        target = defs.get(key)
        if target is not None:
            return _inline_refs(copy.deepcopy(target), defs)
        return node
    return {k: _inline_refs(v, defs) for k, v in node.items()}


# --------------------------------------------------------------------- #
# 工厂与单例
# --------------------------------------------------------------------- #
_client_singleton: Optional[LLMClient] = None
_singleton_key: Optional[tuple] = None


def get_llm_client(settings: Any) -> LLMClient:
    """根据 settings 创建/复用 LLMClient 单例。

    settings 需提供：``llm_provider``、``llm_api_key``、``llm_model``、``llm_timeout``。
    单例按 (provider, api_key, model, timeout) 缓存，配置变化时自动重建。
    """
    global _client_singleton, _singleton_key
    key = (
        settings.llm_provider,
        settings.llm_api_key,
        settings.llm_model,
        settings.llm_timeout,
    )
    if _client_singleton is None or _singleton_key != key:
        _client_singleton = LLMClient(
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout,
        )
        _singleton_key = key
    return _client_singleton

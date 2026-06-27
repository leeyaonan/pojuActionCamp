"""AI 编排层。

按技术方案第六章实现，包含：
- LLMClient：统一封装 anthropic / openai SDK，支持结构化输出、流式、重试、超时。
- PromptEngine：加载与渲染外置提示词模板。
- schemas：AI 输出的 Pydantic 模型，供结构化输出校验。
- prompts/*.txt：外置提示词模板。

使用示例::

    from app.ai import LLMClient, PromptEngine, get_llm_client
    from app.ai.schemas import RoutePlanAI

    client = get_llm_client(settings)
    engine = PromptEngine()
    prompt = engine.get_prompt("route_plan", manual_content=..., total_days=7, ...)
    result = await client.chat(system="你是学习规划专家", messages=[{"role":"user","content":prompt}], response_schema=RoutePlanAI)
"""

from app.ai.llm_client import LLMClient, LLMError, get_llm_client
from app.ai.prompt_engine import PromptEngine
from app.ai.schemas import (
    CheckinDraftAI,
    DayTaskAI,
    DimensionScore,
    GradeDraftAI,
    RoutePlanAI,
)

__all__ = [
    "LLMClient",
    "LLMError",
    "get_llm_client",
    "PromptEngine",
    "RoutePlanAI",
    "DayTaskAI",
    "CheckinDraftAI",
    "GradeDraftAI",
    "DimensionScore",
]

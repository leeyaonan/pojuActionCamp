"""破局接口适配层。

对外提供 PojuClient（httpx 异步封装），负责与破局平台抓包接口交互：
- 拉取学员打卡记录（读）
- 给学员作业打分和评价（写）
- 提交学员打卡（写，待确认）
- Token 有效性校验

鉴权统一携带 Authorization 请求头（MVP 手动配置 Token）。
异常体系见 app.core.exceptions，本层 re-export 便于调用方就近导入。
"""
from app.poju.client import PojuClient
from app.poju.auth import TokenManager
from app.poju.endpoints import ENDPOINTS, PojuEndpoint

__all__ = ["PojuClient", "TokenManager", "ENDPOINTS", "PojuEndpoint"]

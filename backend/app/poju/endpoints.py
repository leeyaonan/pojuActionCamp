"""破局接口端点定义。

集中管理破局平台接口的路径、方法、读写能力与状态。破局接口定义明确后，
仅需修改本文件即可适配，避免改动散落各处（技术方案 7.2）。

⚠️ 当前 URL/字段均为占位：基于发起人上一期 Python 脚本经验确认存在
"拉取学员打卡记录"与"给学员作业打分和评价"两个接口，但最新版志愿者看板
接口尚未开放，开放后需据此替换真实路径与字段映射。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PojuEndpoint:
    """破局接口端点定义。

    Attributes:
        name: 接口中文名。
        method: HTTP 方法。
        path: 接口路径（相对 base_url）。
        capability: 'read' / 'write'。
        status: 'verified'（已验证可用）/ 'pending'（待确认/未开放）。
    """

    name: str
    method: str
    path: str
    capability: str  # 'read' | 'write'
    status: str  # 'verified' | 'pending'


ENDPOINTS: dict[str, PojuEndpoint] = {
    "fetch_checkins": PojuEndpoint(
        name="拉取学员打卡记录",
        method="GET",
        path="/api/volunteer/checkins",
        capability="read",
        status="verified",
    ),
    "submit_grade": PojuEndpoint(
        name="给学员作业打分和评价",
        method="POST",
        path="/api/volunteer/grades",
        capability="write",
        status="verified",
    ),
    "submit_checkin": PojuEndpoint(
        name="提交学员打卡",
        method="POST",
        path="/api/student/checkin",
        capability="write",
        status="pending",  # 待确认是否存在该写接口
    ),
    "fetch_self_progress": PojuEndpoint(
        name="读取学员自身打卡进度",
        method="GET",
        path="/api/student/progress",
        capability="read",
        status="pending",  # 待确认
    ),
}

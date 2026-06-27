"""志愿者功能路由（空桩）。

具体实现由后续阶段填充，对应技术方案 11.3。
"""
from fastapi import APIRouter

router = APIRouter()

# TODO(W2): 实现志愿者链路
# - POST /camps/{id}/sync           手动触发同步
# - GET  /camps/{id}/students       学员看板列表（支持筛选）
# - GET  /students/{id}             学员档案
# - GET  /camps/{id}/grades/pending 待评改列表
# - POST /grades/generate           生成评改
# - POST /grades/confirm            确认并同步
# - POST /grades/{id}/retry         重试同步
# - POST /grades/regenerate         重新生成评改

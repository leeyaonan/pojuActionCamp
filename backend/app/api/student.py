"""学员功能路由（空桩）。

具体实现由后续阶段填充，对应技术方案 11.2。
"""
from fastapi import APIRouter

router = APIRouter()

# TODO(W2): 实现学员链路
# - POST /camps/{id}/route/generate    生成学习路线
# - GET  /camps/{id}/route             获取学习路线
# - PUT  /route/tasks/{task_id}        编辑每日任务
# - POST /camps/{id}/route/regenerate  重新规划
# - GET  /camps/{id}/today             今日任务+进度
# - POST /camps/{id}/checkin/generate  生成打卡内容
# - POST /camps/{id}/checkin/submit    提交打卡（含 auto 开关）
# - GET  /camps/{id}/checkins          打卡记录列表

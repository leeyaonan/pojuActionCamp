"""接口配置路由（空桩）。

具体实现由后续阶段填充，对应技术方案 11.5。
"""
from fastapi import APIRouter

router = APIRouter()

# TODO(W2): 实现接口配置
# - GET  /settings/poju       获取接口配置（token 脱敏）
# - PUT  /settings/poju/token 更新 Token
# - POST /settings/poju/test  测试连接

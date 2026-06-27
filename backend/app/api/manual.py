"""手册管理路由（空桩）。

具体实现由后续阶段填充，对应技术方案 11.4。
"""
from fastapi import APIRouter

router = APIRouter()

# TODO(W2): 实现手册管理
# - POST   /manuals/{camp_id}/upload 上传手册文件（multipart）
# - POST   /manuals/{camp_id}/paste  粘贴手册文本
# - GET    /manuals/{camp_id}        获取手册元信息+预览
# - DELETE /manuals/{camp_id}        删除手册

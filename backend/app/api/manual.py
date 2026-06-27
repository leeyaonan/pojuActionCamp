"""手册管理路由。

对应技术方案 11.4：
- POST   /api/manuals/{camp_id}/upload  上传手册文件（multipart）
- POST   /api/manuals/{camp_id}/paste   粘贴手册文本
- GET    /api/manuals/{camp_id}         获取手册元信息（含预览）
- DELETE /api/manuals/{camp_id}         删除手册

所有路由统一返回 ``success()`` 包裹的 dict，由中间件 / 路由层负责序列化。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Path, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import success
from app.deps import get_db
from app.schemas.manual import ManualOut, ManualPreview, PasteIn
from app.services.manual_service import ManualService

router = APIRouter()


@router.post(
    "/{camp_id}/upload",
    response_model=None,
    summary="上传行动营手册",
)
async def upload_manual(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    file: UploadFile = File(..., description="手册文件（.md / .txt）"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """上传手册文件，按 camp_id 唯一覆盖。"""
    service = ManualService(db)
    manual = await service.upload_manual(camp_id=camp_id, file=file)
    payload = ManualOut.model_validate(manual).model_dump(mode="json")
    return success(payload)


@router.post(
    "/{camp_id}/paste",
    response_model=None,
    summary="粘贴行动营手册文本",
)
async def paste_manual(
    payload: PasteIn,
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """粘贴文本保存为手册（文件名 manual_paste.md）。"""
    service = ManualService(db)
    manual = await service.save_paste(camp_id=camp_id, content=payload.content)
    data = ManualOut.model_validate(manual).model_dump(mode="json")
    return success(data)


@router.get(
    "/{camp_id}",
    response_model=None,
    summary="获取手册元信息与预览",
)
async def get_manual(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    n: int = 500,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """获取手册元信息，并附带 content 前 n 字预览。

    ``ManualPreview`` 仅暴露预览字段；如需全文走 ``GET /api/manuals/{camp_id}/full``
    （后续阶段再补，本期先返回 ManualOut + 预览字段，结构兼容）。
    """
    service = ManualService(db)
    manual = await service.get_manual(camp_id=camp_id)
    preview_text = (manual.content or "")[: max(n, 0)]

    full = ManualOut.model_validate(manual).model_dump(mode="json")
    preview = ManualPreview(
        id=manual.id,
        camp_id=manual.camp_id,
        filename=manual.filename,
        word_count=manual.word_count,
        preview=preview_text,
        uploaded_at=manual.uploaded_at,
    ).model_dump(mode="json")

    # 完整手册 + 预览（前端可按需渲染）
    return success({"manual": full, "preview": preview})


@router.delete(
    "/{camp_id}",
    response_model=None,
    summary="删除行动营手册",
)
async def delete_manual(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除手册文件 + DB 记录（幂等：文件缺失不报错）。"""
    service = ManualService(db)
    await service.delete_manual(camp_id=camp_id)
    return success({"camp_id": camp_id, "deleted": True})
"""手册服务。

职责：
- 校验上传文件扩展名（仅 .md / .txt）。
- 将手册写入 data/manuals/{camp_id}/ 下，文件名固定 manual.{ext}。
- 读全文存 DB ``Manual.content``（AI 评分阶段直接读取 DB，避免重复 IO）。
- CJK 按字符计数（CJK Unicode 范围 U+4E00-U+9FFF + 全角符号等），英文按词，
  最终 ``word_count`` 取「CJK 字符数 + 英文词数」。
- upsert：``camp_id`` 唯一约束，重复上传覆盖原记录与文件。

所有写入文件系统的目录 ``data/manuals/{camp_id}/`` 由本服务创建；
不信任调用方传入的文件名 / 路径，统一以 ``manual.{ext}`` 命名以规避
路径穿越（path traversal）与目录污染。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.manual import Manual

# 允许的扩展名（小写）
ALLOWED_EXTS: tuple[str, ...] = (".md", ".txt")

# 存储根目录（相对项目根）
MANUAL_ROOT = Path("data") / "manuals"

# CJK Unicode 区段：基本汉字 + 扩展（粗略覆盖常见字）
_CJK_PATTERN = re.compile(
    r"[一-鿿"           # CJK Unified Ideographs
    r"㐀-䶿"            # CJK Extension A
    r"぀-ヿ"            # 日文假名
    r"가-힯"            # 韩文音节
    r"＀-￯"            # 全角 ASCII / 全角标点
    r"]"
)


def _safe_camp_id(camp_id: int) -> int:
    """校验 camp_id 为正整数，避免路径拼接时引入 ``..``。

    FastAPI 路径参数 ``camp_id: int`` 已在路由层解析，这里再做防御性校验。
    """
    if not isinstance(camp_id, int) or camp_id <= 0:
        raise ValidationError(f"非法 camp_id: {camp_id!r}")
    return camp_id


def _resolve_ext(filename: str | None) -> str:
    """从原始文件名解析扩展名（统一小写，限制白名单）。"""
    if not filename:
        raise ValidationError("缺少文件名")
    # Path 解析仅取 basename，避免文件名包含路径分隔符
    name = Path(filename).name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValidationError(
            f"仅支持 {'/'.join(ALLOWED_EXTS)} 格式，当前: {ext or '无扩展名'}"
        )
    return ext


def count_words(text: str) -> int:
    """字数统计：CJK 按字符、英文按空白分词数。

    策略：
    - 命中 CJK 字符的连续段，每个字符计 1。
    - 其余字母数字连续段视为一个英文词。
    - 中文段落中夹杂的英文 / 数字仍按词计数。
    """
    if not text:
        return 0
    cjk_chars = len(_CJK_PATTERN.findall(text))
    # 非 CJK 部分：替换 CJK 为空格，再按空白分词
    stripped = _CJK_PATTERN.sub(" ", text)
    en_words = len(re.findall(r"[A-Za-z0-9]+", stripped))
    return cjk_chars + en_words


def _manual_dir(camp_id: int) -> Path:
    """构造并确保手册目录存在。"""
    directory = MANUAL_ROOT / str(camp_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _read_full_text(path: Path) -> str:
    """读取文件全文；按 UTF-8 解码，失败回退 GBK。"""
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    # 全部失败时强制 UTF-8 并忽略错误，避免崩溃
    return raw.decode("utf-8", errors="ignore")


class ManualService:
    """手册服务。

    所有方法接收 ``AsyncSession``，由调用方（路由层 Depends(get_db)）负责生命周期。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    async def upload_manual(self, camp_id: int, file: UploadFile) -> Manual:
        """上传手册文件。

        - 校验扩展名为 .md / .txt。
        - 存到 ``data/manuals/{camp_id}/manual.{ext}``。
        - 读全文 → 算字数 → upsert Manual(camp_id unique)。
        """
        _safe_camp_id(camp_id)
        ext = _resolve_ext(file.filename)

        directory = _manual_dir(camp_id)
        target = directory / f"manual{ext}"

        # 读取上传字节并落盘
        data = await file.read()
        target.write_bytes(data)

        content = _read_full_text(target)
        word_count = count_words(content)

        return await self._upsert(
            camp_id=camp_id,
            filename=file.filename or f"manual{ext}",
            file_path=str(target),
            content=content,
            word_count=word_count,
        )

    async def save_paste(self, camp_id: int, content: str) -> Manual:
        """粘贴文本保存为手册。

        - 文件名固定 ``manual_paste.md``。
        - 全文直接来自请求体，不再读文件。
        """
        _safe_camp_id(camp_id)
        if not content or not content.strip():
            raise ValidationError("粘贴内容不能为空")

        directory = _manual_dir(camp_id)
        target = directory / "manual_paste.md"
        target.write_text(content, encoding="utf-8")

        word_count = count_words(content)

        return await self._upsert(
            camp_id=camp_id,
            filename="manual_paste.md",
            file_path=str(target),
            content=content,
            word_count=word_count,
        )

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    async def get_manual(self, camp_id: int) -> Manual:
        """按 camp_id 取手册；不存在时 raise NotFoundError。"""
        _safe_camp_id(camp_id)
        manual = await self._get_by_camp(camp_id)
        if manual is None:
            raise NotFoundError(f"camp {camp_id} 未配置手册")
        return manual

    async def preview(self, camp_id: int, n: int = 500) -> str:
        """返回手册全文前 n 个字符的预览；手册不存在时 raise NotFoundError。"""
        if n <= 0:
            raise ValidationError("预览长度 n 必须为正整数")
        manual = await self.get_manual(camp_id)
        content = manual.content or ""
        return content[:n]

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------
    async def delete_manual(self, camp_id: int) -> None:
        """删除手册文件 + DB 记录。

        - 文件不存在不报错（幂等）。
        - DB 记录不存在 raise NotFoundError。
        """
        _safe_camp_id(camp_id)
        manual = await self._get_by_camp(camp_id)
        if manual is None:
            raise NotFoundError(f"camp {camp_id} 未配置手册")

        # 删 DB 记录
        await self.session.delete(manual)
        await self.session.flush()

        # 删文件系统（best-effort；不存在也不报错）
        if manual.file_path:
            path = Path(manual.file_path)
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                # 文件删除失败不影响 API 成功（DB 已删），上层日志告警即可
                pass

        await self.session.commit()

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    async def _get_by_camp(self, camp_id: int) -> Manual | None:
        result = await self.session.execute(
            select(Manual).where(Manual.camp_id == camp_id)
        )
        return result.scalar_one_or_none()

    async def _upsert(
        self,
        *,
        camp_id: int,
        filename: str,
        file_path: str,
        content: str,
        word_count: int,
    ) -> Manual:
        """根据 camp_id 唯一约束做 upsert。"""
        manual = await self._get_by_camp(camp_id)
        now = datetime.now(timezone.utc)

        if manual is None:
            manual = Manual(
                camp_id=camp_id,
                filename=filename,
                file_path=file_path,
                content=content,
                word_count=word_count,
                uploaded_at=now,
            )
            self.session.add(manual)
        else:
            # 覆盖原字段；如果旧文件存在且路径不同，尝试删除旧文件
            old_path = manual.file_path
            manual.filename = filename
            manual.file_path = file_path
            manual.content = content
            manual.word_count = word_count
            manual.uploaded_at = now

            if old_path and old_path != file_path:
                try:
                    p = Path(old_path)
                    if p.exists():
                        p.unlink()
                except OSError:
                    pass

        await self.session.commit()
        await self.session.refresh(manual)
        return manual
"""Pydantic Schema 聚合导出。

对应技术方案第五章方法签名与第十一章 API 请求/响应体。
所有 ORM→Schema 转换均使用 ``model_config = ConfigDict(from_attributes=True)``。
"""

from app.schemas.camp import (
    CampBase,
    CampCreate,
    CampOut,
    CampStatus,
    CampSummary,
    CampUpdate,
    Role,
)
from app.schemas.common import ApiResponse, PageParams, Paginated
from app.schemas.grading import DimensionScoreOut, GradeRecordOut, GradeSource
from app.schemas.manual import ManualOut, ManualPreview, PasteIn
from app.schemas.scoring import Dimension, ScoringOut, ScoringUpdate, StarRules
from app.schemas.settings import (
    ConnectionResult,
    PojuConfigOut,
    TokenStatus,
    TokenUpdate,
)
from app.schemas.student import (
    CheckinDraftOut,
    CheckinGenerateIn,
    CheckinRecordOut,
    CheckinSubmitIn,
    CheckinSubmitResult,
    DayTaskOut,
    DayTaskUpdate,
    RouteOut,
    TodayOut,
)
from app.schemas.volunteer import (
    ArchiveStats,
    ArchiveTimelineItem,
    GradeConfirmIn,
    GradeDraftOut,
    GradeGenerateIn,
    PendingGradeOut,
    StudentArchive,
    StudentStatus,
    StudentSummary,
    SyncResult,
)

__all__ = [
    # common
    "ApiResponse",
    "Paginated",
    "PageParams",
    # camp
    "CampBase",
    "CampCreate",
    "CampUpdate",
    "CampOut",
    "CampSummary",
    "Role",
    "CampStatus",
    # manual
    "ManualOut",
    "ManualPreview",
    "PasteIn",
    # student
    "DayTaskOut",
    "RouteOut",
    "DayTaskUpdate",
    "TodayOut",
    "CheckinGenerateIn",
    "CheckinDraftOut",
    "CheckinSubmitIn",
    "CheckinSubmitResult",
    "CheckinRecordOut",
    # volunteer
    "StudentSummary",
    "ArchiveTimelineItem",
    "ArchiveStats",
    "StudentArchive",
    "PendingGradeOut",
    "GradeGenerateIn",
    "GradeDraftOut",
    "GradeConfirmIn",
    "SyncResult",
    "StudentStatus",
    # grading
    "DimensionScoreOut",
    "GradeRecordOut",
    "GradeSource",
    # scoring
    "Dimension",
    "StarRules",
    "ScoringOut",
    "ScoringUpdate",
    # settings
    "PojuConfigOut",
    "TokenUpdate",
    "ConnectionResult",
    "TokenStatus",
]

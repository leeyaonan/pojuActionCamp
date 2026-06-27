"""ORM 模型聚合导出。

导入所有模型类，确保 SQLAlchemy ``Base.metadata`` 收集到全部表，
Alembic autogenerate 能正确发现。模型导入需在运行期实际执行以注册 metadata。
"""

from app.database import Base
from app.models.camp import Camp
from app.models.checkin import CheckinRecord
from app.models.grade import Grade
from app.models.manual import Manual
from app.models.scoring import ScoringStandard
from app.models.settings import PojuConfig
from app.models.student import Student
from app.models.study_route import DayTask, StudyRoute

__all__ = [
    "Base",
    "Camp",
    "Manual",
    "StudyRoute",
    "DayTask",
    "Student",
    "CheckinRecord",
    "Grade",
    "ScoringStandard",
    "PojuConfig",
]

"""SQLAlchemy ORM Model 汇总。

Alembic 会导入本模块，使所有 Model 都注册到 Base.metadata。
"""

from backend.models.divination import Divination
from backend.models.user import User

__all__ = ["Divination", "User"]

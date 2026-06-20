"""services 包 — 保持向后兼容的聚合导出"""
from app.services.core import *      # noqa: F401,F403
from app.services.tencent import *   # noqa: F401,F403
from app.services.knowledge import * # noqa: F401,F403
from app.services.context import *   # noqa: F401,F403
from app.services.analysis import *  # noqa: F401,F403
from app.services.inbox import *     # noqa: F401,F403
from app.services.execution import * # noqa: F401,F403
from app.services.naming import *    # noqa: F401,F403
from app.services.formatting import *  # noqa: F401,F403

# 显式导出私有函数（测试用）
from app.services.context import _migrate_old_deposit_paths  # noqa: F401

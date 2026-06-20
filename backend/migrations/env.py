"""
migrations/env.py - Alembic 环境配置
Phase 1 地基加固：基线迁移配置
"""
from logging.config import fileConfig
from pathlib import Path
import sys

from sqlalchemy import engine_from_config, pool

from alembic import context

# 确保 backend/ 目录在 sys.path 中，以便能 import app
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# 导入 models.py 的 Base.metadata（Alembic autogenerate 需要）
from app.database import Base  # noqa: E402
import app.models  # noqa: F401, E402 — 确保所有模型类都已注册到 Base.metadata

# Alembic Config 对象（提供对 .ini 文件中值的访问）
config = context.config

# 配置日志（如果 ini 文件存在 logging 配置）
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标 metadata，用于 autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """在「离线」模式下运行迁移（无需真实数据库连接）。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在「在线」模式下运行迁移（需要真实数据库连接）。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

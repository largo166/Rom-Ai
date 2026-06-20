import logging
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 写操作串行化锁（防止后台任务与前台竞争写锁）
# ──────────────────────────────────────────────
_write_lock = threading.Lock()


@contextmanager
def serialized_write():
    """串行化写操作，防止后台任务与前台竞争写锁"""
    _write_lock.acquire()
    try:
        yield
    finally:
        _write_lock.release()


def retry_on_lock(max_retries: int = 3, base_delay: float = 0.1):
    """
    SQLite 锁冲突时指数退避重试装饰器。
    用于后台长任务（扫描/索引/分析）中的 DB 写操作。
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "DB locked, retry %d/%d after %.1fs",
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator


def _sqlite_path_from_url(url: str) -> Optional[Path]:
    if not url.startswith("sqlite:///"):
        return None
    raw = url.replace("sqlite:///", "", 1)
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


sqlite_path = _sqlite_path_from_url(settings.database_url)
if sqlite_path:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _configure_sqlite()
    _run_alembic_upgrade()
    # _ensure_sqlite_columns()  # 已被 Alembic 迁移替代，保留函数体供回滚参考

    # Phase 6: 初始化 SQLite FTS5 全文索引
    try:
        from app.retrieval import init_fts5

        init_fts5(engine)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FTS5 initialization failed (non-fatal): %s", exc)


def _run_alembic_upgrade() -> None:
    """如果存在 pending 迁移则自动执行 alembic upgrade head"""
    try:
        from alembic import command
        from alembic.config import Config

        alembic_ini = BASE_DIR.parent / "alembic.ini"
        if not alembic_ini.exists():
            logger.debug("alembic.ini not found, skipping auto-upgrade")
            return
        alembic_cfg = Config(str(alembic_ini))
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic upgrade head completed")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alembic auto-upgrade failed (non-fatal): %s", exc)


def _configure_sqlite() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA busy_timeout=15000")  # 提升到 15 秒，减少锁超时概率
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def _ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    additions = {
        "project_tasks": {
            "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            "assignee_type": "VARCHAR DEFAULT ''",
            "assignee_id": "VARCHAR DEFAULT ''",
            "assignee_name": "VARCHAR DEFAULT ''",
            "source_type": "VARCHAR DEFAULT ''",
            "source_id": "VARCHAR DEFAULT ''",
            "due_date": "DATETIME",
        },
        "knowledge_references": {
            "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        },
        "project_files": {
            "analysis_status": "VARCHAR DEFAULT 'pending'",
            "analysis_batch_id": "VARCHAR DEFAULT ''",
            "analyzed_at": "DATETIME",
        },
        "project_meetings": {
            "updated_at": "DATETIME",
        },
        "meetings": {
            "date": "DATETIME",
            "minutes": "TEXT DEFAULT ''",
            "todos": "TEXT DEFAULT '[]'",
            "recording_url": "VARCHAR DEFAULT ''",
            "tencent_join_url": "VARCHAR DEFAULT ''",
            "tencent_meeting_code": "VARCHAR DEFAULT ''",
            "tencent_meeting_id": "VARCHAR DEFAULT ''",
            "recording_view_url": "VARCHAR DEFAULT ''",
            "record_file_id": "VARCHAR DEFAULT ''",
            "sync_status": "VARCHAR DEFAULT 'not_synced'",
            "sync_error": "TEXT DEFAULT ''",
            "sync_trace_json": "TEXT DEFAULT '{}'",
            "last_synced_at": "DATETIME",
            "transcript": "TEXT DEFAULT ''",
            "summary": "TEXT DEFAULT ''",
            "mindmap_json": "TEXT DEFAULT '{}'",
            "next_actions_json": "TEXT DEFAULT '[]'",
            "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        },
        "skill_cards": {
            "updated_at": "DATETIME",
            "input_data": "TEXT DEFAULT '{}'",
            "output_data": "TEXT DEFAULT ''",
            "input_json": "TEXT DEFAULT '{}'",
            "output_json": "TEXT DEFAULT '{}'",
            "markdown": "TEXT DEFAULT ''",
            "source": "VARCHAR DEFAULT ''",
            "created_by": "VARCHAR DEFAULT 'user'",
            "completed_at": "DATETIME",
        },
        "team_members": {
            "created_at": "DATETIME",
        },
        "team_assignments": {
            "member_id": "VARCHAR DEFAULT ''",
            "member_type": "VARCHAR DEFAULT 'human'",
            "member_name": "VARCHAR DEFAULT ''",
            "role": "VARCHAR DEFAULT ''",
            "responsibilities": "TEXT DEFAULT ''",
            "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        },
        "inbox_items": {
            "file_hash": "VARCHAR DEFAULT ''",
            "duplicate_scope": "VARCHAR DEFAULT ''",
            "duplicate_project_file_id": "VARCHAR DEFAULT ''",
            "duplicate_knowledge_file_id": "VARCHAR DEFAULT ''",
            "recommended_action": "VARCHAR DEFAULT ''",
            "recommend_knowledge_reason": "TEXT DEFAULT ''",
            "archive_group": "VARCHAR DEFAULT '待确认'",
        },
    }
    backup_created = False
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if not existing:
                continue
            for name, definition in columns.items():
                if name not in existing:
                    if not backup_created and sqlite_path and sqlite_path.exists():
                        backup_dir = sqlite_path.parent / "backups"
                        backup_dir.mkdir(parents=True, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        shutil.copy2(sqlite_path, backup_dir / f"{sqlite_path.stem}-pre-migration-{timestamp}{sqlite_path.suffix}")
                        backup_created = True
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        conn.exec_driver_sql(
            """
            UPDATE project_files
            SET analysis_status = 'analyzed',
                analyzed_at = (
                    SELECT MAX(project_reports.created_at)
                    FROM project_reports
                    WHERE project_reports.project_id = project_files.project_id
                      AND project_reports.report_type = 'startup_analysis'
                )
            WHERE analysis_status = 'pending'
              AND parse_status = 'parsed'
              AND EXISTS (
                    SELECT 1
                    FROM project_reports
                    WHERE project_reports.project_id = project_files.project_id
                      AND project_reports.report_type = 'startup_analysis'
                      AND project_reports.created_at >= project_files.created_at
              )
            """
        )

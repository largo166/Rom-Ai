"""003_change_event_engine - P0 主链路: 变更事件引擎

Revision ID: 003_change_event
Revises: 002_project_overview
Create Date: 2026-06-20 02:00:00.000000

1. 创建 project_change_events 表（统一变更事件追踪）
2. ALTER TABLE meetings 添加音频转写字段
3. ALTER TABLE inbox_items 添加版本追踪字段
4. ALTER TABLE project_reports 添加增量分析字段
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_change_event"
down_revision: Union[str, None] = "002_project_overview"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    def columns(table_name: str) -> set[str]:
        return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()}

    def add_column_if_missing(table_name: str, column_name: str, sql: str) -> None:
        if column_name not in columns(table_name):
            conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {sql}")

    # ── 1. 创建 project_change_events 表 ──────────────────────────────────────
    existing_tables = set(sa.inspect(conn).get_table_names())
    if "project_change_events" not in existing_tables:
        op.create_table(
            "project_change_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("source_type", sa.String(30), nullable=True),
            sa.Column("source_id", sa.String(), nullable=True),
            sa.Column("affected_fields", sa.Text(), nullable=True),
            sa.Column("old_snapshot", sa.Text(), nullable=True),
            sa.Column("new_snapshot", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("consumed_by_analysis", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("consumed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    # 索引：按项目+时间查询变更事件
    op.create_index(
        "ix_project_change_events_project_id_created_at",
        "project_change_events",
        ["project_id", "created_at"],
        if_not_exists=True,
    )
    # 索引：查找未消费的变更事件
    op.create_index(
        "ix_project_change_events_project_id_consumed",
        "project_change_events",
        ["project_id", "consumed_by_analysis"],
        if_not_exists=True,
    )

    # ── 2. meetings 添加音频转写字段 ──────────────────────────────────────────
    add_column_if_missing("meetings", "audio_file_path", "audio_file_path VARCHAR(500)")
    add_column_if_missing("meetings", "audio_transcribed_at", "audio_transcribed_at DATETIME")
    add_column_if_missing("meetings", "transcription_source", "transcription_source VARCHAR(30)")

    # ── 3. inbox_items 添加版本追踪字段 ───────────────────────────────────────
    add_column_if_missing("inbox_items", "version_tag", "version_tag VARCHAR(20)")
    add_column_if_missing("inbox_items", "parent_item_id", "parent_item_id VARCHAR")

    # ── 4. project_reports 添加增量分析字段 ───────────────────────────────────
    add_column_if_missing("project_reports", "parent_report_id", "parent_report_id VARCHAR")
    add_column_if_missing("project_reports", "diff_summary", "diff_summary TEXT")


def downgrade() -> None:
    # ── 4. 回滚 project_reports 增量分析字段 ─────────────────────────────────
    with op.batch_alter_table("project_reports") as batch_op:
        batch_op.drop_constraint("fk_project_reports_parent_report_id", type_="foreignkey")
        batch_op.drop_column("diff_summary")
        batch_op.drop_column("parent_report_id")

    # ── 3. 回滚 inbox_items 版本追踪字段 ─────────────────────────────────────
    with op.batch_alter_table("inbox_items") as batch_op:
        batch_op.drop_constraint("fk_inbox_items_parent_item_id", type_="foreignkey")
        batch_op.drop_column("parent_item_id")
        batch_op.drop_column("version_tag")

    # ── 2. 回滚 meetings 音频转写字段 ────────────────────────────────────────
    with op.batch_alter_table("meetings") as batch_op:
        batch_op.drop_column("transcription_source")
        batch_op.drop_column("audio_transcribed_at")
        batch_op.drop_column("audio_file_path")

    # ── 1. 删除 project_change_events 表 ──────────────────────────────────────
    op.drop_index("ix_project_change_events_project_id_consumed", table_name="project_change_events")
    op.drop_index("ix_project_change_events_project_id_created_at", table_name="project_change_events")
    op.drop_table("project_change_events")

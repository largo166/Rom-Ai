"""004_meeting_type - 块 5: 沟通记录复用 Meeting 模型

Revision ID: 004_meeting_type
Revises: 003_change_event
Create Date: 2026-06-20 03:00:00.000000

为 meetings 表添加 meeting_type 字段，用于区分：
  项目会议 / 腾讯会议 / 电话 / 微信摘录 / 邮件摘要 / 现场沟通 / 口头沟通
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_meeting_type"
down_revision: Union[str, None] = "003_change_event"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(meetings)").fetchall()}
    if "meeting_type" not in columns:
        conn.exec_driver_sql("ALTER TABLE meetings ADD COLUMN meeting_type VARCHAR(30) DEFAULT '项目会议'")


def downgrade() -> None:
    with op.batch_alter_table("meetings") as batch_op:
        batch_op.drop_column("meeting_type")

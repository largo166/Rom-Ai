"""002_project_overview_fields - Phase 3: 项目概览指挥台扩展字段

Revision ID: 002_project_overview
Revises: 001_baseline
Create Date: 2026-06-20 00:01:00.000000

为 projects 表添加项目概览指挥台所需的 6 个字段：
  client_name     - 甲方/客户名
  client_contact  - 甲方联系方式
  client_demands  - 甲方诉求记录(JSON)
  milestones      - 关键里程碑(JSON)
  deliverables    - 成果物清单(JSON)
  risk_summary    - 统一风险摘要(JSON)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_project_overview"
down_revision: Union[str, None] = "001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("client_name", sa.String(), nullable=True))
    op.add_column("projects", sa.Column("client_contact", sa.String(), nullable=True))
    op.add_column("projects", sa.Column("client_demands", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("milestones", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("deliverables", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("risk_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "risk_summary")
    op.drop_column("projects", "deliverables")
    op.drop_column("projects", "milestones")
    op.drop_column("projects", "client_demands")
    op.drop_column("projects", "client_contact")
    op.drop_column("projects", "client_name")

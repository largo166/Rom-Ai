"""001_baseline - 基线迁移，包含当前 models.py 的完整 schema

Revision ID: 001_baseline
Revises:
Create Date: 2026-06-20 00:00:00.000000

此迁移记录了 Phase 1 地基加固时点的完整数据库结构。
包含以下 18 个表：
  projects, project_files, inbox_items, project_reports, project_tasks,
  project_timelines, team_plans, knowledge_references, agent_runs,
  agent_triggers, digital_employees, knowledge_files, knowledge_chunks,
  knowledge_tags, knowledge_links, meetings, skill_cards, team_assignments,
  team_members, knowledge_items
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── projects ──────────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("city", sa.String(), nullable=False, server_default=""),
        sa.Column("project_type", sa.String(), nullable=False, server_default=""),
        sa.Column("phase", sa.String(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── project_files ─────────────────────────────────────────────────────────
    op.create_table(
        "project_files",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False, server_default=""),
        sa.Column("filepath", sa.String(), nullable=False, server_default=""),
        sa.Column("filetype", sa.String(), nullable=False, server_default=""),
        sa.Column("filesize", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parsed_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("parse_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("analysis_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("analysis_batch_id", sa.String(), nullable=False, server_default=""),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_files_project_id", "project_files", ["project_id"])

    # ── inbox_items ───────────────────────────────────────────────────────────
    op.create_table(
        "inbox_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False, server_default=""),
        sa.Column("suggested_filename", sa.String(), nullable=False, server_default=""),
        sa.Column("final_filename", sa.String(), nullable=False, server_default=""),
        sa.Column("source_path", sa.String(), nullable=False, server_default=""),
        sa.Column("temp_path", sa.String(), nullable=False, server_default=""),
        sa.Column("archive_path", sa.String(), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(), nullable=False, server_default=""),
        sa.Column("suggested_project_name", sa.String(), nullable=False, server_default=""),
        sa.Column("suggested_city", sa.String(), nullable=False, server_default=""),
        sa.Column("suggested_project_type", sa.String(), nullable=False, server_default=""),
        sa.Column("suggested_phase", sa.String(), nullable=False, server_default=""),
        sa.Column("material_type", sa.String(), nullable=False, server_default=""),
        sa.Column("source_label", sa.String(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("keywords", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="待确认"),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("suggest_knowledge", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("suggest_todo", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("file_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("duplicate_scope", sa.String(), nullable=False, server_default=""),
        sa.Column("duplicate_project_file_id", sa.String(), nullable=False, server_default=""),
        sa.Column("duplicate_knowledge_file_id", sa.String(), nullable=False, server_default=""),
        sa.Column("recommended_action", sa.String(), nullable=False, server_default=""),
        sa.Column("recommend_knowledge_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("archive_group", sa.String(), nullable=False, server_default="待确认"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbox_items_project_id", "inbox_items", ["project_id"])
    op.create_index("ix_inbox_items_status", "inbox_items", ["status"])
    op.create_index("ix_inbox_items_file_hash", "inbox_items", ["file_hash"])
    op.create_index("ix_inbox_items_archive_group", "inbox_items", ["archive_group"])

    # ── project_reports ───────────────────────────────────────────────────────
    op.create_table(
        "project_reports",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("report_type", sa.String(), nullable=False, server_default="project_analysis"),
        sa.Column("content_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("model_name", sa.String(), nullable=False, server_default=""),
        sa.Column("mode", sa.String(), nullable=False, server_default="mock"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_reports_project_id", "project_reports", ["project_id"])

    # ── project_tasks ─────────────────────────────────────────────────────────
    op.create_table(
        "project_tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("task_name", sa.String(), nullable=False, server_default=""),
        sa.Column("task_type", sa.String(), nullable=False, server_default=""),
        sa.Column("priority", sa.String(), nullable=False, server_default="medium"),
        sa.Column("owner_role", sa.String(), nullable=False, server_default=""),
        sa.Column("estimated_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("dependencies", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("risk_level", sa.String(), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(), nullable=False, server_default="todo"),
        sa.Column("output_requirement", sa.Text(), nullable=False, server_default=""),
        sa.Column("assignee_type", sa.String(), nullable=True, server_default=""),
        sa.Column("assignee_id", sa.String(), nullable=True, server_default=""),
        sa.Column("assignee_name", sa.String(), nullable=True, server_default=""),
        sa.Column("source_type", sa.String(), nullable=True, server_default=""),
        sa.Column("source_id", sa.String(), nullable=True, server_default=""),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_tasks_project_id", "project_tasks", ["project_id"])

    # ── project_timelines ─────────────────────────────────────────────────────
    op.create_table(
        "project_timelines",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("stage_name", sa.String(), nullable=False, server_default=""),
        sa.Column("start_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("end_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("milestone", sa.String(), nullable=False, server_default=""),
        sa.Column("dependencies", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("risk_note", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_timelines_project_id", "project_timelines", ["project_id"])

    # ── team_plans ────────────────────────────────────────────────────────────
    op.create_table(
        "team_plans",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("recommended_roles", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("staffing_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_plans_project_id", "team_plans", ["project_id"])

    # ── knowledge_references ──────────────────────────────────────────────────
    op.create_table(
        "knowledge_references",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("source_file", sa.String(), nullable=False, server_default=""),
        sa.Column("source_path", sa.String(), nullable=False, server_default=""),
        sa.Column("chunk_id", sa.String(), nullable=False, server_default=""),
        sa.Column("quote", sa.Text(), nullable=False, server_default=""),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_references_project_id", "knowledge_references", ["project_id"])

    # ── agent_runs ────────────────────────────────────────────────────────────
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False, server_default=""),
        sa.Column("input_context", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])

    # ── agent_triggers ────────────────────────────────────────────────────────
    op.create_table(
        "agent_triggers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False, server_default=""),
        sa.Column("trigger_type", sa.String(), nullable=False, server_default="manual"),
        sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_triggers_project_id", "agent_triggers", ["project_id"])

    # ── digital_employees ─────────────────────────────────────────────────────
    op.create_table(
        "digital_employees",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("role", sa.String(), nullable=False, server_default=""),
        sa.Column("skills", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("avatar", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="available"),
        sa.Column("workload", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── knowledge_files ───────────────────────────────────────────────────────
    op.create_table(
        "knowledge_files",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False, server_default=""),
        sa.Column("filepath", sa.String(), nullable=False, server_default=""),
        sa.Column("filetype", sa.String(), nullable=False, server_default=""),
        sa.Column("filesize", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(), nullable=False, server_default=""),
        sa.Column("folder", sa.String(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_files_filepath", "knowledge_files", ["filepath"])

    # ── knowledge_chunks ──────────────────────────────────────────────────────
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("file_id", sa.String(), nullable=False),
        sa.Column("heading", sa.String(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("path", sa.String(), nullable=False, server_default=""),
        sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("links", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["knowledge_files.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_chunks_file_id", "knowledge_chunks", ["file_id"])

    # ── knowledge_tags ────────────────────────────────────────────────────────
    op.create_table(
        "knowledge_tags",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("file_id", sa.String(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False, server_default=""),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["file_id"], ["knowledge_files.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_tags_file_id", "knowledge_tags", ["file_id"])
    op.create_index("ix_knowledge_tags_tag", "knowledge_tags", ["tag"])

    # ── knowledge_links ───────────────────────────────────────────────────────
    op.create_table(
        "knowledge_links",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("file_id", sa.String(), nullable=False),
        sa.Column("source_path", sa.String(), nullable=False, server_default=""),
        sa.Column("target", sa.String(), nullable=False, server_default=""),
        sa.Column("link_type", sa.String(), nullable=False, server_default="obsidian"),
        sa.ForeignKeyConstraint(["file_id"], ["knowledge_files.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_links_file_id", "knowledge_links", ["file_id"])
    op.create_index("ix_knowledge_links_target", "knowledge_links", ["target"])

    # ── meetings ──────────────────────────────────────────────────────────────
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False, server_default=""),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.Column("agenda", sa.Text(), nullable=False, server_default=""),
        sa.Column("minutes", sa.Text(), nullable=False, server_default=""),
        sa.Column("todos", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("recording_url", sa.String(), nullable=True, server_default=""),
        sa.Column("tencent_join_url", sa.String(), nullable=False, server_default=""),
        sa.Column("tencent_meeting_code", sa.String(), nullable=False, server_default=""),
        sa.Column("tencent_meeting_id", sa.String(), nullable=False, server_default=""),
        sa.Column("recording_view_url", sa.String(), nullable=False, server_default=""),
        sa.Column("record_file_id", sa.String(), nullable=False, server_default=""),
        sa.Column("sync_status", sa.String(), nullable=False, server_default="not_synced"),
        sa.Column("sync_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("sync_trace_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("mindmap_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("next_actions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(), nullable=False, server_default="scheduled"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meetings_project_id", "meetings", ["project_id"])

    # ── skill_cards ───────────────────────────────────────────────────────────
    op.create_table(
        "skill_cards",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("card_type", sa.String(), nullable=False, server_default=""),
        sa.Column("title", sa.String(), nullable=False, server_default=""),
        sa.Column("input_data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_data", sa.Text(), nullable=True, server_default=""),
        sa.Column("input_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_by", sa.String(), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skill_cards_project_id", "skill_cards", ["project_id"])

    # ── team_assignments ──────────────────────────────────────────────────────
    op.create_table(
        "team_assignments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("member_id", sa.String(), nullable=False, server_default=""),
        sa.Column("member_type", sa.String(), nullable=False, server_default="human"),
        sa.Column("member_name", sa.String(), nullable=False, server_default=""),
        sa.Column("role", sa.String(), nullable=False, server_default=""),
        sa.Column("responsibilities", sa.Text(), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_assignments_project_id", "team_assignments", ["project_id"])

    # ── team_members ──────────────────────────────────────────────────────────
    op.create_table(
        "team_members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("role", sa.String(), nullable=False, server_default=""),
        sa.Column("skills", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(), nullable=False, server_default="available"),
        sa.Column("workload", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── knowledge_items ───────────────────────────────────────────────────────
    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_file", sa.String(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=True, server_default=""),
        sa.Column("project_id", sa.String(), nullable=True, server_default=""),
        sa.Column("item_type", sa.String(), nullable=False, server_default="general"),
        sa.Column("tags", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # 按依赖顺序反向删除
    op.drop_table("knowledge_items")
    op.drop_table("team_members")
    op.drop_table("team_assignments")
    op.drop_table("skill_cards")
    op.drop_table("meetings")
    op.drop_table("knowledge_links")
    op.drop_table("knowledge_tags")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_files")
    op.drop_table("digital_employees")
    op.drop_table("agent_triggers")
    op.drop_table("agent_runs")
    op.drop_table("knowledge_references")
    op.drop_table("team_plans")
    op.drop_table("project_timelines")
    op.drop_table("project_tasks")
    op.drop_table("project_reports")
    op.drop_table("inbox_items")
    op.drop_table("project_files")
    op.drop_table("projects")

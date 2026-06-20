from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return uuid4().hex


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(nullable=False)
    city: Mapped[str] = mapped_column(default="")
    project_type: Mapped[str] = mapped_column(default="")
    phase: Mapped[str] = mapped_column(default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(default="active")
    # Phase 3: 项目概览指挥台扩展字段
    client_name: Mapped[str] = mapped_column(String, nullable=True)
    client_contact: Mapped[str] = mapped_column(String, nullable=True)
    client_demands: Mapped[str] = mapped_column(Text, nullable=True)
    milestones: Mapped[str] = mapped_column(Text, nullable=True)
    deliverables: Mapped[str] = mapped_column(Text, nullable=True)
    risk_summary: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    files: Mapped[list["ProjectFile"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    reports: Mapped[list["ProjectReport"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[list["ProjectTask"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    timelines: Mapped[list["ProjectTimeline"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    team_plans: Mapped[list["TeamPlan"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    knowledge_references: Mapped[list["KnowledgeReference"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    agent_triggers: Mapped[list["AgentTrigger"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    meetings: Mapped[list["Meeting"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    skill_cards: Mapped[list["SkillCard"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    team_assignments: Mapped[list["TeamAssignment"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    change_events: Mapped[list["ProjectChangeEvent"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    @property
    def assignments(self) -> list["TeamAssignment"]:
        return self.team_assignments


class ProjectFile(Base):
    __tablename__ = "project_files"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(default="")
    filepath: Mapped[str] = mapped_column(default="")
    filetype: Mapped[str] = mapped_column(default="")
    filesize: Mapped[int] = mapped_column(Integer, default=0)
    parsed_text: Mapped[str] = mapped_column(Text, default="")
    parse_status: Mapped[str] = mapped_column(default="pending")
    analysis_status: Mapped[str] = mapped_column(default="pending")
    analysis_batch_id: Mapped[str] = mapped_column(default="")
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="files")


class InboxItem(Base):
    __tablename__ = "inbox_items"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    original_filename: Mapped[str] = mapped_column(default="")
    suggested_filename: Mapped[str] = mapped_column(default="")
    final_filename: Mapped[str] = mapped_column(default="")
    source_path: Mapped[str] = mapped_column(default="")
    temp_path: Mapped[str] = mapped_column(default="")
    archive_path: Mapped[str] = mapped_column(default="")
    project_id: Mapped[str] = mapped_column(default="", index=True)
    suggested_project_name: Mapped[str] = mapped_column(default="")
    suggested_city: Mapped[str] = mapped_column(default="")
    suggested_project_type: Mapped[str] = mapped_column(default="")
    suggested_phase: Mapped[str] = mapped_column(default="")
    material_type: Mapped[str] = mapped_column(default="")
    source_label: Mapped[str] = mapped_column(default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[str] = mapped_column(Text, default="[]")
    evidence: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(default="待确认", index=True)
    needs_review: Mapped[bool] = mapped_column(default=False)
    suggest_knowledge: Mapped[bool] = mapped_column(default=False)
    suggest_todo: Mapped[bool] = mapped_column(default=False)
    file_hash: Mapped[str] = mapped_column(default="", index=True)
    duplicate_scope: Mapped[str] = mapped_column(default="")
    duplicate_project_file_id: Mapped[str] = mapped_column(default="")
    duplicate_knowledge_file_id: Mapped[str] = mapped_column(default="")
    recommended_action: Mapped[str] = mapped_column(default="")
    recommend_knowledge_reason: Mapped[str] = mapped_column(Text, default="")
    archive_group: Mapped[str] = mapped_column(default="待确认", index=True)
    # 版本追踪
    version_tag: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    parent_item_id: Mapped[Optional[str]] = mapped_column(ForeignKey("inbox_items.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ProjectReport(Base):
    __tablename__ = "project_reports"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    report_type: Mapped[str] = mapped_column(default="project_analysis")
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    markdown: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(default="")
    mode: Mapped[str] = mapped_column(default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 增量分析关联
    parent_report_id: Mapped[Optional[str]] = mapped_column(ForeignKey("project_reports.id"), nullable=True)
    diff_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 变化摘要 Markdown

    project: Mapped[Project] = relationship(back_populates="reports")


class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    task_name: Mapped[str] = mapped_column(default="")
    task_type: Mapped[str] = mapped_column(default="")
    priority: Mapped[str] = mapped_column(default="medium")
    owner_role: Mapped[str] = mapped_column(default="")
    estimated_days: Mapped[int] = mapped_column(Integer, default=1)
    dependencies: Mapped[str] = mapped_column(Text, default="[]")
    risk_level: Mapped[str] = mapped_column(default="medium")
    status: Mapped[str] = mapped_column(default="todo")
    output_requirement: Mapped[str] = mapped_column(Text, default="")
    assignee_type: Mapped[str] = mapped_column(default="", nullable=True)
    assignee_id: Mapped[str] = mapped_column(default="", nullable=True)
    assignee_name: Mapped[str] = mapped_column(default="", nullable=True)
    source_type: Mapped[str] = mapped_column(default="", nullable=True)
    source_id: Mapped[str] = mapped_column(default="", nullable=True)
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    project: Mapped[Project] = relationship(back_populates="tasks")


class ProjectTimeline(Base):
    __tablename__ = "project_timelines"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    stage_name: Mapped[str] = mapped_column(default="")
    start_day: Mapped[int] = mapped_column(Integer, default=1)
    end_day: Mapped[int] = mapped_column(Integer, default=1)
    milestone: Mapped[str] = mapped_column(default="")
    dependencies: Mapped[str] = mapped_column(Text, default="[]")
    risk_note: Mapped[str] = mapped_column(Text, default="")

    project: Mapped[Project] = relationship(back_populates="timelines")


class TeamPlan(Base):
    __tablename__ = "team_plans"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    recommended_roles: Mapped[str] = mapped_column(Text, default="[]")
    staffing_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="team_plans")


class KnowledgeReference(Base):
    __tablename__ = "knowledge_references"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    source_file: Mapped[str] = mapped_column(default="")
    source_path: Mapped[str] = mapped_column(default="")
    chunk_id: Mapped[str] = mapped_column(default="")
    quote: Mapped[str] = mapped_column(Text, default="")
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="knowledge_references")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    agent_id: Mapped[str] = mapped_column(default="")
    input_context: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="agent_runs")


class AgentTrigger(Base):
    __tablename__ = "agent_triggers"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    agent_id: Mapped[str] = mapped_column(default="")
    trigger_type: Mapped[str] = mapped_column(default="manual")
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="agent_triggers")


class DigitalEmployee(Base):
    __tablename__ = "digital_employees"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(default="")
    role: Mapped[str] = mapped_column(default="")
    skills: Mapped[str] = mapped_column(Text, default="[]")
    avatar: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="available")
    workload: Mapped[int] = mapped_column(Integer, default=0)


class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(default="")
    filepath: Mapped[str] = mapped_column(default="", index=True)
    filetype: Mapped[str] = mapped_column(default="")
    filesize: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(default="")
    folder: Mapped[str] = mapped_column(default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    scanned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    file_id: Mapped[str] = mapped_column(ForeignKey("knowledge_files.id"), index=True)
    heading: Mapped[str] = mapped_column(default="")
    content: Mapped[str] = mapped_column(Text, default="")
    path: Mapped[str] = mapped_column(default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    links: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KnowledgeTag(Base):
    __tablename__ = "knowledge_tags"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    file_id: Mapped[str] = mapped_column(ForeignKey("knowledge_files.id"), index=True)
    tag: Mapped[str] = mapped_column(default="", index=True)
    count: Mapped[int] = mapped_column(Integer, default=1)


class KnowledgeLink(Base):
    __tablename__ = "knowledge_links"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    file_id: Mapped[str] = mapped_column(ForeignKey("knowledge_files.id"), index=True)
    source_path: Mapped[str] = mapped_column(default="")
    target: Mapped[str] = mapped_column(default="", index=True)
    link_type: Mapped[str] = mapped_column(default="obsidian")


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(default="")
    meeting_type: Mapped[str] = mapped_column(String(30), default="项目会议")
    date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    agenda: Mapped[str] = mapped_column(Text, default="")
    minutes: Mapped[str] = mapped_column(Text, default="")
    todos: Mapped[str] = mapped_column(Text, default="[]")
    recording_url: Mapped[str] = mapped_column(default="", nullable=True)
    # 音频转写
    audio_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    audio_transcribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    transcription_source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # 可选值: whisper, tencent, manual
    tencent_join_url: Mapped[str] = mapped_column(default="")
    tencent_meeting_code: Mapped[str] = mapped_column(default="")
    tencent_meeting_id: Mapped[str] = mapped_column(default="")
    recording_view_url: Mapped[str] = mapped_column(default="")
    record_file_id: Mapped[str] = mapped_column(default="")
    sync_status: Mapped[str] = mapped_column(default="not_synced")
    sync_error: Mapped[str] = mapped_column(Text, default="")
    sync_trace_json: Mapped[str] = mapped_column(Text, default="{}")
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    transcript: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    mindmap_json: Mapped[str] = mapped_column(Text, default="{}")
    next_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="meetings")

    @property
    def meeting_link(self) -> str:
        return self.recording_url or ""

    @property
    def scheduled_at(self) -> str:
        return self.date.isoformat() if self.date else ""

    @property
    def updated_at(self) -> datetime:
        return self.created_at


class SkillCard(Base):
    __tablename__ = "skill_cards"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    card_type: Mapped[str] = mapped_column(default="")
    title: Mapped[str] = mapped_column(default="")
    input_data: Mapped[str] = mapped_column(Text, default="{}")
    output_data: Mapped[str] = mapped_column(Text, default="", nullable=True)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str] = mapped_column(Text, default="{}", nullable=True)
    markdown: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="pending")
    created_by: Mapped[str] = mapped_column(default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    project: Mapped[Project] = relationship(back_populates="skill_cards")

    @property
    def updated_at(self) -> datetime:
        return self.completed_at or self.created_at


class TeamAssignment(Base):
    __tablename__ = "team_assignments"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    member_id: Mapped[str] = mapped_column(default="")
    member_type: Mapped[str] = mapped_column(default="human")
    member_name: Mapped[str] = mapped_column(default="")
    role: Mapped[str] = mapped_column(default="")
    responsibilities: Mapped[str] = mapped_column(Text, default="", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="team_assignments")

    @property
    def task_id(self) -> str:
        return ""

    @property
    def assignee_type(self) -> str:
        return self.member_type

    @property
    def assignee_id(self) -> str:
        return self.member_id

    @property
    def assignee_name(self) -> str:
        return self.member_name

    @property
    def responsibility(self) -> str:
        return self.responsibilities or ""

    @property
    def status(self) -> str:
        return "active"


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(default="")
    role: Mapped[str] = mapped_column(default="")
    skills: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(default="available")
    workload: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    source_file: Mapped[str] = mapped_column(default="")
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="", nullable=True)
    project_id: Mapped[str] = mapped_column(default="", nullable=True)
    item_type: Mapped[str] = mapped_column(default="general")
    tags: Mapped[str] = mapped_column(Text, default="[]", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProjectChangeEvent(Base):
    """项目变更事件 - 统一记录项目中发生的所有变更"""
    __tablename__ = "project_change_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)

    # 事件类型
    event_type: Mapped[str] = mapped_column(String(50))
    # 可选值: file_uploaded, meeting_confirmed, client_demands_updated,
    #         startup_analysis_generated, okf_stale, risk_updated,
    #         meeting_transcript_ready

    # 来源
    source_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # 可选值: meeting, file, manual, system
    source_id: Mapped[Optional[str]] = mapped_column(nullable=True)

    # 变更详情
    affected_fields: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of field names
    old_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    new_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 人可读描述

    # 消费追踪
    consumed_by_analysis: Mapped[bool] = mapped_column(default=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="change_events")

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    city: str = ""
    project_type: str = ""
    phase: str = ""
    description: str = ""
    status: str = "active"


class InboxItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    suggested_filename: str
    final_filename: str
    source_path: str
    temp_path: str
    archive_path: str
    project_id: str
    suggested_project_name: str
    suggested_city: str
    suggested_project_type: str
    suggested_phase: str
    material_type: str
    source_label: str
    summary: str
    keywords: str
    evidence: str
    confidence: float
    status: str
    needs_review: bool
    suggest_knowledge: bool
    suggest_todo: bool
    file_hash: str = ""
    duplicate_scope: str = ""
    duplicate_project_file_id: str = ""
    duplicate_knowledge_file_id: str = ""
    recommended_action: str = ""
    recommend_knowledge_reason: str = ""
    archive_group: str = "待确认"
    created_at: datetime
    updated_at: datetime


class InboxScanRequest(BaseModel):
    path: str = ""
    source_label: str = "手动目录"
    days: int = 0


class InboxScanJobOut(BaseModel):
    job_id: str
    status: str
    path: str
    source_label: str
    days: int
    step: str = ""
    total_candidates: int = 0
    processed: int = 0
    imported_files: int = 0
    unsupported_files: int = 0
    old_files: int = 0
    failed_files: int = 0
    current_file: str = ""
    error: str = ""
    result: Optional[dict[str, Any]] = None
    created_at: str = ""
    updated_at: str = ""


class InboxClassifyRequest(BaseModel):
    item_ids: list[str] = []


class InboxDeleteRequest(BaseModel):
    item_ids: list[str]


class InboxRecommendRequest(BaseModel):
    item_ids: list[str] = []


class InboxBatchAdviceRequest(BaseModel):
    item_ids: list[str] = []


class InboxBatchAdviceOut(BaseModel):
    total_files: int
    recommended_item_ids: list[str]
    action_counts: dict[str, int]
    project_groups: list[dict[str, Any]]
    knowledge_candidates: list[dict[str, str]]
    duplicates: list[dict[str, str]]
    needs_review: list[dict[str, str]]
    markdown: str
    mode: str = "rule"


class InboxApplyRecommendationsRequest(BaseModel):
    item_ids: list[str]
    force_duplicate_ids: list[str] = []


class LocalOrganizeStartRequest(BaseModel):
    path: str
    include_subfolders: bool = True
    days: int = 0
    source_label: str = "本地整理"


class LocalOrganizeApplyRequest(BaseModel):
    job_id: str
    selected_item_ids: list[str] = []
    output_root: str = ""
    apply_project_library: bool = True
    apply_knowledge: bool = True
    force_duplicate_ids: list[str] = []


class LocalOrganizeJobOut(BaseModel):
    job_id: str
    status: str
    path: str
    output_root: str = ""
    item_ids: list[str] = []
    advice: Optional[dict[str, Any]] = None
    manifest_path: str = ""
    result: Optional[dict[str, Any]] = None
    error: str = ""
    created_at: str = ""
    updated_at: str = ""


class InboxApplyRequest(BaseModel):
    item_ids: list[str]
    project_id: str = ""
    project: Optional[ProjectCreate] = None
    final_filename_by_id: dict[str, str] = {}
    material_type_by_id: dict[str, str] = {}
    enter_knowledge: bool = False


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    project_type: Optional[str] = None
    phase: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    city: str
    project_type: str
    phase: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectDeleteOut(BaseModel):
    deleted: bool
    deleted_project_id: str
    deleted_files: int = 0


class ProjectSummary(ProjectOut):
    file_count: int = 0
    report_count: int = 0
    task_count: int = 0


class ProjectFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    filename: str
    filepath: str
    filetype: str
    filesize: int
    parsed_text: str
    parse_status: str
    analysis_status: str = "pending"
    analysis_batch_id: str = ""
    analyzed_at: Optional[datetime] = None
    created_at: datetime


class InboxApplyOut(BaseModel):
    project: ProjectOut
    files: list[ProjectFileOut]
    items: list[InboxItemOut]


class InboxRecommendationApplyOut(BaseModel):
    files: list[ProjectFileOut]
    items: list[InboxItemOut]
    skipped_count: int = 0
    created_project_count: int = 0


class ProjectReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    report_type: str
    content_json: str
    markdown: str
    model_name: str
    mode: str
    created_at: datetime


class ProjectTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_name: str
    task_type: str
    priority: str
    owner_role: str
    estimated_days: int
    dependencies: str
    risk_level: str
    status: str
    output_requirement: str
    assignee_type: str = ""
    assignee_id: str = ""
    assignee_name: str = ""
    source_type: str = ""
    source_id: str = ""
    due_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ProjectTaskAssigneeUpdate(BaseModel):
    assignee_type: str = ""
    assignee_id: str = ""
    assignee_name: str = ""


class ProjectTaskCreate(BaseModel):
    task_name: str = Field(min_length=1, max_length=200)
    task_type: str = "manual"
    priority: str = "medium"
    owner_role: str = ""
    estimated_days: int = 1
    dependencies: str = "[]"
    risk_level: str = "low"
    status: str = "todo"
    output_requirement: str = ""
    source_type: str = ""
    source_id: str = ""
    due_date: Optional[datetime] = None


class ProjectTaskUpdate(BaseModel):
    task_name: Optional[str] = None
    task_type: Optional[str] = None
    priority: Optional[str] = None
    owner_role: Optional[str] = None
    estimated_days: Optional[int] = None
    dependencies: Optional[str] = None
    risk_level: Optional[str] = None
    status: Optional[str] = None
    output_requirement: Optional[str] = None
    due_date: Optional[datetime] = None


class ProjectTimelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage_name: str
    start_day: int
    end_day: int
    milestone: str
    dependencies: str
    risk_note: str


class TeamPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    recommended_roles: str
    staffing_summary: str
    created_at: datetime


class KnowledgeReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    source_file: str
    source_path: str
    chunk_id: str
    quote: str
    relevance_score: float
    created_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    agent_id: str
    input_context: str
    output_json: str
    status: str
    created_at: datetime


class ProjectExecuteRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)


class AgentTriggerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    agent_id: str
    trigger_type: str
    context_json: str
    status: str
    created_at: datetime


class ProjectMeetingCreate(BaseModel):
    title: str = "项目启动会"
    meeting_type: str = "启动会"
    agenda: str = ""
    meeting_link: str = ""
    transcript: str = ""
    status: str = "planned"
    scheduled_at: str = ""


class TencentMeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    start_time: str
    end_time: str = ""
    agenda: str = ""


class ProjectMeetingUpdate(BaseModel):
    title: Optional[str] = None
    meeting_type: Optional[str] = None
    agenda: Optional[str] = None
    meeting_link: Optional[str] = None
    transcript: Optional[str] = None
    status: Optional[str] = None
    scheduled_at: Optional[str] = None


class ProjectMeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    meeting_type: str
    agenda: str
    meeting_link: str
    tencent_join_url: str = ""
    tencent_meeting_code: str = ""
    tencent_meeting_id: str = ""
    recording_view_url: str = ""
    record_file_id: str = ""
    sync_status: str = "not_synced"
    sync_error: str = ""
    sync_trace_json: str = "{}"
    last_synced_at: Optional[datetime] = None
    transcript: str
    summary: str
    mindmap_json: str
    next_actions_json: str
    status: str
    scheduled_at: str
    created_at: datetime
    updated_at: datetime


class SkillCardRunRequest(BaseModel):
    card_type: str = "task_breakdown"
    prompt: str = ""


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    skill_id: str = ""


class TeamMemberCreate(BaseModel):
    name: str
    role: str = ""
    skills: list[str] = []
    status: str = "available"
    workload: int = 0


class TeamMemberUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    role: Optional[str] = None


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    role: str
    skills: str
    status: str
    workload: int
    created_at: datetime


class ProjectAssignmentCreate(BaseModel):
    task_id: str = ""
    assignee_type: str = "digital_employee"
    assignee_id: str = ""
    assignee_name: str = ""
    role: str = ""
    responsibility: str = ""
    status: str = "active"


class ProjectAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_id: str
    assignee_type: str
    assignee_id: str
    assignee_name: str
    role: str
    responsibility: str
    status: str
    created_at: datetime


class SkillCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    card_type: str
    title: str
    input_data: Optional[str] = "{}"
    output_data: Optional[str] = ""
    input_json: str = "{}"
    output_json: str = "{}"
    markdown: str = ""
    source: str = ""
    status: str
    created_by: str
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgentChatOut(BaseModel):
    intent: str
    confidence: float
    reason: str
    selected_skill: dict[str, Any]
    card: SkillCardOut
    context: dict[str, Any] = {}
    available_skills: list[dict[str, Any]] = []


class ProjectDetail(ProjectOut):
    files: list[ProjectFileOut] = []
    reports: list[ProjectReportOut] = []
    tasks: list[ProjectTaskOut] = []
    timelines: list[ProjectTimelineOut] = []
    team_plans: list[TeamPlanOut] = []
    knowledge_references: list[KnowledgeReferenceOut] = []
    agent_runs: list[AgentRunOut] = []
    agent_triggers: list[AgentTriggerOut] = []
    meetings: list[ProjectMeetingOut] = []
    skill_cards: list[SkillCardOut] = []
    assignments: list[ProjectAssignmentOut] = []


class HealthOut(BaseModel):
    status: str
    service: str
    database: str


class SettingsStatusOut(BaseModel):
    deepseek_configured: bool
    deepseek_base_url: str
    deepseek_model: str
    image_provider: str = "huashu"
    image_configured: bool = False
    image_base_url: str = ""
    image_model: str = ""
    tencent_meeting_configured: bool = False
    default_vault_path: str
    upload_root: str
    cloud_upload_enabled: bool = False
    cloud_upload_root: str = ""
    mock_mode: bool
    database_url: str
    data_dir: str = ""
    env_file: str = ""
    log_dir: str = ""


class DeepSeekSettingsUpdate(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"


class TencentMeetingSettingsUpdate(BaseModel):
    token: str = ""


class KnowledgeScanRequest(BaseModel):
    path: str
    clear_existing: bool = False


class KnowledgeAskRequest(BaseModel):
    question: str
    project_id: Optional[str] = None


class KnowledgeReferenceCreate(BaseModel):
    source_file: str
    source_path: str = ""
    chunk_id: str = ""
    quote: str = ""
    relevance_score: float = 0


class ProjectAnalyzeRequest(BaseModel):
    auto_fetch_knowledge: bool = False


class TeamRequirementRole(BaseModel):
    role: str
    count: int
    skills: list[str] = []
    intensity: str = ""


class TeamRequirementsOut(BaseModel):
    total_headcount: int = 0
    roles: list[TeamRequirementRole] = []


class ProjectAnalyzeOut(BaseModel):
    report: ProjectReportOut
    tasks: list[ProjectTaskOut]
    timeline: list[ProjectTimelineOut]
    team_requirements: TeamRequirementsOut
    knowledge_refs: list[KnowledgeReferenceOut]


class AgentRunRequest(BaseModel):
    project_id: str
    goal: str = "生成项目解析代理成果"


class AgentTriggerRequest(BaseModel):
    trigger_type: str = "manual"
    context_json: dict = {}


class DigitalEmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    role: str
    skills: str
    avatar: str
    status: str
    workload: int


class SkillCardCreate(BaseModel):
    card_type: str = Field(default="task_breakdown", min_length=1, max_length=50)
    title: str = ""
    input_json: dict = {}
    input_data: str = "{}"
    created_by: str = "user"


class TeamAssignmentCreate(BaseModel):
    member_id: str = ""
    member_type: str = "human"
    member_name: str = Field(min_length=1, max_length=100)
    role: str = ""
    responsibilities: str = ""


class TeamAssignmentUpdate(BaseModel):
    member_id: Optional[str] = None
    member_type: Optional[str] = None
    member_name: Optional[str] = None
    role: Optional[str] = None
    responsibilities: Optional[str] = None


class TeamAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    member_id: str
    member_type: str
    member_name: str
    role: str
    responsibilities: str
    created_at: datetime


class KnowledgeItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_file: str
    content: str
    summary: str
    project_id: str
    item_type: str
    tags: str
    created_at: datetime


class KnowledgeChatRequest(BaseModel):
    question: str
    project_id: Optional[str] = None
    context: Optional[str] = None


class KnowledgeIndexRequest(BaseModel):
    path: str
    project_id: Optional[str] = None
    clear_existing: bool = False
    include_sync_notes: bool = False


class KnowledgeSearchRequest(BaseModel):
    question: str
    limit: int = 8


class StartupAnalysisRequest(BaseModel):
    refresh_knowledge: bool = False
    vault_path: str = ""


class ObsidianCandidateCreate(BaseModel):
    item_type: str = "obsidian_candidate"
    title: str = ""
    content: str = ""
    tags: list[str] = []

import { getApiBase } from './runtime';

const apiBase = () => getApiBase();

export type Project = {
  id: string;
  name: string;
  city: string;
  project_type: string;
  phase: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ProjectSummary = Project & {
  file_count: number;
  report_count: number;
  task_count: number;
};

export type ProjectDetail = Project & {
  files: ProjectFile[];
  reports: ProjectReport[];
  tasks: ProjectTask[];
  timelines: ProjectTimeline[];
  team_plans: TeamPlan[];
  knowledge_references: KnowledgeReference[];
  agent_runs: AgentRun[];
  agent_triggers: AgentTrigger[];
  meetings: ProjectMeeting[];
  skill_cards: SkillCard[];
  assignments: ProjectAssignment[];
};

export type ProjectFile = {
  id: string;
  project_id: string;
  filename: string;
  filepath: string;
  filetype: string;
  filesize: number;
  parsed_text: string;
  parse_status: string;
  analysis_status: string;
  analysis_batch_id: string;
  analyzed_at: string | null;
  created_at: string;
};

export type ProjectReport = {
  id: string;
  project_id: string;
  report_type: string;
  content_json: string;
  markdown: string;
  model_name: string;
  mode: string;
  created_at: string;
};

export type ProjectTask = {
  id: string;
  project_id: string;
  task_name: string;
  task_type: string;
  priority: string;
  owner_role: string;
  estimated_days: number;
  dependencies: string;
  risk_level: string;
  status: string;
  output_requirement: string;
  assignee_type: string;
  assignee_id: string;
  assignee_name: string;
  source_type: string;
  source_id: string;
  due_date: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectTimeline = {
  id: string;
  project_id: string;
  stage_name: string;
  start_day: number;
  end_day: number;
  milestone: string;
  dependencies: string;
  risk_note: string;
};

export type TeamPlan = {
  id: string;
  project_id: string;
  recommended_roles: string;
  staffing_summary: string;
  created_at: string;
};

export type KnowledgeReference = {
  id: string;
  project_id: string;
  source_file: string;
  source_path: string;
  chunk_id: string;
  quote: string;
  relevance_score: number;
  created_at: string;
};

export type AgentRun = {
  id: string;
  project_id: string;
  agent_id: string;
  input_context: string;
  output_json: string;
  status: string;
  created_at: string;
};

export type AgentTrigger = {
  id: string;
  project_id: string;
  agent_id: string;
  trigger_type: string;
  context_json: string;
  status: string;
  created_at: string;
};

export type ProjectMeeting = {
  id: string;
  project_id: string;
  title: string;
  meeting_type: string;
  agenda: string;
  meeting_link: string;
  tencent_join_url: string;
  tencent_meeting_code: string;
  tencent_meeting_id: string;
  recording_view_url: string;
  record_file_id: string;
  sync_status: string;
  sync_error: string;
  sync_trace_json: string;
  last_synced_at: string | null;
  transcript: string;
  summary: string;
  mindmap_json: string;
  next_actions_json: string;
  status: string;
  scheduled_at: string;
  created_at: string;
  updated_at: string;
};

export type SkillCard = {
  id: string;
  project_id: string;
  card_type: string;
  title: string;
  status: string;
  input_json: string;
  output_json: string;
  markdown: string;
  source: string;
  created_at: string;
  updated_at: string;
};

export type TeamMember = {
  id: string;
  name: string;
  role: string;
  skills: string;
  status: string;
  workload: number;
  created_at: string;
};

export type NetworkMember = {
  id: string;
  name: string;
  type: 'human' | 'digital_employee';
  role: string;
  skills: string;
  status: string;
  workload: number;
};

export type NetworkMemberWorkload = {
  member_id: string;
  member_type: 'human' | 'digital_employee';
  project_count: number;
  task_count: number;
  projects: Array<{ project_id: string; project_name: string; role: string; responsibilities: string }>;
  tasks: Array<{ id: string; project_id: string; project_name: string; task_name: string; status: string; priority: string }>;
};

export type ProjectAssignment = {
  id: string;
  project_id: string;
  task_id: string;
  assignee_type: string;
  assignee_id: string;
  assignee_name: string;
  role: string;
  responsibility: string;
  status: string;
  created_at: string;
};

export type TeamRequirementRole = {
  role: string;
  count: number;
  skills: string[];
  intensity: string;
};

export type TeamRequirements = {
  total_headcount: number;
  roles: TeamRequirementRole[];
};

export type ProjectAnalyzeResult = {
  report: ProjectReport;
  tasks: ProjectTask[];
  timeline: ProjectTimeline[];
  team_requirements: TeamRequirements;
  knowledge_refs: KnowledgeReference[];
};

export type MindmapNode = {
  id: string;
  label: string;
  children?: MindmapNode[];
};

export type MindmapData = {
  title: string;
  nodes: MindmapNode[];
};

export type TechnicalFocusCard = {
  title: string;
  dimension: string;
  summary: string;
  checkpoints: string[];
  source_refs: string[];
  manual_confirm: string;
};

export type StartupAnalysis = {
  mode?: string;
  error_message?: string;
  report: ProjectReport;
  project_summary: {
    name: string;
    city: string;
    project_type: string;
    phase: string;
    description: string;
    knowledge_refs_count: number;
    summary: string;
  };
  technical_focus_cards: TechnicalFocusCard[];
  task_breakdown: ProjectTask[];
  meeting_agenda: string[];
  ppt_outline: Array<{ page: number; title: string; content: string }>;
  risk_list: string[];
  open_questions: string[];
  mindmap_json: MindmapData;
  source_refs: Array<{ chunk_id: string; source_file: string; source_path: string; heading: string; quote: string }>;
};

export type ObsidianCandidate = {
  id: string;
  source_file: string;
  content: string;
  summary: string;
  project_id: string;
  item_type: string;
  tags: string;
  created_at: string;
};

export type ProjectCreatePayload = {
  name: string;
  city: string;
  project_type: string;
  phase: string;
  description: string;
  status?: string;
};

export type SettingsStatus = {
  deepseek_configured: boolean;
  deepseek_base_url: string;
  deepseek_model: string;
  tencent_meeting_configured: boolean;
  default_vault_path: string;
  upload_root: string;
  mock_mode: boolean;
  database_url: string;
  cloud_upload_enabled?: boolean;
  cloud_upload_root?: string;
  data_dir?: string;
  env_file?: string;
  log_dir?: string;
};

export type DeepSeekSettingsPayload = {
  api_key: string;
  base_url: string;
  model: string;
};

export type TencentMeetingSettingsPayload = {
  token: string;
};

export type DeepSeekModelInfo = {
  id: string;
  owned_by: string;
};

export type DashboardData = {
  mock_mode: boolean;
  project_count: number;
  recent_projects: Array<{ id: string; name: string; city: string; phase: string; status: string }>;
  knowledge: Record<string, unknown>;
  recent_reports: Array<{ id: string; project_id: string; report_type: string; mode: string; created_at: string }>;
  recent_agent_runs: Array<{ id: string; project_id: string; agent_id: string; status: string; created_at: string }>;
  digital_employees: DigitalEmployee[];
};

export type BossDashboardData = {
  project_count: number;
  active_project_count: number;
  task_count: number;
  open_task_count: number;
  meeting_count: number;
  skill_card_count: number;
  phase_counts: Record<string, number>;
  risk_tasks: Array<{ id: string; project_id: string; task_name: string; owner_role: string; risk_level: string; status: string }>;
  recent_meetings: Array<{ id: string; project_id: string; title: string; status: string; scheduled_at: string; next_actions: Array<{ title: string; owner: string; status: string }> }>;
  recent_skill_cards: Array<{ id: string; project_id: string; card_type: string; title: string; status: string; source: string }>;
  member_load: Array<{ id: string; name: string; role: string; workload: number; type: string }>;
  knowledge: Record<string, unknown>;
  ai_card_distribution: Record<string, number>;
};

export type DigitalEmployee = {
  id: string;
  name: string;
  role: string;
  skills: string;
  avatar: string;
  status: string;
  workload: number;
};

export type AgentInfo = {
  id: string;
  name: string;
  scenario: string;
  input: string;
  output: string;
  status: string;
};

export type KnowledgeStats = {
  total_files: number;
  markdown_files: number;
  pdf_docx_xlsx_files: number;
  image_files: number;
  filetype_distribution: Record<string, number>;
  top_tags: Array<{ tag: string; count: number }>;
  link_count: number;
};

export type KnowledgeUploadResult = {
  indexed_files: number;
  skipped_files?: Array<{ filename?: string; reason: string; count?: number }>;
  skipped?: Record<string, number>;
  stats: KnowledgeStats;
  recent_files: unknown[];
  filters?: Record<string, unknown>;
};

export type KnowledgeFileItem = {
  id: string;
  filename: string;
  filepath: string;
  filetype: string;
  filesize: number;
  updated_at: string;
};

export type KnowledgeIndexJob = {
  job_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  path: string;
  total_candidates: number;
  processed: number;
  indexed_files: number;
  skipped_files: number;
  current_file: string;
  error?: string;
  result?: KnowledgeUploadResult;
};

export type InboxScanJob = {
  job_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  path: string;
  source_label: string;
  days: number;
  step: string;
  total_candidates: number;
  processed: number;
  imported_files: number;
  unsupported_files: number;
  old_files: number;
  failed_files: number;
  current_file: string;
  error?: string;
  result?: {
    imported_count: number;
    unsupported_files: number;
    old_files: number;
    failed_count: number;
    batch_advice?: InboxBatchAdvice;
  };
  created_at: string;
  updated_at: string;
};

export type InboxItem = {
  id: string;
  original_filename: string;
  suggested_filename: string;
  final_filename: string;
  source_path: string;
  temp_path: string;
  archive_path: string;
  project_id: string;
  suggested_project_name: string;
  suggested_city: string;
  suggested_project_type: string;
  suggested_phase: string;
  material_type: string;
  source_label: string;
  summary: string;
  keywords: string;
  evidence: string;
  confidence: number;
  status: string;
  needs_review: boolean;
  suggest_knowledge: boolean;
  suggest_todo: boolean;
  file_hash: string;
  duplicate_scope: string;
  duplicate_project_file_id: string;
  duplicate_knowledge_file_id: string;
  recommended_action: string;
  recommend_knowledge_reason: string;
  archive_group: string;
  created_at: string;
  updated_at: string;
};

export type InboxApplyPayload = {
  item_ids: string[];
  project_id?: string;
  project?: ProjectCreatePayload;
  final_filename_by_id?: Record<string, string>;
  material_type_by_id?: Record<string, string>;
  enter_knowledge?: boolean;
};

export type InboxBatchAdvice = {
  total_files: number;
  recommended_item_ids: string[];
  action_counts: Record<string, number>;
  project_groups: Array<{
    kind: string;
    project_id: string;
    project_name: string;
    file_count: number;
    knowledge_count: number;
    item_ids: string[];
    aliases?: string[];
    material_summary: string;
  }>;
  knowledge_candidates: Array<{ id: string; filename: string; material_type: string; reason: string }>;
  duplicates: Array<{ id: string; filename: string; scope: string; reason: string }>;
  needs_review: Array<{ id: string; filename: string; reason: string }>;
  markdown: string;
  mode: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || (await res.text()));
  }
  return res.json();
}

export function listProjects() {
  return request<ProjectSummary[]>('/api/projects');
}

export function listInboxItems(params: { status?: string; project_id?: string } = {}) {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  if (params.project_id) query.set('project_id', params.project_id);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return request<InboxItem[]>(`/api/inbox/items${suffix}`);
}

export function uploadInboxFiles(files: File[]) {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  return fetch(`${apiBase()}/api/inbox/upload`, {
    method: 'POST',
    body: form,
  }).then(async (res) => {
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail || (await res.text()));
    }
    return res.json() as Promise<InboxItem[]>;
  });
}

export function scanInbox(path = '', sourceLabel = '手动目录', days = 7) {
  return request<InboxItem[]>('/api/inbox/scan', {
    method: 'POST',
    body: JSON.stringify({ path, source_label: sourceLabel, days }),
  });
}

export function startInboxScan(path = '', sourceLabel = '手动目录', days = 7) {
  return request<InboxScanJob>('/api/inbox/scan/start', {
    method: 'POST',
    body: JSON.stringify({ path, source_label: sourceLabel, days }),
  });
}

export function getInboxScanJob(jobId: string) {
  return request<InboxScanJob>(`/api/inbox/scan/jobs/${jobId}`);
}

export function getLatestInboxScanJob() {
  return request<InboxScanJob | null>('/api/inbox/scan/latest');
}

export function pickInboxFolder() {
  return request<{ path: string; cancelled: boolean }>('/api/inbox/pick-folder', {
    method: 'POST',
  });
}

export function classifyInbox(itemIds: string[] = []) {
  return request<InboxItem[]>('/api/inbox/classify', {
    method: 'POST',
    body: JSON.stringify({ item_ids: itemIds }),
  });
}

export function recommendInbox(itemIds: string[] = []) {
  return request<InboxItem[]>('/api/inbox/recommend', {
    method: 'POST',
    body: JSON.stringify({ item_ids: itemIds }),
  });
}

export function getInboxBatchAdvice(itemIds: string[] = []) {
  return request<InboxBatchAdvice>('/api/inbox/batch-advice', {
    method: 'POST',
    body: JSON.stringify({ item_ids: itemIds }),
  });
}

export function deleteInboxItems(itemIds: string[]) {
  return request<{ deleted: number }>('/api/inbox/delete', {
    method: 'POST',
    body: JSON.stringify({ item_ids: itemIds }),
  });
}

export function deleteInboxItem(itemId: string) {
  return request<{ deleted: number }>(`/api/inbox/items/${itemId}`, { method: 'DELETE' });
}

export function applyInboxRecommendations(itemIds: string[], forceDuplicateIds: string[] = []) {
  return request<{ files: ProjectFile[]; items: InboxItem[]; skipped_count: number; created_project_count: number }>(
    '/api/inbox/apply-recommendations',
    {
      method: 'POST',
      body: JSON.stringify({ item_ids: itemIds, force_duplicate_ids: forceDuplicateIds }),
    },
  );
}

export function applyInbox(payload: InboxApplyPayload) {
  return request<{ project: Project; files: ProjectFile[]; items: InboxItem[] }>('/api/inbox/apply', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createProject(payload: ProjectCreatePayload) {
  return request<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getProject(projectId: string) {
  return request<ProjectDetail>(`/api/projects/${projectId}`);
}

export function deleteProject(projectId: string) {
  return request<{ deleted: boolean; deleted_project_id: string; deleted_files: number }>(`/api/projects/${projectId}`, {
    method: 'DELETE',
  });
}

export function getSettingsStatus() {
  return request<SettingsStatus>('/api/settings/status');
}

export function updateDeepSeekSettings(payload: DeepSeekSettingsPayload) {
  return request<SettingsStatus>('/api/settings/deepseek', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateTencentMeetingSettings(payload: TencentMeetingSettingsPayload) {
  return request<SettingsStatus>('/api/settings/tencent-meeting', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listDeepSeekModels() {
  return request<{ models: DeepSeekModelInfo[] }>('/api/settings/deepseek/models');
}

export function uploadProjectFiles(projectId: string, files: File[]) {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  return fetch(`${apiBase()}/api/projects/${projectId}/upload`, {
    method: 'POST',
    body: form,
  }).then(async (res) => {
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail || (await res.text()));
    }
    return res.json() as Promise<ProjectFile[]>;
  });
}

export function parseProjectFiles(projectId: string) {
  return request<ProjectFile[]>(`/api/projects/${projectId}/parse`, { method: 'POST' });
}

export function previewProjectFile(projectId: string, fileId: string) {
  return request<{ id: string; filename: string; parse_status: string; content: string }>(
    `/api/projects/${projectId}/files/${fileId}/preview`,
  );
}

export function parseOneProjectFile(projectId: string, fileId: string) {
  return request<ProjectFile>(`/api/projects/${projectId}/files/${fileId}/parse`, { method: 'POST' });
}

export function deleteProjectFile(projectId: string, fileId: string) {
  return request<{ deleted: boolean; deleted_file_id: string }>(`/api/projects/${projectId}/files/${fileId}`, {
    method: 'DELETE',
  });
}

export function analyzeProject(projectId: string, autoFetchKnowledge = false) {
  return request<ProjectAnalyzeResult>(`/api/projects/${projectId}/analyze`, {
    method: 'POST',
    body: JSON.stringify({ auto_fetch_knowledge: autoFetchKnowledge }),
  });
}

export function runStartupAnalysis(projectId: string, refreshKnowledge = false, vaultPath = '') {
  return request<StartupAnalysis>(`/api/projects/${projectId}/startup-analysis`, {
    method: 'POST',
    body: JSON.stringify({ refresh_knowledge: refreshKnowledge, vault_path: vaultPath }),
  });
}

export function executeProjectInstruction(projectId: string, instruction: string) {
  return request<AgentRun>(`/api/projects/${projectId}/execute`, {
    method: 'POST',
    body: JSON.stringify({ instruction }),
  });
}

export function getStartupAnalysis(projectId: string) {
  return request<StartupAnalysis>(`/api/projects/${projectId}/startup-analysis`);
}

export function getProjectMindmap(projectId: string) {
  return request<MindmapData>(`/api/projects/${projectId}/mindmap`);
}

export function listObsidianCandidates(projectId: string) {
  return request<ObsidianCandidate[]>(`/api/projects/${projectId}/obsidian-candidates`);
}

export function runProjectAgent(projectId: string, agentId = 'project-parser') {
  return request<AgentRun>(`/api/agents/${agentId}/run`, {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, goal: '生成项目解析代理成果' }),
  });
}

export function triggerProjectAgent(projectId: string, agentId = 'project-parser') {
  return request<AgentRun>(`/api/projects/${projectId}/trigger-agent/${agentId}`, {
    method: 'POST',
    body: JSON.stringify({ trigger_type: 'manual', context_json: { source: 'project_detail' } }),
  });
}

export function getProjectTasks(projectId: string) {
  return request<ProjectTask[]>(`/api/projects/${projectId}/tasks`);
}

export function getProjectTimeline(projectId: string) {
  return request<ProjectTimeline[]>(`/api/projects/${projectId}/timeline`);
}

export function getProjectAgentRuns(projectId: string) {
  return request<AgentRun[]>(`/api/projects/${projectId}/agent-runs`);
}

export function deleteProjectExecutionRun(projectId: string, runId: string) {
  return request<{ deleted: boolean; deleted_run_id: string }>(`/api/projects/${projectId}/agent-runs/${runId}`, {
    method: 'DELETE',
  });
}

export function createTeamPlan(projectId: string) {
  return request<TeamPlan>(`/api/projects/${projectId}/team-plan`, { method: 'POST' });
}

export function createProjectMeeting(projectId: string, payload: Partial<ProjectMeeting>) {
  return request<ProjectMeeting>(`/api/projects/${projectId}/meetings`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteProjectMeeting(projectId: string, meetingId: string) {
  return request<{ deleted: boolean; deleted_meeting_id: string }>(`/api/projects/${projectId}/meetings/${meetingId}`, {
    method: 'DELETE',
  });
}

export function createTencentProjectMeeting(projectId: string, payload: { title: string; start_time: string; end_time: string; agenda?: string }) {
  return request<ProjectMeeting>(`/api/projects/${projectId}/meetings/tencent`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function syncTencentMeetingMinutes(projectId: string, meetingId: string) {
  return request<ProjectMeeting>(`/api/projects/${projectId}/meetings/${meetingId}/sync-tencent-minutes`, {
    method: 'POST',
  });
}

export function summarizeProjectMeeting(projectId: string, meetingId: string, payload: Partial<ProjectMeeting>) {
  return request<ProjectMeeting>(`/api/projects/${projectId}/meetings/${meetingId}/summarize`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function runSkillCard(projectId: string, cardType: string, prompt = '') {
  return request<SkillCard>(`/api/projects/${projectId}/skill-cards/run`, {
    method: 'POST',
    body: JSON.stringify({ card_type: cardType, prompt }),
  });
}

export function createProjectAssignment(projectId: string, payload: Partial<ProjectAssignment>) {
  return request<ProjectAssignment>(`/api/projects/${projectId}/assignments`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function assignProjectTask(
  projectId: string,
  taskId: string,
  payload: { assignee_type: string; assignee_id: string; assignee_name: string },
) {
  return request<ProjectTask>(`/api/projects/${projectId}/tasks/${taskId}/assignee`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function createProjectTask(projectId: string, payload: Partial<ProjectTask> & { task_name: string }) {
  return request<ProjectTask>(`/api/projects/${projectId}/tasks`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateProjectTask(projectId: string, taskId: string, payload: Partial<ProjectTask>) {
  return request<ProjectTask>(`/api/projects/${projectId}/tasks/${taskId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteProjectTask(projectId: string, taskId: string) {
  return request<{ deleted: boolean; deleted_task_id: string }>(`/api/projects/${projectId}/tasks/${taskId}`, {
    method: 'DELETE',
  });
}

export function getDashboard() {
  return request<DashboardData>('/api/dashboard');
}

export function getBossDashboard() {
  return request<BossDashboardData>('/api/boss/dashboard');
}

export function scanKnowledge(path: string, clearExisting = false) {
  return request<{ indexed_files: number; stats: Record<string, number>; recent_files: unknown[] }>('/api/knowledge/scan', {
    method: 'POST',
    body: JSON.stringify({ path, clear_existing: clearExisting }),
  });
}

export function indexVaultKnowledge(path: string, clearExisting = false, includeSyncNotes = false) {
  return request<KnowledgeUploadResult>('/api/knowledge/index-vault', {
    method: 'POST',
    body: JSON.stringify({ path, clear_existing: clearExisting, include_sync_notes: includeSyncNotes }),
  });
}

export function startVaultIndexJob(path: string, clearExisting = false, includeSyncNotes = false) {
  return request<KnowledgeIndexJob>('/api/knowledge/index-vault/start', {
    method: 'POST',
    body: JSON.stringify({ path, clear_existing: clearExisting, include_sync_notes: includeSyncNotes }),
  });
}

export function getVaultIndexJob(jobId: string) {
  return request<KnowledgeIndexJob>(`/api/knowledge/index-vault/jobs/${jobId}`);
}

export type KnowledgeUploadFile = File | { file: File; relativePath: string };

export function uploadKnowledgeFiles(files: KnowledgeUploadFile[], clearExisting = false, sourceLabel = 'browser-folder') {
  const form = new FormData();
  form.append('clear_existing', String(clearExisting));
  form.append('source_label', sourceLabel);
  files.forEach((entry) => {
    const file = entry instanceof File ? entry : entry.file;
    const relativePath = entry instanceof File ? (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name : entry.relativePath;
    form.append('files', file, relativePath);
  });
  return fetch(`${apiBase()}/api/knowledge/upload`, {
    method: 'POST',
    body: form,
  }).then(async (res) => {
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail || (await res.text()));
    }
    return res.json() as Promise<KnowledgeUploadResult>;
  });
}

export function reindexKnowledge(path: string) {
  return request<{ indexed_files: number; stats: Record<string, number>; recent_files: unknown[] }>('/api/knowledge/reindex', {
    method: 'POST',
    body: JSON.stringify({ path, clear_existing: true }),
  });
}

export function incrementalKnowledge(path: string) {
  return request<{ indexed_files: number; stats: Record<string, number>; recent_files: unknown[] }>('/api/knowledge/incremental', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

export function clearKnowledge() {
  return request<{ ok: boolean }>('/api/knowledge/clear', { method: 'POST' });
}

export function askKnowledge(question: string, projectId?: string) {
  return request<{ mode: string; answer: string; references: Array<{ file_name: string; file_path: string; quote: string }> }>('/api/knowledge/ask', {
    method: 'POST',
    body: JSON.stringify({ question, project_id: projectId }),
  });
}

export function searchKnowledgePost(question: string, limit = 8) {
  return request<{ items: Array<{ chunk_id: string; file_name: string; file_path: string; heading: string; quote: string }>; total: number }>('/api/knowledge/search', {
    method: 'POST',
    body: JSON.stringify({ question, limit }),
  });
}

export function getKnowledgeStats() {
  return request<KnowledgeStats>('/api/knowledge/stats');
}

export function getKnowledgeTree() {
  return request<{ tree: unknown[] }>('/api/knowledge/tree');
}

export function getRecentKnowledgeFiles() {
  return request<{ total: number; items: KnowledgeFileItem[] }>('/api/knowledge/recent-files');
}

export function listKnowledgeFiles(q = '', limit = 100) {
  const query = new URLSearchParams();
  if (q.trim()) query.set('q', q.trim());
  query.set('limit', String(limit));
  return request<{ total: number; items: KnowledgeFileItem[] }>(`/api/knowledge/recent-files?${query.toString()}`);
}

export function listAgents() {
  return request<{ agents: AgentInfo[] }>('/api/agents');
}

export function listDigitalEmployees() {
  return request<DigitalEmployee[]>('/api/designers/digital-employees');
}

export function listTeamMembers() {
  return request<{ members: NetworkMember[] }>('/api/team/members');
}

export function updateNetworkHumanMember(memberId: string, payload: { name?: string; role?: string }) {
  return request<TeamMember>(`/api/team/members/${memberId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function getNetworkMemberWorkload(memberType: 'human' | 'digital_employee', memberId: string) {
  return request<NetworkMemberWorkload>(`/api/network/members/${memberType}/${memberId}/workload`);
}

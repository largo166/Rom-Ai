import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import {
  CheckCircle2,
  Circle,
  Loader2,
  ChevronRight,
  LayoutDashboard,
  FileText,
  CalendarDays,
  ClipboardList,
  Sparkles,
  Users,
  Bot,
  Trash2,
} from 'lucide-react';
import {
  deleteProject,
  getProject,
  runStartupAnalysis,
  type ProjectDetail,
  type StartupAnalysis,
} from '../lib/projectsApi';
import { OverviewTab } from '../components/project/OverviewTab';
import { FilesTab } from '../components/project/FilesTab';
import { ExecutionTab } from '../components/project/ExecutionTab';
import { MeetingsTab } from '../components/project/MeetingsTab';
import { TasksTab } from '../components/project/TasksTab';
import { AiResultsTab } from '../components/project/AiResultsTab';
import { TeamTab } from '../components/project/TeamTab';

const tabs = [
  { key: 'overview', label: '概览', icon: LayoutDashboard },
  { key: 'files', label: '资料', icon: FileText },
  { key: 'execution', label: '执行台', icon: Bot },
  { key: 'meetings', label: '会议', icon: CalendarDays },
  { key: 'tasks', label: '任务', icon: ClipboardList },
  { key: 'ai-results', label: 'AI成果', icon: Sparkles },
  { key: 'team', label: '团队', icon: Users },
] as const;

type TabKey = (typeof tabs)[number]['key'];

type AnalysisStepStatus = 'pending' | 'active' | 'done' | 'error';

type AnalysisStep = {
  key: string;
  title: string;
  detail: string;
  status: AnalysisStepStatus;
};

function getStatusBadge(status: string) {
  const s = status?.toLowerCase() ?? '';
  if (s.includes('active') || s.includes('进行中'))
    return 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300';
  if (s.includes('risk') || s.includes('风险') || s.includes('blocked'))
    return 'border-red-500/20 bg-red-500/10 text-red-300';
  if (s.includes('done') || s.includes('完成') || s.includes('completed'))
    return 'border-zinc-500/20 bg-zinc-500/10 text-zinc-400';
  if (s.includes('paused') || s.includes('暂停'))
    return 'border-yellow-500/20 bg-yellow-500/10 text-yellow-300';
  return 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300';
}

export function ProjectDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get('tab');
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>(
    tabs.some((tab) => tab.key === initialTab) ? initialTab as TabKey : 'overview',
  );
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [analysisStartedAt, setAnalysisStartedAt] = useState<number | null>(null);
  const [analysisElapsed, setAnalysisElapsed] = useState(0);
  const [analysisSteps, setAnalysisSteps] = useState<AnalysisStep[]>([]);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmName, setDeleteConfirmName] = useState('');
  const [focusTaskId, setFocusTaskId] = useState<string>('');
  const [focusMemberId, setFocusMemberId] = useState<string>('');

  function selectTab(tab: TabKey) {
    setActiveTab(tab);
    setSearchParams(tab === 'overview' ? {} : { tab }, { replace: true });
  }

  useEffect(() => {
    if (!busy || !analysisStartedAt) return;
    const timer = window.setInterval(() => {
      setAnalysisElapsed(Math.floor((Date.now() - analysisStartedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [busy, analysisStartedAt]);

  const fileSummary = useMemo(() => {
    const files = project?.files ?? [];
    const pendingAnalysisFiles = files.filter((file) => (file.analysis_status || 'pending') === 'pending');
    const parsed = pendingAnalysisFiles.filter((file) => file.parse_status === 'parsed').length;
    const pending = pendingAnalysisFiles.filter((file) => file.parse_status !== 'parsed').length;
    const analyzed = files.length - pendingAnalysisFiles.length;
    return { files, pendingAnalysisFiles, parsed, pending, analyzed };
  }, [project]);

  function makeAnalysisSteps(activeKey: string, result?: StartupAnalysis): AnalysisStep[] {
    const hasFiles = fileSummary.pendingAnalysisFiles.length > 0;
    const allParsed = hasFiles && fileSummary.pending === 0;
    const mode = result?.mode || result?.report?.mode || '';
    const model = result?.report?.model_name || 'DeepSeek';
    const items: Array<Omit<AnalysisStep, 'status'>> = [
      {
        key: 'files',
        title: '检查待分析资料',
        detail: hasFiles
          ? `本次只分析 ${fileSummary.pendingAnalysisFiles.length} 个待分析文件，${fileSummary.parsed} 个已解析${fileSummary.pending ? `，${fileSummary.pending} 个未解析` : ''}；${fileSummary.analyzed} 个旧文件不重复分析`
          : '当前没有新的待分析文件；如需分析新资料，请先上传并解析文件',
      },
      {
        key: 'context',
        title: '整理分析上下文',
        detail: allParsed
          ? '正在合并项目基本信息、本次新增文件解析文本和知识库引用'
          : '会把未解析文件标记为资料缺口，不伪造文件内容',
      },
      {
        key: 'deepseek',
        title: '调用 DeepSeek',
        detail: mode
          ? `${mode === 'deepseek' ? '真实 API 已返回' : mode === 'mock' ? '当前为 Mock 模式' : 'DeepSeek 调用异常，已回退'} · ${model}`
          : '等待模型生成技术重点、任务拆解、会议议程和 PPT 结构',
      },
      {
        key: 'writeback',
        title: '写入项目工作台',
        detail: result
          ? `已写入 ${result.technical_focus_cards?.length ?? 0} 张技术卡、${result.task_breakdown?.length ?? 0} 个任务、${result.meeting_agenda?.length ?? 0} 条会议议程`
          : '生成后会保存报告，并同步到技术卡、任务、会议和 AI 成果',
      },
    ];
    const activeIndex = items.findIndex((item) => item.key === activeKey);
    return items.map((item, index) => ({
      ...item,
      status: result
        ? 'done'
        : index < activeIndex
          ? 'done'
          : index === activeIndex
            ? 'active'
            : 'pending',
    }));
  }

  function setActiveAnalysisStep(activeKey: string) {
    setAnalysisSteps(makeAnalysisSteps(activeKey));
  }

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setMessage('');
    try {
      setProject(await getProject(id));
    } catch (error) {
      setMessage(`读取项目失败：${String(error)}`);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function runStartup() {
    if (!id) return;
    if (fileSummary.pendingAnalysisFiles.length === 0) {
      setAnalysisSteps(makeAnalysisSteps('files'));
      setMessage('当前没有新的待分析文件。请先上传新资料并解析，再运行启动分析。');
      return;
    }
    const start = Date.now();
    setBusy(true);
    setAnalysisStartedAt(start);
    setAnalysisElapsed(0);
    setMessage('');
    setActiveAnalysisStep('files');
    try {
      window.setTimeout(() => setActiveAnalysisStep('context'), 350);
      window.setTimeout(() => setActiveAnalysisStep('deepseek'), 900);
      const result = await runStartupAnalysis(id);
      setAnalysisSteps(makeAnalysisSteps('writeback', result));
      await load();
      const modeLabel = result.mode === 'deepseek' ? 'DeepSeek 真实分析' : result.mode === 'mock' ? 'Mock 模式分析' : '回退分析';
      setMessage(`项目启动分析已生成（${modeLabel}），技术重点、任务拆解、会议议程已写入。`);
      selectTab('overview');
    } catch (error) {
      setAnalysisSteps((steps) => steps.map((step) => (step.status === 'active' ? { ...step, status: 'error' } : step)));
      setMessage(`启动分析失败：${String(error)}`);
    } finally {
      setBusy(false);
      setAnalysisElapsed(Math.floor((Date.now() - start) / 1000));
    }
  }

  async function onDeleteProject() {
    if (!id || !project || deleteConfirmName.trim() !== project.name) return;
    setBusy(true);
    setMessage('正在删除项目库...');
    try {
      await deleteProject(id);
      navigate('/projects');
    } catch (error) {
      setMessage(`删除项目失败：${String(error)}`);
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#0A0A0A] px-6 pb-20 pt-28 md:px-12">
      <div className="mx-auto max-w-[1320px]">
        {/* 面包屑 */}
        <nav className="mb-6 flex items-center gap-2 text-sm text-zinc-500">
          <Link to="/projects" className="hover:text-white transition-colors">
            项目中心
          </Link>
          <ChevronRight size={14} />
          <span className="text-zinc-300">{project?.name ?? '加载中...'}</span>
        </nav>

        {/* 全局消息 */}
        {message && (
          <div className="mb-5 rounded-lg border border-white/10 bg-white/5 p-4 text-sm text-zinc-300">
            {busy && <Loader2 size={14} className="mr-2 inline animate-spin" />}
            {message}
          </div>
        )}

        {loading && (
          <div className="rounded-xl border border-white/10 bg-white/5 p-8 text-center">
            <Loader2 size={32} className="mx-auto mb-4 animate-spin text-amber-400" />
            <p className="text-sm text-zinc-400">正在读取项目...</p>
          </div>
        )}

        {project && (
          <>
            {/* 项目头部 */}
            <section className="mb-6 rounded-xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm md:p-7">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <h1 className="mb-2 text-2xl font-bold tracking-tight text-white md:text-4xl">
                    {project.name}
                  </h1>
                  {project.description && (
                    <p className="max-w-3xl text-sm leading-6 text-zinc-400">{project.description}</p>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    disabled={busy}
                    onClick={runStartup}
                    className="rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-60"
                  >
                    {busy ? '运行中...' : '运行启动分析'}
                  </button>
                  <span
                    className={`rounded-full border px-3 py-1.5 text-xs ${getStatusBadge(project.status)}`}
                  >
                    {project.status}
                  </span>
                  <button
                    disabled={busy}
                    onClick={() => {
                      setDeleteOpen((value) => !value);
                      setDeleteConfirmName('');
                    }}
                    className="inline-flex items-center gap-2 rounded-lg border border-red-400/30 px-3 py-2 text-sm text-red-200 hover:border-red-300/70 disabled:opacity-50"
                  >
                    <Trash2 size={15} />
                    删除项目库
                  </button>
                </div>
              </div>
              {deleteOpen && (
                <div className="mt-5 rounded-lg border border-red-400/20 bg-red-400/5 p-4">
                  <div className="mb-3">
                    <h2 className="text-sm font-semibold text-red-100">确认删除项目库</h2>
                    <p className="mt-1 text-xs leading-5 text-red-100/70">
                      将删除项目记录、项目资料目录、分析结果、任务、会议和团队分配。收件箱原始来源文件不会被删除。
                    </p>
                  </div>
                  <div className="flex flex-col gap-2 md:flex-row">
                    <input
                      value={deleteConfirmName}
                      onChange={(event) => setDeleteConfirmName(event.target.value)}
                      placeholder={`输入项目名：${project.name}`}
                      className="min-h-10 flex-1 rounded-lg border border-red-400/20 bg-[#0A0A0A] px-3 text-sm text-white outline-none focus:border-red-300/60"
                    />
                    <button
                      onClick={onDeleteProject}
                      disabled={busy || deleteConfirmName.trim() !== project.name}
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-red-400 px-4 py-2 text-sm font-semibold text-black hover:bg-red-300 disabled:opacity-40"
                    >
                      {busy ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                      确认删除
                    </button>
                  </div>
                </div>
              )}
            </section>

            {analysisSteps.length > 0 && (
              <section className="mb-6 rounded-xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm md:p-6">
                <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-white">启动分析行进</h2>
                    <p className="mt-1 text-xs text-zinc-500">耗时 {analysisElapsed}s · 展示当前请求内的关键处理阶段</p>
                  </div>
                  {busy && (
                    <div className="inline-flex w-fit items-center gap-2 rounded-full border border-amber-400/20 bg-amber-400/10 px-3 py-1 text-xs text-amber-200">
                      <Loader2 size={13} className="animate-spin" />
                      正在分析
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                  {analysisSteps.map((step) => (
                    <div key={step.key} className="rounded-lg border border-white/10 bg-[#0E0E0E] p-4">
                      <div className="mb-2 flex items-center gap-2">
                        {step.status === 'done' && <CheckCircle2 size={15} className="text-emerald-300" />}
                        {step.status === 'active' && <Loader2 size={15} className="animate-spin text-amber-300" />}
                        {step.status === 'pending' && <Circle size={15} className="text-zinc-600" />}
                        {step.status === 'error' && <Circle size={15} className="text-red-300" />}
                        <span className="text-sm font-medium text-white">{step.title}</span>
                      </div>
                      <p className="text-xs leading-5 text-zinc-500">{step.detail}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Tab 切换栏 - 底部线条高亮 */}
            <section className="rounded-t-xl border-b border-white/10 bg-white/5">
              <div className="flex gap-0 overflow-x-auto">
                {tabs.map((tab) => {
                  const Icon = tab.icon;
                  const isActive = activeTab === tab.key;
                  return (
                    <button
                      key={tab.key}
                      onClick={() => selectTab(tab.key)}
                      className={`relative flex items-center gap-2 whitespace-nowrap px-4 py-3 text-sm transition-colors ${
                        isActive
                          ? 'text-amber-400'
                          : 'text-gray-400 hover:text-white'
                      }`}
                    >
                      <Icon size={16} />
                      <span>{tab.label}</span>
                      {/* 底部高亮线 */}
                      {isActive && (
                        <span className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-amber-500" />
                      )}
                    </button>
                  );
                })}
              </div>
            </section>

            {/* Tab 内容区 */}
            <section className="rounded-b-xl border border-t-0 border-white/10 bg-white/[0.03] p-5 backdrop-blur-sm md:p-7">
              {activeTab === 'overview' && (
                <OverviewTab projectId={id!} project={project} onRefresh={load} onSwitchTab={selectTab as (tab: string) => void} />
              )}
              {activeTab === 'files' && (
                <FilesTab projectId={id!} project={project} onRefresh={load} />
              )}
              {activeTab === 'execution' && (
                <ExecutionTab projectId={id!} project={project} onRefresh={load} />
              )}
              {activeTab === 'meetings' && (
                <MeetingsTab projectId={id!} meetings={project.meetings} onRefresh={load} />
              )}
              {activeTab === 'tasks' && (
                <TasksTab
                  projectId={id!}
                  project={project}
                  tasks={project.tasks}
                  focusTaskId={focusTaskId}
                  onRefresh={load}
                  onOpenMember={(memberId) => {
                    setFocusMemberId(memberId);
                    selectTab('team');
                  }}
                  onOpenMeeting={() => selectTab('meetings')}
                />
              )}
              {activeTab === 'ai-results' && (
                <AiResultsTab project={project} />
              )}
              {activeTab === 'team' && (
                <TeamTab
                  projectId={id!}
                  project={project}
                  focusMemberId={focusMemberId}
                  onRefresh={load}
                  onOpenTask={(taskId) => {
                    setFocusTaskId(taskId);
                    selectTab('tasks');
                  }}
                />
              )}
            </section>
          </>
        )}
      </div>
    </main>
  );
}

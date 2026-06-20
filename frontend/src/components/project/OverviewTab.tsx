import { useCallback, useEffect, useState } from 'react';
import {
  FileText,
  Calendar,
  ClipboardList,
  AlertTriangle,
  Target,
  RefreshCw,
  ChevronRight,
  Package,
  Loader2,
  PlayCircle,
  MapPin,
  Building2,
  Milestone as MilestoneIcon,
  ShieldAlert,
  type LucideIcon,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardAction } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import {
  type ProjectDetail,
  type OverviewDashboardData,
  type AnalysisFreshness,
  type OkfBundleStatus,
  getOverviewDashboard,
  runStartupAnalysis,
  getAnalysisFreshness,
  runIncrementalAnalysis,
  getOkfBundle,
  generateOkfBundle,
} from '../../lib/projectsApi';
import { RecommendationPanel } from '../knowledge/RecommendationPanel';

type Props = {
  projectId: string;
  project: ProjectDetail;
  onRefresh: () => void;
  onSwitchTab?: (tab: string) => void;
};

// ── 工具函数 ──────────────────────────────────────────────────────────────

function riskColor(level: string): string {
  const l = (level || '').toLowerCase();
  if (l === 'high' || l.includes('高')) return 'text-red-700 border-red-200 bg-red-50';
  if (l === 'low' || l.includes('低')) return 'text-green-700 border-green-200 bg-green-50';
  return 'text-amber-700 border-amber-200 bg-amber-50';
}

function riskDot(level: string): string {
  const l = (level || '').toLowerCase();
  if (l === 'high' || l.includes('高')) return 'bg-red-600';
  if (l === 'low' || l.includes('低')) return 'bg-green-600';
  return 'bg-amber-500';
}

function riskLabel(level: string): string {
  const l = (level || '').toLowerCase();
  if (l === 'high' || l.includes('高')) return '高';
  if (l === 'low' || l.includes('低')) return '低';
  return '中';
}

function milestoneStatusColor(status?: string): string {
  const s = (status || '').toLowerCase();
  if (s.includes('done') || s.includes('完成')) return 'text-green-700 border-green-200';
  if (s.includes('progress') || s.includes('进行')) return 'text-blue-700 border-blue-200';
  return 'text-stone-600 border-stone-300';
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  } catch {
    return iso;
  }
}

// ── 组件 ──────────────────────────────────────────────────────────────────

export function OverviewTab({ projectId, project, onRefresh, onSwitchTab }: Props) {
  const [data, setData] = useState<OverviewDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [okf, setOkf] = useState<OkfBundleStatus | null>(null);
  const [okfBusy, setOkfBusy] = useState(false);

  const fetchOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getOverviewDashboard(projectId);
      setData(res);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

  const fetchOkf = useCallback(async () => {
    try {
      setOkf(await getOkfBundle(projectId));
    } catch {
      setOkf(null);
    }
  }, [projectId]);

  useEffect(() => {
    fetchOkf();
  }, [fetchOkf]);

  async function handleRegenerate() {
    if (!projectId) return;
    setBusy(true);
    setMessage('');
    try {
      await runStartupAnalysis(projectId);
      await fetchOverview();
      await onRefresh();
      setMessage('智能研判已重新生成。');
    } catch (error) {
      setMessage(`生成失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerateOkf() {
    setOkfBusy(true);
    setMessage('');
    try {
      const next = await generateOkfBundle(projectId);
      setOkf(next);
      await onRefresh();
      setMessage(`项目数据链接已刷新：${next.files.length} 个 Markdown 索引文件已生成并进入知识库。`);
    } catch (error) {
      setMessage(`项目数据链接刷新失败：${String(error)}`);
    } finally {
      setOkfBusy(false);
    }
  }

  // ── 加载中骨架 ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-20 w-full rounded-xl bg-stone-200" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl bg-stone-200" />
          ))}
        </div>
        <Skeleton className="h-48 w-full rounded-xl bg-stone-200" />
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <Skeleton className="h-64 rounded-xl bg-stone-200" />
          <Skeleton className="h-64 rounded-xl bg-stone-200" />
        </div>
      </div>
    );
  }

  const proj = data?.project ?? project;
  const metrics = data?.metrics;
  const analysis = data?.analysis;
  const recentMeeting = data?.recent_meeting;
  const nextActions = data?.next_actions ?? [];
  const milestones = data?.milestones ?? [];
  const risks = data?.risks ?? [];

  return (
    <div className="space-y-6">
      {/* 消息提示 */}
      {message && (
        <div className="rounded-lg border border-stone-200 bg-stone-50 p-3 text-sm text-stone-700">
          {busy && <Loader2 size={14} className="mr-2 inline animate-spin" />}
          {message}
        </div>
      )}

      {/* ── 1. 顶部概览条 ─────────────────────────────────────────────── */}
      <Card className="rounded-xl border border-stone-200 bg-white py-4 shadow-xs">
        <CardContent className="px-5">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <span className="font-serif text-lg font-bold text-stone-900">{proj.name}</span>
            <Separator orientation="vertical" className="h-5 bg-stone-200" />
            <span className="text-stone-600">
              阶段：<span className="text-stone-800">{proj.phase || '待补充'}</span>
            </span>
            <Separator orientation="vertical" className="h-5 bg-stone-200" />
            <span className="flex items-center gap-1 text-stone-600">
              <MapPin size={13} />
              <span className="text-stone-800">{proj.city || '待补充'}</span>
            </span>
            <Separator orientation="vertical" className="h-5 bg-stone-200" />
            <span className="text-stone-600">
              业态：<span className="text-stone-800">{proj.project_type || '待补充'}</span>
            </span>
            <Separator orientation="vertical" className="h-5 bg-stone-200" />
            <span className="flex items-center gap-1 text-stone-600">
              <Building2 size={13} />
              <span className="text-stone-800">{proj.client_name || '甲方待补充'}</span>
            </span>
            {proj.client_contact && (
              <>
                <Separator orientation="vertical" className="h-5 bg-stone-200" />
                <span className="text-stone-400">{proj.client_contact}</span>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── 2. 指标条 ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <MetricCard icon={FileText} label="文件数" value={metrics?.files_count} color="text-stone-600" />
        <MetricCard icon={Calendar} label="会议数" value={metrics?.meetings_count} color="text-stone-600" />
        <MetricCard
          icon={ClipboardList}
          label="待办"
          value={metrics ? `${metrics.tasks_done}/${metrics.tasks_total}` : undefined}
          color="text-[#C2703A]"
        />
        <MetricCard icon={AlertTriangle} label="风险数" value={metrics?.risks_count} color="text-red-700" />
        <MetricCard icon={Target} label="成果缺口" value={metrics?.deliverables_gap} color="text-stone-600" />
      </div>

      {/* ── 3. 智能研判区 ──────────────────────────────────────────────── */}
      <Card className="rounded-xl border border-stone-200 bg-white shadow-xs">
        <CardHeader className="border-b border-stone-200 pb-4">
          <CardTitle className="font-serif text-sm font-semibold text-stone-900">智能研判</CardTitle>
          <CardAction>
            <div className="flex items-center gap-3">
              {analysis && (
                <Badge variant="outline" className="border-stone-200 text-[11px] text-stone-600">
                  {analysis.mode === 'deepseek' ? 'DeepSeek' : analysis.mode === 'mock' ? 'Mock' : analysis.mode}
                  {analysis.model_name ? ` · ${analysis.model_name}` : ''}
                </Badge>
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={handleRegenerate}
                disabled={busy}
                className="border-[#C2703A]/30 bg-[#C2703A]/10 text-[#C2703A] hover:bg-[#C2703A]/15"
              >
                {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                重新生成
              </Button>
            </div>
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-4 pt-4">
          <AnalysisFreshnessIndicator projectId={projectId} onRefreshed={fetchOverview} />
          <div className="flex flex-col gap-4 rounded-lg border border-stone-200 bg-stone-50/70 p-4 md:flex-row md:items-center md:justify-between">
              <div className="flex min-w-0 items-start gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#C2703A]/10 text-[#C2703A]">
                  <Package size={18} />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-stone-900">项目数据链接</p>
                    <Badge variant="outline" className={okf?.generated ? 'border-green-200 text-green-700' : 'border-stone-300 text-stone-500'}>
                      {okf?.generated ? '已生成' : '未生成'}
                    </Badge>
                  </div>
                  <p className="mt-1 break-all text-xs leading-5 text-stone-500">
                    {okf?.generated
                      ? `${okf.files.length} 个 AI 可读索引文件 · ${okf.updated_at ? `更新于 ${formatDate(okf.updated_at)}` : '等待更新时间'} · ${okf.root_path}`
                      : '生成后会写入项目受管目录，并进入知识库索引，供 AI 代理读取当前项目资料、会议、任务和判断。'}
                  </p>
                </div>
              </div>
              <Button
                size="sm"
                onClick={handleGenerateOkf}
                disabled={okfBusy}
                className="shrink-0 bg-stone-900 text-white hover:bg-stone-800"
              >
                {okfBusy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                {okf?.generated ? '刷新数据链接' : '生成数据链接'}
              </Button>
          </div>
          {analysis ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {/* 项目定位 */}
              <AnalysisBlock
                title="项目定位"
                content={
                  (analysis.project_summary as Record<string, unknown>)?.summary as string ||
                  analysis.project_basis ||
                  ''
                }
                fallback="暂无项目定位信息"
              />
              {/* 设计主线 */}
              <AnalysisBlock
                title="设计主线"
                content={formatList(analysis.design_difficulties)}
                fallback="暂无设计主线信息"
              />
              {/* 风险提示 */}
              <AnalysisBlock
                title="风险提示"
                content={formatList(analysis.risk_list)}
                fallback="暂无风险提示"
              />
              {/* 开放问题 */}
              <AnalysisBlock
                title="待解决疑问"
                content={formatList(analysis.open_questions)}
                fallback="暂无开放问题"
              />
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <PlayCircle size={32} className="text-stone-300" />
              <p className="text-sm text-stone-400">尚未生成智能研判。点击「重新生成」启动分析。</p>
              <Button
                size="sm"
                onClick={handleRegenerate}
                disabled={busy}
                className="bg-[#C2703A] text-white hover:bg-[#C2703A]/90"
              >
                {busy ? <Loader2 size={14} className="animate-spin" /> : <PlayCircle size={14} />}
                运行启动分析
              </Button>
            </div>
          )}

          {/* 知识推荐面板 — 有分析结果时显示 */}
          {analysis && (
            <RecommendationPanel projectId={projectId} trigger="analysis" />
          )}

          {/* 技术重点卡片（如有）────────────────────────────────────────── */}
          {analysis?.technical_focus_cards && Array.isArray(analysis.technical_focus_cards) && analysis.technical_focus_cards.length > 0 && (
            <>
              <Separator className="my-4 bg-stone-200" />
              <div className="mb-3 flex items-center gap-2">
                <Target size={14} className="text-[#C2703A]" />
                <span className="text-xs font-medium text-stone-700">技术重点</span>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {(analysis.technical_focus_cards as Array<Record<string, unknown>>).map((card, i) => {
                  const dimension = (card.dimension as string) || (card.title as string) || `维度${i + 1}`;
                  const summary = (card.summary as string) || '';
                  const level = (card.manual_confirm as string) || 'medium';
                  return (
                    <div
                      key={i}
                      className={`rounded-lg border p-3 ${riskColor(level)}`}
                    >
                      <div className="mb-1.5 flex items-center justify-between">
                        <span className="text-xs font-medium text-stone-900">{dimension}</span>
                        <span className="flex items-center gap-1">
                          <span className={`h-1.5 w-1.5 rounded-full ${riskDot(level)}`} />
                          <span className="text-[10px]">{riskLabel(level)}</span>
                        </span>
                      </div>
                      <p className="text-[11px] leading-4 text-stone-600">{summary}</p>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* ── 4. 最近会议纪要摘要段 ────────────────────────────────────────── */}
      <Card className="rounded-xl border border-stone-200 bg-white shadow-xs">
        <CardHeader className="border-b border-stone-200 pb-3">
          <CardTitle className="font-serif text-sm font-semibold text-stone-900">最近会议纪要</CardTitle>
          <CardAction>
            {recentMeeting && onSwitchTab && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onSwitchTab('meetings')}
                className="text-[#C2703A] hover:text-[#C2703A]/80"
              >
                查看完整
                <ChevronRight size={14} />
              </Button>
            )}
          </CardAction>
        </CardHeader>
        <CardContent className="pt-3">
          {recentMeeting ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Calendar size={14} className="text-stone-400" />
                <span className="text-sm font-medium text-stone-800">{recentMeeting.title}</span>
                {recentMeeting.date && (
                  <span className="text-xs text-stone-400">{formatDate(recentMeeting.date)}</span>
                )}
                <Badge variant="outline" className="ml-auto border-stone-200 text-[10px] text-stone-600">
                  {recentMeeting.status}
                </Badge>
              </div>
              <p className="line-clamp-3 text-xs leading-6 text-stone-600">
                {recentMeeting.summary || '会议已创建，纪要待生成。'}
              </p>
            </div>
          ) : (
            <p className="py-4 text-center text-xs text-stone-400">
              暂无会议记录。可在会议页或 AI代理的会议纪要卡创建。
            </p>
          )}
        </CardContent>
      </Card>

      {/* ── 5. 双栏区 ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* 左栏：下一步待办 + 里程碑时间线 */}
        <div className="space-y-4">
          {/* 下一步待办 */}
          <Card className="rounded-xl border border-stone-200 bg-white shadow-xs">
            <CardHeader className="border-b border-stone-200 pb-3">
              <CardTitle className="font-serif text-sm font-semibold text-stone-900">下一步待办</CardTitle>
              <CardAction>
                {nextActions.length > 0 && onSwitchTab && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onSwitchTab('tasks')}
                    className="text-[#C2703A] hover:text-[#C2703A]/80"
                  >
                    全部任务
                    <ChevronRight size={14} />
                  </Button>
                )}
              </CardAction>
            </CardHeader>
            <CardContent className="pt-3">
              {nextActions.length > 0 ? (
                <div className="space-y-2">
                  {nextActions.map((task) => (
                    <div
                      key={task.id}
                      className="flex items-start gap-3 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2"
                    >
                      <ClipboardList size={14} className="mt-0.5 shrink-0 text-stone-400" />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-medium text-stone-800">{task.task_name}</div>
                        <div className="mt-0.5 text-[11px] text-stone-400">
                          {task.assignee_name || task.owner_role || '待分配'}
                          {' · '}
                          {task.priority === 'high' ? '高优' : task.priority === 'low' ? '低优' : '普通'}
                          {task.due_date ? ` · 截止 ${formatDate(task.due_date)}` : ''}
                        </div>
                      </div>
                      {task.risk_level && (
                        <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] ${riskColor(task.risk_level)}`}>
                          {riskLabel(task.risk_level)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="py-4 text-center text-xs text-stone-400">
                  暂无待办任务。可用 AI代理生成任务拆解。
                </p>
              )}
            </CardContent>
          </Card>

          {/* 里程碑时间线 */}
          <Card className="rounded-xl border border-stone-200 bg-white shadow-xs">
            <CardHeader className="border-b border-stone-200 pb-3">
              <CardTitle className="flex items-center gap-2 font-serif text-sm font-semibold text-stone-900">
                <MilestoneIcon size={15} className="text-[#C2703A]" />
                里程碑
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-3">
              {milestones.length > 0 ? (
                <div className="relative space-y-3 pl-4">
                  <div className="absolute left-[5px] top-1 bottom-1 w-px bg-stone-200" />
                  {milestones.map((ms, i) => {
                    const name = (ms.name as string) || `里程碑 ${i + 1}`;
                    const date = ms.date as string;
                    const status = ms.status as string;
                    return (
                      <div key={i} className="relative flex items-center gap-3">
                        <span
                          className={`absolute -left-4 h-2.5 w-2.5 rounded-full border-2 bg-white ${milestoneStatusColor(status)}`}
                        />
                        <div className="flex-1">
                          <span className="text-xs font-medium text-stone-800">{name}</span>
                          {date && (
                            <span className="ml-2 text-[11px] text-stone-400">{formatDate(date)}</span>
                          )}
                        </div>
                        {status && (
                          <Badge
                            variant="outline"
                            className={`text-[10px] ${milestoneStatusColor(status)}`}
                          >
                            {status}
                          </Badge>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="py-4 text-center text-xs text-stone-400">
                  暂无里程碑记录。
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* 右栏：风险看板 + 可复用资产 */}
        <div className="space-y-4">
          {/* 风险看板 */}
          <Card className="rounded-xl border border-stone-200 bg-white shadow-xs">
            <CardHeader className="border-b border-stone-200 pb-3">
              <CardTitle className="flex items-center gap-2 font-serif text-sm font-semibold text-stone-900">
                <ShieldAlert size={15} className="text-red-700" />
                风险看板
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-3">
              {risks.length > 0 ? (
                <div className="space-y-2">
                  {risks.map((risk, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-3 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2"
                    >
                      <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${riskDot(risk.level)}`} />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-medium text-stone-800">{risk.title}</div>
                        {risk.detail && (
                          <div className="mt-0.5 line-clamp-2 text-[11px] text-stone-400">{risk.detail}</div>
                        )}
                        <div className="mt-1 flex items-center gap-2">
                          <Badge
                            variant="outline"
                            className={`text-[10px] ${riskColor(risk.level)}`}
                          >
                            {riskLabel(risk.level)}风险
                          </Badge>
                          <span className="text-[10px] text-stone-400">
                            {risk.source === 'task' ? '来源：任务' : risk.source === 'summary' ? '来源：风险摘要' : '来源：分析报告'}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="py-4 text-center text-xs text-stone-400">
                  暂无风险项。
                </p>
              )}
            </CardContent>
          </Card>

          {/* 可复用资产（占位） */}
          <Card className="rounded-xl border border-stone-200 bg-white shadow-xs">
            <CardHeader className="border-b border-stone-200 pb-3">
              <CardTitle className="flex items-center gap-2 font-serif text-sm font-semibold text-stone-900">
                <Package size={15} className="text-stone-600" />
                可复用资产
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-3">
              <div className="flex flex-col items-center gap-2 py-6 text-center">
                <Package size={28} className="text-stone-300" />
                <p className="text-xs text-stone-400">检索接通后自动回填</p>
                <p className="max-w-xs text-[11px] leading-5 text-stone-400">
                  类比项目资料、历史成果模板将在知识检索接入后自动呈现
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ── 子组件 ─────────────────────────────────────────────────────────────────

function MetricCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: LucideIcon;
  label: string;
  value: number | string | undefined;
  color: string;
}) {
  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-xs">
      <div className="mb-2 flex items-center gap-2">
        <Icon size={15} className={color} />
        <span className="text-[11px] text-stone-400">{label}</span>
      </div>
      <div className="text-2xl font-semibold text-stone-900">
        {value !== undefined ? value : '—'}
      </div>
    </div>
  );
}

function AnalysisBlock({
  title,
  content,
  fallback,
}: {
  title: string;
  content: string;
  fallback: string;
}) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="h-1 w-3 rounded-full bg-[#C2703A]" />
        <span className="text-xs font-medium text-stone-700">{title}</span>
      </div>
      <p className="text-xs leading-6 text-stone-600">
        {content || fallback}
      </p>
    </div>
  );
}

// ── 辅助 ──────────────────────────────────────────────────────────────────

function formatList(items: unknown): string {
  if (!items || !Array.isArray(items) || items.length === 0) return '';
  return items
    .map((item) => {
      if (typeof item === 'string') return item;
      if (typeof item === 'object' && item !== null) {
        const obj = item as Record<string, unknown>;
        return (obj.title as string) || (obj.text as string) || (obj.summary as string) || '';
      }
      return String(item);
    })
    .filter(Boolean)
    .join('；');
}

// ── 分析新鲜度指示器 ─────────────────────────────────────────────────────

function AnalysisFreshnessIndicator({
  projectId,
  onRefreshed,
}: {
  projectId: string;
  onRefreshed?: () => void;
}) {
  const [freshness, setFreshness] = useState<AnalysisFreshness | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAnalysisFreshness(projectId)
      .then((data) => {
        if (!cancelled) setFreshness(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  async function handleIncrementalAnalysis() {
    setRefreshing(true);
    try {
      await runIncrementalAnalysis(projectId);
      const data = await getAnalysisFreshness(projectId);
      setFreshness(data);
      onRefreshed?.();
    } catch {
      // 静默失败，避免打扰用户
    } finally {
      setRefreshing(false);
    }
  }

  if (!freshness || !freshness.is_stale) return null;

  return (
    <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm">
      <span className="h-2 w-2 animate-pulse rounded-full bg-[#C2703A]" />
      <span className="text-stone-700">
        有 {freshness.unconsumed_count} 条新变更待刷新
      </span>
      <button
        onClick={handleIncrementalAnalysis}
        disabled={refreshing}
        className="ml-auto text-xs font-medium text-[#C2703A] transition-colors hover:underline disabled:cursor-not-allowed disabled:opacity-50"
      >
        {refreshing ? '刷新中…' : '立即刷新'}
      </button>
    </div>
  );
}

import { useState, useMemo } from 'react';
import {
  ClipboardList,
  Loader2,
  PlayCircle,
  Sun,
  Ruler,
  BarChart3,
  Flame,
  MapPin,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';
import {
  type ProjectDetail,
  type StartupAnalysis,
  runStartupAnalysis,
  getStartupAnalysis,
} from '../../lib/projectsApi';
import { useEffect } from 'react';

type Props = {
  projectId: string;
  project: ProjectDetail;
  onRefresh: () => void;
};

const techPointIcons: Record<string, LucideIcon> = {
  日照: Sun,
  退界: Ruler,
  面积: BarChart3,
  消防: Flame,
  规划: MapPin,
  报批: ShieldCheck,
};

const defaultTechPoints = [
  { dimension: '日照分析', summary: '分析项目日照条件、遮挡关系及合规性', risk_level: 'medium' },
  { dimension: '退界要求', summary: '核查建筑退红线、退绿线等退界条件', risk_level: 'low' },
  { dimension: '面积配比', summary: '复核地上地下面积、容积率、各业态配比', risk_level: 'medium' },
  { dimension: '消防设计', summary: '消防车道、登高面、防火分区等合规性审查', risk_level: 'high' },
  { dimension: '规划条件', summary: '规划条件复核：限高、密度、绿地率、配套设施', risk_level: 'medium' },
  { dimension: '报批风险', summary: '识别报规报建潜在风险点和审批障碍', risk_level: 'high' },
];

function getRiskColor(level: string) {
  const l = level?.toLowerCase() ?? '';
  if (l === 'high' || l.includes('高')) return { bg: 'bg-red-400/10', border: 'border-red-400/30', text: 'text-red-300', dot: 'bg-red-400' };
  if (l === 'low' || l.includes('低')) return { bg: 'bg-emerald-400/10', border: 'border-emerald-400/30', text: 'text-emerald-300', dot: 'bg-emerald-400' };
  return { bg: 'bg-yellow-400/10', border: 'border-yellow-400/30', text: 'text-yellow-300', dot: 'bg-yellow-400' };
}

function getRiskLabel(level: string) {
  const l = level?.toLowerCase() ?? '';
  if (l === 'high' || l.includes('高')) return '高风险';
  if (l === 'low' || l.includes('低')) return '低风险';
  return '中风险';
}

export function OverviewTab({ projectId, project, onRefresh }: Props) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [startupAnalysis, setStartupAnalysis] = useState<StartupAnalysis | null>(null);

  // 尝试加载启动分析
  useEffect(() => {
    if (projectId) {
      getStartupAnalysis(projectId).then(setStartupAnalysis).catch(() => setStartupAnalysis(null));
    }
  }, [projectId]);

  // 统计数据
  const todoTasks = project.tasks.filter((t) => t.status === 'todo' || t.status === 'pending' || t.status === '待办').length;
  const doingTasks = project.tasks.filter((t) => t.status === 'doing' || t.status === 'in_progress' || t.status === '进行中').length;
  const meetingCount = project.meetings.length;
  const aiResultCount = project.skill_cards.length;
  const riskTasks = project.tasks.filter((t) => (t.risk_level || '').includes('高') || (t.risk_level || '').toLowerCase() === 'high');
  const recentMeeting = [...project.meetings].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))[0];
  const nextTasks = project.tasks
    .filter((t) => !['done', 'completed', '已完成'].includes(t.status))
    .slice(0, 5);
  const deliverableGap = Math.max(0, 4 - project.files.filter((file) => ['pptx', 'pdf', 'docx', 'xlsx'].includes(file.filetype)).length);

  const stats = useMemo(() => [
    { label: '待办任务', value: todoTasks, color: 'text-amber-300' },
    { label: '进行中', value: doingTasks, color: 'text-blue-300' },
    { label: '会议数', value: meetingCount, color: 'text-emerald-300' },
    { label: 'AI成果', value: aiResultCount, color: 'text-violet-300' },
    { label: '高风险', value: riskTasks.length, color: 'text-red-300' },
    { label: '成果缺口', value: deliverableGap, color: 'text-sky-300' },
  ], [aiResultCount, deliverableGap, doingTasks, meetingCount, riskTasks.length, todoTasks]);

  // 技术重点：优先使用启动分析的技术重点卡，否则使用默认维度
  const techPoints: Array<{ dimension: string; summary: string; risk_level: string; checkpoints?: string[] }> =
    startupAnalysis?.technical_focus_cards?.length
      ? startupAnalysis.technical_focus_cards.map((card) => ({
          dimension: card.dimension,
          summary: card.summary,
          risk_level: card.manual_confirm || 'medium',
          checkpoints: card.checkpoints,
        }))
      : defaultTechPoints;

  async function handleGenerateTechPoints() {
    if (!projectId) return;
    setBusy(true);
    setMessage('');
    try {
      const result = await runStartupAnalysis(projectId);
      setStartupAnalysis(result);
      await onRefresh();
      setMessage('技术重点分析已生成，结果已保存。');
    } catch (error) {
      setMessage(`生成失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {message && (
        <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-sm text-zinc-300">
          {busy && <Loader2 size={14} className="mr-2 inline animate-spin" />}
          {message}
        </div>
      )}

      {/* 数据看板 */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {stats.map((item) => (
          <div key={item.label} className="rounded-xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm">
            <div className="mb-2 text-2xl font-semibold text-white">{item.value}</div>
            <div className={`text-xs ${item.color}`}>{item.label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_1fr]">
        <div className="rounded-xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm">
          <h2 className="mb-3 text-sm font-semibold text-white">最近会议结论</h2>
          {recentMeeting ? (
            <div className="space-y-3">
              <div className="text-sm font-medium text-zinc-200">{recentMeeting.title}</div>
              <p className="max-h-28 overflow-hidden text-xs leading-6 text-zinc-400">
                {recentMeeting.summary || recentMeeting.agenda || '会议已创建，纪要待生成。'}
              </p>
            </div>
          ) : (
            <p className="text-xs leading-6 text-zinc-500">暂无会议记录。可在会议页或 AI代理的会议纪要卡创建。</p>
          )}
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm">
          <h2 className="mb-3 text-sm font-semibold text-white">下一步</h2>
          {nextTasks.length ? (
            <div className="space-y-2">
              {nextTasks.map((task) => (
                <div key={task.id} className="rounded-lg border border-white/10 bg-[#0E0E0E] px-3 py-2">
                  <div className="text-xs font-medium text-zinc-200">{task.task_name}</div>
                  <div className="mt-1 text-[11px] text-zinc-500">{task.owner_role || '待分配'} · {task.priority || '普通'}</div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs leading-6 text-zinc-500">暂无待办任务。可用 AI代理生成任务拆解。</p>
          )}
        </div>
      </div>

      {/* 技术重点卡片区 */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">技术重点</h2>
          {!startupAnalysis?.technical_focus_cards?.length && (
            <button
              disabled={busy}
              onClick={handleGenerateTechPoints}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-3 py-1.5 text-xs font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <PlayCircle size={14} />}
              生成技术重点分析
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {techPoints.map((point) => {
            const Icon = techPointIcons[point.dimension] ?? ClipboardList;
            const risk = getRiskColor(point.risk_level);
            return (
              <div
                key={point.dimension}
                className={`rounded-lg border ${risk.border} ${risk.bg} p-4 transition-colors hover:border-amber-400/30`}
              >
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Icon size={16} className={risk.text} />
                    <span className="text-sm font-medium text-white">{point.dimension}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className={`h-1.5 w-1.5 rounded-full ${risk.dot}`} />
                    <span className={`text-[11px] ${risk.text}`}>{getRiskLabel(point.risk_level)}</span>
                  </div>
                </div>
                <p className="mb-3 text-xs leading-5 text-zinc-400">{point.summary}</p>
                {point.checkpoints?.length ? (
                  <div className="flex flex-wrap gap-1">
                    {point.checkpoints.slice(0, 3).map((item) => (
                      <span key={item} className="rounded-full bg-[#0E0E0E] px-2 py-0.5 text-[11px] text-zinc-400">
                        {item}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      {/* 项目信息摘要 */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm">
        <h2 className="mb-4 text-sm font-semibold text-white">项目信息</h2>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <InfoItem label="城市" value={project.city || '待补充'} />
          <InfoItem label="类型" value={project.project_type || '待补充'} />
          <InfoItem label="阶段" value={project.phase || '待补充'} />
          <InfoItem label="状态" value={project.status || '待补充'} />
        </div>
        {project.description && (
          <div className="mt-4 rounded-lg border border-white/10 bg-[#0E0E0E] p-3">
            <div className="mb-1 text-[11px] text-zinc-500">项目描述</div>
            <p className="text-sm leading-6 text-zinc-400">{project.description}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="mb-1 text-[11px] text-zinc-500">{label}</div>
      <div className="text-sm text-white">{value}</div>
    </div>
  );
}

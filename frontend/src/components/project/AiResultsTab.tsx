import { useState } from 'react';
import {
  Sparkles,
  Bot,
  ChevronDown,
  ChevronUp,
  FileText,
  Presentation,
  ClipboardList,
  CalendarDays,
  Cpu,
} from 'lucide-react';
import { type ProjectDetail } from '../../lib/projectsApi';

type Props = {
  project: ProjectDetail;
};

function getCardTypeIcon(type: string) {
  const t = type?.toLowerCase() ?? '';
  if (t.includes('task') || t.includes('任务')) return ClipboardList;
  if (t.includes('tech') || t.includes('技术')) return Cpu;
  if (t.includes('meeting') || t.includes('会议') || t.includes('agenda')) return CalendarDays;
  if (t.includes('ppt') || t.includes('汇报')) return Presentation;
  if (t.includes('focus') || t.includes('重点')) return FileText;
  return Bot;
}

function getCardTypeLabel(type: string) {
  const t = type?.toLowerCase() ?? '';
  if (t.includes('task_breakdown') || t.includes('任务拆解')) return '任务拆解';
  if (t.includes('technical_focus') || t.includes('技术重点')) return '技术重点';
  if (t.includes('meeting_agenda') || t.includes('会议议程')) return '会议议程';
  if (t.includes('ppt_outline') || t.includes('ppt')) return 'PPT结构';
  if (t.includes('focus')) return '技术重点';
  return type || 'AI成果';
}

function getStatusBadge(status: string) {
  const s = status?.toLowerCase() ?? '';
  if (s === 'completed' || s === 'done' || s === '完成')
    return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300';
  if (s === 'running' || s === 'pending' || s === '进行中')
    return 'border-blue-400/30 bg-blue-400/10 text-blue-300';
  if (s === 'failed' || s === 'error' || s === '失败')
    return 'border-red-400/30 bg-red-400/10 text-red-300';
  return 'border-zinc-500/30 bg-zinc-500/10 text-zinc-400';
}

function formatJsonOutput(raw: string | undefined): string {
  if (!raw) return '';
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return raw;
  }
}

export function AiResultsTab({ project }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const skillCards = project.skill_cards ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">AI技能卡片执行结果</h2>
        <span className="text-xs text-zinc-500">共 {skillCards.length} 条</span>
      </div>

      {skillCards.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/5 p-8 text-center">
          <Sparkles size={36} className="mx-auto mb-4 text-zinc-600" />
          <h3 className="mb-2 text-sm font-semibold text-white">暂无AI成果</h3>
          <p className="text-sm text-zinc-500">
            运行项目启动分析或从AI代理页面执行技能卡片后，结果会显示在这里。
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {skillCards.map((card) => {
            const isExpanded = expandedId === card.id;
            const Icon = getCardTypeIcon(card.card_type);
            const typeLabel = getCardTypeLabel(card.card_type);
            return (
              <div
                key={card.id}
                className="rounded-xl border border-white/10 bg-white/5 backdrop-blur-sm"
              >
                {/* 卡片头部 */}
                <button
                  onClick={() => setExpandedId(isExpanded ? null : card.id)}
                  className="flex w-full items-center justify-between p-4 text-left"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-400/10">
                      <Icon size={16} className="text-amber-300" />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-white">{card.title || typeLabel}</div>
                      <div className="flex items-center gap-2 text-[11px] text-zinc-500">
                        <span>{typeLabel}</span>
                        <span>·</span>
                        <span>{new Date(card.created_at).toLocaleDateString('zh-CN')}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full border px-2 py-0.5 text-[11px] ${getStatusBadge(card.status)}`}>
                      {card.status}
                    </span>
                    {isExpanded ? (
                      <ChevronUp size={16} className="text-zinc-400" />
                    ) : (
                      <ChevronDown size={16} className="text-zinc-400" />
                    )}
                  </div>
                </button>

                {/* 展开详情 */}
                {isExpanded && (
                  <div className="border-t border-white/10 p-4">
                    {card.markdown ? (
                      <pre className="whitespace-pre-wrap text-sm leading-6 text-zinc-400">
                        {card.markdown}
                      </pre>
                    ) : card.output_json ? (
                      <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-[#0E0E0E] p-4 text-xs leading-5 text-zinc-300">
                        {formatJsonOutput(card.output_json)}
                      </pre>
                    ) : (
                      <p className="text-sm text-zinc-500">暂无输出结果</p>
                    )}

                    <div className="mt-4 rounded-lg border border-white/10 bg-[#0E0E0E] px-3 py-2 text-xs text-zinc-500">
                      该成果已由对应工作流写入项目；未提供真实回写能力的操作不会显示。
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

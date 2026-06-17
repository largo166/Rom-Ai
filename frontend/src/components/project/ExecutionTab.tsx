import { useMemo, useState } from 'react';
import { Bot, Brain, Loader2, Search, Send, Trash2 } from 'lucide-react';
import {
  deleteProjectExecutionRun,
  executeProjectInstruction,
  type AgentRun,
  type ProjectDetail,
} from '../../lib/projectsApi';
import { compactReferenceLabel, uniqueExecutionReferences } from './executionReferences';

type Props = {
  projectId: string;
  project: ProjectDetail;
  onRefresh: () => void;
};

type ExecutionOutput = {
  mode?: string;
  answer?: string;
  references?: Array<{
    source_path?: string;
    heading?: string;
    quote?: string;
  }>;
};

function parseOutput(run: AgentRun): ExecutionOutput {
  try {
    return JSON.parse(run.output_json || '{}') as ExecutionOutput;
  } catch {
    return { answer: run.output_json };
  }
}

function parseInstruction(run: AgentRun) {
  try {
    const input = JSON.parse(run.input_context || '{}') as { instruction?: string };
    return input.instruction || '';
  } catch {
    return '';
  }
}

export function ExecutionTab({ projectId, project, onRefresh }: Props) {
  const [instruction, setInstruction] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [latestRun, setLatestRun] = useState<AgentRun | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [deletedRunIds, setDeletedRunIds] = useState<string[]>([]);

  const executionRuns = useMemo(
    () =>
      [...(project.agent_runs ?? [])]
        .filter((run) => run.agent_id === 'project-execution' && !deletedRunIds.includes(run.id))
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [deletedRunIds, project.agent_runs],
  );

  const visibleRuns = latestRun && !deletedRunIds.includes(latestRun.id)
    ? [latestRun, ...executionRuns.filter((run) => run.id !== latestRun.id)]
    : executionRuns;
  const activeRun = visibleRuns.find((run) => run.id === activeRunId) ?? visibleRuns[0] ?? null;

  async function handleExecute() {
    const text = instruction.trim();
    if (!text) return;
    setBusy(true);
    setMessage('');
    try {
      const run = await executeProjectInstruction(projectId, text);
      setLatestRun(run);
      setActiveRunId(run.id);
      setInstruction('');
      await onRefresh();
      setMessage('执行完成，已保存为本项目上下文。');
    } catch (error) {
      setMessage(`执行失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(run: AgentRun) {
    if (!window.confirm('确认删除这条执行台问答历史？')) return;
    setBusy(true);
    setMessage('');
    try {
      await deleteProjectExecutionRun(projectId, run.id);
      setDeletedRunIds((ids) => [...ids, run.id]);
      if (latestRun?.id === run.id) setLatestRun(null);
      if (activeRunId === run.id) setActiveRunId(null);
      await onRefresh();
      setMessage('问答历史已删除。');
    } catch (error) {
      setMessage(`删除失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[0.34fr_1fr]">
      <div className="rounded-lg border border-[#333333] bg-[#111111] p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
          <Brain size={16} className="text-amber-300" />
          问答历史
        </div>
        <div className="space-y-2">
          {visibleRuns.map((run, index) => {
            const isActive = activeRun?.id === run.id;
            return (
              <div
                key={run.id}
                className={`flex items-center gap-1 rounded-lg ${
                  isActive ? 'bg-amber-400 text-black' : 'bg-[#171717] text-zinc-300 hover:bg-white/10'
                }`}
              >
                <button
                  onClick={() => setActiveRunId(run.id)}
                  className="min-w-0 flex-1 truncate p-3 text-left text-sm"
                >
                  对话 {visibleRuns.length - index}：{parseInstruction(run) || '项目执行'}
                </button>
                <button
                  onClick={() => handleDelete(run)}
                  disabled={busy}
                  aria-label="删除问答历史"
                  title="删除问答历史"
                  className={`mr-2 rounded p-1.5 ${
                    isActive ? 'hover:bg-black/10' : 'text-zinc-500 hover:bg-red-400/10 hover:text-red-300'
                  }`}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            );
          })}
          {!visibleRuns.length && <p className="text-sm text-zinc-500">暂无对话。</p>}
        </div>
      </div>

      <div className="flex min-h-[620px] flex-col rounded-lg border border-[#333333] bg-[#111111]">
        <div className="border-b border-[#333333] p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-400/10 text-amber-300">
              <Bot size={18} />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white">项目执行台</h2>
              <p className="mt-1 text-xs text-zinc-500">自动带入项目上下文、知识库检索结果、任务和会议纪要。</p>
            </div>
          </div>
          {message && (
            <div className="mt-4 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-zinc-300">
              {message}
            </div>
          )}
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {!activeRun && (
            <div className="flex h-full min-h-[320px] items-center justify-center text-center">
              <div>
                <Search size={36} className="mx-auto mb-4 text-zinc-600" />
                <p className="text-sm text-zinc-500">输入指令开始项目问答</p>
                <p className="mt-2 text-xs text-zinc-600">回答会自动带项目上下文和知识库来源。</p>
              </div>
            </div>
          )}

          {activeRun && (() => {
            const output = parseOutput(activeRun);
            const refs = uniqueExecutionReferences(output.references ?? []);
            const asked = parseInstruction(activeRun) || '项目执行';
            return (
              <>
                <div className="flex justify-end">
                  <div className="max-w-[86%] rounded-lg bg-amber-400 p-4 text-black">
                    <p className="whitespace-pre-wrap text-sm leading-7">{asked}</p>
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="max-w-[86%] rounded-lg border border-[#333333] bg-[#171717] p-4 text-zinc-300">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="text-xs text-zinc-500">{output.mode || activeRun.status}</span>
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-7">{output.answer || '暂无输出'}</p>
                    {refs.length > 0 && (
                      <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-[#333333] pt-2 text-[11px] text-zinc-500">
                        <span>引用</span>
                        {refs.slice(0, 4).map((ref, index) => (
                          <span
                            key={`${ref.source_path || compactReferenceLabel(ref)}-${index}`}
                            title={ref.source_path || ref.quote || compactReferenceLabel(ref)}
                            className="max-w-[180px] truncate rounded border border-white/10 bg-[#0E0E0E] px-2 py-1 text-zinc-400"
                          >
                            {compactReferenceLabel(ref)}
                          </span>
                        ))}
                        {refs.length > 4 && <span>+{refs.length - 4}</span>}
                      </div>
                    )}
                  </div>
                </div>
              </>
            );
          })()}
        </div>

        <div className="border-t border-[#333333] p-4">
          <div className="flex gap-3">
            <input
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') handleExecute();
              }}
              placeholder="输入指令，如：基于知识库和当前资料，帮我拆一版总图强排复核任务"
              className="flex-1 rounded-lg border border-[#333333] bg-[#0E0E0E] px-4 py-3 text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-amber-400/60"
            />
            <button
              disabled={busy || !instruction.trim()}
              onClick={handleExecute}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-4 py-3 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

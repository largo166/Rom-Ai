import { useEffect, useRef, useState } from 'react';
import {
  ListTodo, AlertTriangle, FileText, Monitor,
  Sparkles, CheckCircle, Send, Loader2, Bot, X, ClipboardCopy,
} from 'lucide-react';
import {
  listProjects,
  getProject,
  runAgentChat,
  type ProjectDetail,
  type ProjectSummary,
  type SkillCard,
} from '../lib/projectsApi';

/* ---------- Skill card definitions ---------- */
type SkillUi = {
  type: string;
  title: string;
  Icon: typeof ListTodo;
  color: string;
  desc: string;
};

const activeSkills: SkillUi[] = [
  { type: 'brief_interpretation', title: '项目研判', Icon: AlertTriangle, color: 'amber', desc: '启动分析、风险识别、追问清单和下一步建议' },
  { type: 'meeting_minutes', title: '会议助理', Icon: FileText, color: 'green', desc: '会议纪要、录音转写、甲方诉求转译和会议待办' },
  { type: 'task_breakdown', title: '任务编排', Icon: ListTodo, color: 'blue', desc: '任务拆解、责任人建议、里程碑和时间轴' },
  { type: 'ppt_outline', title: '汇报生成', Icon: Monitor, color: 'purple', desc: '汇报主线、PPT 大纲、讲稿和缺图清单' },
  { type: 'ai_image_generation', title: 'AI 生图', Icon: Sparkles, color: 'amber', desc: 'AI 生图、AI 生图提示词、参考图整理和图面表达建议' },
  { type: 'scheme_review', title: '知识复用', Icon: CheckCircle, color: 'green', desc: '类似项目、历史经验、方法模板和方案评审 RAG' },
];

function colorClasses(color: string) {
  const map: Record<string, { bg: string; border: string; text: string; icon: string }> = {
    blue:   { bg: 'bg-blue-400/10',    border: 'border-blue-400/30',    text: 'text-blue-300',    icon: 'text-blue-400' },
    amber:  { bg: 'bg-amber-400/10',   border: 'border-amber-400/30',   text: 'text-amber-300',   icon: 'text-amber-400' },
    green:  { bg: 'bg-emerald-400/10',  border: 'border-emerald-400/30', text: 'text-emerald-300', icon: 'text-emerald-400' },
    purple: { bg: 'bg-purple-400/10',   border: 'border-purple-400/30', text: 'text-purple-300',  icon: 'text-purple-400' },
  };
  return map[color] ?? map.amber;
}

/* ---------- Intent detection ---------- */
function detectIntent(text: string): string | null {
  if (/AI生图|AI 生图|生成图片|效果图|意向图|渲染|生图/.test(text)) return 'ai_image_generation';
  if (/PPT大纲|PPT 大纲|汇报|演示|大纲/.test(text)) return 'ppt_outline';
  if (/任务|拆解|分工|排期|时间轴|待办安排/.test(text)) return 'task_breakdown';
  if (/会议|纪要|待办|记录|腾讯会议|转写|播报/.test(text)) return 'meeting_minutes';
  if (/竞品|对标|类似项目|案例|参考项目|知识复用|评审|检查方案|方案问题|风险检查/.test(text)) return 'scheme_review';
  if (/任务书|设计任务|需求解读|甲方要求|技术|重点|日照|退界|消防|规范|项目分析|研判|启动分析/.test(text)) return 'brief_interpretation';
  return 'brief_interpretation';
}

/* ---------- Types ---------- */
type ChatMsg = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  card?: SkillCard | null;
  isExecuting?: boolean;
};

/* ---------- Component ---------- */
export function AgentsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [projectId, setProjectId] = useState('');
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [dialogSkill, setDialogSkill] = useState<string | null>(null);
  const [dialogInput, setDialogInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listProjects()
      .then((items) => {
        setProjects(items);
        setProjectId(items[0]?.id ?? '');
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) {
      setProjectDetail(null);
      return;
    }
    getProject(projectId).then(setProjectDetail).catch(() => setProjectDetail(null));
  }, [projectId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  /* ---- helpers ---- */
  function addMsg(msg: ChatMsg) {
    setMessages((prev) => [...prev, msg]);
  }

  function updateMsg(id: string, patch: Partial<ChatMsg>) {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }

  /* ---- chat send ---- */
  async function send() {
    if (!input.trim() || busy) return;
    addMsg({ id: crypto.randomUUID(), role: 'user', content: input });
    const text = input;
    setInput('');
    setBusy(true);

    const intent = detectIntent(text);
    if (intent && projectId) {
      const skill = activeSkills.find((s) => s.type === intent);
      const execId = crypto.randomUUID();
      addMsg({ id: execId, role: 'assistant', content: `正在执行 ${skill?.title ?? intent}...`, isExecuting: true });
      try {
        const result = await runAgentChat(projectId, text, intent);
        updateMsg(execId, {
          content: `${result.selected_skill?.name ?? skill?.title ?? intent} 执行完成 · ${result.reason}`,
          card: result.card,
          isExecuting: false,
        });
      } catch (error) {
        updateMsg(execId, { content: `执行失败：${String(error)}`, isExecuting: false });
      }
    } else if (!projectId) {
      addMsg({ id: crypto.randomUUID(), role: 'assistant', content: '请先选择一个项目。' });
    } else {
      addMsg({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '我理解您的需求，但还需要更明确的任务目标。可以输入：做PPT大纲、整理会议纪要、生成概念文字、做竞品分析或生成意向图。',
      });
    }
    setBusy(false);
  }

  /* ---- direct card execution ---- */
  async function executeFromDialog() {
    if (!dialogSkill || !projectId || busy) return;
    setBusy(true);
    const skill = activeSkills.find((s) => s.type === dialogSkill);
    const execId = crypto.randomUUID();
    addMsg({ id: execId, role: 'assistant', content: `正在执行 ${skill?.title ?? dialogSkill}...`, isExecuting: true });
    try {
      const result = await runAgentChat(projectId, dialogInput || skill?.desc || skill?.title || dialogSkill, dialogSkill);
      updateMsg(execId, { content: `${result.selected_skill?.name ?? skill?.title ?? dialogSkill} 执行完成 · ${result.reason}`, card: result.card, isExecuting: false });
    } catch (error) {
      updateMsg(execId, { content: `执行失败：${String(error)}`, isExecuting: false });
    }
    setBusy(false);
    setDialogSkill(null);
    setDialogInput('');
  }

  /* ---- render ---- */
  return (
    <main className="min-h-screen bg-gray-900 px-6 pb-20 pt-28 md:px-12">
      <div className="mx-auto max-w-[1360px]">
        {/* Header */}
        <div className="mb-8">
          <span className="mb-4 block text-xs font-medium uppercase tracking-[0.3em] text-zinc-500">
            Design Agent Console
          </span>
          <h1 className="mb-4 text-3xl font-bold tracking-tight text-white md:text-5xl">AI设计代理</h1>
          <p className="max-w-3xl text-sm leading-7 text-zinc-400">
            输入目标，系统会自动读取项目数据链接、会议、任务和知识库，后台调用项目研判、会议助理、任务编排、PPT 大纲、AI 生图和知识复用能力，并生成可查看的成果卡。
          </p>
        </div>

        {/* Project selector */}
        <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3">
          <span className="text-sm text-zinc-400">当前项目</span>
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="rounded-xl border border-white/10 bg-gray-800 px-4 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
          >
            {!projectId && <option value="">请选择项目</option>}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
            <span className="rounded-full bg-white/5 px-2.5 py-1">{projectDetail?.phase || '阶段待补充'}</span>
            <span className="rounded-full bg-white/5 px-2.5 py-1">{projectDetail?.city || '城市待补充'}</span>
            <span className="rounded-full bg-white/5 px-2.5 py-1">{projectDetail?.project_type || '类型待补充'}</span>
            <span className="rounded-full bg-amber-400/10 px-2.5 py-1 text-amber-300">
              已读取 {projectDetail?.files.length ?? 0} 文件 / {projectDetail?.meetings.length ?? 0} 会议 / {projectDetail?.knowledge_references.length ?? 0} 知识引用
            </span>
          </div>
        </div>

        {/* Main: chat + cards */}
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[3fr_2fr]">
          {/* Left — chat (60%) */}
          <div className="flex min-h-[600px] flex-col rounded-xl border border-white/10 bg-white/5">
            <div className="flex-1 space-y-4 overflow-y-auto p-5">
              {!messages.length && (
                <div className="flex h-full min-h-[420px] items-center justify-center text-center">
                  <div>
                    <Bot size={40} className="mx-auto mb-4 text-zinc-600" />
                    <p className="text-sm text-zinc-500">描述目标，AI 将自动选择后台能力</p>
                    <p className="mt-2 text-xs text-zinc-600">
                      例如：帮我准备下周甲方汇报；根据最近会议生成任务安排；为当前项目生成 AI 生图
                    </p>
                  </div>
                </div>
              )}
              {messages.map((msg) => (
                <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[88%] rounded-xl p-4 ${
                      msg.role === 'user'
                        ? 'bg-amber-400 text-black'
                        : 'border border-white/10 bg-gray-800 text-zinc-300'
                    }`}
                  >
                    {msg.isExecuting ? (
                      <div className="flex items-center gap-2 text-sm">
                        <Loader2 size={16} className="animate-spin text-amber-400" />
                        {msg.content}
                      </div>
                    ) : (
                      <>
                        <p className="text-sm leading-7">{msg.content}</p>
                        {msg.card && (
                          <div className="mt-3 rounded-xl border border-white/10 bg-gray-900 p-4">
                            <div className="mb-2 flex items-center justify-between">
                              <span className="text-sm font-semibold text-amber-300">{msg.card.title}</span>
                              <button
                                onClick={() => navigator.clipboard.writeText(msg.card?.markdown ?? '')}
                                className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300"
                              >
                                <ClipboardCopy size={12} />
                                复制
                              </button>
                            </div>
                            <pre className="max-h-[280px] overflow-y-auto whitespace-pre-wrap text-xs leading-6 text-zinc-400">
                              {msg.card.markdown || JSON.stringify(msg.card.output_json, null, 2)}
                            </pre>
                            <button className="mt-3 rounded-lg bg-amber-400/10 px-3 py-1.5 text-xs font-medium text-amber-300 transition-colors hover:bg-amber-400/20">
                              回写到项目
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
              <div ref={endRef} />
            </div>

            {/* Input */}
            <div className="border-t border-white/10 p-4">
              <div className="flex gap-3">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
                  placeholder="输入目标，如：帮我准备下周甲方汇报，生成 PPT 大纲和 AI 生图提示词..."
                  className="flex-1 rounded-xl border border-white/10 bg-gray-800 px-4 py-3 text-sm text-zinc-200 outline-none placeholder:text-zinc-500 focus:border-amber-400/60"
                />
                <button
                  disabled={busy || !input.trim()}
                  onClick={send}
                  className="flex items-center gap-2 rounded-xl bg-amber-400 px-5 py-3 text-sm font-semibold text-black transition-colors hover:bg-amber-300 disabled:opacity-50"
                >
                  {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                </button>
              </div>
            </div>
          </div>

          {/* Right — skill cards (40%) */}
          <div className="space-y-5">
            <div className="rounded-xl border border-white/10 bg-white/5 p-5">
              <h2 className="mb-1 text-sm font-semibold text-white">成果卡类型</h2>
              <p className="mb-4 text-xs leading-5 text-zinc-500">点击卡片可快速启动对应成果；日常建议直接在左侧输入目标，让 AI 自动后台编排。</p>
              <div className="grid grid-cols-2 gap-3">
                {activeSkills.map((skill) => {
                  const c = colorClasses(skill.color);
                  const SkillIcon = skill.Icon;
                  return (
                    <button
                      key={skill.type}
                      onClick={() => { setDialogSkill(skill.type); setDialogInput(''); }}
                      className={`rounded-xl border ${c.border} ${c.bg} p-4 text-left transition-all hover:scale-[1.02] hover:brightness-125`}
                    >
                      <SkillIcon size={24} className={`mb-2 ${c.icon}`} />
                      <div className={`text-sm font-semibold ${c.text}`}>{skill.title}</div>
                      <p className="mt-1 text-xs text-zinc-500">{skill.desc}</p>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Execute dialog */}
      {dialogSkill && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-white/10 bg-gray-800 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">
                生成 {activeSkills.find((s) => s.type === dialogSkill)?.title} 成果
              </h2>
              <button onClick={() => setDialogSkill(null)} className="text-zinc-400 transition-colors hover:text-white">
                <X size={20} />
              </button>
            </div>
            <textarea
              value={dialogInput}
              onChange={(e) => setDialogInput(e.target.value)}
              placeholder="补充目标或约束（可选），例如：偏现代简洁、用于甲方汇报、需要三页 PPT 大纲..."
              className="mb-4 min-h-[120px] w-full resize-none rounded-xl border border-white/10 bg-gray-900 px-4 py-3 text-sm text-zinc-200 outline-none placeholder:text-zinc-500"
            />
            <button
              disabled={busy}
              onClick={executeFromDialog}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-amber-400 px-4 py-3 text-sm font-semibold text-black transition-colors hover:bg-amber-300 disabled:opacity-50"
            >
              {busy && <Loader2 size={16} className="animate-spin" />}
              执行
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

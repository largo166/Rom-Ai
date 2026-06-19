import { useEffect, useRef, useState } from 'react';
import {
  ListTodo, AlertTriangle, FileText, Monitor, BarChart3, PenTool,
  Image, Sparkles, Brain, CheckCircle, Send, Loader2, Bot, X, ClipboardCopy,
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
  { type: 'brief_interpretation', title: '任务书解读卡', Icon: FileText, color: 'green', desc: '抽取显性目标、隐性诉求、设计矛盾和切入点' },
  { type: 'task_breakdown', title: '任务拆解卡', Icon: ListTodo, color: 'blue', desc: '把项目描述转成任务、责任角色和交付要求' },
  { type: 'technical_focus', title: '技术重点卡', Icon: AlertTriangle, color: 'amber', desc: '提取日照、退界、面积、消防等复用重点' },
  { type: 'meeting_minutes', title: '会议纪要卡', Icon: FileText, color: 'green', desc: '把会议记录转成纪要、脑图和待办' },
  { type: 'ppt_outline', title: 'PPT大纲卡', Icon: Monitor, color: 'purple', desc: '生成业主汇报或内部评审的PPT框架' },
  { type: 'competitor_analysis', title: '竞品分析', Icon: BarChart3, color: 'amber', desc: '调取历史项目和案例经验，提炼可迁移策略' },
  { type: 'concept_copy', title: '概念文字稿', Icon: PenTool, color: 'green', desc: '生成概念标题、设计叙事和汇报文字' },
  { type: 'reference_image_classification', title: '参考图分类', Icon: Image, color: 'blue', desc: '整理参考图的风格、材料和可复用点' },
  { type: 'image_prompt', title: '生图提示词', Icon: Sparkles, color: 'purple', desc: '基于当前项目生成建筑意向图提示词' },
  { type: 'ai_image_generation', title: 'AI生图', Icon: Brain, color: 'amber', desc: '调用内置图片生成服务产出项目意向图' },
  { type: 'scheme_review', title: '方案评审', Icon: CheckCircle, color: 'green', desc: '按项目资料和知识库经验检查方案风险' },
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
  if (/任务书|设计任务|需求解读|甲方要求/.test(text)) return 'brief_interpretation';
  if (/任务|拆解|分工|排期/.test(text)) return 'task_breakdown';
  if (/技术|重点|日照|退界|消防|规范/.test(text)) return 'technical_focus';
  if (/会议|纪要|待办|记录|腾讯会议|转写|播报/.test(text)) return 'meeting_minutes';
  if (/PPT|汇报|演示|大纲/.test(text)) return 'ppt_outline';
  if (/竞品|对标|类似项目|案例|参考项目/.test(text)) return 'competitor_analysis';
  if (/概念|文案|文字稿|叙事|故事线/.test(text)) return 'concept_copy';
  if (/参考图|图片分类|意向图|素材/.test(text)) return 'reference_image_classification';
  if (/提示词|prompt|生图提示/.test(text)) return 'image_prompt';
  if (/生图|生成图片|效果图|AI生图|渲染/.test(text)) return 'ai_image_generation';
  if (/评审|检查方案|方案问题|风险检查/.test(text)) return 'scheme_review';
  return null;
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
            输入需求，系统自动识别意图并执行技能卡片，成果回写到项目作战室。
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
                    <p className="text-sm text-zinc-500">描述您的需求，AI 将自动识别意图</p>
                    <p className="mt-2 text-xs text-zinc-600">
                      当前输入会绑定所选项目，并自动调用技能卡生成成果
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
                  placeholder="输入需求，如：帮我拆解任务..."
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
              <h2 className="mb-4 text-sm font-semibold text-white">内置技能卡片</h2>
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
                执行 {activeSkills.find((s) => s.type === dialogSkill)?.title}
              </h2>
              <button onClick={() => setDialogSkill(null)} className="text-zinc-400 transition-colors hover:text-white">
                <X size={20} />
              </button>
            </div>
            <textarea
              value={dialogInput}
              onChange={(e) => setDialogInput(e.target.value)}
              placeholder="补充执行参数（可选）..."
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

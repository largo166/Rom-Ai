import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import {
  ArrowRight,
  Briefcase,
  Database,
  FolderKanban,
  AlertTriangle,
  BookOpen,
  Plus,
  RefreshCw,
  CheckCircle2,
  Circle,
  Loader2,
} from 'lucide-react';
import { listProjects, type ProjectSummary } from '../lib/projectsApi';

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

function getStatusColor(status: string) {
  const s = status?.toLowerCase() ?? '';
  if (s.includes('active') || s.includes('进行中')) return 'bg-emerald-400';
  if (s.includes('risk') || s.includes('风险') || s.includes('blocked')) return 'bg-red-400';
  if (s.includes('done') || s.includes('完成') || s.includes('completed')) return 'bg-zinc-500';
  if (s.includes('paused') || s.includes('暂停')) return 'bg-yellow-400';
  return 'bg-emerald-400';
}

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

function getTypeBadge(type: string) {
  const t = type ?? '';
  const map: Record<string, string> = {
    住宅: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
    商业: 'border-blue-400/30 bg-blue-400/10 text-blue-200',
    综合体: 'border-purple-400/30 bg-purple-400/10 text-purple-200',
    公建: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
    办公: 'border-cyan-400/30 bg-cyan-400/10 text-cyan-200',
    酒店: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
  };
  return map[t] ?? 'border-zinc-500/30 bg-zinc-500/10 text-zinc-300';
}

export function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');

  async function loadProjects() {
    setLoading(true);
    setMessage('');
    try {
      setProjects(await listProjects());
    } catch (error) {
      setMessage(`读取项目失败：${String(error)}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProjects();
  }, []);

  const totalCount = projects.length;
  const activeCount = projects.filter((p) => {
    const s = p.status?.toLowerCase() ?? '';
    return s.includes('active') || s.includes('进行中');
  }).length;
  const doneCount = projects.filter((p) => {
    const s = p.status?.toLowerCase() ?? '';
    return s.includes('done') || s.includes('完成') || s.includes('completed');
  }).length;
  const riskCount = projects.filter((p) => {
    const s = p.status?.toLowerCase() ?? '';
    return s.includes('risk') || s.includes('风险') || s.includes('blocked');
  }).length;

  const statCards = [
    { label: '项目总数', value: totalCount, icon: FolderKanban, color: 'text-amber-300' },
    { label: '进行中', value: activeCount, icon: Briefcase, color: 'text-emerald-300' },
    { label: '已完成', value: doneCount, icon: CheckCircle2, color: 'text-zinc-400' },
    { label: '风险项目', value: riskCount, icon: AlertTriangle, color: 'text-red-300' },
  ];

  return (
    <main className="min-h-screen bg-[#0A0A0A] px-6 pb-20 pt-28 md:px-12">
      <div className="mx-auto max-w-[1320px]">
        <div className="mb-8 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div>
            <span className="mb-4 block text-xs font-medium uppercase tracking-[0.3em] text-zinc-500">
              Project OS
            </span>
            <h1 className="mb-2 text-3xl font-bold tracking-tight text-white md:text-5xl">
              项目中心
            </h1>
            <p className="max-w-2xl text-sm leading-7 text-zinc-400">
              所有模块围绕 Project 对象运行。上传资料、解析文件、AI分析、任务拆解和团队配置都将回写到对应项目。
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              to="/knowledge?tool=local-folder"
              className="inline-flex items-center gap-2 rounded-lg border border-[#333333] bg-[#171717] px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600"
            >
              <BookOpen size={16} />
              本地资料整理
            </Link>
            <button
              onClick={loadProjects}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-lg border border-[#333333] bg-[#171717] px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600 disabled:opacity-50"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
              刷新
            </button>
            <Link
              to="/projects/new"
              className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-300"
            >
              <Plus size={16} />
              新建项目
            </Link>
          </div>
        </div>

        {message && (
          <div className="mb-5 rounded-lg border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-200">
            {message}
          </div>
        )}

        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          {statCards.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.label}
                className="rounded-xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm"
              >
                <div className="mb-3 flex items-center justify-between">
                  <Icon size={18} className={item.color} />
                  <span className="text-2xl font-semibold text-white">{item.value}</span>
                </div>
                <div className="text-xs text-zinc-500">{item.label}</div>
              </div>
            );
          })}
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {loading && (
            <div className="lg:col-span-3 rounded-xl border border-white/10 bg-white/5 p-8 text-center">
              <Loader2 size={32} className="mx-auto mb-4 animate-spin text-amber-400" />
              <p className="text-sm text-zinc-400">正在读取项目...</p>
            </div>
          )}

          {!loading && projects.length === 0 && (
            <div className="lg:col-span-3 rounded-xl border border-white/10 bg-white/5 p-12 text-center">
              <Database size={40} className="mx-auto mb-4 text-zinc-600" />
              <h2 className="mb-3 text-lg font-semibold text-white">暂无项目</h2>
              <p className="mb-6 text-sm text-zinc-500">
                创建您的第一个项目，开始使用项目管理工作台
              </p>
              <Link
                to="/projects/new"
                className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-5 py-2.5 text-sm font-semibold text-black hover:bg-amber-300"
              >
                <Plus size={16} />
                创建项目
              </Link>
            </div>
          )}

          {projects.map((project) => (
            <Link
              key={project.id}
              to={`/projects/${project.id}`}
              className="group rounded-xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm transition-all hover:border-amber-500/30 hover:bg-white/[0.07]"
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h2 className="mb-2 truncate text-lg font-semibold text-white">
                    {project.name}
                  </h2>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-zinc-500">
                    <span>{project.city || '城市待补充'}</span>
                    {project.project_type && (
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[11px] ${getTypeBadge(project.project_type)}`}
                      >
                        {project.project_type}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${getStatusColor(project.status)}`} />
                  <span
                    className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] ${getStatusBadge(project.status)}`}
                  >
                    {project.status}
                  </span>
                </div>
              </div>

              {project.phase && (
                <div className="mb-4 flex items-center gap-1.5 text-xs text-zinc-500">
                  <Circle size={10} className="text-amber-400/60" />
                  <span>{project.phase}</span>
                </div>
              )}

              <div className="mb-4 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg bg-[#0E0E0E] p-2.5">
                  <div className="text-base font-semibold text-white">{project.file_count}</div>
                  <div className="text-[11px] text-zinc-500">文件</div>
                </div>
                <div className="rounded-lg bg-[#0E0E0E] p-2.5">
                  <div className="text-base font-semibold text-white">{project.report_count}</div>
                  <div className="text-[11px] text-zinc-500">报告</div>
                </div>
                <div className="rounded-lg bg-[#0E0E0E] p-2.5">
                  <div className="text-base font-semibold text-white">{project.task_count}</div>
                  <div className="text-[11px] text-zinc-500">任务</div>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs text-zinc-500">
                <span>创建 {formatDate(project.created_at)}</span>
                <span className="inline-flex items-center gap-1 text-amber-300">
                  打开
                  <ArrowRight
                    size={14}
                    className="transition-transform group-hover:translate-x-1"
                  />
                </span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}

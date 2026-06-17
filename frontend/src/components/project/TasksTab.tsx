import { useState } from 'react';
import {
  Plus,
  Loader2,
  MoreHorizontal,
  AlertCircle,
  User,
  Trash2,
  X,
} from 'lucide-react';
import {
  assignProjectTask,
  createProjectTask,
  deleteProjectTask,
  type ProjectDetail,
  type ProjectTask,
  updateProjectTask,
} from '../../lib/projectsApi';

type Props = {
  projectId: string;
  project: ProjectDetail;
  tasks: ProjectTask[];
  focusTaskId?: string;
  onRefresh: () => void;
  onOpenMember?: (memberId: string) => void;
  onOpenMeeting?: () => void;
};

const columns = [
  { key: 'todo', label: '待办', statusMatch: ['todo', 'pending', '待办'], color: 'border-amber-400/30 bg-amber-400/5', headerColor: 'text-amber-300' },
  { key: 'doing', label: '进行中', statusMatch: ['doing', 'in_progress', '进行中', 'in-progress'], color: 'border-blue-400/30 bg-blue-400/5', headerColor: 'text-blue-300' },
  { key: 'done', label: '已完成', statusMatch: ['done', 'completed', '已完成'], color: 'border-emerald-400/30 bg-emerald-400/5', headerColor: 'text-emerald-300' },
] as const;

function getPriorityColor(priority: string) {
  const p = priority?.toLowerCase() ?? '';
  if (p === 'high' || p === '高' || p === 'p0') return 'bg-red-400';
  if (p === 'medium' || p === '中' || p === 'p1') return 'bg-yellow-400';
  return 'bg-zinc-500';
}

function getPriorityLabel(priority: string) {
  const p = priority?.toLowerCase() ?? '';
  if (p === 'high' || p === '高' || p === 'p0') return '高';
  if (p === 'medium' || p === '中' || p === 'p1') return '中';
  return '低';
}

function getSourceTag(task: ProjectTask) {
  const t = task.task_type?.toLowerCase() ?? '';
  if (t.includes('meeting') || t.includes('会议')) return { label: '会议', color: 'text-blue-300 bg-blue-400/10' };
  if (t.includes('ai') || t.includes('agent')) return { label: 'AI', color: 'text-violet-300 bg-violet-400/10' };
  return { label: '手动', color: 'text-zinc-400 bg-zinc-500/10' };
}

export function TasksTab({ projectId, project, tasks, focusTaskId = '', onRefresh, onOpenMember, onOpenMeeting }: Props) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [menuTaskId, setMenuTaskId] = useState<string | null>(null);
  const [assignTask, setAssignTask] = useState<ProjectTask | null>(null);
  const [editTask, setEditTask] = useState<ProjectTask | null>(null);
  const [selectedAssigneeKey, setSelectedAssigneeKey] = useState('');
  const [editName, setEditName] = useState('');
  const [editPriority, setEditPriority] = useState('medium');
  const [editRisk, setEditRisk] = useState('low');
  const [editDueDate, setEditDueDate] = useState('');
  const [editOutput, setEditOutput] = useState('');

  // 新任务表单
  const [newTaskName, setNewTaskName] = useState('');
  const [newTaskPriority, setNewTaskPriority] = useState('medium');
  const [newTaskOwner, setNewTaskOwner] = useState('');

  function getColumnTasks(colKey: string): ProjectTask[] {
    const col = columns.find((c) => c.key === colKey);
    if (!col) return [];
    return tasks.filter((t) => col.statusMatch.some((s) => t.status?.toLowerCase() === s));
  }

  async function handleAddTask() {
    if (!newTaskName.trim()) return;
    setBusy(true);
    setMessage('');
    try {
      await createProjectTask(projectId, {
        task_name: newTaskName,
        priority: newTaskPriority,
        owner_role: newTaskOwner || undefined,
        status: 'todo',
      });
      setShowAddModal(false);
      setNewTaskName('');
      setNewTaskPriority('medium');
      setNewTaskOwner('');
      await onRefresh();
      setMessage('任务已添加。');
    } catch (error) {
      setMessage(`添加失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleMoveTask(task: ProjectTask, newStatus: string) {
    setBusy(true);
    setMenuTaskId(null);
    setMessage('');
    try {
      await updateProjectTask(projectId, task.id, { status: newStatus });
      await onRefresh();
    } catch (error) {
      setMessage(`移动失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleAssignTask() {
    if (!assignTask || !selectedAssigneeKey) return;
    const member = project.assignments.find((item) => `${item.assignee_type}:${item.assignee_id}` === selectedAssigneeKey);
    if (!member) return;
    setBusy(true);
    setMessage('');
    try {
      await assignProjectTask(projectId, assignTask.id, {
        assignee_type: member.assignee_type,
        assignee_id: member.assignee_id,
        assignee_name: member.assignee_name,
      });
      setAssignTask(null);
      setSelectedAssigneeKey('');
      await onRefresh();
      setMessage('负责人已更新。');
    } catch (error) {
      setMessage(`分配失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteTask(task: ProjectTask) {
    if (!window.confirm(`确认删除任务“${task.task_name}”？`)) return;
    setBusy(true);
    setMenuTaskId(null);
    try {
      await deleteProjectTask(projectId, task.id);
      await onRefresh();
      setMessage('任务已删除。');
    } catch (error) {
      setMessage(`删除失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  function openEditTask(task: ProjectTask) {
    setEditTask(task);
    setEditName(task.task_name);
    setEditPriority(task.priority || 'medium');
    setEditRisk(task.risk_level || 'low');
    setEditDueDate(task.due_date ? task.due_date.slice(0, 10) : '');
    setEditOutput(task.output_requirement || '');
    setMenuTaskId(null);
  }

  async function handleEditTask() {
    if (!editTask || !editName.trim()) return;
    setBusy(true);
    setMessage('');
    try {
      await updateProjectTask(projectId, editTask.id, {
        task_name: editName.trim(),
        priority: editPriority,
        risk_level: editRisk,
        due_date: editDueDate ? new Date(`${editDueDate}T00:00:00`).toISOString() : null,
        output_requirement: editOutput,
      });
      setEditTask(null);
      await onRefresh();
      setMessage('任务已更新。');
    } catch (error) {
      setMessage(`更新失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {message && (
        <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-sm text-zinc-300">
          {busy && <Loader2 size={14} className="mr-2 inline animate-spin" />}
          {message}
        </div>
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">任务看板</h2>
        <button
          onClick={() => setShowAddModal(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-3 py-1.5 text-sm font-semibold text-black hover:bg-amber-300"
        >
          <Plus size={14} />
          添加任务
        </button>
      </div>

      {/* 添加任务 Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-white/10 bg-[#171717] p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">添加任务</h3>
              <button onClick={() => setShowAddModal(false)} className="text-zinc-500 hover:text-white">
                <X size={20} />
              </button>
            </div>
            <div className="space-y-4">
              <label className="block text-xs text-zinc-500">
                任务名称
                <input
                  value={newTaskName}
                  onChange={(e) => setNewTaskName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                  placeholder="例如：完成方案文本"
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-zinc-500">
                  优先级
                  <select
                    value={newTaskPriority}
                    onChange={(e) => setNewTaskPriority(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                  >
                    <option value="high">高</option>
                    <option value="medium">中</option>
                    <option value="low">低</option>
                  </select>
                </label>
                <label className="block text-xs text-zinc-500">
                  负责人
                  <input
                    value={newTaskOwner}
                    onChange={(e) => setNewTaskOwner(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                    placeholder="角色或姓名"
                  />
                </label>
              </div>
              <button
                onClick={handleAddTask}
                disabled={busy || !newTaskName.trim()}
                className="w-full rounded-lg bg-amber-400 py-2.5 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
              >
                {busy ? <Loader2 size={16} className="mx-auto animate-spin" /> : '添加'}
              </button>
            </div>
          </div>
        </div>
      )}

      {assignTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-white/10 bg-[#171717] p-6">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-white">分配负责人</h3>
                <p className="mt-1 text-xs text-zinc-500">{assignTask.task_name}</p>
              </div>
              <button onClick={() => setAssignTask(null)} className="text-zinc-500 hover:text-white">
                <X size={20} />
              </button>
            </div>
            <div className="space-y-4">
              {project.assignments.length === 0 ? (
                <div className="rounded-lg border border-white/10 bg-white/5 p-4 text-sm leading-6 text-zinc-400">
                  这个项目还没有团队成员。请先到团队页从网络平台加入真实员工或 AI 员工。
                </div>
              ) : (
                <label className="block text-xs text-zinc-500">
                  项目团队成员
                  <select
                    value={selectedAssigneeKey}
                    onChange={(event) => setSelectedAssigneeKey(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                  >
                    <option value="">选择负责人</option>
                    <optgroup label="真实成员">
                      {project.assignments.filter((item) => item.assignee_type === 'human').map((item) => (
                        <option key={item.id} value={`${item.assignee_type}:${item.assignee_id}`}>
                          {item.assignee_name} · {item.role || '项目成员'}
                        </option>
                      ))}
                    </optgroup>
                    <optgroup label="AI员工">
                      {project.assignments.filter((item) => item.assignee_type === 'digital_employee').map((item) => (
                        <option key={item.id} value={`${item.assignee_type}:${item.assignee_id}`}>
                          {item.assignee_name} · {item.role || 'AI员工'}
                        </option>
                      ))}
                    </optgroup>
                  </select>
                </label>
              )}
              <button
                onClick={handleAssignTask}
                disabled={busy || !selectedAssigneeKey || project.assignments.length === 0}
                className="w-full rounded-lg bg-amber-400 py-2.5 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
              >
                {busy ? <Loader2 size={16} className="mx-auto animate-spin" /> : '确认分配'}
              </button>
            </div>
          </div>
        </div>
      )}

      {editTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-xl border border-white/10 bg-[#171717] p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">编辑任务</h3>
              <button onClick={() => setEditTask(null)} className="text-zinc-500 hover:text-white"><X size={20} /></button>
            </div>
            <div className="space-y-4">
              <label className="block text-xs text-zinc-500">任务名称
                <input value={editName} onChange={(event) => setEditName(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60" />
              </label>
              <div className="grid grid-cols-3 gap-3">
                <label className="block text-xs text-zinc-500">优先级
                  <select value={editPriority} onChange={(event) => setEditPriority(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200">
                    <option value="high">高</option><option value="medium">中</option><option value="low">低</option>
                  </select>
                </label>
                <label className="block text-xs text-zinc-500">风险
                  <select value={editRisk} onChange={(event) => setEditRisk(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200">
                    <option value="high">高</option><option value="medium">中</option><option value="low">低</option>
                  </select>
                </label>
                <label className="block text-xs text-zinc-500">截止日期
                  <input type="date" value={editDueDate} onChange={(event) => setEditDueDate(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200" />
                </label>
              </div>
              <label className="block text-xs text-zinc-500">交付物要求
                <textarea value={editOutput} onChange={(event) => setEditOutput(event.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60" />
              </label>
              <button onClick={handleEditTask} disabled={busy || !editName.trim()} className="w-full rounded-lg bg-amber-400 py-2.5 text-sm font-semibold text-black disabled:opacity-50">
                {busy ? <Loader2 size={16} className="mx-auto animate-spin" /> : '保存修改'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 看板三列 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {columns.map((col) => {
          const colTasks = getColumnTasks(col.key);
          return (
            <div key={col.key} className={`rounded-xl border p-4 ${col.color}`}>
              <div className="mb-4 flex items-center justify-between">
                <h3 className={`text-sm font-semibold ${col.headerColor}`}>{col.label}</h3>
                <span className="rounded-full bg-[#0E0E0E] px-2 py-0.5 text-xs text-zinc-400">
                  {colTasks.length}
                </span>
              </div>
              <div className="space-y-2">
                {colTasks.length === 0 ? (
                  <div className="rounded-lg border border-white/5 bg-[#0E0E0E] p-4 text-center">
                    <p className="text-xs text-zinc-600">暂无任务</p>
                  </div>
                ) : (
                  colTasks.map((task) => {
                    const source = getSourceTag(task);
                    return (
                      <div
                        key={task.id}
                        className={`group relative rounded-lg border bg-[#111111] p-3 transition-colors hover:border-amber-400/20 ${
                          focusTaskId && focusTaskId === task.id ? 'border-amber-400/60' : 'border-white/10'
                        }`}
                      >
                        <div className="mb-2 flex items-start justify-between gap-2">
                          <h4 className="text-sm font-medium text-white">{task.task_name}</h4>
                          <div className="relative">
                            <button
                              onClick={() => setMenuTaskId(menuTaskId === task.id ? null : task.id)}
                              className="text-zinc-500 hover:text-white"
                            >
                              <MoreHorizontal size={14} />
                            </button>
                            {/* 状态切换菜单 */}
                            {menuTaskId === task.id && (
                              <div className="absolute right-0 top-6 z-10 w-32 rounded-lg border border-white/10 bg-[#1a1a1a] p-1 shadow-xl">
                                {col.key !== 'todo' && (
                                  <button onClick={() => handleMoveTask(task, 'todo')} className="w-full rounded px-2 py-1.5 text-left text-xs text-amber-300 hover:bg-white/5">
                                    移到待办
                                  </button>
                                )}
                                {col.key !== 'doing' && (
                                  <button onClick={() => handleMoveTask(task, 'doing')} className="w-full rounded px-2 py-1.5 text-left text-xs text-blue-300 hover:bg-white/5">
                                    移到进行中
                                  </button>
                                )}
                                {col.key !== 'done' && (
                                  <button onClick={() => handleMoveTask(task, 'done')} className="w-full rounded px-2 py-1.5 text-left text-xs text-emerald-300 hover:bg-white/5">
                                    移到已完成
                                  </button>
                                )}
                                <button
                                  onClick={() => openEditTask(task)}
                                  className="w-full rounded px-2 py-1.5 text-left text-xs text-amber-300 hover:bg-white/5"
                                >
                                  编辑任务
                                </button>
                                <button
                                  onClick={() => {
                                    setAssignTask(task);
                                    setSelectedAssigneeKey(task.assignee_id ? `${task.assignee_type}:${task.assignee_id}` : '');
                                    setMenuTaskId(null);
                                  }}
                                  className="w-full rounded px-2 py-1.5 text-left text-xs text-violet-300 hover:bg-white/5"
                                >
                                  分配负责人
                                </button>
                                <button
                                  onClick={() => handleDeleteTask(task)}
                                  className="w-full rounded px-2 py-1.5 text-left text-xs text-red-300 hover:bg-white/5"
                                >
                                  <span className="inline-flex items-center gap-1"><Trash2 size={11} />删除任务</span>
                                </button>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* 元信息行 */}
                        <div className="flex flex-wrap items-center gap-2 text-[11px]">
                          <span className="flex items-center gap-1">
                            <span className={`h-1.5 w-1.5 rounded-full ${getPriorityColor(task.priority)}`} />
                            {getPriorityLabel(task.priority)}
                          </span>
                          {task.owner_role && (
                            <span className="flex items-center gap-1 text-zinc-500">
                              <User size={10} />
                              {task.owner_role}
                            </span>
                          )}
                          {task.assignee_name && (
                            <button
                              onClick={() => onOpenMember?.(task.assignee_id)}
                              className="flex items-center gap-1 rounded-full bg-emerald-400/10 px-1.5 py-0.5 text-emerald-300 hover:bg-emerald-400/20"
                            >
                              <User size={10} />
                              {task.assignee_name}
                            </button>
                          )}
                          <span className={`rounded-full px-1.5 py-0.5 ${source.color}`}>
                            {source.label}
                          </span>
                          {task.source_type === 'meeting' && (
                            <button onClick={onOpenMeeting} className="text-blue-300 hover:text-blue-200">
                              查看来源会议
                            </button>
                          )}
                          {task.due_date && (
                            <span className="text-zinc-500">截止 {new Date(task.due_date).toLocaleDateString('zh-CN')}</span>
                          )}
                          {task.risk_level && task.risk_level !== 'low' && (
                            <span className="flex items-center gap-1 text-red-400">
                              <AlertCircle size={10} />
                              {task.risk_level}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

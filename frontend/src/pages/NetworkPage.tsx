import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bot, Briefcase, Edit3, Loader2, ListTodo, Save, Tag, UserPlus, Users, X } from 'lucide-react';
import {
  getNetworkMemberWorkload,
  listTeamMembers,
  updateNetworkHumanMember,
  type NetworkMember,
  type NetworkMemberWorkload,
} from '../lib/projectsApi';

function parseSkills(value: string) {
  try {
    return JSON.parse(value || '[]') as string[];
  } catch {
    return [];
  }
}

export function NetworkPage() {
  const [members, setMembers] = useState<NetworkMember[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>('');
  const [workload, setWorkload] = useState<NetworkMemberWorkload | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [editRole, setEditRole] = useState('');

  const loadMembers = useCallback(async (nextSelectedKey = '') => {
    setLoading(true);
    try {
      const result = await listTeamMembers();
      setMembers(result.members);
      if (!nextSelectedKey && result.members.length > 0) {
        setSelectedKey(`${result.members[0].type}:${result.members[0].id}`);
      }
    } catch {
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMembers('');
  }, [loadMembers]);

  const selected = useMemo(
    () => members.find((member) => `${member.type}:${member.id}` === selectedKey),
    [members, selectedKey],
  );
  const humanMembers = members.filter((member) => member.type === 'human');
  const aiMembers = members.filter((member) => member.type === 'digital_employee');

  useEffect(() => {
    if (!selected) {
      setWorkload(null);
      return;
    }
    getNetworkMemberWorkload(selected.type, selected.id)
      .then(setWorkload)
      .catch(() => setWorkload(null));
    setEditing(false);
    setEditName(selected.name);
    setEditRole(selected.role);
  }, [selected]);

  async function handleSaveMember() {
    if (!selected || selected.type !== 'human' || !editName.trim()) return;
    setBusy(true);
    setMessage('');
    try {
      await updateNetworkHumanMember(selected.id, { name: editName.trim(), role: editRole.trim() });
      const nextKey = `${selected.type}:${selected.id}`;
      await loadMembers(nextKey);
      setSelectedKey(nextKey);
      setEditing(false);
      setMessage('成员信息已更新。');
    } catch (error) {
      setMessage(`保存失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  function renderMemberButton(member: NetworkMember) {
    const key = `${member.type}:${member.id}`;
    const active = selectedKey === key;
    return (
      <button
        key={key}
        onClick={() => setSelectedKey(key)}
        className={`flex w-full items-center gap-3 rounded-lg p-3 text-left transition-colors ${
          active ? 'border-l-2 border-amber-400 bg-amber-400/10' : 'bg-white/5 hover:bg-white/10'
        }`}
      >
        <div className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold ${member.type === 'human' ? 'bg-amber-400/10 text-amber-300' : 'bg-blue-400/10 text-blue-300'}`}>
          {member.type === 'human' ? member.name.charAt(0) : 'AI'}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-white">{member.name}</div>
          <div className="truncate text-xs text-zinc-500">{member.role}</div>
        </div>
      </button>
    );
  }

  return (
    <main className="min-h-screen bg-gray-900 px-6 pb-20 pt-28 md:px-12">
      <div className="mx-auto max-w-[1360px]">
        <div className="mb-8 flex items-start justify-between">
          <div>
            <span className="mb-4 block text-xs font-medium uppercase tracking-[0.3em] text-zinc-500">
              Digital Network
            </span>
            <h1 className="mb-4 text-3xl font-bold tracking-tight text-white md:text-5xl">数字网络平台</h1>
            <p className="max-w-3xl text-sm leading-7 text-zinc-400">
              真实员工和 AI 员工的全局成员库。项目团队和任务负责人会从这里统一调用。
            </p>
          </div>
          <button disabled className="flex cursor-not-allowed items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-zinc-500">
            <UserPlus size={16} />
            添加成员
          </button>
        </div>

        {message && (
          <div className="mb-5 rounded-lg border border-white/10 bg-white/5 p-3 text-sm text-zinc-300">
            {busy && <Loader2 size={14} className="mr-2 inline animate-spin" />}
            {message}
          </div>
        )}

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[300px_1fr]">
          <div className="rounded-xl border border-white/10 bg-white/5 p-5">
            <div className="mb-6">
              <div className="mb-3 flex items-center gap-2">
                <Users size={16} className="text-amber-400" />
                <h2 className="text-sm font-semibold text-white">真实成员</h2>
                <span className="text-xs text-zinc-500">({humanMembers.length})</span>
              </div>
              <div className="space-y-1.5">
                {loading ? <p className="py-4 text-center text-sm text-zinc-500">加载中...</p> : humanMembers.map(renderMemberButton)}
              </div>
            </div>

            <div>
              <div className="mb-3 flex items-center gap-2">
                <Bot size={16} className="text-blue-400" />
                <h2 className="text-sm font-semibold text-white">AI数字员工</h2>
                <span className="text-xs text-zinc-500">({aiMembers.length})</span>
              </div>
              <div className="space-y-1.5">
                {aiMembers.map(renderMemberButton)}
                {!loading && aiMembers.length === 0 && <p className="py-4 text-center text-sm text-zinc-500">暂无AI员工</p>}
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/5 p-6">
            {selected ? (
              <>
                <div className="mb-6 flex items-start justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <div className={`flex h-16 w-16 items-center justify-center rounded-full text-2xl font-semibold ${selected.type === 'human' ? 'bg-amber-400/10 text-amber-300' : 'bg-blue-400/10 text-blue-300'}`}>
                      {selected.type === 'human' ? selected.name.charAt(0) : 'AI'}
                    </div>
                    <div>
                      {editing ? (
                        <div className="space-y-2">
                          <input value={editName} onChange={(event) => setEditName(event.target.value)} className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-amber-400/60" />
                          <input value={editRole} onChange={(event) => setEditRole(event.target.value)} className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-amber-400/60" />
                        </div>
                      ) : (
                        <>
                          <h2 className="text-xl font-semibold text-white">{selected.name}</h2>
                          <p className="text-sm text-zinc-400">{selected.role}</p>
                        </>
                      )}
                      <div className="mt-2 flex items-center gap-2">
                        <span className="rounded-full bg-emerald-400/10 px-2 py-0.5 text-xs text-emerald-300">{selected.status}</span>
                        <span className={`rounded-full px-2 py-0.5 text-xs ${selected.type === 'human' ? 'bg-amber-400/10 text-amber-300' : 'bg-blue-400/10 text-blue-300'}`}>
                          {selected.type === 'human' ? '真实员工' : 'AI员工'}
                        </span>
                      </div>
                    </div>
                  </div>
                  {selected.type === 'human' && (
                    <div className="flex gap-2">
                      {editing ? (
                        <>
                          <button onClick={handleSaveMember} disabled={busy || !editName.trim()} className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-3 py-2 text-sm font-semibold text-black disabled:opacity-50">
                            <Save size={14} />
                            保存
                          </button>
                          <button onClick={() => setEditing(false)} className="rounded-lg border border-white/10 p-2 text-zinc-400 hover:text-white">
                            <X size={16} />
                          </button>
                        </>
                      ) : (
                        <button onClick={() => setEditing(true)} className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-zinc-300 hover:bg-white/10">
                          <Edit3 size={14} />
                          编辑姓名/角色
                        </button>
                      )}
                    </div>
                  )}
                </div>

                <div className="mb-6">
                  <div className="mb-3 flex items-center gap-2">
                    <Tag size={16} className="text-amber-400" />
                    <h3 className="text-sm font-semibold text-white">能力标签</h3>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {parseSkills(selected.skills).length > 0 ? (
                      parseSkills(selected.skills).map((skill) => (
                        <span key={skill} className="rounded-full bg-amber-400/20 px-3 py-1 text-xs text-amber-300">
                          {skill}
                        </span>
                      ))
                    ) : (
                      <p className="text-sm text-zinc-500">暂无标签</p>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
                  <div>
                    <div className="mb-3 flex items-center gap-2">
                      <Briefcase size={16} className="text-emerald-400" />
                      <h3 className="text-sm font-semibold text-white">参与项目</h3>
                      <span className="text-xs text-zinc-500">({workload?.project_count ?? 0})</span>
                    </div>
                    {workload?.projects.length ? (
                      <div className="space-y-2">
                        {workload.projects.map((project) => (
                          <div key={`${project.project_id}:${project.role}`} className="rounded-lg border border-white/10 bg-gray-800 p-3 text-sm">
                            <div className="text-zinc-200">{project.project_name}</div>
                            <div className="mt-1 text-xs text-zinc-500">{project.role || '项目成员'}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-zinc-500">暂无关联项目</p>
                    )}
                  </div>

                  <div>
                    <div className="mb-3 flex items-center gap-2">
                      <ListTodo size={16} className="text-violet-400" />
                      <h3 className="text-sm font-semibold text-white">当前任务</h3>
                      <span className="text-xs text-zinc-500">({workload?.task_count ?? 0})</span>
                    </div>
                    {workload?.tasks.length ? (
                      <div className="space-y-2">
                        {workload.tasks.map((task) => (
                          <div key={task.id} className="rounded-lg border border-white/10 bg-gray-800 p-3 text-sm">
                            <div className="text-zinc-200">{task.task_name}</div>
                            <div className="mt-1 flex items-center justify-between text-xs text-zinc-500">
                              <span>{task.project_name}</span>
                              <span>{task.status}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-zinc-500">暂无进行中的任务</p>
                    )}
                  </div>
                </div>
              </>
            ) : (
              <div className="flex h-full min-h-[400px] items-center justify-center text-center">
                <div>
                  <Users size={40} className="mx-auto mb-4 text-zinc-600" />
                  <p className="text-sm text-zinc-500">选择左侧成员查看详情</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

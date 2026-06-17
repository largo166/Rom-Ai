import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bot, ChevronRight, Loader2, Plus, UserCircle, Users, X } from 'lucide-react';
import { type NetworkMember, type ProjectDetail, type ProjectTask, listTeamMembers } from '../../lib/projectsApi';
import {
  addTeamMember,
  listTeamMembers as fetchProjectTeam,
  type TeamMember as ProjectTeamMember,
} from '../../lib/teamApi';

type Props = {
  projectId: string;
  project: ProjectDetail;
  focusMemberId?: string;
  onRefresh: () => void;
  onOpenTask?: (taskId: string) => void;
};

function memberKey(member: Pick<ProjectTeamMember, 'member_type' | 'member_id'>) {
  return `${member.member_type}:${member.member_id}`;
}

function tasksForMember(tasks: ProjectTask[], member: ProjectTeamMember) {
  return tasks.filter((task) => task.assignee_id === member.member_id && task.assignee_type === member.member_type);
}

export function TeamTab({ projectId, project, focusMemberId = '', onRefresh, onOpenTask }: Props) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [projectTeam, setProjectTeam] = useState<ProjectTeamMember[]>([]);
  const [networkMembers, setNetworkMembers] = useState<NetworkMember[]>([]);
  const [selectedMemberKey, setSelectedMemberKey] = useState('');
  const [newRole, setNewRole] = useState('');
  const [responsibilities, setResponsibilities] = useState('');

  const loadTeam = useCallback(async () => {
    const [team, network] = await Promise.all([
      fetchProjectTeam(projectId).catch(() => []),
      listTeamMembers().then((result) => result.members).catch(() => []),
    ]);
    setProjectTeam(team);
    setNetworkMembers(network);
  }, [projectId]);

  useEffect(() => {
    loadTeam();
  }, [loadTeam, project.assignments]);

  const selectedNetworkMember = useMemo(
    () => networkMembers.find((member) => `${member.type}:${member.id}` === selectedMemberKey),
    [networkMembers, selectedMemberKey],
  );
  const assignedKeys = new Set(projectTeam.map(memberKey));
  const availableMembers = networkMembers.filter((member) => !assignedKeys.has(`${member.type}:${member.id}`));
  const humanMembers = projectTeam.filter((member) => member.member_type === 'human');
  const aiMembers = projectTeam.filter((member) => member.member_type === 'digital_employee');

  async function handleAddMember() {
    if (!selectedNetworkMember) return;
    setBusy(true);
    setMessage('');
    try {
      await addTeamMember(projectId, {
        member_id: selectedNetworkMember.id,
        member_type: selectedNetworkMember.type,
        member_name: selectedNetworkMember.name,
        role: newRole.trim() || selectedNetworkMember.role,
        responsibilities,
      });
      setShowAddModal(false);
      setSelectedMemberKey('');
      setNewRole('');
      setResponsibilities('');
      await loadTeam();
      await onRefresh();
      setMessage('成员已加入项目团队。');
    } catch (error) {
      setMessage(`加入失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  function renderMemberList(title: string, icon: 'human' | 'ai', members: ProjectTeamMember[]) {
    const Icon = icon === 'human' ? Users : Bot;
    return (
      <div className="rounded-xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm">
        <div className="mb-4 flex items-center gap-2">
          <Icon size={16} className={icon === 'human' ? 'text-amber-300' : 'text-blue-300'} />
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <span className="text-xs text-zinc-500">({members.length})</span>
        </div>
        {members.length === 0 ? (
          <div className="rounded-lg border border-white/5 bg-[#0E0E0E] p-6 text-center">
            <UserCircle size={28} className="mx-auto mb-3 text-zinc-600" />
            <p className="text-sm text-zinc-500">暂无成员</p>
          </div>
        ) : (
          <div className="space-y-3">
            {members.map((member) => {
              const memberTasks = tasksForMember(project.tasks, member);
              return (
                <div
                  key={member.id}
                  className={`rounded-lg border bg-[#0E0E0E] p-3 ${
                    focusMemberId && focusMemberId === member.member_id
                      ? 'border-amber-400/60'
                      : 'border-white/10'
                  }`}
                >
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold ${icon === 'human' ? 'bg-amber-400/10 text-amber-300' : 'bg-blue-400/10 text-blue-300'}`}>
                        {icon === 'human' ? member.member_name.charAt(0) : 'AI'}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-white">{member.member_name}</div>
                        <div className="text-[11px] text-zinc-500">{member.role || '未设置项目角色'}</div>
                      </div>
                    </div>
                    <span className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-zinc-400">
                      {memberTasks.length} 个任务
                    </span>
                  </div>
                  {member.responsibilities && <p className="mb-3 text-xs leading-5 text-zinc-500">{member.responsibilities}</p>}
                  {memberTasks.length > 0 && (
                    <div className="space-y-1.5">
                      {memberTasks.slice(0, 4).map((task) => (
                        <button
                          key={task.id}
                          onClick={() => onOpenTask?.(task.id)}
                          className="flex w-full items-center justify-between rounded-md bg-white/5 px-2 py-1.5 text-left text-xs text-zinc-300 hover:bg-white/10"
                        >
                          <span className="truncate">{task.task_name}</span>
                          <ChevronRight size={12} className="text-zinc-600" />
                        </button>
                      ))}
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

  return (
    <div className="space-y-4">
      {message && (
        <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-sm text-zinc-300">
          {busy && <Loader2 size={14} className="mr-2 inline animate-spin" />}
          {message}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">项目团队</h2>
          <p className="mt-1 text-xs text-zinc-500">从网络平台加入真实员工或 AI 员工，再把任务分配给团队成员。</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-3 py-1.5 text-sm font-semibold text-black hover:bg-amber-300"
        >
          <Plus size={14} />
          从网络平台加入
        </button>
      </div>

      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-xl border border-white/10 bg-[#171717] p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">加入项目团队</h3>
              <button onClick={() => setShowAddModal(false)} className="text-zinc-500 hover:text-white">
                <X size={20} />
              </button>
            </div>
            <div className="space-y-4">
              <label className="block text-xs text-zinc-500">
                网络平台成员
                <select
                  value={selectedMemberKey}
                  onChange={(event) => {
                    setSelectedMemberKey(event.target.value);
                    const member = networkMembers.find((item) => `${item.type}:${item.id}` === event.target.value);
                    setNewRole(member?.role || '');
                  }}
                  className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                >
                  <option value="">选择成员</option>
                  {availableMembers.map((member) => (
                    <option key={`${member.type}:${member.id}`} value={`${member.type}:${member.id}`}>
                      {member.type === 'human' ? '真实员工' : 'AI员工'} · {member.name} · {member.role}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs text-zinc-500">
                项目角色
                <input
                  value={newRole}
                  onChange={(event) => setNewRole(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                  placeholder="例如：项目负责人、资料整理、方案审核"
                />
              </label>
              <label className="block text-xs text-zinc-500">
                职责说明
                <textarea
                  value={responsibilities}
                  onChange={(event) => setResponsibilities(event.target.value)}
                  className="mt-1 min-h-20 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                  placeholder="这个成员在本项目里负责什么"
                />
              </label>
              <button
                onClick={handleAddMember}
                disabled={busy || !selectedNetworkMember}
                className="w-full rounded-lg bg-amber-400 py-2.5 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
              >
                {busy ? <Loader2 size={16} className="mx-auto animate-spin" /> : '加入项目团队'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {renderMemberList('真实成员', 'human', humanMembers)}
        {renderMemberList('AI数字员工', 'ai', aiMembers)}
      </div>
    </div>
  );
}

import { useState, useEffect } from 'react';
import {
  CalendarPlus,
  ChevronDown,
  ChevronUp,
  Loader2,
  Play,
  Sparkles,
  Square,
  CalendarDays,
  Trash2,
  X,
} from 'lucide-react';
import {
  type ProjectMeeting,
  createProjectMeeting,
  createTencentProjectMeeting,
  deleteProjectMeeting,
  syncTencentMeetingMinutes,
  summarizeProjectMeeting,
} from '../../lib/projectsApi';
import { parseMeetingActionItems } from './meetingActions';

type Props = {
  projectId: string;
  meetings: ProjectMeeting[];
  onRefresh: () => void;
};

const TRANSCRIPT_PREVIEW_LINES = 5;

function formatDate(value: string) {
  if (!value) return '';
  return new Date(value).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getStatusBadge(status: string) {
  const s = status?.toLowerCase() ?? '';
  if (s.includes('scheduled') || s.includes('计划'))
    return 'border-blue-400/30 bg-blue-400/10 text-blue-300';
  if (s.includes('completed') || s.includes('完成') || s.includes('done'))
    return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300';
  if (s.includes('summarized') || s.includes('纪要'))
    return 'border-amber-400/30 bg-amber-400/10 text-amber-300';
  return 'border-zinc-500/30 bg-zinc-500/10 text-zinc-400';
}

function extractTencentJoinUrl(meetingLink: string) {
  return meetingLink.match(/https:\/\/meeting\.tencent\.com\/dm\/[^\s，。)）]+/)?.[0] ?? '';
}

function extractTencentRecordingUrl(meetingLink: string) {
  return meetingLink.match(/https:\/\/meeting\.tencent\.com\/crw\/[^\s，。)）]+/)?.[0] ?? '';
}

export function MeetingsTab({ projectId, meetings, onRefresh }: Props) {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProjectMeeting | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  // 创建会议表单
  const [newTitle, setNewTitle] = useState('');
  const [newDate, setNewDate] = useState('');
  const [newEndDate, setNewEndDate] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [createTencent, setCreateTencent] = useState(false);

  // 纪要生成
  const [transcriptMap, setTranscriptMap] = useState<Record<string, string>>({});
  const [expandedTranscriptMap, setExpandedTranscriptMap] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setMessage('');
  }, [projectId]);

  const sortedMeetings = [...meetings].sort((a, b) => {
    const da = a.scheduled_at || a.created_at;
    const db = b.scheduled_at || b.created_at;
    return new Date(db).getTime() - new Date(da).getTime();
  });

  async function handleCreateMeeting() {
    if (!newTitle.trim()) return;
    if (createTencent && (!newDate || !newEndDate)) {
      setMessage('同步创建腾讯会议需要填写开始和结束时间。');
      return;
    }
    setBusy(true);
    setMessage('');
    try {
      if (createTencent) {
        const meeting = await createTencentProjectMeeting(projectId, {
          title: newTitle,
          start_time: `${newDate}:00+08:00`,
          end_time: `${newEndDate}:00+08:00`,
          agenda: newNotes,
        });
        const joinUrl = meeting.tencent_join_url || extractTencentJoinUrl(meeting.meeting_link);
        if (joinUrl) {
          window.open(joinUrl, '_blank', 'noopener,noreferrer');
        }
      } else {
        await createProjectMeeting(projectId, {
          title: newTitle,
          meeting_link: newNotes || undefined,
          scheduled_at: newDate || undefined,
        });
      }
      setShowCreateModal(false);
      setNewTitle('');
      setNewDate('');
      setNewEndDate('');
      setNewNotes('');
      setCreateTencent(false);
      await onRefresh();
      setMessage(createTencent ? '腾讯会议已创建，并已写入项目会议卡片。' : '会议已创建。');
    } catch (error) {
      setMessage(`创建失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerateMinutes(meeting: ProjectMeeting) {
    setBusy(true);
    setMessage('');
    try {
      const transcript = transcriptMap[meeting.id] || meeting.transcript;
      await summarizeProjectMeeting(projectId, meeting.id, { transcript });
      setTranscriptMap((prev) => {
        const next = { ...prev };
        delete next[meeting.id];
        return next;
      });
      await onRefresh();
      setMessage('已基于真实会议转写生成AI纪要和待办。');
    } catch (error) {
      setMessage(`生成纪要失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleSyncTencentMinutes(meeting: ProjectMeeting) {
    setBusy(true);
    setMessage('');
    try {
      await syncTencentMeetingMinutes(projectId, meeting.id);
      await onRefresh();
      setMessage('已同步腾讯会议真实原始转写和录屏入口。');
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setMessage(`暂时无法同步腾讯原始转写：${detail}。请确认这场会议已开启云录制和转写。`);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteMeeting() {
    if (!deleteTarget) return;
    const deletedMeeting = deleteTarget;
    setBusy(true);
    setMessage('');
    try {
      await deleteProjectMeeting(projectId, deletedMeeting.id);
      setDeleteTarget(null);
      setExpandedId((current) => current === deletedMeeting.id ? null : current);
      setTranscriptMap((prev) => {
        const next = { ...prev };
        delete next[deletedMeeting.id];
        return next;
      });
      setExpandedTranscriptMap((prev) => {
        const next = { ...prev };
        delete next[deletedMeeting.id];
        return next;
      });
      await onRefresh();
      setMessage(`已删除会议记录“${deletedMeeting.title}”。`);
    } catch (error) {
      setMessage(`删除失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  // 解析待办事项
  function getActionItems(meeting: ProjectMeeting): string[] {
    return parseMeetingActionItems(meeting.next_actions_json);
  }

  return (
    <div className="space-y-4">
      {message && (
        <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-sm text-zinc-300">
          {busy && <Loader2 size={14} className="mr-2 inline animate-spin" />}
          {message}
        </div>
      )}

      {/* 标题 + 新建按钮 */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">会议记录</h2>
        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-300"
        >
          <CalendarPlus size={15} />
          新建会议
        </button>
      </div>

      {/* 创建会议 Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-xl border border-white/10 bg-[#171717] p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">新建会议</h3>
              <button onClick={() => setShowCreateModal(false)} className="text-zinc-500 hover:text-white">
                <X size={20} />
              </button>
            </div>

            <div className="space-y-4">
              <label className="block text-xs text-zinc-500">
                会议标题
                <input
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                  placeholder="例如：项目启动会"
                />
              </label>
              <label className="block text-xs text-zinc-500">
                开始时间
                <input
                  type="datetime-local"
                  value={newDate}
                  onChange={(e) => setNewDate(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                />
              </label>
              {createTencent && (
                <label className="block text-xs text-zinc-500">
                  结束时间
                  <input
                    type="datetime-local"
                    value={newEndDate}
                    onChange={(e) => setNewEndDate(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                  />
                </label>
              )}
              <label className="block text-xs text-zinc-500">
                {createTencent ? '会前议程 / 备注' : '备注 / 会议链接'}
                <textarea
                  value={newNotes}
                  onChange={(e) => setNewNotes(e.target.value)}
                  className="mt-1 min-h-[72px] w-full resize-none rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 outline-none focus:border-amber-400/60"
                  placeholder={createTencent ? '可选：填写真实会前议程或备注；留空则不生成内容' : '腾讯会议链接或其他备注'}
                />
              </label>
              <label className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 p-3 text-xs text-zinc-300">
                <input
                  type="checkbox"
                  checked={createTencent}
                  onChange={(event) => setCreateTencent(event.target.checked)}
                  className="h-4 w-4 accent-amber-400"
                />
                同步创建腾讯会议，并把会议号/链接写入本项目
              </label>
              <button
                onClick={handleCreateMeeting}
                disabled={busy || !newTitle.trim()}
                className="w-full rounded-lg bg-amber-400 py-2.5 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
              >
                {busy ? <Loader2 size={16} className="mx-auto animate-spin" /> : createTencent ? '创建腾讯会议' : '创建会议'}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-red-400/20 bg-[#171717] p-6">
            <h3 className="text-lg font-semibold text-white">删除会议记录</h3>
            <p className="mt-3 text-sm leading-6 text-zinc-400">
              确认删除“{deleteTarget.title}”？会议记录及其生成的知识库纪要将被删除，此操作无法撤销。
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                disabled={busy}
                onClick={() => setDeleteTarget(null)}
                className="rounded-lg border border-white/10 px-4 py-2 text-sm text-zinc-300 hover:bg-white/5 disabled:opacity-50"
              >
                取消
              </button>
              <button
                disabled={busy}
                onClick={handleDeleteMeeting}
                className="inline-flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-sm font-semibold text-white hover:bg-red-400 disabled:opacity-50"
              >
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 会议列表 */}
      {sortedMeetings.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/5 p-8 text-center">
          <CalendarDays size={36} className="mx-auto mb-4 text-zinc-600" />
          <h3 className="mb-2 text-sm font-semibold text-white">暂无会议记录</h3>
          <p className="text-sm text-zinc-500">
            点击"新建会议"创建第一条会议纪要，或由AI代理自动生成。
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {sortedMeetings.map((meeting) => {
            const isExpanded = expandedId === meeting.id;
            const actionItems = getActionItems(meeting);
            const transcriptLines = meeting.transcript.trimEnd().split(/\r?\n/);
            const isLongTranscript = transcriptLines.length > TRANSCRIPT_PREVIEW_LINES;
            const isTranscriptExpanded = expandedTranscriptMap[meeting.id] ?? false;
            const visibleTranscript =
              isLongTranscript && !isTranscriptExpanded
                ? `${transcriptLines.slice(0, TRANSCRIPT_PREVIEW_LINES).join('\n').trimEnd()}\n…`
                : meeting.transcript;
            const joinUrl = meeting.tencent_join_url || extractTencentJoinUrl(meeting.meeting_link);
            const recordingUrl = meeting.recording_view_url || extractTencentRecordingUrl(meeting.meeting_link);
            return (
              <div
                key={meeting.id}
                className="rounded-xl border border-white/10 bg-white/5 backdrop-blur-sm"
              >
                {/* 会议卡片头部 */}
                <button
                  onClick={() => setExpandedId(isExpanded ? null : meeting.id)}
                  className="flex w-full items-center justify-between p-4 text-left"
                >
                  <div className="flex-1">
                    <div className="mb-1 flex items-center gap-3">
                      <h3 className="text-sm font-semibold text-white">{meeting.title}</h3>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${getStatusBadge(meeting.status)}`}>
                        {meeting.status}
                      </span>
                    </div>
                    <div className="text-xs text-zinc-500">
                      {formatDate(meeting.scheduled_at || meeting.created_at)}
                    </div>
                  </div>
                  {isExpanded ? (
                    <ChevronUp size={18} className="text-zinc-400" />
                  ) : (
                    <ChevronDown size={18} className="text-zinc-400" />
                  )}
                </button>

                {/* 展开详情 */}
                {isExpanded && (
                  <div className="border-t border-white/10 p-4">
                    {/* 会前议程 */}
                    {meeting.agenda && (
                      <div className="mb-4">
                        <div className="mb-2 text-xs font-medium text-amber-300">会前议程</div>
                        <pre className="whitespace-pre-wrap text-sm leading-6 text-zinc-400">
                          {meeting.agenda}
                        </pre>
                      </div>
                    )}

                    {(meeting.meeting_link || joinUrl || meeting.tencent_meeting_id) && (
                      <div className="mb-4">
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <div className="text-xs font-medium text-blue-300">腾讯会议</div>
                          <div className="flex items-center gap-2">
                            {recordingUrl && (
                              <button
                                onClick={() => window.open(recordingUrl, '_blank', 'noopener,noreferrer')}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-purple-400/30 bg-purple-400/10 px-2.5 py-1.5 text-xs text-purple-200 hover:bg-purple-400/20"
                              >
                                <Play size={12} />
                                查看录屏
                              </button>
                            )}
                            {joinUrl && (
                              <button
                                onClick={() => window.open(joinUrl, '_blank', 'noopener,noreferrer')}
                                className="rounded-lg border border-blue-400/30 bg-blue-400/10 px-2.5 py-1.5 text-xs text-blue-200 hover:bg-blue-400/20"
                              >
                                进入会议
                              </button>
                            )}
                            <button
                              disabled={busy}
                              onClick={() => handleSyncTencentMinutes(meeting)}
                              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1.5 text-xs text-emerald-200 hover:bg-emerald-400/20 disabled:opacity-50"
                            >
                              {busy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                              同步腾讯原始记录
                            </button>
                          </div>
                        </div>
                        <div className="rounded-lg border border-white/10 bg-[#0E0E0E] px-3 py-2.5 text-xs text-zinc-500">
                          已关联腾讯会议
                          {recordingUrl && ' · 已获取会议录屏'}
                          {meeting.last_synced_at && ` · 最近同步 ${formatDate(meeting.last_synced_at)}`}
                        </div>
                        {meeting.sync_status === 'failed' && meeting.sync_error && (
                          <div className="mt-2 rounded-lg border border-red-400/20 bg-red-400/5 px-3 py-2 text-xs text-red-300">
                            上次同步失败：{meeting.sync_error}
                          </div>
                        )}
                      </div>
                    )}

                    {/* 纪要 */}
                    {meeting.summary && (
                      <div className="mb-4">
                        <div className="mb-2 text-xs font-medium text-emerald-300">AI纪要（基于真实转写）</div>
                        <pre className="whitespace-pre-wrap text-sm leading-6 text-zinc-400">
                          {meeting.summary}
                        </pre>
                      </div>
                    )}

                    {meeting.transcript && (
                      <div className="mb-4">
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <div className="text-xs font-medium text-purple-300">
                            腾讯原始转写
                            <span className="ml-2 font-normal text-zinc-500">
                              {meeting.transcript.length.toLocaleString('zh-CN')} 字
                            </span>
                          </div>
                          {isLongTranscript && (
                            <button
                              onClick={() =>
                                setExpandedTranscriptMap((prev) => ({
                                  ...prev,
                                  [meeting.id]: !isTranscriptExpanded,
                                }))
                              }
                              className="inline-flex shrink-0 items-center gap-1 text-xs text-purple-300 hover:text-purple-200"
                            >
                              {isTranscriptExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                              {isTranscriptExpanded ? '收起全文' : '展开全文'}
                            </button>
                          )}
                        </div>
                        <pre className={`${isTranscriptExpanded ? 'max-h-[60vh]' : 'max-h-80'} overflow-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-[#0E0E0E] p-3 text-sm leading-6 text-zinc-300`}>
                          {visibleTranscript}
                        </pre>
                      </div>
                    )}

                    {/* 待办事项 */}
                    {actionItems.length > 0 && (
                      <div className="mb-4">
                        <div className="mb-2 text-xs font-medium text-blue-300">待办事项</div>
                        <div className="space-y-2">
                          {actionItems.map((item, index) => (
                            <div key={index} className="flex items-start gap-2 text-sm text-zinc-400">
                              <Square size={14} className="mt-0.5 shrink-0 text-zinc-500" />
                              <span>{item}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 真实会议记录输入 + AI生成纪要 */}
                    <div className="mt-3 space-y-3">
                      <textarea
                        value={transcriptMap[meeting.id] ?? ''}
                        onChange={(e) =>
                          setTranscriptMap((prev) => ({ ...prev, [meeting.id]: e.target.value }))
                        }
                        placeholder="没有腾讯转写时，可粘贴真实会议记录文本，用于生成AI纪要和待办"
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-400/60 min-h-[80px] resize-none"
                      />
                      <button
                        disabled={busy}
                        onClick={() => handleGenerateMinutes(meeting)}
                        className="inline-flex items-center gap-2 rounded-lg border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-200 hover:bg-amber-400/20 disabled:opacity-50"
                      >
                        {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                        基于真实转写生成AI纪要
                      </button>
                    </div>
                    <div className="mt-4 border-t border-white/10 pt-4">
                      <button
                        disabled={busy}
                        onClick={() => setDeleteTarget(meeting)}
                        className="inline-flex items-center gap-2 rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-2 text-sm text-red-200 hover:bg-red-400/20 disabled:opacity-50"
                      >
                        <Trash2 size={14} />
                        删除会议记录
                      </button>
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

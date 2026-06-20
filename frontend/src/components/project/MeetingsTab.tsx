import { useState, useEffect, useRef } from 'react';
import {
  CalendarPlus,
  ChevronDown,
  ChevronUp,
  Loader2,
  Play,
  Square,
  Sparkles,
  CalendarDays,
  Trash2,
  X,
  Volume2,
  VolumeX,
  CheckCircle,
  Eye,
  EyeOff,
  AlertCircle,
  FileText,
  MessageSquareQuote,
  ClipboardList,
  ListTodo,
  Gavel,
  Video,
  Upload,
  ClipboardPaste,
  MessageSquare,
} from 'lucide-react';
import {
  type ProjectMeeting,
  type MeetingMinutesResult,
  type MeetingMinutesContent,
  type MeetingScriptStatus,
  type MeetingRefluxSummary,
  type CommunicationType,
  createProjectMeeting,
  createTencentProjectMeeting,
  createCommunication,
  deleteProjectMeeting,
  syncTencentMeetingMinutes,
  summarizeProjectMeeting,
  generateMeetingMinutes,
  confirmMeetingMinutes,
  getMeetingScriptStatus,
} from '../../lib/projectsApi';
import { parseMeetingActionItems } from './meetingActions';
import { AudioUploader } from '../meeting/AudioUploader';
import { TranscriptPaster } from '../meeting/TranscriptPaster';
import { RecommendationPanel } from '../knowledge/RecommendationPanel';

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
    return 'border-blue-200 bg-blue-50 text-blue-700';
  if (s.includes('completed') || s.includes('完成') || s.includes('done'))
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (s.includes('summarized') || s.includes('纪要'))
    return 'border-amber-200 bg-amber-50 text-amber-700';
  return 'border-stone-200 bg-stone-100 text-stone-500';
}

function getCommunicationMeta(type: string) {
  const map: Record<string, { label: string; icon: string }> = {
    phone: { label: '电话', icon: '📞' },
    wechat: { label: '微信摘录', icon: '💬' },
    email: { label: '邮件摘要', icon: '✉️' },
    onsite: { label: '现场沟通', icon: '🏢' },
    verbal: { label: '口头沟通', icon: '🗣️' },
  };
  return map[type] ?? null;
}

function getPriorityColor(priority: string) {
  if (priority === 'high') return 'text-red-600';
  if (priority === 'medium') return 'text-amber-600';
  return 'text-stone-500';
}

function extractTencentJoinUrl(meetingLink: string) {
  return meetingLink.match(/https:\/\/meeting\.tencent\.com\/dm\/[^\s，。)）]+/)?.[0] ?? '';
}

function extractTencentRecordingUrl(meetingLink: string) {
  return meetingLink.match(/https:\/\/meeting\.tencent\.com\/crw\/[^\s，。)）]+/)?.[0] ?? '';
}

function getConfidenceColor(confidence: number) {
  if (confidence >= 0.8) return 'text-emerald-600';
  if (confidence >= 0.6) return 'text-amber-600';
  return 'text-red-600';
}

type QuickRecordFormProps = {
  commType: CommunicationType;
  setCommType: (v: CommunicationType) => void;
  participants: string;
  setParticipants: (v: string) => void;
  content: string;
  setContent: (v: string) => void;
  occurredAt: string;
  setOccurredAt: (v: string) => void;
  busy: boolean;
  onSubmit: () => void;
};

function QuickRecordForm({
  commType,
  setCommType,
  participants,
  setParticipants,
  content,
  setContent,
  occurredAt,
  setOccurredAt,
  busy,
  onSubmit,
}: QuickRecordFormProps) {
  const options: { value: CommunicationType; label: string; icon: string }[] = [
    { value: 'phone', label: '电话', icon: '📞' },
    { value: 'wechat', label: '微信摘录', icon: '💬' },
    { value: 'email', label: '邮件摘要', icon: '✉️' },
    { value: 'onsite', label: '现场', icon: '🏢' },
    { value: 'verbal', label: '总监/甲方口头', icon: '🗣️' },
  ];

  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1 text-xs text-stone-500">沟通类型</div>
        <div className="flex flex-wrap gap-2">
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setCommType(opt.value)}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs transition-colors ${
                commType === opt.value
                  ? 'border-[#C2703A] bg-[#C2703A]/10 text-[#C2703A]'
                  : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50'
              }`}
            >
              <span>{opt.icon}</span>
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <label className="block text-xs text-stone-500">
        参与人（可选）
        <input
          value={participants}
          onChange={(e) => setParticipants(e.target.value)}
          className="mt-1 w-full rounded-lg border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-900 outline-none transition-colors focus:border-[#C2703A] focus:ring-1 focus:ring-[#C2703A]"
          placeholder="例如：甲方王总、项目经理李工"
        />
      </label>

      <label className="block text-xs text-stone-500">
        沟通内容 <span className="text-red-500">*</span>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="粘贴或输入沟通内容…"
          className="mt-1 min-h-[160px] w-full resize-y rounded-lg border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-900 outline-none transition-colors focus:border-[#C2703A] focus:ring-1 focus:ring-[#C2703A]"
        />
        <div className="mt-1 text-right text-xs text-stone-400">
          {content.length.toLocaleString('zh-CN')} 字
        </div>
      </label>

      <label className="block text-xs text-stone-500">
        发生时间（可选，默认当前时间）
        <input
          type="datetime-local"
          value={occurredAt}
          onChange={(e) => setOccurredAt(e.target.value)}
          className="mt-1 w-full rounded-lg border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-900 outline-none transition-colors focus:border-[#C2703A] focus:ring-1 focus:ring-[#C2703A]"
        />
      </label>

      <button
        type="button"
        onClick={onSubmit}
        disabled={busy || content.trim().length < 10}
        className="w-full rounded-lg bg-[#C2703A] py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#A85C30] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? <Loader2 size={16} className="mx-auto animate-spin" /> : '记录并生成纪要'}
      </button>
    </div>
  );
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
  const [createInputTab, setCreateInputTab] = useState<'tencent' | 'audio' | 'paste' | 'quick'>('tencent');
  const [createdMeetingId, setCreatedMeetingId] = useState<string | null>(null);

  // 快速记录（沟通记录）
  const [commType, setCommType] = useState<CommunicationType>('phone');
  const [commParticipants, setCommParticipants] = useState('');
  const [commContent, setCommContent] = useState('');
  const [commOccurredAt, setCommOccurredAt] = useState('');

  // 纪要生成
  const [transcriptMap, setTranscriptMap] = useState<Record<string, string>>({});
  const [expandedTranscriptMap, setExpandedTranscriptMap] = useState<Record<string, boolean>>({});

  // Phase 4: 五段式纪要状态
  const [minutesResultMap, setMinutesResultMap] = useState<Record<string, MeetingMinutesResult>>({});
  const [minutesLoadingMap, setMinutesLoadingMap] = useState<Record<string, boolean>>({});
  const [showInternalMap, setShowInternalMap] = useState<Record<string, boolean>>({});
  const [confirmingMap, setConfirmingMap] = useState<Record<string, boolean>>({});

  // 纪要回流摘要
  const [refluxSummaryMap, setRefluxSummaryMap] = useState<Record<string, MeetingRefluxSummary>>({});

  // 播报状态
  const [speakingMap, setSpeakingMap] = useState<Record<string, boolean>>({});
  const [pausedMap, setPausedMap] = useState<Record<string, boolean>>({});

  // 腾讯脚本状态
  const [scriptStatus, setScriptStatus] = useState<MeetingScriptStatus | null>(null);

  const speechSynthRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    setMessage('');
  }, [projectId]);

  useEffect(() => {
    getMeetingScriptStatus().then(setScriptStatus).catch(() => {
      setScriptStatus({ available: false, script_path: null, error_message: '无法获取脚本状态' });
    });
  }, []);

  const sortedMeetings = [...meetings].sort((a, b) => {
    const da = a.scheduled_at || a.created_at;
    const db = b.scheduled_at || b.created_at;
    return new Date(db).getTime() - new Date(da).getTime();
  });

  async function handleCreateMeeting() {
    if (!newTitle.trim()) return;
    if (createInputTab === 'tencent' && (!newDate || !newEndDate)) {
      setMessage('同步创建腾讯会议需要填写开始和结束时间。');
      return;
    }
    setBusy(true);
    setMessage('');
    try {
      if (createInputTab === 'tencent') {
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
        setShowCreateModal(false);
        resetCreateForm();
        await onRefresh();
        setMessage('腾讯会议已创建，并已写入项目会议卡片。');
      } else {
        const meeting = await createProjectMeeting(projectId, {
          title: newTitle,
          meeting_link: newNotes || undefined,
          scheduled_at: newDate || undefined,
        });
        setCreatedMeetingId(meeting.id);
        await onRefresh();
        setMessage('会议已创建，请继续上传录音或粘贴转写文本。');
      }
    } catch (error) {
      setMessage(`创建失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  function resetCreateForm() {
    setNewTitle('');
    setNewDate('');
    setNewEndDate('');
    setNewNotes('');
    setCreateInputTab('tencent');
    setCreatedMeetingId(null);
    setCommType('phone');
    setCommParticipants('');
    setCommContent('');
    setCommOccurredAt('');
  }

  async function handleCreateCommunication() {
    if (!commContent.trim() || commContent.trim().length < 10) {
      setMessage('请输入至少 10 个字符的沟通内容。');
      return;
    }
    setBusy(true);
    setMessage('');
    try {
      await createCommunication(projectId, {
        communication_type: commType,
        title: newTitle || undefined,
        participants: commParticipants || undefined,
        content: commContent,
        occurred_at: commOccurredAt || undefined,
      });
      setShowCreateModal(false);
      resetCreateForm();
      await onRefresh();
      setMessage('沟通记录已保存，五段式纪要已生成。');
    } catch (error) {
      setMessage(`记录失败：${String(error)}`);
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

  // Phase 4: 生成五段式纪要
  async function handleGenerateFiveSectionMinutes(meeting: ProjectMeeting) {
    const transcript = transcriptMap[meeting.id] || meeting.transcript;
    if (!transcript.trim()) {
      setMessage('请先粘贴或输入会议转写文本。');
      return;
    }
    setMinutesLoadingMap((prev) => ({ ...prev, [meeting.id]: true }));
    setMessage('');
    try {
      const result = await generateMeetingMinutes(projectId, transcript);
      setMinutesResultMap((prev) => ({ ...prev, [meeting.id]: result }));
      setShowInternalMap((prev) => ({ ...prev, [meeting.id]: true }));
      setMessage('五段式纪要已生成（草案），请审阅后确认。');
    } catch (error) {
      setMessage(`生成五段式纪要失败：${String(error)}`);
    } finally {
      setMinutesLoadingMap((prev) => ({ ...prev, [meeting.id]: false }));
    }
  }

  // Phase 4: 确认纪要回流
  async function handleConfirmMinutes(meeting: ProjectMeeting) {
    const result = minutesResultMap[meeting.id];
    if (!result) return;
    const minutes = showInternalMap[meeting.id]
      ? result.internal_version
      : (result.external_version as MeetingMinutesContent);
    setConfirmingMap((prev) => ({ ...prev, [meeting.id]: true }));
    setMessage('');
    try {
      const data = await confirmMeetingMinutes(projectId, meeting.id, minutes);
      if (data.reflux_summary) {
        setRefluxSummaryMap((prev) => ({ ...prev, [meeting.id]: data.reflux_summary }));
      }
      await onRefresh();
      setMessage('纪要已确认为正式版，待办已回流任务看板。');
      setMinutesResultMap((prev) => {
        const next = { ...prev };
        delete next[meeting.id];
        return next;
      });
    } catch (error) {
      setMessage(`确认纪要失败：${String(error)}`);
    } finally {
      setConfirmingMap((prev) => ({ ...prev, [meeting.id]: false }));
    }
  }

  // 播报脚本
  function handleSpeak(meetingId: string, script: string) {
    if (!('speechSynthesis' in window)) {
      setMessage('当前浏览器不支持语音播报。');
      return;
    }
    if (speakingMap[meetingId]) {
      window.speechSynthesis.cancel();
      setSpeakingMap((prev) => ({ ...prev, [meetingId]: false }));
      setPausedMap((prev) => ({ ...prev, [meetingId]: false }));
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(script);
    utterance.lang = 'zh-CN';
    utterance.rate = 1.0;
    utterance.onend = () => {
      setSpeakingMap((prev) => ({ ...prev, [meetingId]: false }));
      setPausedMap((prev) => ({ ...prev, [meetingId]: false }));
    };
    utterance.onerror = () => {
      setSpeakingMap((prev) => ({ ...prev, [meetingId]: false }));
      setPausedMap((prev) => ({ ...prev, [meetingId]: false }));
    };
    speechSynthRef.current = utterance;
    setSpeakingMap((prev) => ({ ...prev, [meetingId]: true }));
    window.speechSynthesis.speak(utterance);
  }

  function handlePauseSpeak(meetingId: string) {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.pause();
    setPausedMap((prev) => ({ ...prev, [meetingId]: true }));
  }

  function handleResumeSpeak(meetingId: string) {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.resume();
    setPausedMap((prev) => ({ ...prev, [meetingId]: false }));
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
      setMessage(`已删除会议记录"${deletedMeeting.title}"。`);
    } catch (error) {
      setMessage(`删除失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  function getActionItems(meeting: ProjectMeeting): string[] {
    return parseMeetingActionItems(meeting.next_actions_json);
  }

  return (
    <div className="space-y-4">
      {message && (
        <div className="rounded-lg border border-stone-200 bg-white p-3 text-sm text-stone-700 shadow-xs">
          {busy && <Loader2 size={14} className="mr-2 inline animate-spin text-[#C2703A]" />}
          {message}
        </div>
      )}

      {/* 标题 + 腾讯脚本状态 + 新建按钮 */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="font-serif text-base font-semibold text-stone-900">会议记录</h2>
          {scriptStatus && (
            <div className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] ${
              scriptStatus.available
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-stone-200 bg-stone-100 text-stone-500'
            }`}>
              <div className={`h-1.5 w-1.5 rounded-full ${scriptStatus.available ? 'bg-emerald-500' : 'bg-stone-400'}`} />
              {scriptStatus.available ? '腾讯会议脚本可用' : '腾讯脚本未配置'}
            </div>
          )}
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-[#C2703A] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#A85C30]"
        >
          <CalendarPlus size={15} />
          新建会议
        </button>
      </div>

      {/* 腾讯脚本不可用提示 */}
      {scriptStatus && !scriptStatus.available && (
        <div className="flex items-start gap-2 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5 text-xs text-stone-500">
          <AlertCircle size={13} className="mt-0.5 shrink-0 text-[#C2703A]" />
          <span>腾讯会议自动同步不可用，但手动粘贴转写文本生成五段式纪要始终可用。{scriptStatus.error_message}</span>
        </div>
      )}

      {/* 创建会议 Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-xl rounded-xl border border-stone-200 bg-[#FAF8F5] p-6 shadow-lg">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="font-serif text-lg font-semibold text-stone-900">
                {createdMeetingId ? '录入会议内容' : '新建会议'}
              </h3>
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  resetCreateForm();
                }}
                className="text-stone-400 transition-colors hover:text-stone-700"
              >
                <X size={20} />
              </button>
            </div>

            {/* 新建会议入口 - 四种方式 */}
            {!createdMeetingId && (
              <div className="mb-4 flex border-b border-stone-200">
                <button
                  onClick={() => setCreateInputTab('tencent')}
                  className={`flex flex-1 items-center justify-center gap-1.5 border-b-2 px-3 py-2.5 text-sm transition-colors ${
                    createInputTab === 'tencent'
                      ? 'border-[#C2703A] font-medium text-[#C2703A]'
                      : 'border-transparent text-stone-500 hover:text-stone-700'
                  }`}
                >
                  <Video size={14} />
                  腾讯会议
                </button>
                <button
                  onClick={() => setCreateInputTab('audio')}
                  className={`flex flex-1 items-center justify-center gap-1.5 border-b-2 px-3 py-2.5 text-sm transition-colors ${
                    createInputTab === 'audio'
                      ? 'border-[#C2703A] font-medium text-[#C2703A]'
                      : 'border-transparent text-stone-500 hover:text-stone-700'
                  }`}
                >
                  <Upload size={14} />
                  上传录音
                </button>
                <button
                  onClick={() => setCreateInputTab('paste')}
                  className={`flex flex-1 items-center justify-center gap-1.5 border-b-2 px-3 py-2.5 text-sm transition-colors ${
                    createInputTab === 'paste'
                      ? 'border-[#C2703A] font-medium text-[#C2703A]'
                      : 'border-transparent text-stone-500 hover:text-stone-700'
                  }`}
                >
                  <ClipboardPaste size={14} />
                  粘贴文本
                </button>
                <button
                  onClick={() => setCreateInputTab('quick')}
                  className={`flex flex-1 items-center justify-center gap-1.5 border-b-2 px-3 py-2.5 text-sm transition-colors ${
                    createInputTab === 'quick'
                      ? 'border-[#C2703A] font-medium text-[#C2703A]'
                      : 'border-transparent text-stone-500 hover:text-stone-700'
                  }`}
                >
                  <MessageSquare size={14} />
                  快速记录
                </button>
              </div>
            )}

            <div className="space-y-4">
              {/* 会议标题（始终需要） */}
              {!createdMeetingId && (
                <label className="block text-xs text-stone-500">
                  会议标题
                  <input
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-900 outline-none transition-colors focus:border-[#C2703A] focus:ring-1 focus:ring-[#C2703A]"
                    placeholder="例如：项目启动会"
                  />
                </label>
              )}

              {/* 腾讯会议表单 */}
              {!createdMeetingId && createInputTab === 'tencent' && (
                <>
                  <label className="block text-xs text-stone-500">
                    开始时间
                    <input
                      type="datetime-local"
                      value={newDate}
                      onChange={(e) => setNewDate(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-900 outline-none transition-colors focus:border-[#C2703A] focus:ring-1 focus:ring-[#C2703A]"
                    />
                  </label>
                  <label className="block text-xs text-stone-500">
                    结束时间
                    <input
                      type="datetime-local"
                      value={newEndDate}
                      onChange={(e) => setNewEndDate(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-900 outline-none transition-colors focus:border-[#C2703A] focus:ring-1 focus:ring-[#C2703A]"
                    />
                  </label>
                  <label className="block text-xs text-stone-500">
                    会前议程 / 备注
                    <textarea
                      value={newNotes}
                      onChange={(e) => setNewNotes(e.target.value)}
                      className="mt-1 min-h-[72px] w-full resize-none rounded-lg border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-900 outline-none transition-colors focus:border-[#C2703A] focus:ring-1 focus:ring-[#C2703A]"
                      placeholder="可选：填写真实会前议程或备注"
                    />
                  </label>
                </>
              )}

              {/* 上传录音 / 粘贴文本 共用字段 */}
              {!createdMeetingId && createInputTab !== 'tencent' && createInputTab !== 'quick' && (
                <label className="block text-xs text-stone-500">
                  开始时间（可选）
                  <input
                    type="datetime-local"
                    value={newDate}
                    onChange={(e) => setNewDate(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-900 outline-none transition-colors focus:border-[#C2703A] focus:ring-1 focus:ring-[#C2703A]"
                  />
                </label>
              )}

              {/* 快速记录（沟通记录）表单 */}
              {!createdMeetingId && createInputTab === 'quick' && (
                <QuickRecordForm
                  commType={commType}
                  setCommType={setCommType}
                  participants={commParticipants}
                  setParticipants={setCommParticipants}
                  content={commContent}
                  setContent={setCommContent}
                  occurredAt={commOccurredAt}
                  setOccurredAt={setCommOccurredAt}
                  busy={busy}
                  onSubmit={handleCreateCommunication}
                />
              )}

              {/* 创建按钮 / 输入组件 */}
              {!createdMeetingId && createInputTab !== 'quick' && (
                <button
                  onClick={handleCreateMeeting}
                  disabled={busy || !newTitle.trim()}
                  className="w-full rounded-lg bg-[#C2703A] py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#A85C30] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? (
                    <Loader2 size={16} className="mx-auto animate-spin" />
                  ) : createInputTab === 'tencent' ? (
                    '创建腾讯会议'
                  ) : (
                    '创建会议并继续录入'
                  )}
                </button>
              )}

              {/* 会议内容录入区 */}
              {createdMeetingId && (
                <div className="space-y-4">
                  <div className="mb-4 flex border-b border-stone-200">
                    <button
                      onClick={() => setCreateInputTab('audio')}
                      className={`flex flex-1 items-center justify-center gap-1.5 border-b-2 px-3 py-2.5 text-sm transition-colors ${
                        createInputTab === 'audio'
                          ? 'border-[#C2703A] font-medium text-[#C2703A]'
                          : 'border-transparent text-stone-500 hover:text-stone-700'
                      }`}
                    >
                      <Upload size={14} />
                      上传录音
                    </button>
                    <button
                      onClick={() => setCreateInputTab('paste')}
                      className={`flex flex-1 items-center justify-center gap-1.5 border-b-2 px-3 py-2.5 text-sm transition-colors ${
                        createInputTab === 'paste'
                          ? 'border-[#C2703A] font-medium text-[#C2703A]'
                          : 'border-transparent text-stone-500 hover:text-stone-700'
                      }`}
                    >
                      <ClipboardPaste size={14} />
                      粘贴文本
                    </button>
                  </div>

                  {createInputTab === 'audio' && (
                    <AudioUploader
                      projectId={projectId}
                      meetingId={createdMeetingId}
                      onTranscribed={(transcript) => {
                        setTranscriptMap((prev) => ({ ...prev, [createdMeetingId]: transcript }));
                        setShowCreateModal(false);
                        resetCreateForm();
                        setExpandedId(createdMeetingId);
                        setMessage('音频转写完成，已生成会议转写文本。');
                        onRefresh();
                      }}
                    />
                  )}

                  {createInputTab === 'paste' && (
                    <TranscriptPaster
                      projectId={projectId}
                      meetingId={createdMeetingId}
                      onSaved={(cleanedText) => {
                        setTranscriptMap((prev) => ({ ...prev, [createdMeetingId]: cleanedText }));
                        setShowCreateModal(false);
                        resetCreateForm();
                        setExpandedId(createdMeetingId);
                        setMessage('转写文本已保存并清洗。');
                        onRefresh();
                      }}
                    />
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl border border-red-200 bg-white p-6 shadow-lg">
            <h3 className="font-serif text-lg font-semibold text-stone-900">删除会议记录</h3>
            <p className="mt-3 text-sm leading-6 text-stone-600">
              确认删除"{deleteTarget.title}"？会议记录及其生成的知识库纪要将被删除，此操作无法撤销。
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                disabled={busy}
                onClick={() => setDeleteTarget(null)}
                className="rounded-lg border border-stone-200 px-4 py-2 text-sm text-stone-600 transition-colors hover:bg-stone-50 disabled:opacity-50"
              >
                取消
              </button>
              <button
                disabled={busy}
                onClick={handleDeleteMeeting}
                className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-500 disabled:opacity-50"
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
        <div className="rounded-xl border border-stone-200 bg-white p-8 text-center shadow-xs">
          <CalendarDays size={36} className="mx-auto mb-4 text-stone-300" />
          <h3 className="mb-2 font-serif text-sm font-semibold text-stone-900">暂无会议记录</h3>
          <p className="text-sm text-stone-500">
            点击"新建会议"创建第一条会议纪要，或由AI代理自动生成。
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {sortedMeetings.map((meeting) => {
            const isExpanded = expandedId === meeting.id;
            const commMeta = getCommunicationMeta(meeting.meeting_type);
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
            const minutesResult = minutesResultMap[meeting.id];
            const isMinutesLoading = minutesLoadingMap[meeting.id] ?? false;
            const showInternal = showInternalMap[meeting.id] ?? true;
            const isConfirming = confirmingMap[meeting.id] ?? false;
            const isSpeaking = speakingMap[meeting.id] ?? false;
            const isPaused = pausedMap[meeting.id] ?? false;
            const currentMinutes = minutesResult
              ? (showInternal ? minutesResult.internal_version : minutesResult.external_version as MeetingMinutesContent)
              : null;

            return (
              <div
                key={meeting.id}
                className="rounded-xl border border-stone-200 bg-white shadow-xs"
              >
                {/* 会议卡片头部 */}
                <button
                  onClick={() => setExpandedId(isExpanded ? null : meeting.id)}
                  className="flex w-full items-center justify-between p-4 text-left"
                >
                  <div className="flex-1">
                    <div className="mb-1 flex items-center gap-3">
                      <h3 className="font-serif text-sm font-semibold text-stone-900">{meeting.title}</h3>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${getStatusBadge(meeting.status)}`}>
                        {meeting.status}
                      </span>
                      {commMeta && (
                        <span className="inline-flex items-center gap-1 rounded bg-stone-100 px-2 py-0.5 text-xs text-stone-600">
                          <span>{commMeta.icon}</span>
                          {commMeta.label}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-stone-500">
                      {formatDate(meeting.scheduled_at || meeting.created_at)}
                    </div>
                  </div>
                  {isExpanded ? (
                    <ChevronUp size={18} className="text-stone-400" />
                  ) : (
                    <ChevronDown size={18} className="text-stone-400" />
                  )}
                </button>

                {/* 展开详情 */}
                {isExpanded && (
                  <div className="border-t border-stone-200 p-4 space-y-4">
                    {/* 会前议程 */}
                    {meeting.agenda && (
                      <div>
                        <div className="mb-2 text-xs font-medium text-[#C2703A]">会前议程</div>
                        <pre className="whitespace-pre-wrap text-sm leading-6 text-stone-600">
                          {meeting.agenda}
                        </pre>
                      </div>
                    )}

                    {/* 腾讯会议信息 */}
                    {(meeting.meeting_link || joinUrl || meeting.tencent_meeting_id) && (
                      <div>
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <div className="text-xs font-medium text-blue-600">腾讯会议</div>
                          <div className="flex items-center gap-2">
                            {recordingUrl && (
                              <button
                                onClick={() => window.open(recordingUrl, '_blank', 'noopener,noreferrer')}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-purple-200 bg-purple-50 px-2.5 py-1.5 text-xs text-purple-700 transition-colors hover:bg-purple-100"
                              >
                                <Play size={12} />
                                查看录屏
                              </button>
                            )}
                            {joinUrl && (
                              <button
                                onClick={() => window.open(joinUrl, '_blank', 'noopener,noreferrer')}
                                className="rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1.5 text-xs text-blue-700 transition-colors hover:bg-blue-100"
                              >
                                进入会议
                              </button>
                            )}
                            <button
                              disabled={busy || !scriptStatus?.available}
                              onClick={() => handleSyncTencentMinutes(meeting)}
                              title={!scriptStatus?.available ? '腾讯会议脚本未配置' : '同步腾讯原始记录'}
                              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs text-emerald-700 transition-colors hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                              {busy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                              同步腾讯原始记录
                            </button>
                          </div>
                        </div>
                        <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5 text-xs text-stone-500">
                          已关联腾讯会议
                          {recordingUrl && ' · 已获取会议录屏'}
                          {meeting.last_synced_at && ` · 最近同步 ${formatDate(meeting.last_synced_at)}`}
                        </div>
                        {meeting.sync_status === 'failed' && meeting.sync_error && (
                          <div className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
                            上次同步失败：{meeting.sync_error}
                          </div>
                        )}
                      </div>
                    )}

                    {/* 旧版AI纪要 */}
                    {meeting.summary && !minutesResult && (
                      <div>
                        <div className="mb-2 text-xs font-medium text-emerald-600">AI纪要（基于真实转写）</div>
                        <pre className="whitespace-pre-wrap text-sm leading-6 text-stone-600">
                          {meeting.summary}
                        </pre>
                      </div>
                    )}

                    {/* 转写文本 */}
                    {meeting.transcript && (
                      <div>
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <div className="text-xs font-medium text-purple-600">
                            原始转写
                            <span className="ml-2 font-normal text-stone-500">
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
                              className="inline-flex shrink-0 items-center gap-1 text-xs text-purple-600 transition-colors hover:text-purple-700"
                            >
                              {isTranscriptExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                              {isTranscriptExpanded ? '收起全文' : '展开全文'}
                            </button>
                          )}
                        </div>
                        <pre className={`${isTranscriptExpanded ? 'max-h-[60vh]' : 'max-h-80'} overflow-auto whitespace-pre-wrap rounded-lg border border-stone-200 bg-stone-50 p-3 text-sm leading-6 text-stone-700`}>
                          {visibleTranscript}
                        </pre>
                      </div>
                    )}

                    {/* 旧版待办事项 */}
                    {actionItems.length > 0 && !minutesResult && (
                      <div>
                        <div className="mb-2 text-xs font-medium text-blue-600">待办事项</div>
                        <div className="space-y-2">
                          {actionItems.map((item, index) => (
                            <div key={index} className="flex items-start gap-2 text-sm text-stone-600">
                              <Square size={14} className="mt-0.5 shrink-0 text-stone-400" />
                              <span>{item}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* ─────────────── Phase 4: 五段式纪要区域 ─────────────── */}
                    <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4 space-y-4">
                      <div className="flex items-center gap-2">
                        <FileText size={14} className="text-[#C2703A]" />
                        <span className="text-xs font-semibold text-[#C2703A]">五段式会议纪要</span>
                        <span className="ml-auto text-[10px] text-stone-500">AI出草案，人工审定后确认</span>
                      </div>

                      {/* 转写输入区 */}
                      <div>
                        <div className="mb-1 text-xs text-stone-500">粘贴会议转写文本（永远可用，无需腾讯脚本）</div>
                        <textarea
                          value={transcriptMap[meeting.id] ?? ''}
                          onChange={(e) =>
                            setTranscriptMap((prev) => ({ ...prev, [meeting.id]: e.target.value }))
                          }
                          placeholder="将会议录音转写文字粘贴至此，支持任何来源的文字记录…"
                          className="w-full min-h-[100px] resize-y rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 outline-none transition-colors focus:border-[#C2703A] focus:ring-1 focus:ring-[#C2703A]"
                        />
                      </div>

                      {/* 生成按钮 */}
                      <div className="flex flex-wrap gap-2">
                        <button
                          disabled={isMinutesLoading}
                          onClick={() => handleGenerateFiveSectionMinutes(meeting)}
                          className="inline-flex items-center gap-2 rounded-lg bg-[#C2703A] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#A85C30] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {isMinutesLoading ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Sparkles size={14} />
                          )}
                          {isMinutesLoading ? '生成中…' : '生成五段式纪要'}
                        </button>
                        {!minutesResult && (
                          <button
                            disabled={busy}
                            onClick={() => handleGenerateMinutes(meeting)}
                            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-600 transition-colors hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                            旧版AI纪要
                          </button>
                        )}
                      </div>

                      {/* 五段式纪要结果 */}
                      {minutesResult && currentMinutes && (
                        <div className="space-y-4">
                          {/* 草案状态 + 内/外版切换 */}
                          <div className="flex flex-wrap items-center gap-3">
                            <div className="flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs text-amber-700">
                              <AlertCircle size={11} />
                              草案 · 待人工审定
                            </div>
                            <div className="flex items-center overflow-hidden rounded-lg border border-stone-200 text-xs">
                              <button
                                onClick={() => setShowInternalMap((p) => ({ ...p, [meeting.id]: true }))}
                                className={`flex items-center gap-1.5 px-3 py-1.5 transition-colors ${showInternal ? 'bg-[#C2703A]/10 text-[#C2703A]' : 'text-stone-500 hover:text-stone-700'}`}
                              >
                                <Eye size={11} />
                                内部版（含转译）
                              </button>
                              <button
                                onClick={() => setShowInternalMap((p) => ({ ...p, [meeting.id]: false }))}
                                className={`flex items-center gap-1.5 px-3 py-1.5 transition-colors ${!showInternal ? 'bg-[#C2703A]/10 text-[#C2703A]' : 'text-stone-500 hover:text-stone-700'}`}
                              >
                                <EyeOff size={11} />
                                对外版（不含转译）
                              </button>
                            </div>
                          </div>

                          {/* 1. 纪要内容 */}
                          {currentMinutes.meeting_content && (
                            <div>
                              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-emerald-700">
                                <FileText size={12} />
                                纪要内容摘要
                              </div>
                              <div className="rounded-lg border border-stone-200 bg-white px-3 py-3 text-sm leading-6 text-stone-700">
                                {currentMinutes.meeting_content}
                              </div>
                            </div>
                          )}

                          {/* 2. 核心事项 */}
                          {currentMinutes.key_items.length > 0 && (
                            <div>
                              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-blue-700">
                                <ListTodo size={12} />
                                核心事项
                              </div>
                              <div className="space-y-2">
                                {currentMinutes.key_items.map((item, i) => (
                                  <div key={i} className="flex items-start gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2.5">
                                    <span className={`mt-0.5 text-xs font-semibold ${getPriorityColor(item.priority)}`}>
                                      {item.priority === 'high' ? '高' : item.priority === 'medium' ? '中' : '低'}
                                    </span>
                                    <span className="flex-1 text-sm text-stone-700">{item.item}</span>
                                    {item.owner && (
                                      <span className="shrink-0 text-xs text-stone-500">@{item.owner}</span>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 3. 甲方诉求转译（仅内部版） */}
                          {showInternal && minutesResult.internal_version.client_translation.length > 0 && (
                            <div>
                              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-purple-700">
                                <MessageSquareQuote size={12} />
                                甲方诉求转译
                                <span className="font-normal text-stone-500">（内部版专用，每条锚定原话）</span>
                              </div>
                              <div className="space-y-2">
                                {minutesResult.internal_version.client_translation.map((t, i) => (
                                  <div key={i} className="rounded-lg border border-purple-200 bg-purple-50/50 p-3 space-y-2">
                                    <div className="flex items-start justify-between gap-3">
                                      <div className="flex-1">
                                        <div className="mb-1 text-xs text-stone-500">甲方原话</div>
                                        <div className="text-sm italic text-stone-700">"{t.source_quote || t.original}"</div>
                                      </div>
                                      <div className={`shrink-0 text-xs font-semibold ${getConfidenceColor(t.confidence)}`}>
                                        置信度 {Math.round(t.confidence * 100)}%
                                      </div>
                                    </div>
                                    <div>
                                      <div className="mb-1 text-xs text-stone-500">设计语言转译</div>
                                      <div className="flex flex-wrap gap-1.5">
                                        {t.translation.map((tr, j) => (
                                          <span key={j} className="rounded-md border border-purple-200 bg-purple-50 px-2 py-0.5 text-xs text-purple-700">
                                            {tr}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                    {t.jargon_matched && (
                                      <div className="text-[10px] text-stone-500">
                                        匹配关键词：{t.jargon_matched} · 来源：{t.source === 'seed_dictionary' ? '种子词典' : 'AI分析'}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 4. 会议决议 */}
                          {currentMinutes.decisions.length > 0 && (
                            <div>
                              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-amber-700">
                                <Gavel size={12} />
                                会议决议
                              </div>
                              <div className="space-y-2">
                                {currentMinutes.decisions.map((d, i) => (
                                  <div key={i} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5">
                                    <div className="text-sm text-stone-700">{d.decision}</div>
                                    <div className="mt-1 flex gap-3 text-xs text-stone-500">
                                      {d.responsible && <span>负责：{d.responsible}</span>}
                                      {d.deadline && <span>截止：{d.deadline}</span>}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 5. 待办事项 */}
                          {currentMinutes.action_items.length > 0 && (
                            <div>
                              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-teal-700">
                                <ClipboardList size={12} />
                                待办事项
                                <span className="font-normal text-stone-500">（确认后自动回流任务看板）</span>
                              </div>
                              <div className="space-y-2">
                                {currentMinutes.action_items.map((a, i) => (
                                  <div key={i} className="flex items-start gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2.5">
                                    <Square size={13} className="mt-0.5 shrink-0 text-stone-400" />
                                    <div className="flex-1">
                                      <div className="text-sm text-stone-700">{a.task}</div>
                                      <div className="mt-1 flex flex-wrap gap-2 text-xs text-stone-500">
                                        {a.assignee && <span>@{a.assignee}</span>}
                                        {a.due_date && <span>截止 {a.due_date}</span>}
                                        <span className={getPriorityColor(a.priority)}>
                                          {a.priority === 'high' ? '紧急' : a.priority === 'medium' ? '一般' : '低优先'}
                                        </span>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 播报脚本 */}
                          {minutesResult.broadcast_script && (
                            <div>
                              <div className="mb-2 flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2 text-xs font-semibold text-stone-700">
                                  <Volume2 size={12} />
                                  播报脚本
                                </div>
                                <div className="flex flex-wrap items-center gap-2">
                                  <button
                                    onClick={() => handleSpeak(meeting.id, minutesResult.broadcast_script)}
                                    className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                                      isSpeaking
                                        ? 'border-red-200 bg-red-50 text-red-700 hover:bg-red-100'
                                        : 'border-stone-200 bg-stone-50 text-stone-600 hover:bg-stone-100'
                                    }`}
                                  >
                                    {isSpeaking ? <VolumeX size={12} /> : <Volume2 size={12} />}
                                    {isSpeaking ? '停止' : '播报要点'}
                                  </button>
                                  {isSpeaking && !isPaused && (
                                    <button
                                      onClick={() => handlePauseSpeak(meeting.id)}
                                      className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50 px-3 py-1.5 text-xs text-stone-600 hover:bg-stone-100"
                                    >
                                      <Square size={12} />
                                      暂停
                                    </button>
                                  )}
                                  {isSpeaking && isPaused && (
                                    <button
                                      onClick={() => handleResumeSpeak(meeting.id)}
                                      className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50 px-3 py-1.5 text-xs text-stone-600 hover:bg-stone-100"
                                    >
                                      <Play size={12} />
                                      继续
                                    </button>
                                  )}
                                </div>
                              </div>
                              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-stone-200 bg-stone-50 px-3 py-3 text-xs leading-6 text-stone-500">
                                {minutesResult.broadcast_script}
                              </pre>
                            </div>
                          )}

                          {/* 确认按钮 */}
                          <div className="flex items-center gap-3 border-t border-stone-200 pt-3">
                            <button
                              disabled={isConfirming}
                              onClick={() => handleConfirmMinutes(meeting)}
                              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {isConfirming ? (
                                <Loader2 size={14} className="animate-spin" />
                              ) : (
                                <CheckCircle size={14} />
                              )}
                              确认纪要（回流任务看板）
                            </button>
                            <span className="text-xs text-stone-500">
                              确认后：待办事项将写入任务看板，纪要状态变为"summarized"
                            </span>
                          </div>

                          {/* 纪要确认后的回流反馈 */}
                          {refluxSummaryMap[meeting.id] && (
                            (() => {
                              const summary = refluxSummaryMap[meeting.id];
                              const transcript = transcriptMap[meeting.id] || meeting.transcript || '';
                              return (
                                <>
                                <div className="mt-4 rounded-lg border border-stone-200 bg-white p-4 shadow-xs">
                                  <h4 className="mb-2 font-serif text-sm font-medium text-stone-900">纪要已确认，回流完成</h4>
                                  <div className="flex flex-wrap gap-3 text-xs text-stone-600">
                                    {summary.demands_added > 0 && (
                                      <span className="rounded bg-amber-50 px-2 py-1 text-amber-700">
                                        新增 {summary.demands_added} 条甲方诉求
                                      </span>
                                    )}
                                    {summary.risks_added > 0 && (
                                      <span className="rounded bg-red-50 px-2 py-1 text-red-700">
                                        标记 {summary.risks_added} 个新风险
                                      </span>
                                    )}
                                    {summary.tasks_created > 0 && (
                                      <span className="rounded bg-blue-50 px-2 py-1 text-blue-700">
                                        生成 {summary.tasks_created} 个待办
                                      </span>
                                    )}
                                    {summary.okf_stale_cards && summary.okf_stale_cards.length > 0 && (
                                      <span className="rounded bg-orange-50 px-2 py-1 text-[#C2703A]">
                                        {summary.okf_stale_cards.length} 个技能卡需刷新
                                      </span>
                                    )}
                                  </div>
                                </div>
                                <div className="mt-3">
                                  <RecommendationPanel
                                    projectId={projectId}
                                    trigger="meeting"
                                    options={transcript ? { transcript_text: transcript.slice(0, 500) } : undefined}
                                  />
                                </div>
                                </>
                              );
                            })()
                          )}
                        </div>
                      )}
                    </div>
                    {/* ─────────────── End Phase 4 ─────────────── */}

                    {/* 删除按钮 */}
                    <div className="border-t border-stone-200 pt-4">
                      <button
                        disabled={busy}
                        onClick={() => setDeleteTarget(meeting)}
                        className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
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

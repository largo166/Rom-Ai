import { useEffect, useState } from 'react';
import { Loader2, ClipboardPaste, Trash2 } from 'lucide-react';
import { pasteMeetingTranscript } from '../../lib/projectsApi';

type Props = {
  projectId: string;
  meetingId: string;
  onSaved?: (cleanedText: string) => void;
};

function draftKey(projectId: string) {
  return `rmo-draft-${projectId}`;
}

export function TranscriptPaster({ projectId, meetingId, onSaved }: Props) {
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // 自动恢复草稿
  useEffect(() => {
    try {
      const saved = localStorage.getItem(draftKey(projectId));
      if (saved) setText(saved);
    } catch {
      // localStorage 不可用则静默跳过
    }
  }, [projectId]);

  // 自动保存草稿
  useEffect(() => {
    try {
      if (text.trim()) {
        localStorage.setItem(draftKey(projectId), text);
      } else {
        localStorage.removeItem(draftKey(projectId));
      }
    } catch {
      // 静默跳过
    }
  }, [text, projectId]);

  const handleClear = () => {
    setText('');
    try {
      localStorage.removeItem(draftKey(projectId));
    } catch {
      // 静默跳过
    }
  };

  const handleSave = async () => {
    if (text.trim().length < 10) return;
    setSaving(true);
    setError('');
    try {
      const data = await pasteMeetingTranscript(projectId, meetingId, text);
      onSaved?.(data.cleaned_text);
      setText(data.cleaned_text);
      localStorage.removeItem(draftKey(projectId));
    } catch (err) {
      setError(`保存失败：${String(err)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="粘贴会议转写文本…&#10;&#10;支持腾讯会议导出格式、纯文本等&#10;系统会自动清洗格式、标准化时间戳和说话人标记"
        className="w-full min-h-[200px] max-h-[400px] resize-y rounded-lg border border-stone-200 bg-white p-4 text-sm text-stone-900 placeholder:text-stone-400 focus:outline-none focus:ring-1 focus:ring-[#C2703A]"
      />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs text-stone-400">
            {text.length.toLocaleString('zh-CN')} 字
          </span>
          {text.trim().length > 0 && (
            <button
              type="button"
              onClick={handleClear}
              className="inline-flex items-center gap-1 text-xs text-stone-500 transition-colors hover:text-red-600"
            >
              <Trash2 size={12} />
              清空
            </button>
          )}
        </div>
        <button
          onClick={handleSave}
          disabled={text.trim().length < 10 || saving}
          className="inline-flex items-center gap-2 rounded-md bg-[#C2703A] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#A85C30] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <ClipboardPaste size={14} />
          )}
          {saving ? '保存中…' : '保存并清洗'}
        </button>
      </div>
      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}

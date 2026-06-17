import { useState } from 'react';
import { Link } from 'react-router';
import { Eye, FolderInput, Upload, FileText, Loader2, RefreshCw, Trash2, X } from 'lucide-react';
import {
  deleteProjectFile,
  parseOneProjectFile,
  uploadProjectFiles,
  parseProjectFiles,
  previewProjectFile,
  type ProjectDetail,
} from '../../lib/projectsApi';

type Props = {
  projectId: string;
  project: ProjectDetail;
  onRefresh: () => void;
};

export function FilesTab({ projectId, project, onRefresh }: Props) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [preview, setPreview] = useState<{ filename: string; content: string } | null>(null);

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setMessage('');
    try {
      await uploadProjectFiles(projectId, Array.from(files));
      await onRefresh();
      setMessage('新文件已上传并标记为待分析。下一步可以点击"解析文件"。');
    } catch (error) {
      setMessage(`上传失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function onParse() {
    setBusy(true);
    setMessage('');
    try {
      await parseProjectFiles(projectId);
      await onRefresh();
      setMessage('待解析文件已解析完成。旧文件不会重复解析。');
    } catch (error) {
      setMessage(`解析失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function onPreview(fileId: string) {
    setBusy(true);
    try {
      const result = await previewProjectFile(projectId, fileId);
      setPreview({ filename: result.filename, content: result.content || '该文件暂时没有可预览的解析文本。' });
    } catch (error) {
      setMessage(`预览失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function onReparse(fileId: string) {
    setBusy(true);
    try {
      await parseOneProjectFile(projectId, fileId);
      await onRefresh();
      setMessage('文件已重新解析，并标记为待分析。');
    } catch (error) {
      setMessage(`重新解析失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(fileId: string, filename: string) {
    if (!window.confirm(`确认删除项目资料“${filename}”？此操作无法撤销。`)) return;
    setBusy(true);
    try {
      await deleteProjectFile(projectId, fileId);
      await onRefresh();
      setMessage(`已删除项目资料“${filename}”。`);
    } catch (error) {
      setMessage(`删除失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-semibold text-black">
          <Upload size={15} />
          上传资料
          <input
            type="file"
            multiple
            accept=".pdf,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg"
            className="hidden"
            onChange={(event) => onUpload(event.target.files)}
          />
        </label>
        <button
          disabled={busy}
          onClick={onParse}
          className="rounded-lg border border-[#333333] px-3 py-2 text-sm text-zinc-300 hover:border-zinc-600"
        >
          解析文件
        </button>
        <Link
          to={`/inbox?project_id=${projectId}`}
          className="inline-flex items-center gap-2 rounded-lg border border-amber-400/30 px-3 py-2 text-sm text-amber-200 hover:border-amber-300/60"
        >
          <FolderInput size={15} />
          从收件箱导入
        </Link>
      </div>

      {message && (
        <div className="rounded-lg border border-[#333333] bg-[#171717] p-3 text-sm text-zinc-300">
          {busy && <Loader2 size={14} className="mr-2 inline animate-spin" />}
          {message}
        </div>
      )}

      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6 backdrop-blur-sm">
          <div className="flex max-h-[85vh] w-full max-w-4xl flex-col rounded-xl border border-white/10 bg-[#171717]">
            <div className="flex items-center justify-between border-b border-white/10 p-4">
              <h3 className="text-sm font-semibold text-white">{preview.filename}</h3>
              <button onClick={() => setPreview(null)} className="text-zinc-500 hover:text-white"><X size={18} /></button>
            </div>
            <pre className="overflow-auto whitespace-pre-wrap p-5 text-sm leading-6 text-zinc-300">{preview.content}</pre>
          </div>
        </div>
      )}

      {/* File list */}
      <div className="space-y-3">
        {project.files.map((file) => (
          <div key={file.id} className="rounded-lg border border-[#333333] bg-[#171717] p-4 text-sm text-zinc-300">
            <div className="mb-1 flex items-center gap-2">
              <FileText size={14} className="text-amber-300" />
              <span className="font-medium text-white">{file.filename}</span>
            </div>
            <div className="text-xs text-zinc-500">
              {file.filetype} · {(file.filesize / 1024).toFixed(1)}KB · {file.parse_status} · {file.analysis_status === 'analyzed' ? '已分析' : '待分析'}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button onClick={() => onPreview(file.id)} className="inline-flex items-center gap-1 rounded-md border border-[#333333] px-2 py-1 text-xs text-zinc-300 hover:border-amber-400/50">
                <Eye size={13} />预览
              </button>
              <button onClick={() => onReparse(file.id)} className="inline-flex items-center gap-1 rounded-md border border-[#333333] px-2 py-1 text-xs text-zinc-300 hover:border-blue-400/50">
                <RefreshCw size={13} />重新解析
              </button>
              <button onClick={() => onDelete(file.id, file.filename)} className="inline-flex items-center gap-1 rounded-md border border-red-400/30 px-2 py-1 text-xs text-red-300 hover:bg-red-400/10">
                <Trash2 size={13} />删除
              </button>
            </div>
          </div>
        ))}
        {project.files.length === 0 && (
          <p className="text-sm text-zinc-500">暂无文件。点击"上传资料"开始。</p>
        )}
      </div>
    </div>
  );
}

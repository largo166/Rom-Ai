import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import { Brain, ChevronDown, ChevronUp, Clipboard, FolderOpen, Loader2, Search, Send, ShieldCheck, Trash2, UploadCloud } from 'lucide-react';
import {
  askKnowledge,
  clearKnowledge,
  getVaultIndexJob,
  getKnowledgeStats,
  listKnowledgeFiles,
  startVaultIndexJob,
  uploadKnowledgeFiles,
  type KnowledgeFileItem,
  type KnowledgeIndexJob,
  type KnowledgeStats,
  type KnowledgeUploadFile,
} from '../lib/projectsApi';

const DEFAULT_VAULT = '';
const MAX_BROWSER_FILES = 360;
const MAX_BROWSER_TOTAL_BYTES = 120 * 1024 * 1024;
const MAX_BROWSER_FILE_BYTES = 25 * 1024 * 1024;
const SUPPORTED_EXTS = new Set(['.md', '.txt', '.pdf', '.docx', '.xlsx', '.csv', '.pptx']);
const SKIP_DIRS = new Set(['.obsidian', '.git', 'node_modules', 'dist', 'build', '.trash', '.playwright-mcp']);
const CHAT_STORAGE_KEY = 'rom-ai:knowledge-chat-history:v1';
const MAX_SAVED_MESSAGES = 80;

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  references?: Array<{ file_name: string; file_path: string; quote: string }>;
};

function loadSavedMessages() {
  try {
    const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(-MAX_SAVED_MESSAGES) as ChatMessage[] : [];
  } catch {
    return [];
  }
}

function uniqueReferences(references: Array<{ file_name: string; file_path: string; quote: string }>) {
  const seen = new Set<string>();
  return references.filter((ref) => {
    const key = ref.file_path || ref.file_name;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

type UploadCandidate = {
  file: File;
  relativePath: string;
};

type SelectionState = {
  files: UploadCandidate[];
  skipped: number;
  totalBytes: number;
  capped: boolean;
};

type DirectoryPicker = () => Promise<FileSystemDirectoryHandle>;
type DirectoryHandleWithEntries = FileSystemDirectoryHandle & {
  entries: () => AsyncIterable<[string, FileSystemHandle]>;
};

function extname(filename: string) {
  const index = filename.lastIndexOf('.');
  return index >= 0 ? filename.slice(index).toLowerCase() : '';
}

function pathHasSkippedDir(relativePath: string) {
  return relativePath.replaceAll('\\', '/').split('/').some((part) => SKIP_DIRS.has(part));
}

function canAcceptFile(file: File, relativePath: string, state: SelectionState) {
  if (pathHasSkippedDir(relativePath)) return false;
  if (!SUPPORTED_EXTS.has(extname(file.name))) return false;
  if (file.size > MAX_BROWSER_FILE_BYTES) return false;
  if (state.files.length >= MAX_BROWSER_FILES || state.totalBytes + file.size > MAX_BROWSER_TOTAL_BYTES) {
    state.capped = true;
    return false;
  }
  return true;
}

function skippedCount(result: { skipped_files?: Array<{ count?: number }>; skipped?: Record<string, number> }) {
  if (Array.isArray(result.skipped_files)) {
    return result.skipped_files.reduce((total, item) => total + (item.count ?? 1), 0);
  }
  if (result.skipped) {
    return Object.values(result.skipped).reduce((total, count) => total + count, 0);
  }
  return 0;
}

async function walkDirectory(handle: FileSystemDirectoryHandle, prefix: string, state: SelectionState) {
  for await (const [name, child] of (handle as DirectoryHandleWithEntries).entries()) {
    if (state.capped) break;
    const relativePath = prefix ? `${prefix}/${name}` : name;
    if (child.kind === 'directory') {
      if (!SKIP_DIRS.has(name)) await walkDirectory(child as FileSystemDirectoryHandle, relativePath, state);
      continue;
    }
    const file = await (child as FileSystemFileHandle).getFile();
    if (canAcceptFile(file, relativePath, state)) {
      state.files.push({ file, relativePath });
      state.totalBytes += file.size;
    } else {
      state.skipped += 1;
    }
  }
}

export function KnowledgePage() {
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [vaultPath, setVaultPath] = useState(DEFAULT_VAULT);
  const [includeSyncNotes, setIncludeSyncNotes] = useState(false);
  const [replaceOnUpload, setReplaceOnUpload] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [indexJob, setIndexJob] = useState<KnowledgeIndexJob | null>(null);
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadSavedMessages());
  const [expandedReferenceIds, setExpandedReferenceIds] = useState<Record<string, boolean>>({});
  const [knowledgeFiles, setKnowledgeFiles] = useState<KnowledgeFileItem[]>([]);
  const [knowledgeFilesTotal, setKnowledgeFilesTotal] = useState(0);
  const [fileQuery, setFileQuery] = useState('');
  const [copiedPath, setCopiedPath] = useState('');

  async function refresh() {
    try {
      setStats(await getKnowledgeStats());
    } catch (error) {
      setNotice(`读取知识库状态失败：${String(error)}`);
    }
  }

  const refreshKnowledgeFiles = useCallback(async (query: string) => {
    try {
      const result = await listKnowledgeFiles(query, 100);
      setKnowledgeFiles(result.items);
      setKnowledgeFilesTotal(result.total);
    } catch (error) {
      setNotice(`读取知识库文件目录失败：${String(error)}`);
    }
  }, []);

  useEffect(() => {
    refresh();
    refreshKnowledgeFiles('');
  }, [refreshKnowledgeFiles]);

  useEffect(() => {
    window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages.slice(-MAX_SAVED_MESSAGES)));
  }, [messages]);

  async function runIndex(clearExisting: boolean) {
    setBusy(true);
    setNotice('');
    setIndexJob(null);
    try {
      const started = await startVaultIndexJob(vaultPath, clearExisting, includeSyncNotes);
      setIndexJob(started);
      setNotice('索引任务已启动，正在扫描本地路径...');
      let current = started;
      while (current.status === 'queued' || current.status === 'running') {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        current = await getVaultIndexJob(started.job_id);
        setIndexJob(current);
      }
      if (current.status === 'failed') {
        throw new Error(current.error || '索引任务失败');
      }
      const result = current.result;
      if (!result) throw new Error('索引任务没有返回结果');
      setStats(result.stats);
      await refreshKnowledgeFiles(fileQuery);
      setNotice(`本地路径索引完成：新增 ${result.indexed_files} 个文件，跳过 ${skippedCount(result)} 个。`);
    } catch (error) {
      setNotice(`本地路径索引失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function runClear() {
    setBusy(true);
    setNotice('');
    try {
      await clearKnowledge();
      await refresh();
      setNotice('知识库已清空。');
    } catch (error) {
      setNotice(`清空失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  function clearChatHistory() {
    setMessages([]);
    setExpandedReferenceIds({});
    window.localStorage.removeItem(CHAT_STORAGE_KEY);
  }

  async function uploadCandidates(files: UploadCandidate[], skippedBeforeUpload: number, capped: boolean) {
    if (!files.length) {
      setNotice('没有找到可安全上传的文件。已跳过系统目录、超大文件和暂不支持的格式。');
      return;
    }
    setBusy(true);
    setNotice(`准备上传 ${files.length} 个文件，正在建立索引...`);
    try {
      const payload: KnowledgeUploadFile[] = files.map((item) => ({ file: item.file, relativePath: item.relativePath }));
      const result = await uploadKnowledgeFiles(payload, replaceOnUpload, 'browser-folder-safe');
      setStats(result.stats);
      await refreshKnowledgeFiles(fileQuery);
      const cappedText = capped ? '已达到浏览器安全上限，大型 Vault 请改用“索引本地路径”。' : '';
      setNotice(`文件夹安全索引完成：新增 ${result.indexed_files} 个文件，前置跳过 ${skippedBeforeUpload} 个，后端跳过 ${skippedCount(result)} 个。${cappedText}`);
    } catch (error) {
      setNotice(`文件夹上传索引失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function chooseFolderSafely() {
    const picker = (window as unknown as { showDirectoryPicker?: DirectoryPicker }).showDirectoryPicker;
    if (!picker) {
      folderInputRef.current?.click();
      return;
    }
    try {
      const directory = await picker();
      const state: SelectionState = { files: [], skipped: 0, totalBytes: 0, capped: false };
      await walkDirectory(directory, directory.name, state);
      await uploadCandidates(state.files, state.skipped, state.capped);
    } catch (error) {
      if (!String(error).includes('AbortError')) setNotice(`读取文件夹失败：${String(error)}`);
    }
  }

  async function onFolderUpload(event: ChangeEvent<HTMLInputElement>) {
    const fileList = event.target.files;
    event.target.value = '';
    if (!fileList?.length) return;

    const state: SelectionState = { files: [], skipped: 0, totalBytes: 0, capped: false };
    for (let index = 0; index < fileList.length; index += 1) {
      if (state.capped) break;
      const file = fileList.item(index);
      if (!file) continue;
      const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
      if (canAcceptFile(file, relativePath, state)) {
        state.files.push({ file, relativePath });
        state.totalBytes += file.size;
      } else {
        state.skipped += 1;
      }
    }
    await uploadCandidates(state.files, state.skipped, state.capped);
  }

  async function ask() {
    const text = question.trim();
    if (!text || busy) return;
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: text };
    setMessages((items) => [...items, userMessage]);
    setQuestion('');
    setBusy(true);
    try {
      const result = await askKnowledge(text);
      setMessages((items) => [
        ...items,
        { id: crypto.randomUUID(), role: 'assistant', content: result.answer, references: result.references },
      ]);
    } catch (error) {
      setMessages((items) => [...items, { id: crypto.randomUUID(), role: 'assistant', content: `问答失败：${String(error)}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function copyPath(path: string) {
    await navigator.clipboard.writeText(path);
    setCopiedPath(path);
    window.setTimeout(() => setCopiedPath(''), 1500);
  }

  return (
    <main className="min-h-screen bg-[#0A0A0A] px-6 pb-20 pt-28 md:px-12">
      <div className="mx-auto max-w-[1320px]">
        <div className="mb-8">
          <span className="mb-4 block text-xs font-medium uppercase tracking-[0.3em] text-zinc-500">Architecture Brain</span>
          <h1 className="mb-4 text-3xl font-bold tracking-tight text-white md:text-5xl">设计知识库</h1>
          <p className="max-w-3xl text-sm leading-7 text-zinc-400">读取本地 Obsidian、案例和项目资料，提供带来源引用的对话式问答，并为项目技术复用卡提供依据。</p>
        </div>

        {notice && (
          <div className="mb-5 rounded-lg border border-[#333333] bg-[#111111] p-4 text-sm text-zinc-300">
            {busy && <Loader2 size={14} className="mr-2 inline animate-spin" />}
            {notice}
          </div>
        )}

        {indexJob && (
          <section className="mb-5 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-emerald-100">本地路径索引进度</div>
              <div className="rounded-full border border-emerald-400/20 px-3 py-1 text-xs text-emerald-200">
                {indexJob.status === 'succeeded' ? '已完成' : indexJob.status === 'failed' ? '失败' : '进行中'}
              </div>
            </div>
            <div className="mb-3 h-2 overflow-hidden rounded-full bg-[#0E0E0E]">
              <div
                className="h-full bg-emerald-400 transition-all"
                style={{ width: `${indexJob.total_candidates ? Math.min(100, Math.round((indexJob.processed / indexJob.total_candidates) * 100)) : 5}%` }}
              />
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs text-zinc-300 md:grid-cols-4">
              <div className="rounded-lg bg-[#111111] p-3">候选文件：{indexJob.total_candidates}</div>
              <div className="rounded-lg bg-[#111111] p-3">已处理：{indexJob.processed}</div>
              <div className="rounded-lg bg-[#111111] p-3">已索引：{indexJob.indexed_files}</div>
              <div className="rounded-lg bg-[#111111] p-3">已跳过：{indexJob.skipped_files}</div>
            </div>
            {indexJob.current_file && (
              <div className="mt-3 truncate rounded-lg bg-[#111111] p-3 text-xs text-zinc-500">
                当前文件：{indexJob.current_file}
              </div>
            )}
          </section>
        )}

        <section className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
          {[
            ['总文件', stats?.total_files ?? 0],
            ['Markdown', stats?.markdown_files ?? 0],
            ['PDF/Word/Excel', stats?.pdf_docx_xlsx_files ?? 0],
            ['图片', stats?.image_files ?? 0],
            ['双链', stats?.link_count ?? 0],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg border border-[#333333] bg-[#111111] p-4">
              <div className="text-2xl font-semibold text-white">{value}</div>
              <div className="text-xs text-zinc-500">{label}</div>
            </div>
          ))}
        </section>

        <section className="mb-6 rounded-lg border border-[#333333] bg-[#111111] p-5">
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <FolderOpen size={17} className="text-emerald-300" />
            知识库管理
          </div>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.1fr_0.9fr]">
            <div>
              <label className="mb-2 block text-xs text-zinc-500">本地路径扫描，推荐用于大型 Obsidian Vault</label>
              <input value={vaultPath} onChange={(event) => setVaultPath(event.target.value)} className="mb-3 w-full rounded-lg border border-[#333333] bg-[#0E0E0E] px-3 py-3 text-sm text-zinc-200 outline-none" />
              <div className="flex flex-wrap gap-2">
                <button disabled={busy} onClick={() => runIndex(false)} className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-black">
                  索引本地路径
                </button>
                <button disabled={busy} onClick={() => runIndex(true)} className="rounded-lg border border-[#333333] px-4 py-2 text-sm text-zinc-300">
                  重建索引
                </button>
                <button disabled={busy} onClick={runClear} className="inline-flex items-center gap-2 rounded-lg border border-red-500/30 px-4 py-2 text-sm text-red-300">
                  <Trash2 size={15} />
                  清空
                </button>
              </div>
            </div>
            <div>
              <label className="mb-4 flex items-center gap-2 text-xs text-zinc-400">
                <input type="checkbox" checked={replaceOnUpload} onChange={(event) => setReplaceOnUpload(event.target.checked)} className="h-4 w-4 accent-emerald-400" />
                浏览器上传前替换当前知识库索引
              </label>
              <label className="mb-4 flex items-center gap-2 text-xs text-zinc-400">
                <input type="checkbox" checked={includeSyncNotes} onChange={(event) => setIncludeSyncNotes(event.target.checked)} className="h-4 w-4 accent-emerald-400" />
                本地路径扫描包含“笔记同步助手”
              </label>
              <div className="mb-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs leading-6 text-emerald-100/80">
                <ShieldCheck size={15} className="mr-2 inline text-emerald-300" />
                点选文件夹会限制数量、体积并跳过系统目录，避免浏览器因一次性读取整个 Vault 而崩溃。
              </div>
              <input ref={folderInputRef} type="file" multiple className="hidden" onChange={onFolderUpload} {...({ webkitdirectory: '', directory: '' } as Record<string, string>)} />
              <button disabled={busy} onClick={chooseFolderSafely} className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-white px-4 py-3 text-sm font-semibold text-black">
                <UploadCloud size={16} />
                安全点选文件夹
              </button>
              <p className="mt-3 text-xs leading-6 text-zinc-500">当前安全上限：最多 {MAX_BROWSER_FILES} 个文件、总量 120MB、单文件 25MB。大型 Vault 请优先使用左侧路径扫描。</p>
            </div>
          </div>
        </section>

        <section className="mb-6 rounded-lg border border-[#333333] bg-[#111111] p-5">
          <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <FolderOpen size={17} className="text-emerald-300" />
                知识库文件目录
              </div>
              <p className="mt-1 text-xs text-zinc-500">
                展示知识库当前索引记录里的本地路径。这里只是本地资料索引，不会改变你的原始文件。
              </p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                value={fileQuery}
                onChange={(event) => setFileQuery(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && refreshKnowledgeFiles(fileQuery)}
                placeholder="搜索文件名或本地路径"
                className="min-h-10 w-full rounded-lg border border-[#333333] bg-[#0E0E0E] px-3 text-sm text-zinc-200 outline-none focus:border-emerald-400/50 sm:w-72"
              />
              <button
                disabled={busy}
                onClick={() => refreshKnowledgeFiles(fileQuery)}
                className="rounded-lg border border-[#333333] px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600 disabled:opacity-50"
              >
                搜索
              </button>
            </div>
          </div>
          <div className="mb-3 text-xs text-zinc-500">
            显示 {knowledgeFiles.length} / {knowledgeFilesTotal} 个索引文件
          </div>
          <div className="max-h-[360px] space-y-2 overflow-y-auto pr-1">
            {knowledgeFiles.map((file) => (
              <div key={file.id} className="rounded-lg border border-white/10 bg-[#171717] p-3">
                <div className="mb-2 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-white">{file.filename}</div>
                    <div className="mt-1 text-xs text-zinc-500">
                      {file.filetype || 'file'} · {(file.filesize / 1024).toFixed(1)}KB
                    </div>
                  </div>
                  <button
                    onClick={() => copyPath(file.filepath)}
                    className="inline-flex w-fit items-center gap-1 rounded-md border border-[#333333] px-2 py-1 text-xs text-zinc-300 hover:border-emerald-400/50 hover:text-emerald-100"
                  >
                    <Clipboard size={13} />
                    {copiedPath === file.filepath ? '已复制' : '复制路径'}
                  </button>
                </div>
                <div className="break-all rounded-md bg-[#0E0E0E] p-2 text-xs leading-5 text-zinc-500">
                  {file.filepath}
                </div>
              </div>
            ))}
            {!knowledgeFiles.length && (
              <div className="rounded-lg border border-dashed border-[#333333] p-6 text-center text-sm text-zinc-500">
                暂无文件目录。请先索引本地路径或上传知识库资料。
              </div>
            )}
          </div>
        </section>

        <section className="grid grid-cols-1 gap-5 lg:grid-cols-[0.34fr_1fr]">
          <div className="rounded-lg border border-[#333333] bg-[#111111] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <Brain size={16} className="text-emerald-300" />
                对话历史
              </div>
              <button
                disabled={!messages.length}
                onClick={clearChatHistory}
                className="rounded-md p-1.5 text-zinc-500 hover:bg-red-500/10 hover:text-red-200 disabled:opacity-30"
                title="清空对话历史"
              >
                <Trash2 size={14} />
              </button>
            </div>
            <div className="space-y-2">
              {messages.filter((item) => item.role === 'user').map((item, index) => (
                <button key={item.id} className="block w-full truncate rounded-lg bg-[#171717] p-3 text-left text-sm text-zinc-300">
                  对话 {index + 1}：{item.content}
                </button>
              ))}
              {!messages.length && <p className="text-sm text-zinc-500">暂无对话。</p>}
            </div>
          </div>

          <div className="flex min-h-[620px] flex-col rounded-lg border border-[#333333] bg-[#111111]">
            <div className="flex-1 space-y-4 overflow-y-auto p-5">
              {!messages.length && (
                <div className="flex h-full min-h-[320px] items-center justify-center text-center">
                  <div>
                    <Search size={36} className="mx-auto mb-4 text-zinc-600" />
                    <p className="text-sm text-zinc-500">输入问题开始知识库问答</p>
                    <p className="mt-2 text-xs text-zinc-600">回答会附带本地资料来源，便于项目经理回查。</p>
                  </div>
                </div>
              )}
              {messages.map((item) => (
                <div key={item.id} className={`flex ${item.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[86%] rounded-lg p-4 ${item.role === 'user' ? 'bg-amber-400 text-black' : 'border border-[#333333] bg-[#171717] text-zinc-300'}`}>
                    <p className="whitespace-pre-wrap text-sm leading-7">{item.content}</p>
                    {item.references?.length ? (
                      <div className="mt-3 border-t border-[#333333] pt-3">
                        <button
                          onClick={() => setExpandedReferenceIds((current) => ({ ...current, [item.id]: !current[item.id] }))}
                          className="mb-2 inline-flex items-center gap-1 rounded-md border border-[#333333] px-2 py-1 text-xs text-zinc-400 hover:border-zinc-600 hover:text-white"
                        >
                          引用来源 {uniqueReferences(item.references).length} 个
                          {expandedReferenceIds[item.id] ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                        </button>
                        <div className="space-y-1.5">
                          {uniqueReferences(item.references).slice(0, expandedReferenceIds[item.id] ? undefined : 3).map((ref) => (
                            <div key={`${ref.file_path}-${ref.file_name}`} className="rounded-md bg-[#0E0E0E] px-2 py-1.5 text-xs text-zinc-500">
                              <div className="truncate text-zinc-300">{ref.file_name}</div>
                              <div className="truncate">{ref.file_path}</div>
                              {expandedReferenceIds[item.id] && ref.quote && (
                                <p className="mt-1 line-clamp-2 leading-5 text-zinc-500">{ref.quote}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
            <div className="border-t border-[#333333] p-4">
              <div className="flex gap-3">
                <input
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => event.key === 'Enter' && ask()}
                  placeholder="输入问题，如：这个项目启动阶段有哪些技术风险？"
                  className="flex-1 rounded-lg border border-[#333333] bg-[#0E0E0E] px-4 py-3 text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-amber-400/60"
                />
                <button disabled={busy || !question.trim()} onClick={ask} className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-4 py-3 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-50">
                  {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

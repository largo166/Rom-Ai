import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { Archive, Check, ChevronDown, ChevronUp, Database, FolderInput, Loader2, RefreshCw, Trash2, Upload, Wand2, Sparkles } from 'lucide-react';
import { ArchiveWizard } from '../components/inbox/ArchiveWizard';
import { ArchivePlanPreview } from '../components/inbox/ArchivePlanPreview';
import { RecommendationPanel } from '../components/knowledge/RecommendationPanel';
import {
  applyInbox,
  applyInboxRecommendations,
  deleteInboxItem,
  deleteInboxItems,
  generateBatchArchivePlan,
  getInboxBatchAdvice,
  getInboxScanJob,
  getLatestInboxScanJob,
  listInboxItems,
  pickInboxFolder,
  listProjects,
  recommendInbox,
  startInboxScan,
  uploadInboxFiles,
  type InboxItem,
  type InboxBatchAdvice,
  type InboxScanJob,
  type ProjectSummary,
  type BatchArchivePlanResponse,
} from '../lib/projectsApi';

const columns = ['可直接确认', '未归属项目', '重复文件', '需审核', '已归档', '已进入知识库'];
const quickDeleteColumns = new Set(['可直接确认', '未归属项目', '重复文件']);
const materialTypes = ['项目基础资料', '技术条件', '会议资料', '设计过程', '参考案例', '交付成果', '审核反馈', '压缩包与杂项', '设计源文件'];
const SCAN_JOB_STORAGE_KEY = 'rom-ai-inbox-scan-job-id';

function confidenceText(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function InboxPage() {
  const [params] = useSearchParams();
  const presetProjectId = params.get('project_id') ?? '';
  const [items, setItems] = useState<InboxItem[]>([]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [scanPath, setScanPath] = useState('');
  const [projectById, setProjectById] = useState<Record<string, string>>({});
  const [filenameById, setFilenameById] = useState<Record<string, string>>({});
  const [typeById, setTypeById] = useState<Record<string, string>>({});
  const [knowledgeById, setKnowledgeById] = useState<Record<string, boolean>>({});
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({});
  const [batchAdvice, setBatchAdvice] = useState<InboxBatchAdvice | null>(null);
  const [scanJob, setScanJob] = useState<InboxScanJob | null>(null);
  const [showArchiveWizard, setShowArchiveWizard] = useState(false);
  const [showPlanPreview, setShowPlanPreview] = useState(false);
  const [archivePlan, setArchivePlan] = useState<BatchArchivePlanResponse | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planExecuting, setPlanExecuting] = useState(false);
  const [archiveResult, setArchiveResult] = useState<{ projectId: string; fileNames: string } | null>(null);
  const scanRunning = scanJob?.status === 'queued' || scanJob?.status === 'running';

  async function load() {
    setBusy(true);
    setMessage('');
    try {
      const [nextItems, nextProjects] = await Promise.all([listInboxItems(), listProjects()]);
      setItems(nextItems);
      setProjects(nextProjects);
    } catch (error) {
      setMessage(`读取收件箱失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function refreshBatchAdvice(itemIds: string[] = []) {
    const advice = await getInboxBatchAdvice(itemIds);
    setBatchAdvice(advice);
    setSelectedIds((current) => {
      const next = { ...current };
      advice.recommended_item_ids.forEach((id) => {
        next[id] = true;
      });
      advice.duplicates.forEach((item) => {
        next[item.id] = false;
      });
      advice.needs_review.forEach((item) => {
        next[item.id] = false;
      });
      return next;
    });
    return advice;
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function restoreScanJob() {
      try {
        const savedJobId = window.localStorage.getItem(SCAN_JOB_STORAGE_KEY);
        const job = savedJobId ? await getInboxScanJob(savedJobId) : await getLatestInboxScanJob();
        if (!cancelled && job) setScanJob(job);
      } catch {
        window.localStorage.removeItem(SCAN_JOB_STORAGE_KEY);
      }
    }
    restoreScanJob();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!scanJob || (scanJob.status !== 'queued' && scanJob.status !== 'running')) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const current = await getInboxScanJob(scanJob.job_id);
        if (cancelled) return;
        setScanJob(current);
        if (current.status === 'succeeded') {
          if (current.result?.batch_advice) setBatchAdvice(current.result.batch_advice);
          await load();
          setMessage(`扫描完成，导入 ${current.imported_files} 个文件，并已生成整体归档建议。`);
          window.localStorage.removeItem(SCAN_JOB_STORAGE_KEY);
        }
        if (current.status === 'failed') {
          setMessage(`扫描失败：${current.error || '任务失败'}`);
          window.localStorage.removeItem(SCAN_JOB_STORAGE_KEY);
        }
      } catch (error) {
        if (!cancelled) setMessage(`读取扫描进度失败：${String(error)}`);
      }
    }, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [scanJob]);

  useEffect(() => {
    const nextProjects: Record<string, string> = {};
    const nextNames: Record<string, string> = {};
    const nextTypes: Record<string, string> = {};
    const nextKnowledge: Record<string, boolean> = {};
    items.forEach((item) => {
      nextProjects[item.id] = presetProjectId || item.project_id || '';
      nextNames[item.id] = item.final_filename || item.suggested_filename || item.original_filename;
      nextTypes[item.id] = item.material_type;
      nextKnowledge[item.id] = item.suggest_knowledge;
    });
    setProjectById((current) => ({ ...nextProjects, ...current }));
    setFilenameById((current) => ({ ...nextNames, ...current }));
    setTypeById((current) => ({ ...nextTypes, ...current }));
    setKnowledgeById((current) => ({ ...nextKnowledge, ...current }));
    setSelectedIds((current) => {
      const nextSelected: Record<string, boolean> = {};
      items.forEach((item) => {
        nextSelected[item.id] = current[item.id] ?? item.archive_group === '可直接确认';
      });
      return nextSelected;
    });
  }, [items, presetProjectId]);

  const grouped = useMemo(() => {
    const result: Record<string, InboxItem[]> = Object.fromEntries(columns.map((column) => [column, []]));
    items.forEach((item) => {
      const group = item.archive_group || item.status;
      const key = columns.includes(group) ? group : item.needs_review ? '需审核' : '可直接确认';
      result[key].push(item);
    });
    return result;
  }, [items]);

  const selectedItems = items.filter((item) => selectedIds[item.id]);
  const selectedActionable = selectedItems.filter((item) => item.archive_group !== '重复文件' && item.recommended_action !== '需人工确认');
  const selectedKnowledgeCount = selectedActionable.filter((item) => item.suggest_knowledge).length;
  const selectedDuplicateCount = selectedItems.filter((item) => item.archive_group === '重复文件').length;
  const scanProgressPercent = scanJob?.total_candidates
    ? Math.min(100, Math.round((scanJob.processed / scanJob.total_candidates) * 100))
    : scanRunning
      ? 8
      : 0;

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setMessage('正在上传并识别文件...');
    try {
      const imported = await uploadInboxFiles(Array.from(files));
      await load();
      await refreshBatchAdvice(imported.map((item) => item.id));
      setMessage('文件已进入收件箱，并已生成整体归档建议。');
    } catch (error) {
      setMessage(`上传失败：${String(error)}`);
      setBusy(false);
    }
  }

  async function onScanDownloads() {
    setMessage('扫描任务已启动，正在处理 Downloads 文件...');
    try {
      const started = await startInboxScan('', 'Downloads', 7);
      setScanJob(started);
      window.localStorage.setItem(SCAN_JOB_STORAGE_KEY, started.job_id);
    } catch (error) {
      setMessage(`扫描失败：${String(error)}`);
    }
  }

  async function onPickFolder() {
    setBusy(true);
    setMessage('正在打开本机文件夹选择器...');
    try {
      const result = await pickInboxFolder();
      if (result.cancelled || !result.path) {
        setMessage('已取消选择文件夹。');
        return;
      }
      setScanPath(result.path);
      setMessage('已选择文件夹路径。确认后点击“扫描目录”开始复制并识别文件。');
    } catch (error) {
      setMessage(`选择文件夹失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function onScanPath() {
    if (!scanPath.trim()) {
      setMessage('请先填写要扫描的本地目录。');
      return;
    }
    setMessage('扫描任务已启动，正在处理本地目录...');
    try {
      const started = await startInboxScan(scanPath.trim(), '手动目录', 0);
      setScanJob(started);
      window.localStorage.setItem(SCAN_JOB_STORAGE_KEY, started.job_id);
    } catch (error) {
      setMessage(`扫描失败：${String(error)}`);
    }
  }

  async function onRecommend() {
    setBusy(true);
    setMessage('正在重新计算整体归档建议...');
    try {
      await recommendInbox();
      await load();
      await refreshBatchAdvice();
      setMessage('整体建议已更新。可批量执行的文件已自动勾选。');
    } catch (error) {
      setMessage(`推荐失败：${String(error)}`);
      setBusy(false);
    }
  }

  async function onDeleteSelected() {
    const ids = Object.keys(selectedIds).filter((id) => selectedIds[id]);
    if (!ids.length) {
      setMessage('请先选择要删除的收件箱文件。');
      return;
    }
    setBusy(true);
    setMessage('正在删除收件箱临时文件...');
    try {
      const result = await deleteInboxItems(ids);
      await load();
      setMessage(`已删除 ${result.deleted} 个收件箱文件，原始来源和已归档资料不会受影响。`);
    } catch (error) {
      setMessage(`删除失败：${String(error)}`);
      setBusy(false);
    }
  }

  async function onDeleteGroup(column: string) {
    const ids = (grouped[column] ?? []).map((item) => item.id);
    if (!ids.length) {
      setMessage(`${column}暂无可删除文件。`);
      return;
    }
    setBusy(true);
    setMessage(`正在删除${column}里的收件箱临时文件...`);
    try {
      const result = await deleteInboxItems(ids);
      await load();
      setMessage(`已删除${column} ${result.deleted} 个文件，原始来源和已归档资料不会受影响。`);
    } catch (error) {
      setMessage(`删除失败：${String(error)}`);
      setBusy(false);
    }
  }

  async function onDeleteOne(item: InboxItem) {
    setBusy(true);
    setMessage('正在删除收件箱临时文件...');
    try {
      await deleteInboxItem(item.id);
      await load();
      setMessage(`已删除 ${item.original_filename}。`);
    } catch (error) {
      setMessage(`删除失败：${String(error)}`);
      setBusy(false);
    }
  }

  async function onApplyRecommendations() {
    const ids = batchAdvice?.recommended_item_ids.length ? batchAdvice.recommended_item_ids : Object.keys(selectedIds).filter((id) => selectedIds[id]);
    if (!ids.length) {
      setMessage('暂无可按建议归档的文件，请先生成整体建议或处理需审核文件。');
      return;
    }
    setBusy(true);
    setMessage('正在按整体建议批量归档...');
    try {
      const result = await applyInboxRecommendations(ids);
      await load();
      await refreshBatchAdvice();
      setMessage(`批量完成：归档 ${result.files.length} 个，创建项目 ${result.created_project_count} 个，跳过 ${result.skipped_count} 个。`);
      // 归档成功后触发知识推荐
      const firstProjectId = batchAdvice?.project_groups?.[0]?.project_id || '';
      const fileNames = items.filter((i) => ids.includes(i.id)).map((i) => i.original_filename).join(',');
      if (firstProjectId) setArchiveResult({ projectId: firstProjectId, fileNames });
    } catch (error) {
      setMessage(`批量归档失败：${String(error)}`);
      setBusy(false);
    }
  }

  async function onBuildBatchAdvice() {
    setBusy(true);
    setMessage('正在读取文件内容、比对项目库和知识库，并生成整体建议...');
    try {
      const advice = await refreshBatchAdvice();
      setMessage(`整体建议已生成：建议归档 ${advice.action_counts['归档文件'] ?? 0} 个，入知识库 ${advice.action_counts['入知识库'] ?? 0} 个，跳过重复 ${advice.action_counts['跳过重复'] ?? 0} 个。`);
    } catch (error) {
      setMessage(`生成整体建议失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function onGenerateArchivePlan() {
    const itemIds = items.length > 0 ? items.map((item) => item.id) : undefined;
    setPlanLoading(true);
    setPlanExecuting(false);
    setArchivePlan(null);
    setShowPlanPreview(true);
    setMessage('');
    try {
      const plan = await generateBatchArchivePlan({ item_ids: itemIds, format_markdown: true });
      setArchivePlan(plan);
    } catch (error) {
      setMessage(`生成归档方案失败：${String(error)}`);
      setShowPlanPreview(false);
    } finally {
      setPlanLoading(false);
    }
  }

  async function onConfirmArchivePlan() {
    if (!archivePlan) return;
    const itemIds = archivePlan.groups
      .flatMap((group) => group.files)
      .filter((file) => file.action !== 'skip')
      .map((file) => file.id);
    if (!itemIds.length) {
      setMessage('没有可执行的归档文件。');
      return;
    }
    setPlanExecuting(true);
    setMessage('正在执行批量归档...');
    try {
      const result = await applyInboxRecommendations(itemIds);
      setShowPlanPreview(false);
      setArchivePlan(null);
      await load();
      await refreshBatchAdvice();
      setMessage(`归档完成：归档 ${result.files.length} 个，创建项目 ${result.created_project_count} 个，跳过 ${result.skipped_count} 个。`);
      // 归档成功后触发知识推荐
      const firstProjectId = batchAdvice?.project_groups?.[0]?.project_id || '';
      const fileNames = archivePlan?.groups.flatMap((g) => g.files).map((f) => f.original_name).join(',') || '';
      if (firstProjectId) setArchiveResult({ projectId: firstProjectId, fileNames });
    } catch (error) {
      setMessage(`归档执行失败：${String(error)}`);
    } finally {
      setPlanExecuting(false);
    }
  }

  function onCancelArchivePlan() {
    setShowPlanPreview(false);
    if (!planExecuting) {
      setArchivePlan(null);
    }
  }

  const adviceCounts = batchAdvice?.action_counts ?? {};

  async function onApply(item: InboxItem, createProject = false) {
    setBusy(true);
    setMessage('正在归档文件...');
    const selectedProjectId = projectById[item.id] || item.project_id;
    try {
      await applyInbox({
        item_ids: [item.id],
        project_id: createProject ? '' : selectedProjectId,
        project: createProject
          ? {
              name: item.suggested_project_name || '未命名项目',
              city: item.suggested_city,
              project_type: item.suggested_project_type || '住宅',
              phase: item.suggested_phase || '待确认',
              description: `由文件收件箱根据 ${item.original_filename} 创建`,
            }
          : undefined,
        final_filename_by_id: { [item.id]: filenameById[item.id] || item.suggested_filename },
        material_type_by_id: { [item.id]: typeById[item.id] || item.material_type },
        enter_knowledge: knowledgeById[item.id] ?? item.suggest_knowledge,
      });
      await load();
      setMessage(createProject ? '已创建新项目并完成入库。' : '文件已归档到项目资料。');
    } catch (error) {
      setMessage(`归档失败：${String(error)}`);
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#0A0A0A] px-6 pb-20 pt-28 md:px-12">
      <div className="mx-auto max-w-[1500px]">
        <div className="mb-6 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <span className="mb-3 block text-xs font-medium uppercase tracking-[0.3em] text-zinc-500">Project Inbox</span>
            <h1 className="mb-2 text-3xl font-bold tracking-tight text-white md:text-5xl">文件收件箱</h1>
            <p className="max-w-3xl text-sm leading-7 text-zinc-400">
              先收文件，再识别项目。系统会建议归属项目、资料类型、规范文件名和知识库入库状态，确认后再归档。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-300">
              <Upload size={16} />
              上传文件
              <input type="file" multiple className="hidden" onChange={(event) => onUpload(event.target.files)} />
            </label>
            <button onClick={onScanDownloads} disabled={busy || scanRunning} className="inline-flex items-center gap-2 rounded-lg border border-[#333333] bg-[#171717] px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600 disabled:opacity-50">
              <FolderInput size={16} />
              扫描 Downloads
            </button>
            <button onClick={load} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-[#333333] bg-[#171717] px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600 disabled:opacity-50">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
              刷新
            </button>
            <button onClick={onRecommend} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-[#333333] bg-[#171717] px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600 disabled:opacity-50">
              <Wand2 size={16} />
              重新推荐
            </button>
            <button onClick={onBuildBatchAdvice} disabled={busy || items.length === 0} className="inline-flex items-center gap-2 rounded-lg border border-amber-400/40 bg-amber-400/10 px-4 py-2 text-sm text-amber-100 hover:border-amber-300 disabled:opacity-50">
              <Wand2 size={16} />
              整体归档建议
            </button>
            <button
              onClick={onGenerateArchivePlan}
              disabled={busy || planLoading || items.length === 0}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
            >
              {planLoading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              智能归档
            </button>
          </div>
        </div>

        <div className="mb-5 rounded-lg border border-white/10 bg-white/5 p-3">
          <div className="flex flex-col gap-2 md:flex-row">
          <button
            onClick={onPickFolder}
            disabled={busy || scanRunning}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
          >
            <FolderInput size={16} />
            选择文件夹
          </button>
          <input
            value={scanPath}
            onChange={(event) => setScanPath(event.target.value)}
            placeholder="或输入本地目录路径，例如 /Users/leslie/Downloads/项目资料"
            className="min-h-10 flex-1 rounded-lg border border-[#333333] bg-[#0E0E0E] px-3 text-sm text-white outline-none focus:border-amber-400/50"
          />
          <button onClick={onScanPath} disabled={busy || scanRunning} className="inline-flex items-center justify-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-black disabled:opacity-50">
            {scanRunning ? <Loader2 size={16} className="animate-spin" /> : <Archive size={16} />}
            {scanRunning ? '扫描中' : '扫描目录'}
          </button>
          </div>
        </div>

        {message && <div className="mb-5 rounded-lg border border-[#333333] bg-[#171717] p-3 text-sm text-zinc-300">{message}</div>}

        {/* 归档完成后知识推荐 */}
        {archiveResult && archiveResult.projectId && (
          <div className="mb-5">
            <RecommendationPanel
              projectId={archiveResult.projectId}
              trigger="archive"
              options={archiveResult.fileNames ? { file_names: archiveResult.fileNames } : undefined}
            />
          </div>
        )}

        <section className="mb-5 rounded-lg border border-amber-400/25 bg-[#15120A] p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <Archive size={18} className="text-amber-400" />
                一键归档向导
              </h2>
              <p className="mt-1 text-sm text-zinc-400">
                选择本地文件夹，系统自动分层扫描、规则分类、生成归档方案，确认后复制到新结构并自动入库。
              </p>
            </div>
            <button
              onClick={() => setShowArchiveWizard((v) => !v)}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-300"
            >
              {showArchiveWizard ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              {showArchiveWizard ? '收起向导' : '打开向导'}
            </button>
          </div>
          {showArchiveWizard && (
            <div className="mt-4">
              <ArchiveWizard />
            </div>
          )}
        </section>

        {scanJob && (
          <section className="mb-5 rounded-lg border border-blue-400/20 bg-blue-400/5 p-4">
            <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-sm font-semibold text-white">扫描目录进度</h2>
                <p className="mt-1 text-xs text-zinc-400">
                  {scanJob.step || '准备中'}
                  {scanJob.current_file ? `：${scanJob.current_file}` : ''}
                </p>
              </div>
              <span className="rounded-full bg-white/10 px-2 py-1 text-xs text-zinc-300">
                {scanJob.status === 'succeeded' ? '已完成' : scanJob.status === 'failed' ? '失败' : '进行中'}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-black/40">
              <div className="h-full rounded-full bg-blue-300 transition-all" style={{ width: `${scanProgressPercent}%` }} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-zinc-400 md:grid-cols-5">
              <div>已处理 <span className="text-white">{scanJob.processed}</span> / {scanJob.total_candidates}</div>
              <div>已导入 <span className="text-white">{scanJob.imported_files}</span></div>
              <div>不支持 <span className="text-white">{scanJob.unsupported_files}</span></div>
              <div>过期跳过 <span className="text-white">{scanJob.old_files}</span></div>
              <div>失败 <span className="text-white">{scanJob.failed_files}</span></div>
            </div>
            {scanJob.error && <div className="mt-3 text-xs text-red-200">{scanJob.error}</div>}
          </section>
        )}

        <section className="mb-5 rounded-lg border border-amber-400/25 bg-[#15120A] p-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 flex-1">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold text-white">整体归档建议</h2>
                {batchAdvice && <span className="rounded-full bg-amber-400/15 px-2 py-0.5 text-xs text-amber-100">{batchAdvice.total_files} 个文件已评估</span>}
              </div>
              {batchAdvice ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
                    {[
                      ['建议归档', adviceCounts['归档文件'] ?? 0],
                      ['建议建项目', adviceCounts['创建项目'] ?? 0],
                      ['入知识库', adviceCounts['入知识库'] ?? 0],
                      ['跳过重复', adviceCounts['跳过重复'] ?? 0],
                      ['需审核', adviceCounts['需审核'] ?? 0],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-lg border border-white/10 bg-black/25 p-3">
                        <div className="text-xs text-zinc-500">{label}</div>
                        <div className="mt-1 text-2xl font-semibold text-white">{value}</div>
                      </div>
                    ))}
                  </div>
                  <div className="whitespace-pre-wrap rounded-lg border border-white/10 bg-black/25 p-3 text-sm leading-6 text-zinc-300">
                    {batchAdvice.markdown}
                  </div>
                  {batchAdvice.project_groups.length > 0 && (
                    <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                      {batchAdvice.project_groups.slice(0, 6).map((group) => (
                        <div key={`${group.kind}-${group.project_id || group.project_name}`} className="rounded-lg border border-white/10 bg-black/20 p-3">
                          <div className="mb-1 flex items-center justify-between gap-2">
                            <div className="truncate text-sm font-medium text-white">{group.project_name}</div>
                            <span className="shrink-0 rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-zinc-300">{group.kind === 'new' ? '新项目' : '已有项目'}</span>
                          </div>
                          <div className="text-xs leading-5 text-zinc-400">
                            已归并 {group.file_count} 个文件 · {group.knowledge_count} 个入知识库
                            <br />
                            {group.material_summary}
                            {group.aliases?.length ? (
                              <>
                                <br />
                                来源名：{group.aliases.slice(0, 3).join(' / ')}
                              </>
                            ) : null}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm leading-6 text-zinc-400">
                  扫描或上传后，系统会先读取文件名和可解析内容，自动比对项目库、知识库，再给出一份整体归档方案。
                </p>
              )}
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <button onClick={onBuildBatchAdvice} disabled={busy || items.length === 0} className="inline-flex items-center gap-2 rounded-lg border border-amber-400/40 px-4 py-2 text-sm font-semibold text-amber-100 hover:border-amber-300 disabled:opacity-40">
                <Wand2 size={16} />
                生成整体建议
              </button>
              <button onClick={onApplyRecommendations} disabled={busy || !(batchAdvice?.recommended_item_ids.length || selectedItems.length)} className="inline-flex items-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-40">
                <Check size={16} />
                按建议归档
              </button>
            </div>
          </div>
        </section>

        <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div className="text-xs text-zinc-500">
            已选 {selectedItems.length} 个 · 可归档 {selectedActionable.length} 个 · 入知识库 {selectedKnowledgeCount} 个 · 重复 {selectedDuplicateCount} 个
          </div>
          <button onClick={onDeleteSelected} disabled={busy || selectedItems.length === 0} className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-400/30 px-3 py-2 text-xs text-red-200 hover:border-red-300/60 disabled:opacity-40">
            <Trash2 size={14} />
            删除所选
          </button>
        </div>

        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {columns.map((column) => (
            <div key={column} className="rounded-lg border border-white/10 bg-white/5 p-3">
              <div className="text-xs text-zinc-500">{column}</div>
              <div className="mt-1 text-2xl font-semibold text-white">{grouped[column]?.length ?? 0}</div>
            </div>
          ))}
        </div>

        <div className="grid gap-4 xl:grid-cols-6">
          {columns.map((column) => (
            <section key={column} className="min-h-[320px] rounded-lg border border-white/10 bg-[#111111] p-2.5">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h2 className="flex min-w-0 items-center gap-2 text-sm font-semibold text-white">
                  <span className="truncate">{column}</span>
                  <span className="rounded-full bg-white/10 px-2 py-0.5 text-xs text-zinc-400">{grouped[column]?.length ?? 0}</span>
                </h2>
                {quickDeleteColumns.has(column) && (
                  <button
                    onClick={() => onDeleteGroup(column)}
                    disabled={busy || (grouped[column]?.length ?? 0) === 0}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-red-500/10 hover:text-red-200 disabled:opacity-30"
                    title={`删除${column}`}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
              <div className="space-y-2">
                {(grouped[column] ?? []).map((item) => (
                  <article key={item.id} className="rounded-lg border border-[#333333] bg-[#171717] p-2 text-sm">
                    <div className="mb-1.5 flex items-start gap-2">
                      <input
                        type="checkbox"
                        checked={!!selectedIds[item.id]}
                        onChange={(event) => setSelectedIds((current) => ({ ...current, [item.id]: event.target.checked }))}
                        className="mt-1"
                      />
                      <div className="min-w-0 flex-1 truncate font-medium leading-5 text-white" title={item.original_filename}>{item.original_filename}</div>
                      <button
                        onClick={() => setExpandedIds((current) => ({ ...current, [item.id]: !current[item.id] }))}
                        className="rounded-md p-1 text-zinc-500 hover:bg-white/10 hover:text-white"
                        title={expandedIds[item.id] ? '收起详情' : '展开详情'}
                      >
                        {expandedIds[item.id] ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                      <button onClick={() => onDeleteOne(item)} disabled={busy} className="rounded-md p-1 text-zinc-500 hover:bg-red-500/10 hover:text-red-200 disabled:opacity-40" title="删除收件箱文件">
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <div className="mb-1.5 flex flex-wrap gap-1.5 text-[11px]">
                      <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-amber-200">
                        {item.recommended_action || '待推荐'}
                      </span>
                      <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-zinc-300">
                        {typeById[item.id] ?? item.material_type}
                      </span>
                      {item.archive_group === '重复文件' && (
                        <span className="rounded-full border border-red-400/30 bg-red-400/10 px-2 py-0.5 text-red-200">
                          {item.duplicate_scope === 'project' ? '项目库已存在' : '知识库已存在'}
                        </span>
                      )}
                    </div>
                    <div className="mb-2 text-[11px] leading-4 text-zinc-500">
                      <div className="truncate">项目：{item.suggested_project_name || '未识别'} · {confidenceText(item.confidence)}</div>
                      {item.recommend_knowledge_reason && <div className="line-clamp-1">{item.recommend_knowledge_reason}</div>}
                    </div>
                    {expandedIds[item.id] && (
                      <div className="mb-2 space-y-2 rounded-md bg-[#0A0A0A] p-2">
                        <input
                          value={filenameById[item.id] ?? item.suggested_filename}
                          onChange={(event) => setFilenameById((current) => ({ ...current, [item.id]: event.target.value }))}
                          className="w-full rounded-md border border-[#333333] bg-[#050505] px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-amber-400/50"
                        />
                        <select
                          value={projectById[item.id] ?? item.project_id}
                          onChange={(event) => setProjectById((current) => ({ ...current, [item.id]: event.target.value }))}
                          className="w-full rounded-md border border-[#333333] bg-[#050505] px-2 py-1.5 text-xs text-zinc-200 outline-none"
                        >
                          <option value="">未选择项目</option>
                          {projects.map((project) => (
                            <option key={project.id} value={project.id}>{project.name}</option>
                          ))}
                        </select>
                        <select
                          value={typeById[item.id] ?? item.material_type}
                          onChange={(event) => setTypeById((current) => ({ ...current, [item.id]: event.target.value }))}
                          className="w-full rounded-md border border-[#333333] bg-[#050505] px-2 py-1.5 text-xs text-zinc-200 outline-none"
                        >
                          {materialTypes.map((type) => <option key={type} value={type}>{type}</option>)}
                        </select>
                        <div className="text-xs leading-5 text-zinc-400">
                          <div>阶段：{item.suggested_phase || '待确认'} · 置信度：{confidenceText(item.confidence)}</div>
                          {item.evidence && <div>依据：{item.evidence}</div>}
                        </div>
                        {item.summary && <p className="line-clamp-3 text-xs leading-5 text-zinc-500">{item.summary}</p>}
                        <label className="flex items-center gap-2 text-xs text-zinc-300">
                          <input
                            type="checkbox"
                            checked={knowledgeById[item.id] ?? item.suggest_knowledge}
                            onChange={(event) => setKnowledgeById((current) => ({ ...current, [item.id]: event.target.checked }))}
                          />
                          入知识库
                        </label>
                      </div>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                      <button
                        onClick={() => onApply(item, false)}
                        disabled={busy || !(projectById[item.id] || item.project_id)}
                        className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 text-xs font-semibold text-black disabled:opacity-40"
                      >
                        <Check size={13} />
                        归档
                      </button>
                      {!item.project_id && (
                        <button onClick={() => onApply(item, true)} disabled={busy} className="inline-flex items-center gap-1 rounded-md border border-amber-400/40 px-2 py-1 text-xs font-semibold text-amber-200 disabled:opacity-40">
                          <Database size={13} />
                          创建项目
                        </button>
                      )}
                    </div>
                    {item.project_id && <Link to={`/projects/${item.project_id}`} className="mt-2 block text-xs text-amber-300">打开项目</Link>}
                  </article>
                ))}
                {(grouped[column] ?? []).length === 0 && <div className="rounded-lg border border-dashed border-[#333333] p-6 text-center text-xs text-zinc-600">暂无文件</div>}
              </div>
            </section>
          ))}
        </div>
      </div>

      <ArchivePlanPreview
        open={showPlanPreview}
        plan={archivePlan}
        loading={planLoading}
        executing={planExecuting}
        onConfirm={onConfirmArchivePlan}
        onCancel={onCancelArchivePlan}
      />
    </main>
  );
}

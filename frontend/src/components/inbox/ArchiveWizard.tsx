import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { FolderOpen, FileText, CheckCircle, Undo2, AlertTriangle, Loader2 } from 'lucide-react';
import { getApiBase, pickDesktopFolder } from '@/lib/runtime';

interface ScannedFile {
  path: string;
  name: string;
  ext: string;
  size: number;
  file_type: string;
  category: string;
  confidence: number;
  reason: string;
  needs_ai: boolean;
  target_subdir: string;
}

interface ArchiveItem {
  source: string;
  target: string;
  type: string;
  category: string;
  confidence: number;
  reason: string;
  status: string;
  is_duplicate: boolean;
}

type Step = 'select' | 'scanning' | 'review' | 'confirm' | 'executing' | 'done';

export function ArchiveWizard() {
  const [step, setStep] = useState<Step>('select');
  const [folderPath, setFolderPath] = useState('');
  const [targetBase, setTargetBase] = useState('');
  const [scannedFiles, setScannedFiles] = useState<ScannedFile[]>([]);
  const [planItems, setPlanItems] = useState<ArchiveItem[]>([]);
  const [planId, setPlanId] = useState('');
  const [manifestId, setManifestId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState({ total: 0, ready: 0, conflicts: 0, duplicates: 0 });

  const apiBase = () => `${getApiBase()}/api/inbox`;

  const selectFolder = async () => {
    setError('');
    // 优先使用 Electron 桌面选择器
    if (window.romAI?.pickFolder) {
      try {
        const result = await pickDesktopFolder();
        if (result && !result.cancelled && result.path) {
          setFolderPath(result.path);
          setTargetBase(`${result.path}_archived`);
          await scanFolder(result.path);
        }
        return;
      } catch (e: any) {
        setError(`桌面选择器失败：${e.message || e}，将使用手动输入`);
      }
    }
    // fallback: 手动输入
    const path = window.prompt('请输入要归档的文件夹路径：');
    if (path) {
      setFolderPath(path);
      setTargetBase(`${path}_archived`);
      await scanFolder(path);
    }
  };

  const scanFolder = async (path: string) => {
    setStep('scanning');
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${apiBase()}/archive/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: path })
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || '扫描失败');
        setStep('select');
        return;
      }
      setScannedFiles(data.files);
      setStep('review');
    } catch (e: any) {
      setError(e.message || '网络错误');
      setStep('select');
    } finally {
      setLoading(false);
    }
  };

  const generatePlan = async () => {
    if (!targetBase.trim()) {
      setError('请输入归档目标目录');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${apiBase()}/archive/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_folder: folderPath,
          target_base: targetBase,
          scanned_files: scannedFiles.map(f => ({ path: f.path, name: f.name, ext: f.ext, size: f.size })),
          classifications: scannedFiles.map(f => ({
            file_type: f.file_type,
            category: f.category,
            target_subdir: f.target_subdir,
            suggested_name: f.name,
            confidence: f.confidence,
            reason: f.reason
          }))
        })
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || '方案生成失败');
        return;
      }
      setPlanId(data.plan_id);
      setPlanItems(data.items);
      setStats({
        total: data.total_files,
        ready: data.ready,
        conflicts: data.conflicts,
        duplicates: data.skipped_duplicates
      });
      setStep('confirm');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const executePlan = async () => {
    setStep('executing');
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${apiBase()}/archive/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plan: {
            plan_id: planId,
            source_folder: folderPath,
            target_base: targetBase,
            items: planItems.map(item => ({
              source: item.source,
              target: item.target,
              type: item.type,
              category: item.category,
              confidence: item.confidence,
              reason: item.reason,
              status: item.status,
              is_duplicate: item.is_duplicate
            }))
          }
        })
      });
      const data = await res.json();
      if (data.success) {
        setManifestId(data.manifest_id);
        setStep('done');
      } else {
        setError('执行失败');
        setStep('confirm');
      }
    } catch (e: any) {
      setError(e.message);
      setStep('confirm');
    } finally {
      setLoading(false);
    }
  };

  const undoArchive = async () => {
    if (!manifestId) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${apiBase()}/archive/undo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manifest_id: manifestId })
      });
      const data = await res.json();
      if (data.success) {
        setStep('select');
        setManifestId('');
        setPlanItems([]);
        setPlanId('');
        setScannedFiles([]);
        setFolderPath('');
        setTargetBase('');
      } else {
        setError(`撤销部分失败：${data.errors?.join(', ')}`);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const resetWizard = () => {
    setStep('select');
    setManifestId('');
    setPlanItems([]);
    setPlanId('');
    setScannedFiles([]);
    setFolderPath('');
    setTargetBase('');
    setError('');
  };

  const getConfidenceBadge = (confidence: number) => {
    if (confidence >= 0.8) return <Badge className="bg-green-100 text-green-800 hover:bg-green-100">高置信</Badge>;
    if (confidence >= 0.6) return <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">中置信</Badge>;
    return <Badge className="bg-red-100 text-red-800 hover:bg-red-100">低置信</Badge>;
  };

  return (
    <Card className="w-full border-white/10 bg-[#111111] text-white">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-white">
          <FolderOpen className="h-5 w-5" />
          一键归档
          {step !== 'select' && <Badge variant="outline" className="text-zinc-300 border-zinc-600">{folderPath}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 text-red-200 rounded flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span className="flex-1">{error}</span>
            <Button variant="ghost" size="sm" onClick={() => setError('')} className="text-red-200 hover:bg-red-500/10">关闭</Button>
          </div>
        )}

        {step === 'select' && (
          <div className="text-center py-8">
            <p className="text-zinc-400 mb-4">选择一个本地文件夹，系统将生成分类归档方案供你审核</p>
            <Button onClick={selectFolder} size="lg" className="bg-amber-400 text-black hover:bg-amber-300">
              <FolderOpen className="mr-2 h-4 w-4" /> 选择文件夹
            </Button>
          </div>
        )}

        {step === 'scanning' && (
          <div className="text-center py-8">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-amber-400" />
            <p className="text-zinc-300">正在扫描文件夹...</p>
          </div>
        )}

        {step === 'review' && (
          <div>
            <div className="flex flex-col gap-3 md:flex-row md:justify-between md:items-center mb-4">
              <p className="text-sm text-zinc-400">
                扫描到 {scannedFiles.length} 个文件，请确认分类结果
              </p>
              <div className="flex flex-col gap-2 md:flex-row md:items-center">
                <input
                  value={targetBase}
                  onChange={(e) => setTargetBase(e.target.value)}
                  placeholder="目标根目录，例如 /Users/leslie/项目资料_archived"
                  className="min-h-9 rounded-md border border-zinc-700 bg-[#0A0A0A] px-3 text-sm text-white outline-none focus:border-amber-400/50"
                />
                <Button onClick={generatePlan} disabled={loading || !targetBase.trim()} className="bg-white text-black hover:bg-zinc-200">
                  生成归档方案
                </Button>
              </div>
            </div>
            <div className="max-h-96 overflow-y-auto space-y-2">
              {scannedFiles.slice(0, 50).map((file, i) => (
                <div key={i} className="flex items-center justify-between p-2 border border-zinc-800 rounded text-sm bg-[#0A0A0A]">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-4 w-4 text-zinc-500 shrink-0" />
                    <span className="truncate text-zinc-200" title={file.name}>{file.name}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant="outline" className="text-zinc-300 border-zinc-700">{file.file_type}</Badge>
                    {getConfidenceBadge(file.confidence)}
                  </div>
                </div>
              ))}
              {scannedFiles.length > 50 && (
                <p className="text-center text-zinc-500 text-sm">
                  ... 还有 {scannedFiles.length - 50} 个文件
                </p>
              )}
            </div>
          </div>
        )}

        {step === 'confirm' && (
          <div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div className="text-center p-3 bg-zinc-800/50 rounded">
                <div className="text-2xl font-bold text-white">{stats.total}</div>
                <div className="text-xs text-zinc-400">总文件</div>
              </div>
              <div className="text-center p-3 bg-green-500/10 rounded">
                <div className="text-2xl font-bold text-green-400">{stats.ready}</div>
                <div className="text-xs text-zinc-400">待执行</div>
              </div>
              <div className="text-center p-3 bg-yellow-500/10 rounded">
                <div className="text-2xl font-bold text-yellow-400">{stats.conflicts}</div>
                <div className="text-xs text-zinc-400">冲突</div>
              </div>
              <div className="text-center p-3 bg-zinc-800/50 rounded">
                <div className="text-2xl font-bold text-zinc-300">{stats.duplicates}</div>
                <div className="text-xs text-zinc-400">重复跳过</div>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setStep('review')} className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">返回修改</Button>
              <Button onClick={executePlan} disabled={stats.ready === 0 || loading} className="bg-amber-400 text-black hover:bg-amber-300">
                确认执行（复制到新结构）
              </Button>
            </div>
          </div>
        )}

        {step === 'executing' && (
          <div className="text-center py-8">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-amber-400" />
            <p className="text-zinc-300">正在执行归档...</p>
          </div>
        )}

        {step === 'done' && (
          <div className="text-center py-8">
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
            <p className="text-lg font-medium mb-2 text-white">归档完成！</p>
            <p className="text-sm text-zinc-400 mb-4">
              文件已复制到新结构，原文件未移动。已入库 {stats.ready} 个文件。
            </p>
            <div className="flex gap-2 justify-center">
              <Button variant="outline" onClick={undoArchive} disabled={loading} className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
                <Undo2 className="mr-2 h-4 w-4" /> 撤销归档
              </Button>
              <Button onClick={resetWizard} className="bg-white text-black hover:bg-zinc-200">
                继续归档其他文件夹
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

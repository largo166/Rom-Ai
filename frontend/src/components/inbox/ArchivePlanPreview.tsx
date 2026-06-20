import { useMemo } from 'react';
import { AlertTriangle, ArrowRight, FileCode2, FileText, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { BatchArchivePlanResponse } from '@/lib/projectsApi';

interface ArchivePlanPreviewProps {
  open: boolean;
  plan: BatchArchivePlanResponse | null;
  loading: boolean;
  executing: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ArchivePlanPreview({
  open,
  plan,
  loading,
  executing,
  onConfirm,
  onCancel,
}: ArchivePlanPreviewProps) {
  const actionableCount = useMemo(() => {
    if (!plan) return 0;
    return plan.groups.reduce(
      (sum, group) => sum + group.files.filter((file) => file.action !== 'skip').length,
      0,
    );
  }, [plan]);

  const skipCount = useMemo(() => {
    if (!plan) return 0;
    return plan.groups.reduce(
      (sum, group) => sum + group.files.filter((file) => file.action === 'skip').length,
      0,
    );
  }, [plan]);

  return (
    <Dialog open={open} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="flex max-h-[90vh] max-w-4xl flex-col overflow-hidden border-white/10 bg-[#111111] p-0 text-white">
        <DialogHeader className="px-6 pt-6">
          <DialogTitle className="flex items-center gap-2 text-white">
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin text-amber-400" />
            ) : (
              <FileText className="h-5 w-5 text-amber-400" />
            )}
            {loading ? 'AI 正在分析文件...' : '整体归档方案'}
          </DialogTitle>
          <DialogDescription className="text-zinc-400">
            {loading
              ? '正在读取文件内容、比对项目库并生成重命名与归档路径建议。'
              : plan?.summary || '请确认以下归档方案，确认后系统将按项目分组归档文件。'}
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-2">
          {loading && !plan && (
            <div className="flex flex-col items-center justify-center py-16">
              <Loader2 className="mb-4 h-10 w-10 animate-spin text-amber-400" />
              <p className="text-zinc-300">AI 正在分析文件...</p>
              <p className="mt-1 text-xs text-zinc-500">这可能需要几秒钟</p>
            </div>
          )}

          {!loading && plan && (
            <>
              {plan.naming_conflicts.length > 0 && (
                <div className="mb-4 flex items-start gap-2 rounded-lg border border-red-400/30 bg-red-400/10 p-3">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
                  <div className="text-sm text-red-100">
                    <div className="mb-1 font-medium">发现命名冲突</div>
                    <ul className="list-inside list-disc text-xs leading-5 text-red-200">
                      {plan.naming_conflicts.map((conflict, index) => (
                        <li key={index}>{conflict}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              <div className="mb-4 grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-white/10 bg-black/25 p-3 text-center">
                  <div className="text-2xl font-semibold text-white">{plan.total_files}</div>
                  <div className="text-xs text-zinc-500">总文件</div>
                </div>
                <div className="rounded-lg border border-white/10 bg-black/25 p-3 text-center">
                  <div className="text-2xl font-semibold text-amber-400">{actionableCount}</div>
                  <div className="text-xs text-zinc-500">待执行</div>
                </div>
                <div className="rounded-lg border border-white/10 bg-black/25 p-3 text-center">
                  <div className="text-2xl font-semibold text-zinc-300">{skipCount}</div>
                  <div className="text-xs text-zinc-500">跳过</div>
                </div>
              </div>

              <div className="space-y-4">
                {plan.groups.map((group) => (
                  <div key={group.project} className="rounded-lg border border-white/10 bg-black/20 p-3">
                    <div className="mb-3 flex items-center gap-2">
                      <span className="text-sm font-semibold text-white">{group.project}</span>
                      <Badge variant="outline" className="border-zinc-700 text-zinc-300">
                        {group.file_count} 个文件
                      </Badge>
                    </div>
                    <div className="space-y-2">
                      {group.files.map((file) => (
                        <div
                          key={file.id}
                          className="flex flex-col gap-1.5 rounded-md border border-zinc-800 bg-[#0A0A0A] p-2.5 text-sm"
                        >
                          <div className="flex items-center gap-2">
                            <span
                              className="truncate text-zinc-400"
                              title={file.original_name}
                            >
                              {file.original_name}
                            </span>
                            <ArrowRight className="h-3.5 w-3.5 shrink-0 text-zinc-600" />
                            <span
                              className="truncate font-medium text-white"
                              title={file.new_name}
                            >
                              {file.new_name}
                            </span>
                          </div>
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <Badge variant="outline" className="border-zinc-700 text-zinc-300">
                              {file.file_type}
                            </Badge>
                            <span className="text-zinc-500">→ {file.target_path}</span>
                            {file.action === 'skip' && (
                              <Badge className="bg-zinc-700 text-zinc-200 hover:bg-zinc-700">
                                跳过
                              </Badge>
                            )}
                            {file.will_format && (
                              <Badge className="border-amber-400/30 bg-amber-400/20 text-amber-200 hover:bg-amber-400/20">
                                <FileCode2 className="mr-1 h-3 w-3" />
                                格式化
                              </Badge>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
                {plan.groups.length === 0 && (
                  <div className="rounded-lg border border-dashed border-zinc-700 p-8 text-center text-sm text-zinc-500">
                    没有可归档的文件
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        <DialogFooter className="border-t border-white/10 bg-black/20 px-6 py-4">
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={executing}
            className="border-zinc-700 bg-transparent text-zinc-300 hover:bg-zinc-800 hover:text-white"
          >
            取消
          </Button>
          <Button
            onClick={onConfirm}
            disabled={loading || executing || !plan || actionableCount === 0}
            className="bg-amber-400 text-black hover:bg-amber-300 disabled:opacity-50"
          >
            {executing ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            确认归档
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

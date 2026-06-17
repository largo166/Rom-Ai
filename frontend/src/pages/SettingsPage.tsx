import { useEffect, useState } from 'react';
import { DownloadCloud, FolderOpen, Loader2, Save, ShieldCheck } from 'lucide-react';
import { getSettingsStatus, listDeepSeekModels, updateDeepSeekSettings, type DeepSeekModelInfo, type SettingsStatus } from '../lib/projectsApi';
import { openDesktopPath } from '../lib/runtime';

export function SettingsPage() {
  const [status, setStatus] = useState<SettingsStatus | null>(null);
  const [message, setMessage] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://api.deepseek.com');
  const [model, setModel] = useState('deepseek-chat');
  const [models, setModels] = useState<DeepSeekModelInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);

  async function loadStatus() {
    try {
      const data = await getSettingsStatus();
      setStatus(data);
      setBaseUrl(data.deepseek_base_url || 'https://api.deepseek.com');
      setModel(data.deepseek_model || 'deepseek-chat');
    } catch (error) {
      setMessage(`读取设置失败：${String(error)}`);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  async function saveDeepSeekSettings() {
    setSaving(true);
    setMessage('');
    try {
      const updated = await updateDeepSeekSettings({
        api_key: apiKey,
        base_url: baseUrl,
        model,
      });
      setStatus(updated);
      setApiKey('');
      setMessage('DeepSeek 配置已保存。启动分析时会优先使用真实 API。');
    } catch (error) {
      setMessage(`保存失败：${String(error)}`);
    } finally {
      setSaving(false);
    }
  }

  async function fetchModels() {
    setLoadingModels(true);
    setMessage('');
    try {
      const data = await listDeepSeekModels();
      setModels(data.models);
      if (data.models.length && !data.models.some((item) => item.id === model)) {
        setModel(data.models[0].id);
      }
      setMessage(data.models.length ? '模型列表已拉取，请选择要使用的模型。' : '没有拉取到可用模型。');
    } catch (error) {
      setMessage(`拉取模型失败：${String(error)}`);
    } finally {
      setLoadingModels(false);
    }
  }

  async function openPath(key: string, label: string) {
    const opened = await openDesktopPath(key);
    if (!opened) setMessage(`${label}只能在桌面应用中直接打开。`);
  }

  return (
    <main className="min-h-screen bg-[#0A0A0A] px-6 pb-20 pt-28 md:px-12">
      <div className="mx-auto max-w-4xl">
        <div className="mb-8">
          <span className="mb-4 block text-xs font-medium uppercase tracking-[0.3em] text-zinc-500">Settings</span>
          <h1 className="mb-4 text-3xl font-bold tracking-tight text-white md:text-5xl">系统设置</h1>
          <p className="text-sm leading-7 text-zinc-400">只显示 Key 是否已配置，不显示完整 Key。用户数据、日志和缓存默认写入 AppData。</p>
        </div>

        {message && <div className="mb-5 rounded-lg border border-white/10 bg-white/5 p-4 text-sm text-zinc-200">{message}</div>}

        {status && (
          <div className="space-y-5">
            <div className="rounded-lg border border-[#333333] bg-[#111111] p-5">
              <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-white">
                <ShieldCheck size={18} className="text-emerald-300" />
                DeepSeek 配置
              </div>
              <div className="grid grid-cols-1 gap-4 text-sm">
                <label className="space-y-2">
                  <span className="text-xs text-zinc-500">API Key</span>
                  <input
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    type="password"
                    placeholder={status.deepseek_configured ? '已配置，输入新 Key 可覆盖' : '输入 DeepSeek API Key'}
                    className="w-full rounded-lg border border-[#333333] bg-[#171717] px-3 py-2 text-white outline-none focus:border-amber-400"
                  />
                </label>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <label className="space-y-2">
                    <span className="text-xs text-zinc-500">Base URL</span>
                    <input
                      value={baseUrl}
                      onChange={(event) => setBaseUrl(event.target.value)}
                      className="w-full rounded-lg border border-[#333333] bg-[#171717] px-3 py-2 text-white outline-none focus:border-amber-400"
                    />
                  </label>
                  <div className="space-y-2">
                    <span className="text-xs text-zinc-500">模型</span>
                    {models.length ? (
                      <select
                        value={model}
                        onChange={(event) => setModel(event.target.value)}
                        className="w-full rounded-lg border border-[#333333] bg-[#171717] px-3 py-2 text-white outline-none focus:border-amber-400"
                      >
                        {models.map((item) => (
                          <option key={item.id} value={item.id}>{item.id}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        value={model}
                        onChange={(event) => setModel(event.target.value)}
                        className="w-full rounded-lg border border-[#333333] bg-[#171717] px-3 py-2 text-white outline-none focus:border-amber-400"
                      />
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={fetchModels}
                    disabled={loadingModels}
                    className="inline-flex w-fit items-center gap-2 rounded-lg border border-[#333333] bg-[#171717] px-4 py-2 text-sm font-semibold text-zinc-200 hover:border-zinc-600 disabled:opacity-50"
                  >
                    {loadingModels ? <Loader2 size={16} className="animate-spin" /> : <DownloadCloud size={16} />}
                    拉取模型
                  </button>
                  <button
                    onClick={saveDeepSeekSettings}
                    disabled={saving}
                    className="inline-flex w-fit items-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
                  >
                    {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                    保存配置
                  </button>
                </div>
                {models.length ? (
                  <div className="rounded-lg border border-white/10 bg-[#171717] p-3 text-xs text-zinc-400">
                    已拉取 {models.length} 个模型：{models.map((item) => item.id).join('、')}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="rounded-lg border border-[#333333] bg-[#111111] p-5">
              <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-white">
                <ShieldCheck size={18} className="text-emerald-300" />
                后端状态
              </div>
              <div className="grid grid-cols-1 gap-4 text-sm md:grid-cols-2">
                <div className="rounded-lg bg-[#171717] p-4">DeepSeek：{status.deepseek_configured ? '已配置' : '未配置'}</div>
                <div className="rounded-lg bg-[#171717] p-4">Mock 模式：{status.mock_mode ? '开启' : '关闭'}</div>
                <div className="rounded-lg bg-[#171717] p-4">当前模型：{status.deepseek_model}</div>
                <div className="rounded-lg bg-[#171717] p-4">Base URL：{status.deepseek_base_url}</div>
                <div className="rounded-lg bg-[#171717] p-4 md:col-span-2">默认 Vault：{status.default_vault_path || '未设置'}</div>
                <div className="rounded-lg bg-[#171717] p-4 md:col-span-2">上传路径：{status.upload_root}</div>
                <div className="rounded-lg bg-[#171717] p-4 md:col-span-2">数据库：{status.database_url}</div>
                <div className="rounded-lg bg-[#171717] p-4 md:col-span-2">数据目录：{status.data_dir || '未返回'}</div>
                <div className="rounded-lg bg-[#171717] p-4 md:col-span-2">配置文件：{status.env_file || '未返回'}</div>
                <div className="rounded-lg bg-[#171717] p-4 md:col-span-2">日志目录：{status.log_dir || '未返回'}</div>
              </div>
              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  onClick={() => openPath('dataDir', '数据目录')}
                  className="inline-flex items-center gap-2 rounded-lg border border-[#333333] bg-[#171717] px-4 py-2 text-sm text-zinc-200 hover:border-zinc-600"
                >
                  <FolderOpen size={16} />
                  打开数据目录
                </button>
                <button
                  onClick={() => openPath('logDir', '日志目录')}
                  className="inline-flex items-center gap-2 rounded-lg border border-[#333333] bg-[#171717] px-4 py-2 text-sm text-zinc-200 hover:border-zinc-600"
                >
                  <FolderOpen size={16} />
                  打开日志目录
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

import { useEffect, useState } from 'react';
import { DownloadCloud, FolderOpen, Loader2, Power, RefreshCw, Save, ShieldCheck, Video } from 'lucide-react';
import {
  getSettingsStatus,
  listDeepSeekModels,
  updateDeepSeekSettings,
  updateTencentMeetingSettings,
  type DeepSeekModelInfo,
  type SettingsStatus,
} from '../lib/projectsApi';
import {
  checkDesktopUpdate,
  downloadDesktopUpdate,
  getDesktopVersion,
  installDesktopUpdate,
  onDesktopUpdateStatus,
  openDesktopPath,
  type UpdateStatusPayload,
} from '../lib/runtime';

export function SettingsPage() {
  const [status, setStatus] = useState<SettingsStatus | null>(null);
  const [message, setMessage] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://api.deepseek.com');
  const [model, setModel] = useState('deepseek-chat');
  const [models, setModels] = useState<DeepSeekModelInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const [savingTencent, setSavingTencent] = useState(false);
  const [tencentToken, setTencentToken] = useState('');
  const [loadingModels, setLoadingModels] = useState(false);
  const [versionInfo, setVersionInfo] = useState<{ version: string; isPackaged: boolean } | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatusPayload>({ status: 'idle' });
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [downloadingUpdate, setDownloadingUpdate] = useState(false);

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
    getDesktopVersion().then((data) => {
      if (data) setVersionInfo({ version: data.version, isPackaged: data.isPackaged });
    });
    onDesktopUpdateStatus((payload) => {
      setUpdateStatus(payload);
      setCheckingUpdate(payload.status === 'checking');
      setDownloadingUpdate(payload.status === 'downloading');
    });
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

  async function saveTencentMeetingSettings() {
    if (!tencentToken.trim()) {
      setMessage('请输入腾讯会议 Token。');
      return;
    }
    setSavingTencent(true);
    setMessage('');
    try {
      const updated = await updateTencentMeetingSettings({ token: tencentToken });
      setStatus(updated);
      setTencentToken('');
      setMessage('腾讯会议 Token 已保存。创建腾讯会议和同步会议纪要时会使用该配置。');
    } catch (error) {
      setMessage(`保存腾讯会议配置失败：${String(error)}`);
    } finally {
      setSavingTencent(false);
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

  async function checkUpdate() {
    setMessage('');
    setCheckingUpdate(true);
    try {
      const result = await checkDesktopUpdate();
      if (!result) setMessage('检查更新只能在桌面应用中使用。');
    } catch (error) {
      setMessage(`检查更新失败：${String(error)}`);
    } finally {
      setCheckingUpdate(false);
    }
  }

  async function downloadUpdate() {
    setMessage('');
    setDownloadingUpdate(true);
    try {
      const result = await downloadDesktopUpdate();
      if (!result) setMessage('下载更新只能在桌面应用中使用。');
    } catch (error) {
      setMessage(`下载更新失败：${String(error)}`);
      setDownloadingUpdate(false);
    }
  }

  async function installUpdate() {
    try {
      await installDesktopUpdate();
    } catch (error) {
      setMessage(`安装更新失败：${String(error)}`);
    }
  }

  const updateLabelByStatus: Record<UpdateStatusPayload['status'], string> = {
    idle: '等待检查',
    checking: '正在检查更新',
    available: '发现新版本',
    'not-available': '已是最新版本',
    downloading: '正在下载更新',
    downloaded: '更新已下载',
    error: '更新检查失败',
    'dev-mode': '开发模式',
  };

  const updateProgress = Math.round(updateStatus.info?.percent ?? 0);
  const updateVersion = updateStatus.info?.version;

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
                <Video size={18} className="text-sky-300" />
                腾讯会议配置
              </div>
              <div className="grid grid-cols-1 gap-4 text-sm">
                <div className="rounded-lg bg-[#171717] p-4">
                  Token 状态：{status.tencent_meeting_configured ? '已配置' : '未配置'}
                </div>
                <label className="space-y-2">
                  <span className="text-xs text-zinc-500">TENCENT_MEETING_TOKEN</span>
                  <input
                    value={tencentToken}
                    onChange={(event) => setTencentToken(event.target.value)}
                    type="password"
                    placeholder={status.tencent_meeting_configured ? '已配置，输入新 Token 可覆盖' : '输入腾讯会议 Token'}
                    className="w-full rounded-lg border border-[#333333] bg-[#171717] px-3 py-2 text-white outline-none focus:border-sky-300"
                  />
                </label>
                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={saveTencentMeetingSettings}
                    disabled={savingTencent}
                    className="inline-flex w-fit items-center gap-2 rounded-lg bg-sky-300 px-4 py-2 text-sm font-semibold text-black hover:bg-sky-200 disabled:opacity-50"
                  >
                    {savingTencent ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                    保存腾讯会议配置
                  </button>
                </div>
                <div className="rounded-lg border border-white/10 bg-[#171717] p-3 text-xs leading-6 text-zinc-400">
                  配置后，“项目会议”里的创建腾讯会议、同步腾讯会议纪要会使用这个 Token。Token 只写入本机 AppData 配置文件，不会提交到 GitHub。
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-[#333333] bg-[#111111] p-5">
              <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-white">
                <ShieldCheck size={18} className="text-emerald-300" />
                后端状态
              </div>
              <div className="grid grid-cols-1 gap-4 text-sm md:grid-cols-2">
                <div className="rounded-lg bg-[#171717] p-4">DeepSeek：{status.deepseek_configured ? '已配置' : '未配置'}</div>
                <div className="rounded-lg bg-[#171717] p-4">腾讯会议：{status.tencent_meeting_configured ? '已配置' : '未配置'}</div>
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

            <div className="rounded-lg border border-[#333333] bg-[#111111] p-5">
              <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-white">
                <RefreshCw size={18} className="text-sky-300" />
                应用更新
              </div>
              <div className="grid grid-cols-1 gap-4 text-sm md:grid-cols-2">
                <div className="rounded-lg bg-[#171717] p-4">当前版本：{versionInfo?.version || '未知'}</div>
                <div className="rounded-lg bg-[#171717] p-4">运行模式：{versionInfo?.isPackaged ? '正式安装版' : '开发模式'}</div>
                <div className="rounded-lg bg-[#171717] p-4 md:col-span-2">
                  更新状态：{updateLabelByStatus[updateStatus.status]}
                  {updateVersion ? ` · 最新版本 ${updateVersion}` : ''}
                  {updateStatus.info?.message ? ` · ${updateStatus.info.message}` : ''}
                </div>
                {updateStatus.status === 'downloading' ? (
                  <div className="rounded-lg bg-[#171717] p-4 md:col-span-2">
                    <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
                      <span>下载进度</span>
                      <span>{updateProgress}%</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-black/40">
                      <div className="h-full rounded-full bg-sky-300" style={{ width: `${updateProgress}%` }} />
                    </div>
                  </div>
                ) : null}
              </div>
              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  onClick={checkUpdate}
                  disabled={checkingUpdate || downloadingUpdate}
                  className="inline-flex items-center gap-2 rounded-lg border border-[#333333] bg-[#171717] px-4 py-2 text-sm text-zinc-200 hover:border-zinc-600 disabled:opacity-50"
                >
                  {checkingUpdate ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                  检查更新
                </button>
                <button
                  onClick={downloadUpdate}
                  disabled={updateStatus.status !== 'available' || downloadingUpdate}
                  className="inline-flex items-center gap-2 rounded-lg border border-[#333333] bg-[#171717] px-4 py-2 text-sm text-zinc-200 hover:border-zinc-600 disabled:opacity-50"
                >
                  {downloadingUpdate ? <Loader2 size={16} className="animate-spin" /> : <DownloadCloud size={16} />}
                  下载更新
                </button>
                <button
                  onClick={installUpdate}
                  disabled={updateStatus.status !== 'downloaded'}
                  className="inline-flex items-center gap-2 rounded-lg bg-sky-300 px-4 py-2 text-sm font-semibold text-black hover:bg-sky-200 disabled:opacity-50"
                >
                  <Power size={16} />
                  重启安装
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

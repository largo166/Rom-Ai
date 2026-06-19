const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const log = require('electron-log');
const { autoUpdater } = require('electron-updater');
const http = require('http');
const net = require('net');
const path = require('path');
const fs = require('fs');

let backendProcess = null;
let mainWindow = null;
let runtimePaths = null;

const DEFAULT_BACKEND_PORT = 8000;

app.setName('ROM-AI');
autoUpdater.logger = log;
autoUpdater.autoDownload = false;

function updateInfoPayload(info = {}) {
  return {
    version: app.getVersion(),
    isPackaged: app.isPackaged,
    info,
  };
}

function sendUpdateStatus(status, detail = {}) {
  const payload = { status, ...updateInfoPayload(detail) };
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('update-status', payload);
  }
  return payload;
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function escapeWindowsPath(value) {
  return value.replace(/\\/g, '\\\\');
}

function ensureEnvDefaults(envPath, defaults) {
  const existingText = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : '';
  const lines = existingText ? existingText.split(/\r?\n/) : [];
  const keys = new Set(lines.map((line) => line.split('=')[0]).filter(Boolean));
  let changed = false;
  defaults.forEach((line) => {
    const key = line.split('=')[0];
    if (!keys.has(key)) {
      lines.push(line);
      changed = true;
    }
  });
  if (changed) {
    fs.writeFileSync(envPath, `${lines.filter((line) => line !== '').join('\n')}\n`, 'utf8');
  }
}

function ensureUserEnv() {
  const userData = app.getPath('userData');
  const dataDir = ensureDir(path.join(userData, 'backend-data'));
  const uploadsDir = ensureDir(path.join(dataDir, 'uploads'));
  const cloudDir = ensureDir(path.join(dataDir, 'cloud'));
  const logDir = ensureDir(path.join(userData, 'logs'));
  const envPath = path.join(dataDir, '.env');

  const envDefaults = [
    'DEEPSEEK_API_KEY=',
    'DEEPSEEK_BASE_URL=https://api.deepseek.com',
    'DEEPSEEK_MODEL=deepseek-chat',
    'IMAGE_PROVIDER=huashu',
    'IMAGE_API_KEY=sk-sPMCRDvfxLhCLJlqMvvGpSFhzH4d0q69ApfsFb6BrPGK3MFZ',
    'IMAGE_BASE_URL=https://api.openai.com/v1',
    'IMAGE_MODEL=gpt-image-1',
    'TENCENT_MEETING_TOKEN=',
    'DEFAULT_VAULT_PATH=',
    `UPLOAD_ROOT=${escapeWindowsPath(uploadsDir)}`,
    'CLOUD_UPLOAD_ENABLED=false',
    `CLOUD_UPLOAD_ROOT=${escapeWindowsPath(cloudDir)}`,
    `DATABASE_URL=sqlite:///${path.join(dataDir, 'rmo_ai.db').replace(/\\/g, '/')}`,
  ];
  if (!fs.existsSync(envPath)) {
    fs.writeFileSync(envPath, `${envDefaults.join('\n')}\n`, 'utf8');
  } else {
    ensureEnvDefaults(envPath, envDefaults);
  }

  runtimePaths = { userData, dataDir, uploadsDir, cloudDir, logDir, envPath };
  return runtimePaths;
}

function resolveBackendExe() {
  const candidates = [
    path.join(process.resourcesPath, 'backend', 'rom-ai-backend', 'rom-ai-backend.exe'),
    path.join(process.resourcesPath, 'backend', 'rom-ai-backend.exe'),
    path.join(process.resourcesPath, 'app.asar.unpacked', 'backend', 'rom-ai-backend', 'rom-ai-backend.exe'),
    path.join(process.resourcesPath, 'app.asar.unpacked', 'backend', 'rom-ai-backend.exe'),
    path.join(__dirname, '..', 'backend_dist', 'rom-ai-backend', 'rom-ai-backend.exe'),
    path.join(__dirname, '..', 'backend_dist', 'rom-ai-backend.exe'),
  ];
  return {
    exe: candidates.find((candidate) => fs.existsSync(candidate)),
    candidates,
  };
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, '127.0.0.1');
  });
}

async function findBackendPort() {
  const requested = Number(process.env.ROM_AI_BACKEND_PORT || DEFAULT_BACKEND_PORT);
  if (await isPortFree(requested)) return requested;
  for (let port = 8010; port < 8050; port += 1) {
    if (await isPortFree(port)) return port;
  }
  throw new Error(`Backend port ${requested} is busy, and ports 8010-8049 are also unavailable. Close the program using those ports and try again.`);
}

function openAppendStream(filePath) {
  ensureDir(path.dirname(filePath));
  return fs.createWriteStream(filePath, { flags: 'a' });
}

function waitForBackendHealth(port, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    function check() {
      const request = http.get(`http://127.0.0.1:${port}/api/health`, (response) => {
        response.resume();
        if (response.statusCode && response.statusCode >= 200 && response.statusCode < 300) {
          resolve();
          return;
        }
        retry();
      });
      request.on('error', retry);
      request.setTimeout(3000, () => {
        request.destroy();
        retry();
      });
    }

    function retry() {
      if (Date.now() >= deadline) {
        reject(new Error(`Backend did not become healthy on port ${port} within ${timeoutMs / 1000} seconds.`));
        return;
      }
      setTimeout(check, 500);
    }

    check();
  });
}

async function startBackend() {
  const { exe, candidates } = resolveBackendExe();
  if (!exe) {
    throw new Error(`Cannot find backend executable rom-ai-backend.exe.\nChecked:\n${candidates.join('\n')}`);
  }

  const port = await findBackendPort();
  const { dataDir, envPath, logDir } = ensureUserEnv();
  const outLog = openAppendStream(path.join(logDir, 'backend.log'));
  const errLog = openAppendStream(path.join(logDir, 'backend-error.log'));
  outLog.write(`\n[${new Date().toISOString()}] Starting backend: ${exe}\n`);

  backendProcess = spawn(exe, [], {
    cwd: dataDir,
    env: {
      ...process.env,
      ROM_AI_ENV_FILE: envPath,
      ROM_AI_BASE_DIR: dataDir,
      ROM_AI_LOG_DIR: logDir,
      ROM_AI_BACKEND_PORT: String(port),
    },
    windowsHide: true,
  });

  backendProcess.stdout?.pipe(outLog);
  backendProcess.stderr?.pipe(errLog);

  backendProcess.on('exit', (code, signal) => {
    outLog.write(`[${new Date().toISOString()}] Backend exited. code=${code} signal=${signal}\n`);
    if (code !== 0 && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('backend-exit', { code, signal, logDir });
    }
  });

  await waitForBackendHealth(port);

  return port;
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    title: 'ROM-AI',
    backgroundColor: '#0A0A0A',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const runtime = {
    backendBaseUrl: `http://127.0.0.1:${port}`,
    paths: runtimePaths,
  };
  const indexPath = path.join(__dirname, 'frontend', 'index.html');
  mainWindow.loadFile(indexPath, {
    query: { backendBaseUrl: runtime.backendBaseUrl },
    hash: '/projects',
  });
  mainWindow.webContents.once('did-finish-load', () => {
    mainWindow.webContents.send('rom-ai-runtime', runtime);
    sendUpdateStatus(app.isPackaged ? 'idle' : 'dev-mode');
  });
}

function stopBackend() {
  if (!backendProcess) return;
  const child = backendProcess;
  backendProcess = null;
  if (!child.killed) child.kill();
}

function setupAutoUpdate() {
  autoUpdater.on('checking-for-update', () => {
    sendUpdateStatus('checking');
  });

  autoUpdater.on('update-available', (info) => {
    sendUpdateStatus('available', info);
  });

  autoUpdater.on('update-not-available', (info) => {
    sendUpdateStatus('not-available', info);
  });

  autoUpdater.on('download-progress', (progress) => {
    sendUpdateStatus('downloading', progress);
  });

  autoUpdater.on('update-downloaded', (info) => {
    sendUpdateStatus('downloaded', info);
  });

  autoUpdater.on('error', (error) => {
    sendUpdateStatus('error', { message: String(error && error.message ? error.message : error) });
  });
}

async function checkForUpdates() {
  if (!app.isPackaged) {
    return sendUpdateStatus('dev-mode', { message: '开发模式下不检查 GitHub Release 更新。' });
  }
  sendUpdateStatus('checking');
  const result = await autoUpdater.checkForUpdates();
  return updateInfoPayload(result?.updateInfo || {});
}

async function downloadUpdate() {
  if (!app.isPackaged) {
    return sendUpdateStatus('dev-mode', { message: '开发模式下不能下载更新。' });
  }
  sendUpdateStatus('downloading');
  await autoUpdater.downloadUpdate();
  return updateInfoPayload();
}

function installUpdate() {
  if (!app.isPackaged) {
    return sendUpdateStatus('dev-mode', { message: '开发模式下不能安装更新。' });
  }
  autoUpdater.quitAndInstall(false, true);
  return true;
}

ipcMain.handle('rom-ai:get-runtime', () => ({
  backendBaseUrl: process.env.ROM_AI_BACKEND_PORT
    ? `http://127.0.0.1:${process.env.ROM_AI_BACKEND_PORT}`
    : undefined,
  paths: runtimePaths,
}));

ipcMain.handle('rom-ai:open-path', async (_event, key) => {
  if (!runtimePaths || !Object.prototype.hasOwnProperty.call(runtimePaths, key)) {
    throw new Error('Unknown path');
  }
  await shell.openPath(runtimePaths[key]);
  return true;
});

ipcMain.handle('rom-ai:pick-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: '选择要扫描的项目资料文件夹',
    properties: ['openDirectory'],
  });
  const pathValue = result.filePaths?.[0] || '';
  return { path: pathValue, cancelled: result.canceled || !pathValue };
});

ipcMain.handle('rom-ai:get-version', () => updateInfoPayload());
ipcMain.handle('rom-ai:check-update', checkForUpdates);
ipcMain.handle('rom-ai:download-update', downloadUpdate);
ipcMain.handle('rom-ai:install-update', installUpdate);

app.whenReady().then(async () => {
  try {
    setupAutoUpdate();
    const port = await startBackend();
    process.env.ROM_AI_BACKEND_PORT = String(port);
    createWindow(port);
  } catch (error) {
    dialog.showErrorBox('ROM-AI failed to start', String(error && error.message ? error.message : error));
    app.quit();
  }
});

app.on('before-quit', stopBackend);

app.on('window-all-closed', () => {
  stopBackend();
  app.quit();
});

const { contextBridge, ipcRenderer } = require('electron');

let runtime = null;

window.addEventListener('DOMContentLoaded', () => {
  document.documentElement.dataset.desktop = 'true';
});

ipcRenderer.on('rom-ai-runtime', (_event, payload) => {
  runtime = payload;
  window.dispatchEvent(new CustomEvent('rom-ai-runtime', { detail: payload }));
});

contextBridge.exposeInMainWorld('romAI', {
  getRuntime: async () => runtime || ipcRenderer.invoke('rom-ai:get-runtime'),
  openPath: async (key) => ipcRenderer.invoke('rom-ai:open-path', key),
  pickFolder: async () => ipcRenderer.invoke('rom-ai:pick-folder'),
  getVersion: async () => ipcRenderer.invoke('rom-ai:get-version'),
  checkUpdate: async () => ipcRenderer.invoke('rom-ai:check-update'),
  downloadUpdate: async () => ipcRenderer.invoke('rom-ai:download-update'),
  installUpdate: async () => ipcRenderer.invoke('rom-ai:install-update'),
  onUpdateStatus: (callback) => {
    ipcRenderer.on('update-status', (_event, payload) => callback(payload));
  },
  onBackendExit: (callback) => {
    ipcRenderer.on('backend-exit', (_event, payload) => callback(payload));
  },
});

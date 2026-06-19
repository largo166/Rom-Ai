export type RomAIRuntime = {
  backendBaseUrl?: string;
  paths?: Record<string, string>;
};

export type UpdateStatusPayload = {
  status: 'idle' | 'checking' | 'available' | 'not-available' | 'downloading' | 'downloaded' | 'error' | 'dev-mode';
  version?: string;
  isPackaged?: boolean;
  info?: {
    version?: string;
    releaseName?: string;
    releaseDate?: string;
    percent?: number;
    transferred?: number;
    total?: number;
    bytesPerSecond?: number;
    message?: string;
  };
};

declare global {
  interface Window {
    romAI?: {
      getRuntime: () => Promise<RomAIRuntime>;
      openPath: (key: string) => Promise<boolean>;
      pickFolder: () => Promise<{ path: string; cancelled: boolean }>;
      getVersion: () => Promise<{ version: string; isPackaged: boolean; info?: Record<string, unknown> }>;
      checkUpdate: () => Promise<unknown>;
      downloadUpdate: () => Promise<unknown>;
      installUpdate: () => Promise<boolean>;
      onUpdateStatus: (callback: (payload: UpdateStatusPayload) => void) => void;
      onBackendExit: (callback: (payload: unknown) => void) => void;
    };
  }
}

const fallbackApiBase = (import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000').replace(/\/$/, '');

function readInitialRuntime(): RomAIRuntime | null {
  if (typeof window === 'undefined') return null;
  const backendBaseUrl = new URLSearchParams(window.location.search).get('backendBaseUrl');
  return backendBaseUrl ? { backendBaseUrl } : null;
}

let runtimeCache: RomAIRuntime | null = readInitialRuntime();

window.addEventListener('rom-ai-runtime', (event) => {
  runtimeCache = (event as CustomEvent<RomAIRuntime>).detail;
});

export function getApiBase() {
  return (runtimeCache?.backendBaseUrl ?? fallbackApiBase).replace(/\/$/, '');
}

export async function getDesktopRuntime() {
  if (runtimeCache) return runtimeCache;
  if (!window.romAI) return null;
  runtimeCache = await window.romAI.getRuntime();
  return runtimeCache;
}

export async function openDesktopPath(key: string) {
  if (!window.romAI) return false;
  return window.romAI.openPath(key);
}

export async function pickDesktopFolder() {
  if (!window.romAI?.pickFolder) return null;
  return window.romAI.pickFolder();
}

export async function getDesktopVersion() {
  if (!window.romAI) return null;
  return window.romAI.getVersion();
}

export async function checkDesktopUpdate() {
  if (!window.romAI) return null;
  return window.romAI.checkUpdate();
}

export async function downloadDesktopUpdate() {
  if (!window.romAI) return null;
  return window.romAI.downloadUpdate();
}

export async function installDesktopUpdate() {
  if (!window.romAI) return false;
  return window.romAI.installUpdate();
}

export function onDesktopUpdateStatus(callback: (payload: UpdateStatusPayload) => void) {
  if (!window.romAI) return false;
  window.romAI.onUpdateStatus(callback);
  return true;
}

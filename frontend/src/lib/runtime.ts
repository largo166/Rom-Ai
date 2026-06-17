export type RomAIRuntime = {
  backendBaseUrl?: string;
  paths?: Record<string, string>;
};

declare global {
  interface Window {
    romAI?: {
      getRuntime: () => Promise<RomAIRuntime>;
      openPath: (key: string) => Promise<boolean>;
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

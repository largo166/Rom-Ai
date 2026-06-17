import { getApiBase } from './runtime';

const apiBase = () => getApiBase();

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || (await res.text()));
  }
  return res.json();
}

/* ---------- Types ---------- */
export type BossMetric = {
  label: string;
  value: number;
  trend?: 'up' | 'down' | 'stable';
  trend_value?: number;
};

export type BossTimeline = {
  id: string;
  title: string;
  date: string;
  type: 'meeting' | 'milestone' | 'deadline';
};

export type BossTodo = {
  id: string;
  title: string;
  project_name: string;
  priority: 'high' | 'medium' | 'low';
  due_date?: string;
  status: 'open' | 'in_progress' | 'overdue';
};

export type BossDashboard = {
  metrics: BossMetric[];
  timeline: BossTimeline[];
  todos: BossTodo[];
};

/* ---------- API Functions ---------- */
export function getBossDashboard() {
  return request<BossDashboard>('/api/boss/dashboard');
}

export function getBossMetrics() {
  return request<BossMetric[]>('/api/boss/metrics');
}

export function getBossTimeline() {
  return request<BossTimeline[]>('/api/boss/timeline');
}

export function getBossTodos() {
  return request<BossTodo[]>('/api/boss/todos');
}

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
export type Task = {
  id: string;
  project_id: string;
  task_name: string;
  task_type: string;
  priority: string;
  owner_role: string;
  estimated_days: number;
  dependencies: string;
  risk_level: string;
  status: string;
  output_requirement: string;
  created_at: string;
  updated_at: string;
};

export type TaskCreatePayload = {
  task_name: string;
  task_type?: string;
  priority?: string;
  owner_role?: string;
  estimated_days?: number;
  dependencies?: string;
  risk_level?: string;
  status?: string;
  output_requirement?: string;
};

export type TaskUpdatePayload = Partial<TaskCreatePayload> & { status?: string };

/* ---------- API Functions ---------- */
export function listTasks(projectId: string) {
  return request<Task[]>(`/api/projects/${projectId}/tasks`);
}

export function createTask(projectId: string, payload: TaskCreatePayload) {
  return request<Task>(`/api/projects/${projectId}/tasks`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateTask(taskId: string, payload: TaskUpdatePayload) {
  return request<Task>(`/api/tasks/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteTask(taskId: string) {
  return request<{ ok: boolean }>(`/api/tasks/${taskId}`, { method: 'DELETE' });
}

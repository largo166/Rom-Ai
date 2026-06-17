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
export type SkillCard = {
  id: string;
  name: string;
  scenario: string;
  input: string;
  output: string;
  status: string;
};

export type SkillExecution = {
  id: string;
  project_id: string;
  skill_card_id: string;
  input_context: string;
  output_json: string;
  status: string;
  created_at: string;
};

export type SkillExecutionPayload = {
  project_id: string;
  input_context?: string;
};

/* ---------- API Functions ---------- */
export function listSkillCards() {
  return request<{ skill_cards: SkillCard[] }>('/api/skill-cards');
}

export function executeSkillCard(skillCardId: string, payload: SkillExecutionPayload) {
  return request<SkillExecution>(`/api/skill-cards/${skillCardId}/execute`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listSkillExecutions(projectId: string) {
  return request<SkillExecution[]>(`/api/projects/${projectId}/skill-executions`);
}

export function getSkillExecution(executionId: string) {
  return request<SkillExecution>(`/api/skill-executions/${executionId}`);
}

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
export type KnowledgeConversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type KnowledgeMessage = {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  references?: Array<{ file_name: string; file_path: string; quote: string }>;
  created_at: string;
};

export type ChatResponse = {
  mode: string;
  answer: string;
  references: Array<{ file_name: string; file_path: string; quote: string }>;
};

/* ---------- API Functions ---------- */
export function listConversations() {
  return request<KnowledgeConversation[]>('/api/knowledge/conversations');
}

export function createConversation(title?: string) {
  return request<KnowledgeConversation>('/api/knowledge/conversations', {
    method: 'POST',
    body: JSON.stringify({ title: title || '新对话' }),
  });
}

export function getConversationMessages(conversationId: string) {
  return request<KnowledgeMessage[]>(`/api/knowledge/conversations/${conversationId}/messages`);
}

export function sendMessage(conversationId: string, content: string) {
  return request<KnowledgeMessage>(`/api/knowledge/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

export function deleteConversation(conversationId: string) {
  return request<{ ok: boolean }>(`/api/knowledge/conversations/${conversationId}`, { method: 'DELETE' });
}

/* ---------- Simple Chat & Index ---------- */

export function chatKnowledge(question: string, projectId?: string) {
  return request<ChatResponse>('/api/knowledge/chat', {
    method: 'POST',
    body: JSON.stringify({ question, project_id: projectId }),
  });
}

export function reindexKnowledge() {
  return request<{ ok: boolean; message: string; indexed_files?: number }>('/api/knowledge/index', {
    method: 'POST',
  });
}

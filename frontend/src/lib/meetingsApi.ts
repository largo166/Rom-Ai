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
export type Meeting = {
  id: string;
  project_id: string;
  title: string;
  date: string;
  attendees: string;
  summary: string;
  action_items: string;
  created_at: string;
};

export type MeetingCreatePayload = {
  title: string;
  date: string;
  attendees?: string;
  summary?: string;
  action_items?: string;
};

/* ---------- API Functions ---------- */
export function listMeetings(projectId: string) {
  return request<Meeting[]>(`/api/projects/${projectId}/meetings`);
}

export function createMeeting(projectId: string, payload: MeetingCreatePayload) {
  return request<Meeting>(`/api/projects/${projectId}/meetings`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getMeeting(meetingId: string) {
  return request<Meeting>(`/api/meetings/${meetingId}`);
}

export function updateMeeting(meetingId: string, payload: Partial<MeetingCreatePayload>) {
  return request<Meeting>(`/api/meetings/${meetingId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteMeeting(meetingId: string) {
  return request<{ ok: boolean }>(`/api/meetings/${meetingId}`, { method: 'DELETE' });
}

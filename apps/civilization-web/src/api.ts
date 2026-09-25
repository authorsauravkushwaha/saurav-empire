/**
 * API client. One origin (the gateway), one owner token, no invented data.
 *
 * If a call fails the UI must say so — the world never fills the gap with decoration.
 */
import type {
  Department, EmpireEvent, Opportunity, RuntimeStatus, Task, WorldAgent, WorldLayout, WorldState,
} from './types';

const TOKEN_KEY = 'empire.owner.token';

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? '';
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token.trim());
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Owner-Token': getToken(),
      ...(init.headers ?? {}),
    },
  });
  const text = await res.text();
  const body = text ? JSON.parse(text) : {};
  if (!res.ok) {
    const detail = body?.detail?.detail ?? body?.detail ?? body?.error ?? res.statusText;
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return body as T;
}

const get = <T,>(p: string) => request<T>(p);
const post = <T,>(p: string, body: unknown = {}) =>
  request<T>(p, { method: 'POST', body: JSON.stringify(body) });

export const api = {
  health: () => get<any>('/api/health'),
  dashboard: () => get<any>('/api/dashboard'),
  services: () => get<any>('/api/services'),
  commands: () => get<any>('/api/commands'),
  command: (text: string) => post<any>('/api/command', { text }),

  layout: () => get<WorldLayout>('/api/world/world/layout'),
  worldState: () => get<WorldState>('/api/world/world/state'),
  agentDetail: (id: string) => get<any>(`/api/world/world/agent/${id}`),
  worldAnalytics: () => get<any>('/api/world/world/analytics'),

  agents: () => get<{ count: number; agents: WorldAgent[] }>('/api/agent/agents?limit=2000'),
  departments: () => get<{ count: number; departments: Department[] }>('/api/agent/departments'),
  createDepartment: (body: Record<string, unknown>) => post<any>('/api/agent/departments', body),
  hire: (body: Record<string, unknown>) => post<any>('/api/agent/agents/hire', body),
  runtime: () => get<RuntimeStatus>('/api/agent/runtime'),
  runtimeStart: () => post<any>('/api/agent/runtime/start'),
  runtimeStop: () => post<any>('/api/agent/runtime/stop'),

  tasks: (status?: string) =>
    get<{ count: number; tasks: Task[] }>(
      `/api/workflow/tasks?limit=200${status ? `&status=${status}` : ''}`,
    ),
  taskMetrics: () => get<any>('/api/workflow/tasks/metrics/summary'),
  automations: () => get<any>('/api/workflow/automations'),
  runAutomation: (name: string) => post<any>(`/api/workflow/automations/${name}/run`),

  economy: () => get<any>('/api/economy/economy/summary'),
  ledger: () => get<any>('/api/economy/economy/ledger'),
  opportunities: () => get<{ count: number; opportunities: Opportunity[] }>('/api/economy/economy/opportunities'),
  experiments: () => get<any>('/api/economy/economy/experiments'),
  lessons: () => get<any>('/api/economy/economy/lessons'),
  discover: () => post<any>('/api/economy/economy/discover'),

  university: () => get<any>('/api/university/university/status'),
  tracks: () => get<any>('/api/university/university/tracks'),
  exams: () => get<any>('/api/university/university/exams'),

  integrations: () => get<any>('/api/integration/integrations'),
  integrationHealth: () => get<any>('/api/integration/integrations/health'),
  models: () => get<any>('/api/model/models/status'),
  modelStats: () => get<any>('/api/model/models/stats'),

  approvals: () => get<{ count: number; approvals: any[] }>('/api/security/security/approvals'),
  audit: () => get<{ count: number; entries: any[] }>('/api/security/security/audit?limit=120'),
  securityCheck: () => get<any>('/api/security/security/self-check'),
  killSwitch: () => get<any>('/api/security/security/killswitch'),
  engageKillSwitch: (reason: string) => post<any>('/api/security/security/killswitch/engage', { reason }),
  disengageKillSwitch: (reason: string) => post<any>('/api/security/security/killswitch/disengage', { reason }),
  decide: (id: string, decision: string, note = '') =>
    post<any>(`/api/security/security/approvals/${id}/decide`, { decision, note }),

  memoryStats: () => get<any>('/api/memory/memory/stats'),
  search: (q: string) => get<any>(`/api/memory/memory/search?q=${encodeURIComponent(q)}&limit=30`),
  events: (since = 0, limit = 200) =>
    get<{ count: number; events: EmpireEvent[] }>(`/api/event/events?since=${since}&limit=${limit}`),
};

/** WebSocket to the gateway, which relays the event-service feed. */
export function openEventStream(onEvent: (e: EmpireEvent) => void, onStatus: (up: boolean) => void): () => void {
  let socket: WebSocket | null = null;
  let closing = false;

  const connect = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    socket = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(getToken())}`);
    socket.onopen = () => onStatus(true);
    socket.onclose = () => {
      onStatus(false);
      if (!closing) setTimeout(connect, 2500);
    };
    socket.onerror = () => onStatus(false);
    socket.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data);
        const list = Array.isArray(parsed) ? parsed : [parsed];
        list.filter((e) => e && e.type).forEach(onEvent);
      } catch {
        /* a malformed frame is dropped, never rendered as if it were real */
      }
    };
  };

  connect();
  return () => {
    closing = true;
    socket?.close();
  };
}

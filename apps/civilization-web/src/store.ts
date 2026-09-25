/**
 * Client state. Every field here is either fetched from the backend or derived from it.
 * There are no placeholder numbers: when a fetch fails the field becomes null and the UI says so.
 */
import { create } from 'zustand';
import { api } from './api';
import type {
  Department, EmpireEvent, LayoutBuilding, Opportunity, RuntimeStatus, Task, WorldAgent, WorldLayout,
} from './types';

export type PanelId =
  | 'none'
  | 'command'
  | 'departments'
  | 'agents'
  | 'tasks'
  | 'economy'
  | 'university'
  | 'approvals'
  | 'security'
  | 'integrations'
  | 'models'
  | 'events';

interface EmpireStore {
  token: string;
  unlocked: boolean;
  unlock: (token: string) => Promise<{ ok: boolean; error?: string }>;
  lock: () => void;

  streamUp: boolean;
  setStreamUp: (up: boolean) => void;

  layout: WorldLayout | null;
  agents: WorldAgent[];
  statusCounts: Record<string, number>;
  runtime: RuntimeStatus | null;
  departments: Department[];
  tasks: Task[];
  taskMetrics: any;
  economy: any;
  opportunities: Opportunity[];
  experiments: any;
  university: any;
  approvals: any[];
  audit: any[];
  integrals: any;
  models: any;
  services: any;
  dashboard: any;
  memoryStats: any;
  events: EmpireEvent[];

  lastError: string | null;
  loading: boolean;
  lastSync: number | null;

  selectedAgent: string | null;
  selectedBuilding: string | null;
  selectedCity: string | null;
  followAgent: boolean;
  panel: PanelId;
  paused: boolean;
  showLabels: boolean;
  cameraPreset: 'overview' | 'command' | 'ring';

  select: (agentId: string | null) => void;
  selectBuilding: (buildingId: string | null, cityId?: string | null) => void;
  selectCity: (cityId: string | null) => void;
  setFollow: (on: boolean) => void;
  setPanel: (panel: PanelId) => void;
  setPaused: (paused: boolean) => void;
  setLabels: (on: boolean) => void;
  setCameraPreset: (preset: 'overview' | 'command' | 'ring') => void;
  pushEvent: (event: EmpireEvent) => void;

  bootstrap: () => Promise<void>;
  refreshWorld: () => Promise<void>;
  refreshPanels: () => Promise<void>;
  commandText: (text: string) => Promise<any>;
}

const pick = async <T,>(fn: () => Promise<T>, fallback: T): Promise<T> => {
  try {
    return await fn();
  } catch {
    return fallback;
  }
};

export const useEmpire = create<EmpireStore>((set, get) => ({
  token: '',
  unlocked: false,

  async unlock(token) {
    set({ token });
    try {
      const res = await fetch('/api/health', { headers: { 'X-Owner-Token': token } });
      if (res.status === 401 || res.status === 403) {
        return { ok: false, error: 'The owner token was rejected. Check data/state/secrets/owner_token.' };
      }
      set({ unlocked: true });
      await get().bootstrap();
      return { ok: true };
    } catch (err) {
      return { ok: false, error: `Cannot reach the gateway on this origin: ${String(err)}` };
    }
  },
  lock() {
    set({ unlocked: false, token: '' });
  },

  streamUp: false,
  setStreamUp: (up) => set({ streamUp: up }),

  layout: null,
  agents: [],
  statusCounts: {},
  runtime: null,
  departments: [],
  tasks: [],
  taskMetrics: null,
  economy: null,
  opportunities: [],
  experiments: null,
  university: null,
  approvals: [],
  audit: [],
  integrals: null,
  models: null,
  services: null,
  dashboard: null,
  memoryStats: null,
  events: [],

  lastError: null,
  loading: false,
  lastSync: null,

  selectedAgent: null,
  selectedBuilding: null,
  selectedCity: null,
  followAgent: false,
  panel: 'command',
  paused: false,
  showLabels: true,
  cameraPreset: 'overview',

  select: (agentId) => set({ selectedAgent: agentId, selectedBuilding: null }),
  selectBuilding: (buildingId, cityId = null) =>
    set({ selectedBuilding: buildingId, selectedCity: cityId ?? get().selectedCity }),
  selectCity: (cityId) => set({ selectedCity: cityId, selectedBuilding: null }),
  setFollow: (on) => set({ followAgent: on }),
  setPanel: (panel) => set({ panel }),
  setPaused: (paused) => set({ paused }),
  setLabels: (on) => set({ showLabels: on }),
  setCameraPreset: (preset) => set({ cameraPreset: preset }),

  pushEvent: (event) =>
    set((s) => ({ events: [event, ...s.events].slice(0, 250) })),

  async bootstrap() {
    set({ loading: true });
    const layout = await pick(() => api.layout(), null as WorldLayout | null);
    if (!layout) {
      set({ lastError: 'The world layout could not be loaded from the world service.', loading: false });
      return;
    }
    set({ layout, loading: false, lastError: null, lastSync: Date.now() });
    await Promise.all([get().refreshWorld(), get().refreshPanels()]);
  },

  async refreshWorld() {
    if (get().paused) return;
    const state = await pick(() => api.worldState(), null);
    if (!state) {
      set({ lastError: 'Live world state is unavailable — the 3D view is showing the last known truth.' });
      return;
    }
    const runtime = await pick(() => api.runtime(), null);
    set({
      agents: state.agents,
      statusCounts: state.status_counts,
      runtime,
      lastSync: Date.now(),
      lastError: null,
    });
  },

  async refreshPanels() {
    const [
      departments, tasks, taskMetrics, economy, opportunities, experiments,
      university, approvals, audit, integrals, models, services, dashboard, memoryStats, events,
    ] = await Promise.all([
      pick(() => api.departments(), { count: 0, departments: [] }),
      pick(() => api.tasks(), { count: 0, tasks: [] }),
      pick(() => api.taskMetrics(), null),
      pick(() => api.economy(), null),
      pick(() => api.opportunities(), { count: 0, opportunities: [] }),
      pick(() => api.experiments(), null),
      pick(() => api.university(), null),
      pick(() => api.approvals(), { count: 0, approvals: [] }),
      pick(() => api.audit(), { count: 0, entries: [] }),
      pick(() => api.integrations(), null),
      pick(() => api.models(), null),
      pick(() => api.services(), null),
      pick(() => api.dashboard(), null),
      pick(() => api.memoryStats(), null),
      pick(() => api.events(0, 120), { count: 0, events: [] }),
    ]);
    set({
      departments: departments.departments ?? [],
      tasks: tasks.tasks ?? [],
      taskMetrics,
      economy,
      opportunities: opportunities.opportunities ?? [],
      experiments,
      university,
      approvals: approvals.approvals ?? [],
      audit: audit.entries ?? [],
      integrals,
      models,
      services,
      dashboard,
      memoryStats,
      events: (events.events ?? []).slice(0, 250),
    });
  },

  async commandText(text) {
    const result = await api.command(text);
    await Promise.all([get().refreshWorld(), get().refreshPanels()]);
    return result;
  },
}));

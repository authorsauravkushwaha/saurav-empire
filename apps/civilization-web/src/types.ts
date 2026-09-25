/**
 * Shared types for the 3D owner console.
 *
 * These mirror the backend payloads exactly. If the backend changes shape, TypeScript should
 * complain here rather than the world silently rendering something that is not real.
 */

export interface LayoutBuilding {
  id: string;
  name: string;
  city: string;
  city_name: string;
  theme: string;
  shape: 'tower' | 'dome' | 'hall' | 'block' | string;
  pos: [number, number, number];
  size: [number, number, number];
  slots: number;
  purpose: string;
  entry: [number, number, number];
  workstation: [number, number, number];
}

export interface LayoutCity {
  id: string;
  name: string;
  tagline: string;
  theme: string;
  pos: [number, number, number];
  radius: number;
  buildings: LayoutBuilding[];
}

export interface WorldLayout {
  ground_size: number;
  style: string;
  cities: LayoutCity[];
  status_colors: Record<string, string>;
  generated_at: number;
}

export interface WorldAgent {
  id: string;
  name: string;
  role: string;
  rank: string;
  department: string | null;
  department_name: string | null;
  status: string;
  color: string;
  /** [x, z] in world units — the backend owns this, the renderer only draws it. */
  position: [number, number];
  building: string | null;
  target_building: string | null;
  active_task: string | null;
  energy: number;
  performance: number;
  reliability: number;
  certs: string[];
  model_tier: string;
}

export interface WorldState {
  generated_at: number;
  agents: WorldAgent[];
  status_counts: Record<string, number>;
  running: boolean;
  tick: number;
}

export interface Department {
  id: string;
  name: string;
  city: string;
  building: string;
  objective: string;
  kpis: string[];
  status: string;
  parent_id?: string | null;
  boss_agent_id?: string | null;
  budget_inr?: number;
  agent_count?: number;
  meta?: Record<string, any>;
}

export interface Task {
  id: string;
  title: string;
  description?: string;
  task_type: string;
  department_id: string | null;
  assignee_id: string | null;
  status: string;
  priority: number;
  payload?: Record<string, any>;
  result?: Record<string, any>;
  verification?: { passed?: boolean; score?: number; method?: string; issues?: string[] };
  created_at: number;
  started_at?: number | null;
  completed_at?: number | null;
}

export interface EmpireEvent {
  id: number;
  ts: number;
  type: string;
  source: string;
  subject?: string | null;
  severity: string;
  payload: Record<string, any>;
}

export interface Opportunity {
  id: string;
  title: string;
  problem: string;
  customer: string;
  status: string;
  score: number;
  required_capital_inr: number;
  expected_revenue_inr: number;
  legal_risk: string;
  time_to_mvp_days?: number;
  evidence?: any[];
}

export interface RuntimeStatus {
  running: boolean;
  tick_seconds: number;
  ticks: number;
  last_tick: Record<string, number>;
  queue: Record<string, number>;
  safe_mode: boolean;
  kill_switch: boolean;
  errors: string[];
}

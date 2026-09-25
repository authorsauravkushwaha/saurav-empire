/**
 * Event pulses: a short-lived arc that appears when the event bus records something real.
 *
 * The origin comes from the event's own `source` (or an explicit building in its payload) — never
 * from a random pick — so what you see is where the event actually came from.
 */
import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useEmpire } from '../store';
import type { EmpireEvent } from '../types';

const SOURCE_BUILDINGS: Record<string, string> = {
  tasks: 'mission-control',
  workflow: 'mission-control',
  'workflow-service': 'mission-control',
  agent_runtime: 'agent-registry',
  registry: 'agent-registry',
  agent: 'agent-registry',
  'agent-service': 'agent-registry',
  university: 'ai-university',
  'university-service': 'ai-university',
  economy: 'economic-command',
  'economy-service': 'economic-command',
  research: 'web-research',
  'research-service': 'web-research',
  finance: 'revenue-accounting',
  'finance-service': 'revenue-accounting',
  memory: 'memory-archive',
  'memory-service': 'memory-archive',
  model_router: 'analytics-engine',
  'model-service': 'analytics-engine',
  integration: 'automation-control',
  'integration-service': 'automation-control',
  security: 'security-center',
  'security-service': 'security-center',
  killswitch: 'security-center',
  'command-center': 'owner-command-center',
  gateway: 'owner-command-center',
  world: 'observability',
  'world-service': 'observability',
  repair: 'agent-registry',
};

const FALLBACK_TARGETS = ['analytics-engine', 'memory-archive', 'event-stream', 'data-warehouse'];
const POOL = 16;

interface Pulse {
  from: THREE.Vector3;
  to: THREE.Vector3;
  started: number;
  ttl: number;
  color: string;
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#ef4444',
  error: '#ef4444',
  warning: '#f59e0b',
  notice: '#22d3ee',
  info: '#38bdf8',
  debug: '#8b93a7',
};

export function EventFlows() {
  const events = useEmpire((s) => s.events);
  const layout = useEmpire((s) => s.layout);
  const lastSeen = useRef(0);
  const pulses = useRef<Pulse[]>([]);
  const meshes = useRef<(THREE.Mesh | null)[]>([]);
  const accumulator = useRef(0);
  const scratch = useMemo(() => new THREE.Vector3(), []);
  const pending = useRef<EmpireEvent[]>([]);

  const positions = useMemo(() => {
    const map: Record<string, THREE.Vector3> = {};
    layout?.cities.forEach((city) =>
      city.buildings.forEach((b) => {
        map[b.id] = new THREE.Vector3(b.pos[0], 0, b.pos[2]);
      }),
    );
    return map;
  }, [layout]);

  // Collect new events as they arrive (cheap: no state churn).
  const seen = useMemo(() => new Set<number>(), []);
  for (const event of events) {
    if (!seen.has(event.id)) {
      seen.add(event.id);
      if (events.length) pending.current.push(event);
    }
  }
  pending.current = pending.current.slice(-POOL);

  useFrame((state, delta) => {
    accumulator.current += delta;
    if (accumulator.current < 0.05) return;     // ~20 Hz
    accumulator.current = 0;

    const now = state.clock.elapsedTime;
    while (pending.current.length && pulses.current.length < POOL) {
      const event = pending.current.shift() as EmpireEvent;
      const originId = (typeof event.payload?.building === 'string' && positions[event.payload.building])
        ? event.payload.building
        : SOURCE_BUILDINGS[event.source ?? ''] ?? 'mission-control';
      const targetId = (event.subject && positions[event.subject])
        ? event.subject
        : FALLBACK_TARGETS[event.id % FALLBACK_TARGETS.length];
      const from = positions[originId] ?? positions['observability'];
      const to = positions[targetId] ?? positions['observability'];
      if (!from || !to || from === to) continue;
      pulses.current.push({
        from: from.clone(),
        to: to.clone(),
        started: now,
        ttl: event.severity === 'error' || event.severity === 'critical' ? 2.2 : 1.5,
        color: SEVERITY_COLOR[event.severity] ?? '#38bdf8',
      });
    }

    pulses.current = pulses.current.filter((p) => now - p.started < p.ttl);
    for (let i = 0; i < POOL; i += 1) {
      const mesh = meshes.current[i];
      if (!mesh) continue;
      const pulse = pulses.current[i];
      if (!pulse) {
        mesh.visible = false;
        continue;
      }
      const t = (now - pulse.started) / pulse.ttl;
      scratch.copy(pulse.from).lerp(pulse.to, t);
      scratch.y = 4 + Math.sin(Math.PI * t) * 14;
      mesh.position.copy(scratch);
      mesh.visible = true;
      mesh.scale.setScalar(1 - t * 0.5);
      (mesh.material as THREE.MeshBasicMaterial).color.set(pulse.color);
      (mesh.material as THREE.MeshBasicMaterial).opacity = 0.95 * (1 - t);
    }
  });

  return (
    <group>
      {Array.from({ length: POOL }).map((_, i) => (
        <mesh
          key={i}
          visible={false}
          ref={(el) => {
            meshes.current[i] = el;
          }}
        >
          <sphereGeometry args={[0.9, 10, 10]} />
          <meshBasicMaterial color="#38bdf8" transparent opacity={0.9} />
        </mesh>
      ))}
    </group>
  );
}

/**
 * The workforce, rendered exactly as the backend reports it.
 *
 * Positions come from /api/world/world/state. The renderer interpolates between samples so motion
 * is smooth, and colours come from the service's status palette — the client never invents
 * activity, it only draws what the runtime is doing.
 */
import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import { useEmpire } from '../store';
import type { WorldAgent } from '../types';

function AgentMesh({ agent, target }: { agent: WorldAgent; target: THREE.Vector3 }) {
  const select = useEmpire((s) => s.select);
  const selectedAgent = useEmpire((s) => s.selectedAgent);
  const showLabels = useEmpire((s) => s.showLabels);
  const group = useRef<THREE.Group>(null);
  const [hovered, setHovered] = useState(false);
  const selected = selectedAgent === agent.id;

  const color = agent.color || '#8b93a7';
  const phase = useMemo(() => Math.random() * Math.PI * 2, []);

  useFrame((state, delta) => {
    if (!group.current) return;
    const pos = group.current.position;
    pos.lerp(target, Math.min(1, delta * 4.5));
    // A gentle bob keeps a crowd readable without pretending anyone is moving who is not.
    pos.y = 2.2 + Math.sin(state.clock.elapsedTime * 2 + phase) * 0.25;
    if (selected || hovered) {
      group.current.scale.setScalar(THREE.MathUtils.lerp(group.current.scale.x, 1.35, delta * 8));
    } else {
      group.current.scale.setScalar(THREE.MathUtils.lerp(group.current.scale.x, 1, delta * 8));
    }
  });

  const rankScale = agent.rank === 'SUPREME' || agent.rank === 'COMMANDER' ? 1.35
    : agent.rank === 'MANAGER' ? 1.15 : 1;

  return (
    <group ref={group} position={[target.x, 2.2, target.z]}>
      <mesh
        scale={rankScale}
        onClick={(e) => {
          e.stopPropagation();
          select(agent.id);
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHovered(true);
        }}
        onPointerOut={() => setHovered(false)}
      >
        <capsuleGeometry args={[0.85, 1.9, 6, 12]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={agent.status === 'ERROR' ? 1.1 : selected || hovered ? 0.9 : 0.35}
          roughness={0.35}
          metalness={0.25}
        />
      </mesh>
      <mesh position={[0, -2.0, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.2, 1.5, 24]} />
        <meshBasicMaterial color={color} transparent opacity={selected ? 0.95 : 0.35} />
      </mesh>
      {(selected || hovered || (showLabels && (agent.status === 'TRAVELING' || agent.status === 'ERROR'))) && (
        <Html center distanceFactor={110} position={[0, 3.4, 0]} zIndexRange={[30, 0]}>
          <div className={`a-label${selected ? ' selected' : ''}`}>
            <span className="a-name">{agent.name}</span>
            <span className="a-status" style={{ color }}>
              {agent.status}
            </span>
          </div>
        </Html>
      )}
    </group>
  );
}

export function Workforce() {
  const agents = useEmpire((s) => s.agents);
  const layout = useEmpire((s) => s.layout);

  // Building-id → world [x, z] lookup, straight from the layout payload.
  const buildingPos = useMemo(() => {
    const map: Record<string, [number, number]> = {};
    layout?.cities.forEach((c) =>
      c.buildings.forEach((b) => {
        map[b.id] = [b.pos[0], b.pos[2]];
      }),
    );
    return map;
  }, [layout]);

  return (
    <group>
      {agents.map((agent) => {
        const target = new THREE.Vector3(
          agent.position?.[0] ?? 0,
          2.2,
          agent.position?.[1] ?? 0,
        );
        // If an agent has no recorded position yet, park it at the building it belongs to
        // instead of at the origin of the world.
        if (!agent.position || (agent.position[0] === 0 && agent.position[1] === 0)) {
          const home = buildingPos[(agent.target_building ?? agent.building) as string];
          if (home) target.set(home[0], 2.2, home[1]);
        }
        return <AgentMesh key={agent.id} agent={agent} target={target} />;
      })}
    </group>
  );
}

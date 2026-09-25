/**
 * Cities and buildings.
 *
 * Geometry comes from the world-service layout (config/civilization.yaml). Nothing here is
 * decorative invention: a building glows because agents or tasks are actually working there.
 */
import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import { useEmpire } from '../store';
import type { LayoutBuilding, LayoutCity } from '../types';

interface BuildingActivity {
  agentsInside: number;
  agentsEnRoute: number;
  openTasks: number;
  intensity: number;
}

export function useBuildingActivity(): Record<string, BuildingActivity> {
  const agents = useEmpire((s) => s.agents);
  const tasks = useEmpire((s) => s.tasks);
  return useMemo(() => {
    const activity: Record<string, BuildingActivity> = {};
    const touch = (id?: string | null): BuildingActivity | null => {
      if (!id) return null;
      activity[id] = activity[id] ?? { agentsInside: 0, agentsEnRoute: 0, openTasks: 0, intensity: 0 };
      return activity[id];
    };
    for (const agent of agents) {
      const inside = touch(agent.building);
      if (inside) inside.agentsInside += 1;
      const heading = touch(agent.target_building);
      if (heading && agent.target_building !== agent.building) heading.agentsEnRoute += 1;
    }
    for (const task of tasks) {
      if (['DONE', 'CANCELLED', 'FAILED'].includes(task.status)) continue;
      const dept = task.department_id;
      const building = dept ? (activity[`__dept__${dept}`] as any) : null;
      if (building) building.openTasks += 1;
    }
    for (const key of Object.keys(activity)) {
      const a = activity[key];
      a.intensity = Math.min(1, a.agentsInside / 8 + a.agentsEnRoute / 6);
    }
    return activity;
  }, [agents, tasks]);
}

function BuildingMesh({ building, activity }: { building: LayoutBuilding; activity?: BuildingActivity }) {
  const selectBuilding = useEmpire((s) => s.selectBuilding);
  const selectCity = useEmpire((s) => s.selectCity);
  const selectedBuilding = useEmpire((s) => s.selectedBuilding);
  const showLabels = useEmpire((s) => s.showLabels);
  const [hovered, setHovered] = useState(false);
  const glow = useRef<THREE.Mesh>(null);

  const [w, h, d] = building.size;
  const selected = selectedBuilding === building.id;
  const intensity = activity?.intensity ?? 0;
  const base = useMemo(() => new THREE.Color(building.theme), [building.theme]);

  useFrame((state) => {
    if (!glow.current) return;
    const pulse = 0.5 + 0.5 * Math.sin(state.clock.elapsedTime * 1.6 + building.pos[0] * 0.01);
    const target = 0.12 + intensity * (0.45 + 0.35 * pulse);
    (glow.current.material as THREE.MeshStandardMaterial).emissiveIntensity = target;
  });

  const geometry = () => {
    switch (building.shape) {
      case 'dome':
        return <sphereGeometry args={[Math.max(w, d) / 2, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />;
      case 'tower':
        return <cylinderGeometry args={[w / 2.4, w / 2, h, 8]} />;
      default:
        return <boxGeometry args={[w, h, d]} />;
    }
  };

  return (
    <group position={building.pos}>
      <mesh
        castShadow
        receiveShadow
        position={[0, h / 2, 0]}
        onClick={(e) => {
          e.stopPropagation();
          selectCity(building.city);
          selectBuilding(building.id, building.city);
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHovered(true);
        }}
        onPointerOut={() => setHovered(false)}
      >
        {geometry()}
        <meshStandardMaterial
          color={base}
          emissive={base}
          emissiveIntensity={0.08 + intensity * 0.25}
          metalness={0.35}
          roughness={0.45}
          transparent
          opacity={hovered || selected ? 1 : 0.9}
        />
      </mesh>
      <mesh ref={glow} position={[0, h + 1.1, 0]}>
        <sphereGeometry args={[1.1 + (hovered ? 0.5 : 0), 16, 16]} />
        <meshStandardMaterial color={base} emissive={base} emissiveIntensity={0.2} />
      </mesh>
      {(hovered || selected || (showLabels && intensity > 0.55)) && (
        <Html center distanceFactor={90} position={[0, h + 6, 0]} zIndexRange={[20, 0]}>
          <div className={`b-label${selected ? ' selected' : ''}`} style={{ borderColor: building.theme }}>
            <span className="b-name">{building.name}</span>
            <span className="b-meta">
              {activity?.agentsInside ?? 0} inside
              {activity?.agentsEnRoute ? ` · ${activity.agentsEnRoute} en route` : ''}
            </span>
          </div>
        </Html>
      )}
    </group>
  );
}

export function CityPlate({ city }: { city: LayoutCity }) {
  const selectCity = useEmpire((s) => s.selectCity);
  const selectedCity = useEmpire((s) => s.selectedCity);
  const activity = useBuildingActivity();
  const selected = selectedCity === city.id;
  const agents = useEmpire((s) => s.agents);

  const population = useMemo(
    () => agents.filter((a) => (a.building ?? '').startsWith('') && city.buildings.some((b) => b.id === a.building)).length,
    [agents, city],
  );

  return (
    <group position={city.pos}>
      <mesh
        position={[0, -0.6, 0]}
        receiveShadow
        onClick={(e) => {
          e.stopPropagation();
          selectCity(city.id);
        }}
      >
        <cylinderGeometry args={[city.radius, city.radius + 6, 1.2, 64]} />
        <meshStandardMaterial
          color={city.theme}
          emissive={city.theme}
          emissiveIntensity={selected ? 0.22 : 0.07}
          transparent
          opacity={0.32}
          roughness={0.8}
        />
      </mesh>
      <mesh position={[0, -0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[city.radius - 1.2, city.radius, 96]} />
        <meshBasicMaterial color={city.theme} transparent opacity={selected ? 0.9 : 0.4} />
      </mesh>
      <Html center distanceFactor={150} position={[0, 6, city.radius * 0.55]} zIndexRange={[10, 0]}>
        <div className="city-label" style={{ borderColor: city.theme }}>
          <div className="city-name">{city.name}</div>
          <div className="city-meta">
            {population} agents · {city.buildings.length} buildings
          </div>
        </div>
      </Html>
      {city.buildings.map((b) => (
        <BuildingMesh key={b.id} building={b} activity={activity[b.id]} />
      ))}
    </group>
  );
}

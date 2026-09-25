/**
 * Camera control: overview / command-centre / city-ring presets, orbit, and agent follow.
 * The camera only ever looks at positions that came from the backend.
 */
import { useEffect, useRef } from 'react';
import { OrbitControls } from '@react-three/drei';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { useEmpire } from '../store';

const PRESETS: Record<string, { pos: [number, number, number]; target: [number, number, number] }> = {
  overview: { pos: [0, 300, 330], target: [0, 0, 0] },
  command: { pos: [0, 130, 120], target: [0, 0, 0] },
  ring: { pos: [330, 220, 330], target: [0, 0, 0] },
};

export function CameraRig() {
  const preset = useEmpire((s) => s.cameraPreset);
  const followAgent = useEmpire((s) => s.followAgent);
  const selectedAgent = useEmpire((s) => s.selectedAgent);
  const selectedBuilding = useEmpire((s) => s.selectedBuilding);
  const layout = useEmpire((s) => s.layout);
  const agents = useEmpire((s) => s.agents);

  const controls = useRef<any>(null);
  const desiredPos = useRef(new THREE.Vector3(...PRESETS.overview.pos));
  const desiredTarget = useRef(new THREE.Vector3(0, 0, 0));
  const camera = useThree((s) => s.camera);
  const intro = useRef(true);

  // Preset changes and building selections move the camera; the owner can always take over.
  useEffect(() => {
    if (preset) desiredPos.current.set(...PRESETS[preset].pos);
    desiredTarget.current.set(...PRESETS[preset].target);
  }, [preset]);

  useEffect(() => {
    if (!selectedBuilding || !layout) return;
    for (const city of layout.cities) {
      const building = city.buildings.find((b) => b.id === selectedBuilding);
      if (building) {
        desiredTarget.current.set(building.pos[0], building.size[1] / 2, building.pos[2]);
        desiredPos.current.set(
          building.pos[0] + building.size[0] * 2.4,
          building.size[1] * 3.2 + 40,
          building.pos[2] + building.size[2] * 2.6,
        );
        break;
      }
    }
  }, [selectedBuilding, layout]);

  useFrame((_, delta) => {
    const agent = followAgent && selectedAgent ? agents.find((a) => a.id === selectedAgent) : null;
    if (agent && agent.position) {
      desiredTarget.current.set(agent.position[0], 3, agent.position[1]);
      desiredPos.current.set(agent.position[0] + 42, 36, agent.position[1] + 42);
    }
    const speed = intro.current ? delta * 0.9 : delta * 2.4;
    camera.position.lerp(desiredPos.current, Math.min(1, speed));
    if (controls.current) {
      controls.current.target.lerp(desiredTarget.current, Math.min(1, delta * 2.4));
      controls.current.update();
    }
    if (intro.current && camera.position.distanceTo(desiredPos.current) < 24) intro.current = false;
  });

  return (
    <OrbitControls
      ref={controls}
      enableDamping
      dampingFactor={0.08}
      maxPolarAngle={Math.PI / 2.08}
      minDistance={18}
      maxDistance={900}
      makeDefault
    />
  );
}

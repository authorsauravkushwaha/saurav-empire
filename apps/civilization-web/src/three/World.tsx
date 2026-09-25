/**
 * The world: 9 cities, their buildings, the workforce and the event traffic between them.
 *
 * Rule (spec §4, constitution): REAL BACKEND STATE → 3D VISUALIZATION. Nothing is spawned,
 * animated or lit because it would look good. If the backend is silent, the world is still.
 */
import { Suspense, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { Html, Stars, useTexture } from '@react-three/drei';
import * as THREE from 'three';
import { useEmpire } from '../store';
import { CityPlate } from './City';
import { Workforce } from './Agents';
import { EventFlows } from './EventFlows';
import { CameraRig } from './CameraRig';

function Ground({ size }: { size: number }) {
  const grid = useMemo(() => size, [size]);
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.2, 0]} receiveShadow>
        <planeGeometry args={[size, size]} />
        <meshStandardMaterial color="#080b13" roughness={1} metalness={0.1} />
      </mesh>
      <gridHelper args={[grid, 90, '#141d33', '#0d1424']} position={[0, -1.15, 0]} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.1, 0]}>
        <ringGeometry args={[300, 302, 128]} />
        <meshBasicMaterial color="#1b2540" transparent opacity={0.6} />
      </mesh>
    </group>
  );
}

function SceneContent() {
  const layout = useEmpire((s) => s.layout);
  if (!layout) return null;
  return (
    <>
      <Ground size={layout.ground_size} />
      {layout.cities.map((city) => (
        <CityPlate key={city.id} city={city} />
      ))}
      <Workforce />
      <EventFlows />
    </>
  );
}

export function WorldCanvas() {
  const layout = useEmpire((s) => s.layout);
  const unlockState = useEmpire((s) => s.unlocked);
  return (
    <Canvas
      shadows
      dpr={[1, 1.8]}
      camera={{ position: [0, 670, 524], fov: 45, near: 1, far: 6000 }}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      onPointerMissed={() => useEmpire.getState().select(null)}
    >
      <color attach="background" args={['#05060a']} />
      <fog attach="fog" args={['#05060a', 700, 2600]} />
      <ambientLight intensity={0.55} />
      <hemisphereLight args={['#5b7cff', '#0a0d16', 0.6]} />
      <directionalLight
        position={[220, 340, 180]}
        intensity={1.15}
        castShadow
        shadow-mapSize={[2048, 2048]}
      />
      <pointLight position={[0, 120, 0]} intensity={0.9} color="#7c5cff" distance={520} />
      <pointLight position={[-260, 90, -220]} intensity={0.5} color="#38bdf8" distance={460} />
      <Stars radius={1400} depth={180} count={2600} factor={6} saturation={0} fade speed={0.4} />
      <Suspense fallback={null}>
        {unlockState && layout ? (
          <SceneContent />
        ) : (
          <Html center>
            <div className="canvas-note">
              {layout ? 'Select the owner token to stream live state.' : 'Loading world layout…'}
            </div>
          </Html>
        )}
      </Suspense>
      <CameraRig />
    </Canvas>
  );
}

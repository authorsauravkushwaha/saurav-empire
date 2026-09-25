/**
 * Application shell: one canvas, one HUD, one event stream.
 *
 * Polling keeps the world truthful at a low, predictable cost; the WebSocket adds events the
 * moment they happen. Nothing is animated without a backend fact behind it.
 */
import { useEffect } from 'react';
import { openEventStream, getToken } from './api';
import { useEmpire } from './store';
import { WorldCanvas } from './three/World';
import { CommandBar, EventFeed, Inspector, LeftRail, TopBar } from './ui/Hud';
import { Panels } from './ui/Panels';
import { LockScreen } from './ui/LockScreen';

export default function App() {
  const unlocked = useEmpire((s) => s.unlocked);
  const paused = useEmpire((s) => s.paused);
  const pushEvent = useEmpire((s) => s.pushEvent);
  const setStreamUp = useEmpire((s) => s.setStreamUp);
  const refreshWorld = useEmpire((s) => s.refreshWorld);
  const refreshPanels = useEmpire((s) => s.refreshPanels);
  const bootstrap = useEmpire((s) => s.bootstrap);

  // A stored token from a previous session is re-validated, never trusted blindly.
  useEffect(() => {
    const stored = getToken();
    if (stored) void useEmpire.getState().unlock(stored);
  }, []);

  useEffect(() => {
    if (!unlocked) return;
    const stopStream = openEventStream(pushEvent, setStreamUp);
    const world = setInterval(() => void refreshWorld(), 1600);
    const panels = setInterval(() => void refreshPanels(), 6500);
    return () => {
      stopStream();
      clearInterval(world);
      clearInterval(panels);
    };
  }, [unlocked, paused, pushEvent, setStreamUp, refreshWorld, refreshPanels, bootstrap]);

  if (!unlocked) return <LockScreen />;

  return (
    <div className="app">
      <WorldCanvas />
      <TopBar />
      <LeftRail />
      <Inspector />
      <EventFeed />
      <CommandBar />
      <Panels />
    </div>
  );
}

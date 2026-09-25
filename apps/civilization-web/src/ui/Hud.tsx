/**
 * HUD: the owner's head-up display over the world.
 *
 * Every number shown here is fetched from a service or transcribed from an event. Where a number
 * is an estimate, the backend's own label is carried through ("Estimate", "Not verified", …).
 */
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { useEmpire } from '../store';

const fmt = (n: number | null | undefined, digits = 0) =>
  n === null || n === undefined || Number.isNaN(n) ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: digits });

const timeOf = (ts?: number | null) => (ts ? new Date(ts * 1000).toLocaleTimeString() : '—');

export function TopBar() {
  const runtime = useEmpire((s) => s.runtime);
  const economy = useEmpire((s) => s.economy);
  const taskMetrics = useEmpire((s) => s.taskMetrics);
  const agents = useEmpire((s) => s.agents);
  const departments = useEmpire((s) => s.departments);
  const streamUp = useEmpire((s) => s.streamUp);
  const lastSync = useEmpire((s) => s.lastSync);
  const lastError = useEmpire((s) => s.lastError);
  const paused = useEmpire((s) => s.paused);
  const setPaused = useEmpire((s) => s.setPaused);
  const setPanel = useEmpire((s) => s.setPanel);
  const lock = useEmpire((s) => s.lock);
  const setCameraPreset = useEmpire((s) => s.setCameraPreset);
  const setLabels = useEmpire((s) => s.setLabels);
  const showLabels = useEmpire((s) => s.showLabels);

  const working = agents.filter((a) => !['IDLE', 'ERROR', 'BLOCKED'].includes(a.status)).length;
  const revenue = economy?.revenue_inr ?? economy?.honesty?.verified_revenue_inr ?? null;
  const queue = runtime?.queue ?? {};

  return (
    <header className="topbar">
      <div className="brand">
        <span className={`dot ${runtime?.running ? 'live' : 'dead'}`} />
        <div>
          <div className="brand-title">SAURAV AI CIVILIZATION</div>
          <div className="brand-sub">
            {runtime?.running ? `runtime tick ${fmt(runtime.ticks)} · ${runtime.tick_seconds}s` : 'runtime stopped'}
            {runtime?.safe_mode ? ' · SAFE MODE' : ''}
            {runtime?.kill_switch ? ' · KILL SWITCH' : ''}
          </div>
        </div>
      </div>

      <div className="kpis">
        <Kpi label="verified revenue" value={`₹${fmt(revenue, 2)}`} hint="ledger, verified only" />
        <Kpi label="workforce" value={fmt(agents.length)} hint={`${departments.length} departments`} />
        <Kpi label="working now" value={fmt(working)} hint={`${fmt(agents.length - working)} idle/other`} />
        <Kpi label="tasks done" value={fmt(taskMetrics?.completed)} hint={`${fmt(taskMetrics?.failed)} failed`} />
        <Kpi label="queue" value={fmt((queue.QUEUED ?? 0) + (queue.ASSIGNED ?? 0))} hint="queued + assigned" />
      </div>

      <div className="topbar-actions">
        <span className={`stream ${streamUp ? 'up' : 'down'}`}>{streamUp ? 'live feed' : 'feed reconnecting'}</span>
        <span className="sync">synced {lastSync ? new Date(lastSync).toLocaleTimeString() : '—'}</span>
        <button onClick={() => setCameraPreset('overview')}>overview</button>
        <button onClick={() => setCameraPreset('ring')}>ring</button>
        <button onClick={() => setLabels(!showLabels)}>{showLabels ? 'labels on' : 'labels off'}</button>
        <button className={paused ? 'warn' : ''} onClick={() => setPaused(!paused)}>
          {paused ? 'frozen' : 'freeze view'}
        </button>
        <button onClick={() => setPanel('command')}>command</button>
        <button className="ghost" onClick={lock}>lock</button>
      </div>
      {lastError && <div className="topbar-error">{lastError}</div>}
    </header>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  );
}

export function LeftRail() {
  const layout = useEmpire((s) => s.layout);
  const agents = useEmpire((s) => s.agents);
  const departments = useEmpire((s) => s.departments);
  const selectCity = useEmpire((s) => s.selectCity);
  const selectedCity = useEmpire((s) => s.selectedCity);
  const selectBuilding = useEmpire((s) => s.selectBuilding);
  const selectedBuilding = useEmpire((s) => s.selectedBuilding);
  const [tab, setTab] = useState<'cities' | 'departments'>('cities');

  const byCity = useMemo(() => {
    const map: Record<string, number> = {};
    agents.forEach((a) => {
      const city = layout?.cities.find((c) => c.buildings.some((b) => b.id === a.building));
      if (city) map[city.id] = (map[city.id] ?? 0) + 1;
    });
    return map;
  }, [agents, layout]);

  return (
    <aside className="panel left">
      <div className="panel-tabs">
        <button className={tab === 'cities' ? 'active' : ''} onClick={() => setTab('cities')}>
          Cities
        </button>
        <button className={tab === 'departments' ? 'active' : ''} onClick={() => setTab('departments')}>
          Departments
        </button>
      </div>

      {tab === 'cities' && (
        <div className="rail-list">
          {layout?.cities.map((city) => (
            <div key={city.id} className={`city-row${selectedCity === city.id ? ' selected' : ''}`}>
              <div
                className="city-head"
                onClick={() => selectCity(selectedCity === city.id ? null : city.id)}
              >
                <span className="swatch" style={{ background: city.theme }} />
                <span className="city-name">{city.name}</span>
                <span className="count">{byCity[city.id] ?? 0}</span>
              </div>
              {selectedCity === city.id && (
                <div className="city-buildings">
                  {city.buildings.map((b) => (
                    <button
                      key={b.id}
                      className={`building-row${selectedBuilding === b.id ? ' selected' : ''}`}
                      onClick={() => selectBuilding(b.id, city.id)}
                      title={b.purpose}
                    >
                      <span>{b.name}</span>
                      <span className="slots">{b.slots}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === 'departments' && (
        <div className="rail-list">
          {departments.map((d) => {
            const staff = agents.filter((a) => a.department === d.id);
            return (
              <button
                key={d.id}
                className="dept-row"
                onClick={() => selectBuilding(d.building, d.city)}
                title={d.objective}
              >
                <div className="dept-head">
                  <span>{d.name}</span>
                  <span className="count">{staff.length}</span>
                </div>
                <div className="dept-kpis">{(d.kpis ?? []).slice(0, 3).join(' · ') || 'no KPI declared'}</div>
              </button>
            );
          })}
          {!departments.length && <div className="empty">No departments loaded.</div>}
        </div>
      )}
    </aside>
  );
}

export function Inspector() {
  const selectedAgent = useEmpire((s) => s.selectedAgent);
  const selectedBuilding = useEmpire((s) => s.selectedBuilding);
  const agents = useEmpire((s) => s.agents);
  const layout = useEmpire((s) => s.layout);
  const tasks = useEmpire((s) => s.tasks);
  const departments = useEmpire((s) => s.departments);
  const select = useEmpire((s) => s.select);
  const follow = useEmpire((s) => s.followAgent);
  const setFollow = useEmpire((s) => s.setFollow);
  const [detail, setDetail] = useState<any>(null);

  const agent = agents.find((a) => a.id === selectedAgent) ?? null;
  const building = useMemo(() => {
    if (!selectedBuilding || !layout) return null;
    for (const city of layout.cities) {
      const found = city.buildings.find((b) => b.id === selectedBuilding);
      if (found) return found;
    }
    return null;
  }, [selectedBuilding, layout]);

  useEffect(() => {
    if (!agent) {
      setDetail(null);
      return;
    }
    let live = true;
    api
      .agentDetail(agent.id)
      .then((d) => live && setDetail(d))
      .catch(() => live && setDetail(null));
    return () => {
      live = false;
    };
  }, [agent?.id]);

  if (!agent && !building) {
    return (
      <aside className="panel right">
        <div className="panel-title">Inspector</div>
        <div className="empty">
          Click an agent to see its record, or a building to see its purpose and staffing.
        </div>
      </aside>
    );
  }

  if (building) {
    const staff = agents.filter((a) => a.building === building.id || a.target_building === building.id);
    const here = staff.filter((a) => a.building === building.id).length;
    const incoming = staff.length - here;
    return (
      <aside className="panel right">
        <div className="panel-title">{building.name}</div>
        <div className="kv">
          <Row k="city" v={building.city_name} />
          <Row k="purpose" v={building.purpose} />
          <Row k="slots" v={String(building.slots)} />
          <Row k="present" v={String(here)} />
          <Row k="en route" v={String(incoming)} />
        </div>
        <div className="panel-title small">present &amp; inbound</div>
        <div className="mini-list">
          {staff.slice(0, 24).map((a) => (
            <button key={a.id} className="mini-row" onClick={() => select(a.id)}>
              <span className="swatch" style={{ background: a.color }} />
              <span>{a.name}</span>
              <span className="muted">{a.status}</span>
            </button>
          ))}
          {!staff.length && <div className="empty">Nobody is assigned here right now.</div>}
        </div>
      </aside>
    );
  }

  const department = departments.find((d) => d.id === agent!.department);
  const agentTasks = detail?.tasks ?? tasks.filter((t) => t.assignee_id === agent!.id);

  return (
    <aside className="panel right">
      <div className="panel-title">
        {agent!.name}
        <button className="link" onClick={() => select(null)}>
          close
        </button>
      </div>
      <div className="kv">
        <Row k="role" v={agent!.role} />
        <Row k="rank" v={agent!.rank} />
        <Row k="department" v={department?.name ?? agent!.department_name ?? '—'} />
        <Row k="status" v={agent!.status} />
        <Row k="model tier" v={agent!.model_tier} />
        <Row k="building" v={agent!.building ?? '—'} />
        <Row k="energy" v={fmt(agent!.energy, 1)} />
        <Row k="performance" v={fmt(agent!.performance, 3)} />
        <Row k="reliability" v={fmt(agent!.reliability, 3)} />
        <Row k="certificates" v={(agent!.certs ?? []).join(', ') || 'none'} />
      </div>
      <label className="follow">
        <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
        follow this agent
      </label>
      <div className="panel-title small">recent tasks</div>
      <div className="mini-list">
        {agentTasks.slice(0, 10).map((t: any) => (
          <div key={t.id} className="mini-row static">
            <span>{t.title?.slice(0, 44)}</span>
            <span className={`badge ${String(t.status).toLowerCase()}`}>{t.status}</span>
          </div>
        ))}
        {!agentTasks.length && <div className="empty">No tasks on record for this agent.</div>}
      </div>
      {detail?.memory?.length > 0 && (
        <>
          <div className="panel-title small">memory</div>
          <div className="mini-list">
            {detail.memory.slice(0, 5).map((m: any) => (
              <div key={m.id} className="mini-row static">
                <span className="muted">{m.layer}</span>
                <span>{String(m.content).slice(0, 70)}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="row">
      <span className="k">{k}</span>
      <span className="v">{v}</span>
    </div>
  );
}

export function EventFeed() {
  const events = useEmpire((s) => s.events);
  const [filter, setFilter] = useState('');
  const shown = useMemo(
    () => events.filter((e) => !filter || e.type.includes(filter)).slice(0, 60),
    [events, filter],
  );
  const sev = (s: string) => (s === 'critical' || s === 'error' ? 'err' : s === 'warning' ? 'warn' : 'info');

  return (
    <footer className="panel feed">
      <div className="feed-head">
        <span className="panel-title small">Event stream (append-only)</span>
        <input
          placeholder="filter by type…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <div className="feed-rows">
        {shown.map((e) => (
          <div key={e.id} className={`feed-row ${sev(e.severity)}`}>
            <span className="t">{timeOf(e.ts)}</span>
            <span className="type">{e.type}</span>
            <span className="src muted">{e.source}</span>
            <span className="payload">{summarise(e.payload)}</span>
          </div>
        ))}
        {!shown.length && <div className="empty">No events yet.</div>}
      </div>
    </footer>
  );
}

function summarise(payload: Record<string, any> | undefined): string {
  if (!payload) return '';
  const parts: string[] = [];
  for (const [k, v] of Object.entries(payload)) {
    if (v === null || v === undefined || v === '') continue;
    parts.push(`${k}=${typeof v === 'object' ? JSON.stringify(v).slice(0, 40) : String(v).slice(0, 46)}`);
    if (parts.length >= 4) break;
  }
  return parts.join('  ');
}

export function CommandBar() {
  const commandText = useEmpire((s) => s.commandText);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const setPanel = useEmpire((s) => s.setPanel);

  const submit = async () => {
    const value = text.trim();
    if (!value) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await commandText(value);
      setResult(res);
      setText('');
    } catch (err) {
      setError(String(err));
    }
    setBusy(false);
  };

  return (
    <div className="commandbar">
      <div className="command-input">
        <span className="prompt">›</span>
        <input
          placeholder="talk to the empire — “status report”, “hire 3 agents for research-lab”, “create a department for paid templates”"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void submit();
          }}
        />
        <button onClick={() => void submit()} disabled={busy}>
          {busy ? 'working…' : 'send'}
        </button>
        <button className="ghost" onClick={() => setPanel('command')}>
          all commands
        </button>
      </div>
      {result && (
        <div className="command-result">
          <strong>{result.intent ?? 'executed'}</strong> {result.summary ?? ''}
          {result.requires_approval && <span className="badge pending">owner approval required</span>}
          <button className="link" onClick={() => setResult(null)}>
            dismiss
          </button>
        </div>
      )}
      {error && <div className="command-error">{error}</div>}
    </div>
  );
}

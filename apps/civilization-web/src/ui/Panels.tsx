/**
 * Domain panels. Each one is a window onto one service: nothing here is computed locally
 * except presentation (sorting, truncation, percentages of a total the backend supplied).
 */
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { useEmpire, type PanelId } from '../store';

const TABS: { id: PanelId; label: string }[] = [
  { id: 'command', label: 'Owner Command' },
  { id: 'agents', label: 'Workforce' },
  { id: 'departments', label: 'Departments' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'economy', label: 'Economy' },
  { id: 'university', label: 'University' },
  { id: 'approvals', label: 'Approvals' },
  { id: 'security', label: 'Security & Audit' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'models', label: 'Models' },
  { id: 'events', label: 'Events' },
];

export function Panels() {
  const panel = useEmpire((s) => s.panel);
  const setPanel = useEmpire((s) => s.setPanel);

  if (panel === 'none') return null;

  return (
    <section className="panels">
      <nav className="panel-tabs wide">
        {TABS.map((t) => (
          <button key={t.id} className={panel === t.id ? 'active' : ''} onClick={() => setPanel(t.id)}>
            {t.label}
          </button>
        ))}
        <button className="close" onClick={() => setPanel('none')}>
          close
        </button>
      </nav>
      <div className="panel-body">
        {panel === 'command' && <CommandPanel />}
        {panel === 'agents' && <AgentsPanel />}
        {panel === 'departments' && <DepartmentsPanel />}
        {panel === 'tasks' && <TasksPanel />}
        {panel === 'economy' && <EconomyPanel />}
        {panel === 'university' && <UniversityPanel />}
        {panel === 'approvals' && <ApprovalsPanel />}
        {panel === 'security' && <SecurityPanel />}
        {panel === 'integrations' && <IntegrationsPanel />}
        {panel === 'models' && <ModelsPanel />}
        {panel === 'events' && <EventsPanel />}
      </div>
    </section>
  );
}

function Table({ head, rows }: { head: string[]; rows: (JSX.Element | string)[][] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          {head.map((h) => (
            <th key={h}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>
            {row.map((cell, j) => (
              <td key={j}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The master prompt §28 DECISION OUTPUT STANDARD, rendered so the owner sees the reasoning. */
function DecisionStandard({ d }: { d: any }) {
  if (!d?.verdict || typeof d.verdict !== 'object') return null;
  const v = d.verdict;
  const cls = String(d.classification ?? v.classification ?? '');
  const tone = cls === 'STOP' || cls === 'REJECT' ? 'failed'
    : cls === 'DEFER' || cls === 'TEST' ? 'pending'
      : cls === 'SCALE' || cls === 'CONTINUE' ? 'done' : 'info';
  const claims: any[] = d.evidence?.claims ?? [];
  return (
    <div className="decision">
      <div className="decision-head">
        <span className={`badge ${tone}`}>{cls || 'DECISION'}</span>
        <span className={`badge ${d.confidence === 'HIGH' ? 'done' : d.confidence === 'MEDIUM' ? 'info' : 'pending'}`}>
          confidence {d.confidence}
        </span>
        <strong>{v.decision}</strong>
      </div>
      {v.confidence_note && <div className="note">{v.confidence_note}</div>}
      <div className="decision-section">
        <span className="muted">EVIDENCE — strength {(Number(d.evidence?.strength ?? 0) * 100).toFixed(0)}%,
          {' '}{d.evidence?.proof_count ?? 0} verified FACT(s)</span>
        <ul className="tight">
          {claims.slice(0, 8).map((c: any, i: number) => (
            <li key={i}><span className="claim-kind">{c.kind}</span> {c.text}</li>
          ))}
          {!claims.length && <li className="muted">Nothing verified was supplied — every mind is provisional.</li>}
        </ul>
      </div>
      <div className="decision-section">
        <span className="muted">AGREEMENT / DISAGREEMENT</span>
        <ul className="tight">
          {(d.agreement ?? []).map((a: string, i: number) => <li key={`a${i}`}>{a}</li>)}
          {(d.disagreement ?? []).map((a: string, i: number) => <li key={`d${i}`} className="disagree">{a}</li>)}
        </ul>
      </div>
      <div className="decision-section">
        <span className="muted">REALITY CHECK — cheapest test: {d.reality_check?.cheapest_test}</span>
        <ul className="tight">
          <li><strong>Do now:</strong> {d.reality_check?.do_now}</li>
          <li><strong>Kill criterion:</strong> {d.reality_check?.kill_criterion}</li>
          <li><strong>Missing:</strong> {(d.reality_check?.what_we_are_missing ?? []).join('; ')}</li>
          <li><strong>Can break this:</strong> {(d.reality_check?.what_can_break_this ?? []).slice(0, 3).join('; ')}</li>
        </ul>
      </div>
      <div className="decision-section">
        <span className="muted">ACTION PLAN</span>
        <ul className="tight">
          {(d.action_plan ?? []).map((s: any) => (
            <li key={s.order}>
              <strong>{s.order}.</strong> {s.action}
              <span className="muted"> — owner {s.owner}, ₹{Number(s.budget_inr ?? 0).toFixed(0)},
                {' '}{s.duration_minutes} min, metric: {s.success_metric}</span>
              {s.spends_money && !s.approval_ref && <span className="badge pending">approval required</span>}
            </li>
          ))}
        </ul>
      </div>
      {d.forecast && (
        <div className="decision-section">
          <span className="muted">FORECAST — {d.forecast.label}</span>
          <div>
            {d.forecast.metric}: {String(d.forecast.expected)} {d.forecast.unit} over {d.forecast.horizon_days} days
            {' '}({d.forecast.comparator}). Kill: {d.forecast.kill_criterion}
          </div>
        </div>
      )}
      {d.opportunity_cost && (
        <div className="decision-section muted">
          OPPORTUNITY COST — ₹{Number(d.opportunity_cost.rupees ?? 0).toFixed(0)},
          {' '}{d.opportunity_cost.minutes} min: {d.opportunity_cost.displaced}
        </div>
      )}
      <div className="decision-section">
        <span className="muted">EXPECTED IMPACT</span>
        <ul className="tight">
          <li><strong>Customer:</strong> {d.expected_impact?.customer}</li>
          <li><strong>Financial:</strong> revenue ₹{Number(d.expected_impact?.financial?.revenue_inr ?? 0).toFixed(2)},
            {' '}modelled contribution ₹{Number(d.expected_impact?.financial?.modelled_contribution_inr ?? 0).toFixed(0)}
            {' '}({d.expected_impact?.financial?.label})</li>
          <li><strong>Strategic:</strong> {d.expected_impact?.strategic}</li>
        </ul>
      </div>
      <div className="decision-section">
        <span className="muted">8-MIND ANALYSIS — {(d.eight_minds?.minds ?? []).length} minds, none averaged away</span>
        <div className="minds">
          {(d.eight_minds?.minds ?? []).map((m: any) => (
            <div key={m.mind} className="mind" title={m.domain}>
              <span className="mind-name">{m.mind.replace('_ADVISOR', '').replace('_', ' ')}</span>
              <span className={`badge ${m.confidence === 'MEDIUM' ? 'info' : 'pending'}`}>{m.confidence}</span>
              <span className="muted">{m.findings?.[0]?.slice(0, 150)}</span>
              {!!m.inputs_missing?.length && (
                <span className="muted">missing: {m.inputs_missing.join(', ')}</span>
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="muted">standard: {d.standard} · decision id {d.id}</div>
    </div>
  );
}

function DecisionEngineCard() {
  const [meta, setMeta] = useState<any>(null);
  useEffect(() => { api.decisionEngine().then(setMeta).catch(() => setMeta(null)); }, []);
  if (!meta) return null;
  const cal = meta.calibration ?? {};
  return (
    <div className="note">
      <strong>Decision engine:</strong> {meta.minds?.length ?? 0} minds · evidence hierarchy{' '}
      {meta.evidence_hierarchy?.length ?? 0} tiers · classes {(meta.classes ?? []).join(' | ')}
      <div className="muted">
        Forecast calibration: {cal.scored_decisions ?? 0} scored,
        {' '}{cal.hit_rate === null || cal.hit_rate === undefined ? 'no claims of accuracy' :
          `${(cal.hit_rate * 100).toFixed(0)}% held`}. {cal.note}
      </div>
    </div>
  );
}

function CommandPanel() {
  const commands = useEmpire((s) => s.dashboard);
  const [list, setList] = useState<any>(null);
  const [text, setText] = useState('');
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const commandText = useEmpire((s) => s.commandText);

  useEffect(() => {
    api.commands().then(setList).catch(() => setList(null));
  }, []);

  const run = async (value: string) => {
    setError(null);
    try {
      setResult(await commandText(value));
      setText('');
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="grid two">
      <div>
        <div className="section-title">Natural-language control</div>
        <textarea
          rows={3}
          value={text}
          placeholder="e.g. “status report”, “run the free resource scan”, “create a department for a paid Notion template”, “queue a task: audit catalog”"
          onChange={(e) => setText(e.target.value)}
        />
        <button onClick={() => void run(text)}>execute</button>
        {error && <div className="command-error">{error}</div>}
        {result && (
          <div className="result">
            <div>
              <strong>{result.intent}</strong> — {result.summary ?? result.said}
            </div>
            {result.requires_approval && <div className="badge pending">queued for owner approval</div>}
            <DecisionStandard d={result} />
            {!result.verdict && <pre>{JSON.stringify(result.data ?? result, null, 2).slice(0, 1600)}</pre>}
          </div>
        )}
      </div>
      <div>
        <div className="section-title">Available intents</div>
        {list ? (
          <div className="intent-list">
            {(list.commands ?? list.intents ?? []).map((c: any) => (
              <button key={c.name ?? c.intent} className="intent" onClick={() => void run(c.example ?? c.name)}>
                <span className="intent-name">{c.name ?? c.intent}</span>
                <span className="muted">{c.description}</span>
                {c.example && <span className="intent-example">{c.example}</span>}
                {c.requires_approval && <span className="badge pending">approval</span>}
              </button>
            ))}
          </div>
        ) : (
          <div className="empty">Command list unavailable.</div>
        )}
        <DecisionEngineCard />
        {commands?.honesty && (
          <div className="note">
            <strong>Owner dashboard note:</strong> {commands.honesty.note ?? 'see payload'}
          </div>
        )}
      </div>
    </div>
  );
}

function AgentsPanel() {
  const agents = useEmpire((s) => s.agents);
  const departments = useEmpire((s) => s.departments);
  const select = useEmpire((s) => s.select);
  const [filter, setFilter] = useState('');
  const [dept, setDept] = useState('');

  const rows = useMemo(
    () =>
      agents
        .filter((a) => (!filter || a.name.toLowerCase().includes(filter.toLowerCase()) || a.role.toLowerCase().includes(filter.toLowerCase())))
        .filter((a) => !dept || a.department === dept)
        .slice(0, 400),
    [agents, filter, dept],
  );

  return (
    <div>
      <div className="toolbar">
        <input placeholder="search name or role…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <select value={dept} onChange={(e) => setDept(e.target.value)}>
          <option value="">all departments</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <span className="muted">{rows.length} shown of {agents.length}</span>
      </div>
      <Table
        head={['name', 'role', 'rank', 'department', 'status', 'building', 'perf', 'rel']}
        rows={rows.map((a) => [
          <button className="link" onClick={() => select(a.id)}>
            {a.name}
          </button>,
          a.role,
          a.rank,
          a.department_name ?? '—',
          <span className={`badge ${a.status.toLowerCase()}`}>{a.status}</span>,
          a.target_building ? `→ ${a.target_building}` : a.building ?? '—',
          a.performance?.toFixed(2) ?? '—',
          a.reliability?.toFixed(2) ?? '—',
        ])}
      />
    </div>
  );
}

function DepartmentsPanel() {
  const departments = useEmpire((s) => s.departments);
  const agents = useEmpire((s) => s.agents);
  const [form, setForm] = useState({
    name: '',
    objective: '',
    kpis: '',
    city: 'revenue',
    building: 'digital-products',
    kill_criteria: 'No verified outcome in 60 days.',
  });
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const refreshPanels = useEmpire((s) => s.refreshPanels);
  const layout = useEmpire((s) => s.layout);

  const create = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const res = await api.createDepartment({
        ...form,
        kpis: form.kpis.split(',').map((k) => k.trim()).filter(Boolean),
        consumer_of: 'internal',
        producer_for: 'finance-treasury',
        parent_id: 'executive-council',
      });
      setMessage(`Created ${res.department?.name ?? form.name} with boss ${res.department?.boss_agent_id ?? '?'}.`);
      setForm({ ...form, name: '', objective: '', kpis: '' });
      await refreshPanels();
    } catch (err) {
      setMessage(`Refused: ${String(err)}`);
    }
    setBusy(false);
  };

  const buildings = useMemo(() => {
    const out: { id: string; name: string; city: string }[] = [];
    layout?.cities.forEach((c) => c.buildings.forEach((b) => out.push({ id: b.id, name: `${c.name} · ${b.name}`, city: c.id })));
    return out;
  }, [layout]);

  return (
    <div className="grid two">
      <div>
        <div className="section-title">Departments ({departments.length})</div>
        <Table
          head={['name', 'city', 'building', 'agents', 'status', 'kpis']}
          rows={departments.map((d) => [
            d.name,
            d.city,
            d.building,
            String(agents.filter((a) => a.department === d.id).length),
            <span className={`badge ${d.status.toLowerCase()}`}>{d.status}</span>,
            (d.kpis ?? []).join(', ') || '—',
          ])}
        />
      </div>
      <div>
        <div className="section-title">Department Factory</div>
        <p className="muted">
          A department is a declaration, not a folder: it must name an objective, KPIs and a kill
          criterion, and it gets its own workspace, channel, memory namespace, queue, budget and boss.
        </p>
        <label>name</label>
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Digital Products Lab" />
        <label>objective</label>
        <input value={form.objective} onChange={(e) => setForm({ ...form, objective: e.target.value })} placeholder="Ship one paid template this quarter" />
        <label>KPIs (comma separated)</label>
        <input value={form.kpis} onChange={(e) => setForm({ ...form, kpis: e.target.value })} placeholder="verified_sales, refund_rate" />
        <label>building</label>
        <select value={form.building} onChange={(e) => setForm({ ...form, building: e.target.value, city: buildings.find((b) => b.id === e.target.value)?.city ?? form.city })}>
          {buildings.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
        <label>kill criterion</label>
        <input value={form.kill_criteria} onChange={(e) => setForm({ ...form, kill_criteria: e.target.value })} />
        <button disabled={busy || !form.name || !form.objective} onClick={() => void create()}>
          {busy ? 'provisioning…' : 'create department'}
        </button>
        {message && <div className="note">{message}</div>}
      </div>
    </div>
  );
}

function TasksPanel() {
  const tasks = useEmpire((s) => s.tasks);
  const metrics = useEmpire((s) => s.taskMetrics);
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState<string | null>(null);

  const rows = tasks.filter((t) => !status || t.status === status).slice(0, 300);
  const task = tasks.find((t) => t.id === selected);

  return (
    <div>
      <div className="toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {['', 'QUEUED', 'ASSIGNED', 'IN_PROGRESS', 'VERIFYING', 'DONE', 'FAILED', 'CANCELLED', 'BLOCKED'].map((s) => (
            <option key={s} value={s}>
              {s || 'all statuses'}
            </option>
          ))}
        </select>
        <span className="muted">
          done {metrics?.completed ?? '—'} · failed {metrics?.failed ?? '—'} · failure rate{' '}
          {metrics?.failure_rate !== undefined ? `${(metrics.failure_rate * 100).toFixed(1)}%` : '—'} · avg latency{' '}
          {metrics?.avg_latency_seconds?.toFixed?.(2) ?? '—'}s
        </span>
      </div>
      <div className="grid two">
        <Table
          head={['title', 'type', 'status', 'score', 'assignee']}
          rows={rows.map((t) => [
            <button className="link" onClick={() => setSelected(t.id)}>
              {t.title.slice(0, 52)}
            </button>,
            t.task_type,
            <span className={`badge ${t.status.toLowerCase()}`}>{t.status}</span>,
            t.verification?.score !== undefined ? `${(t.verification.score * 100).toFixed(0)}%` : '—',
            t.assignee_id ?? '—',
          ])}
        />
        <div>
          {task ? (
            <>
              <div className="section-title">{task.title}</div>
              <div className="kv">
                <div className="row"><span className="k">type</span><span className="v">{task.task_type}</span></div>
                <div className="row"><span className="k">status</span><span className="v">{task.status}</span></div>
                <div className="row"><span className="k">priority</span><span className="v">{task.priority}</span></div>
                <div className="row"><span className="k">department</span><span className="v">{task.department_id ?? '—'}</span></div>
              </div>
              <div className="section-title small">verification</div>
              <pre>{JSON.stringify(task.verification ?? {}, null, 2).slice(0, 900)}</pre>
              <div className="section-title small">result</div>
              <pre>{JSON.stringify(task.result ?? {}, null, 2).slice(0, 1600)}</pre>
            </>
          ) : (
            <div className="empty">Select a task to inspect its result and verification.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function EconomyPanel() {
  const economy = useEmpire((s) => s.economy);
  const opportunities = useEmpire((s) => s.opportunities);
  const experiments = useEmpire((s) => s.experiments);
  const refreshPanels = useEmpire((s) => s.refreshPanels);
  const [busy, setBusy] = useState(false);

  return (
    <div className="grid two">
      <div>
        <div className="section-title">Ledger &amp; honesty</div>
        {economy ? (
          <div className="kv">
            <div className="row"><span className="k">verified revenue</span><span className="v">₹{economy.revenue_inr?.toFixed(2)}</span></div>
            <div className="row"><span className="k">verified costs</span><span className="v">₹{economy.costs_inr?.toFixed(2)}</span></div>
            <div className="row"><span className="k">contribution</span><span className="v">₹{economy.contribution_inr?.toFixed(2)}</span></div>
            <div className="row"><span className="k">entries</span><span className="v">{economy.ledger_entries ?? '—'}</span></div>
            {economy.honesty && (
              <div className="note">
                {Object.entries(economy.honesty).map(([k, v]) => (
                  <div key={k}>
                    <strong>{k}</strong>: {String(v)}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="empty">Economy service unavailable.</div>
        )}
        <div className="section-title">Opportunities ({opportunities.length})</div>
        <Table
          head={['title', 'score', 'capital', 'expected', 'risk', 'status']}
          rows={opportunities.slice(0, 40).map((o) => [
            o.title,
            o.score?.toFixed?.(2) ?? '—',
            `₹${o.required_capital_inr ?? 0}`,
            `₹${o.expected_revenue_inr ?? 0}`,
            o.legal_risk ?? '—',
            <span className="badge">{o.status}</span>,
          ])}
        />
      </div>
      <div>
        <div className="section-title">Experiments</div>
        <pre>{JSON.stringify(experiments ?? {}, null, 2).slice(0, 1600)}</pre>
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await api.discover();
              await refreshPanels();
            } finally {
              setBusy(false);
            }
          }}
        >
          run zero-capital discovery scan
        </button>
        <div className="note">
          The zero-capital rule is enforced in code: an experiment or opportunity that needs money
          is rejected while the treasury holds ₹0 unless the owner funds it first.
        </div>
      </div>
    </div>
  );
}

function UniversityPanel() {
  const university = useEmpire((s) => s.university);
  const [tracks, setTracks] = useState<any>(null);
  useEffect(() => {
    api.tracks().then(setTracks).catch(() => setTracks(null));
  }, []);
  return (
    <div className="grid two">
      <div>
        <div className="section-title">Pipeline</div>
        <pre>{JSON.stringify(university ?? {}, null, 2).slice(0, 2200)}</pre>
      </div>
      <div>
        <div className="section-title">Tracks</div>
        {tracks ? (
          <Table
            head={['track', 'subjects', 'threshold', 'certified']}
            rows={(tracks.tracks ?? []).map((t: any) => [
              t.name ?? t.id,
              String((t.subjects ?? []).length),
              String(t.pass_threshold ?? t.threshold ?? '—'),
              String(t.certified ?? '—'),
            ])}
          />
        ) : (
          <div className="empty">Track list unavailable.</div>
        )}
        <div className="note">
          When no local model is installed the exam engine scores the deterministic dimensions and
          reports the reasoning dimensions as <em>not assessed</em> — it never invents a pass.
        </div>
      </div>
    </div>
  );
}

function ApprovalsPanel() {
  const approvals = useEmpire((s) => s.approvals);
  const refreshPanels = useEmpire((s) => s.refreshPanels);
  const [note, setNote] = useState('');
  const decide = async (id: string, decision: string) => {
    await api.decide(id, decision, note);
    setNote('');
    await refreshPanels();
  };
  return (
    <div>
      <div className="section-title">Owner approval queue ({approvals.length})</div>
      {!approvals.length && <div className="empty">Nothing is waiting on you.</div>}
      {approvals.map((a) => (
        <div key={a.id} className="approval">
          <div className="approval-head">
            <strong>{a.action}</strong>
            <span className={`badge ${a.risk?.toLowerCase()}`}>{a.risk}</span>
            <span className="muted">
              {a.requester} ({a.requester_rank})
            </span>
          </div>
          <div className="approval-body">
            <div><span className="k">what</span> {a.what}</div>
            <div><span className="k">why</span> {a.why}</div>
            <div><span className="k">expected</span> {a.expected_result}</div>
            <div><span className="k">risk</span> {a.risk_notes}</div>
            <div><span className="k">reversible</span> {a.reversibility}</div>
          </div>
          <div className="approval-actions">
            <input placeholder="decision note (kept in the audit log)" value={note} onChange={(e) => setNote(e.target.value)} />
            <button onClick={() => void decide(a.id, 'APPROVE')}>approve</button>
            <button className="ghost" onClick={() => void decide(a.id, 'REJECT')}>reject</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function SecurityPanel() {
  const audit = useEmpire((s) => s.audit);
  const [check, setCheck] = useState<any>(null);
  useEffect(() => {
    api.securityCheck().then(setCheck).catch(() => setCheck(null));
  }, []);
  return (
    <div className="grid two">
      <div>
        <div className="section-title">Self-check</div>
        <pre>{JSON.stringify(check ?? {}, null, 2).slice(0, 1800)}</pre>
      </div>
      <div>
        <div className="section-title">Audit trail</div>
        <Table
          head={['time', 'actor', 'action', 'tool', 'risk', 'allowed']}
          rows={audit.slice(0, 120).map((a: any) => [
            new Date(a.ts * 1000).toLocaleTimeString(),
            a.actor,
            a.action,
            a.tool ?? '—',
            a.risk ?? '—',
            a.allowed ? 'yes' : 'no',
          ])}
        />
      </div>
    </div>
  );
}

function IntegrationsPanel() {
  const integrals = useEmpire((s) => s.integrals);
  const [health, setHealth] = useState<any>(null);
  useEffect(() => {
    api.integrationHealth().then(setHealth).catch(() => setHealth(null));
  }, []);
  return (
    <div className="grid two">
      <div>
        <div className="section-title">Connectors</div>
        <pre>{JSON.stringify(integrals ?? {}, null, 2).slice(0, 2000)}</pre>
      </div>
      <div>
        <div className="section-title">Health &amp; quotas</div>
        <pre>{JSON.stringify(health ?? {}, null, 2).slice(0, 2000)}</pre>
        <div className="note">
          Connectors are read/simulate-only until the owner supplies official API credentials.
          Sends and publishes stay unimplemented: nothing leaves the machine without an approval.
        </div>
      </div>
    </div>
  );
}

function ModelsPanel() {
  const models = useEmpire((s) => s.models);
  const [stats, setStats] = useState<any>(null);
  useEffect(() => {
    api.modelStats().then(setStats).catch(() => setStats(null));
  }, []);
  return (
    <div className="grid two">
      <div>
        <div className="section-title">Routing</div>
        <pre>{JSON.stringify(models ?? {}, null, 2).slice(0, 2200)}</pre>
      </div>
      <div>
        <div className="section-title">Usage</div>
        <pre>{JSON.stringify(stats ?? {}, null, 2).slice(0, 2200)}</pre>
      </div>
    </div>
  );
}

function EventsPanel() {
  const events = useEmpire((s) => s.events);
  const [type, setType] = useState('');
  const rows = events.filter((e) => !type || e.type.includes(type)).slice(0, 300);
  return (
    <div>
      <div className="toolbar">
        <input placeholder="filter by type…" value={type} onChange={(e) => setType(e.target.value)} />
        <span className="muted">{rows.length} of {events.length} loaded</span>
      </div>
      <Table
        head={['time', 'type', 'source', 'subject', 'severity', 'payload']}
        rows={rows.map((e) => [
          new Date(e.ts * 1000).toLocaleTimeString(),
          e.type,
          e.source,
          e.subject ?? '—',
          <span className={`badge ${e.severity}`}>{e.severity}</span>,
          JSON.stringify(e.payload ?? {}).slice(0, 90),
        ])}
      />
    </div>
  );
}

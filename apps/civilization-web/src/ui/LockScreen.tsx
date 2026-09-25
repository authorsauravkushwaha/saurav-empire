/**
 * The owner gate. No session, no civilization — every API call carries this token.
 */
import { useState } from 'react';
import { setToken } from '../api';
import { useEmpire } from '../store';

export function LockScreen() {
  const unlock = useEmpire((s) => s.unlock);
  const unlocked = useEmpire((s) => s.unlocked);
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!value.trim()) {
      setError('Paste the owner token first.');
      return;
    }
    setBusy(true);
    setError(null);
    const result = await unlock(value.trim());
    if (result.ok) setToken(value.trim());
    else setError(result.error ?? 'Access denied.');
    setBusy(false);
  };

  return (
    <div className="lock">
      <div className="lock-card">
        <div className="lock-kicker">LOCAL-FIRST · OWNER-GATED · TRUTH-FIRST</div>
        <h1>Saurav AI Civilization</h1>
        <p className="lock-sub">
          An autonomous, self-training business organization. This console shows only verified
          backend state — it will not decorate the world with activity that does not exist.
        </p>
        <label htmlFor="token">Owner token</label>
        <input
          id="token"
          type="password"
          autoComplete="off"
          spellCheck={false}
          placeholder="paste the token from data/state/secrets/owner_token"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void submit();
          }}
        />
        <button onClick={() => void submit()} disabled={busy || unlocked}>
          {busy ? 'Verifying…' : 'Enter the civilization'}
        </button>
        {error && <div className="lock-error">{error}</div>}
        <div className="lock-foot">
          <span>python3 scripts/empire.py token</span> prints the location — it never prints the secret.
        </div>
      </div>
    </div>
  );
}

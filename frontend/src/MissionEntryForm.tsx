import type { FormEvent } from 'react';

export function MissionEntryForm({ callsign, busy, error, joining, onCallsign, onSubmit }: {
  callsign: string; busy: boolean; error: string; joining: boolean;
  onCallsign: (value: string) => void; onSubmit: (event: FormEvent) => void;
}) {
  return <form onSubmit={onSubmit} aria-busy={busy}>
    <label htmlFor="callsign">Your callsign</label>
    <input id="callsign" value={callsign} onChange={event => onCallsign(event.target.value)}
      aria-invalid={error ? true : undefined} aria-describedby={error ? 'callsign-error' : undefined}
      placeholder="e.g. Rivera" required maxLength={24} autoComplete="nickname" />
    {error && <p id="callsign-error" className="error" role="alert">{error}</p>}
    <button disabled={busy || !callsign.trim()}>{busy ? 'Connecting…' : joining ? 'Join Mission' : 'Create Mission'}</button>
  </form>;
}

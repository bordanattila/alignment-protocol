import type { FormEvent } from 'react';
import type { MissionMode } from './types';

export function MissionEntryForm({ callsign, busy, error, joining, onCallsign, onSubmit,
  mode = 'authored', generatedAvailable = false, onMode }: {
  callsign: string; busy: boolean; error: string; joining: boolean;
  mode?: MissionMode; generatedAvailable?: boolean; onMode?: (value: MissionMode) => void;
  onCallsign: (value: string) => void; onSubmit: (event: FormEvent) => void;
}) {
  return <form onSubmit={onSubmit} aria-busy={busy}>
    <label htmlFor="callsign">Your callsign</label>
    <input id="callsign" value={callsign} onChange={event => onCallsign(event.target.value)}
      aria-invalid={error ? true : undefined} aria-describedby={error ? 'callsign-error' : undefined}
      placeholder="e.g. Rivera" required maxLength={24} autoComplete="nickname" />
    {!joining && <>
      <label htmlFor="mission-mode">Mission mode</label>
      <select id="mission-mode" value={mode} disabled={busy} aria-describedby="mission-mode-description"
        onChange={event => onMode?.(event.target.value as MissionMode)}>
        <option value="authored">Authored Mission</option>
        <option value="generated" disabled={!generatedAvailable}>AI-Generated Mission{!generatedAvailable ? ' — unavailable' : ''}</option>
      </select>
      <p id="mission-mode-description">{mode === 'generated'
        ? 'Crises adapt to previous decisions, with authored fallback when needed.'
        : 'Seeded scenarios from the established library. No LLM dependency.'}</p>
      {!generatedAvailable && <p>AI-generated missions are unavailable on this server.</p>}
    </>}
    {error && <p id="callsign-error" className="error" role="alert">{error}</p>}
    <button disabled={busy || !callsign.trim()}>{busy ? 'Connecting…' : joining ? 'Join Mission' : 'Create Mission'}</button>
  </form>;
}

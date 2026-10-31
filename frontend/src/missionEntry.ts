import type { Session, MissionMode } from './types';

export async function generatedMissionsAvailable(): Promise<boolean> {
  try {
    const response = await fetch('/api/capabilities');
    return response.ok && (await response.json()).generated_missions === true;
  } catch { return false; }
}

export const duplicateCallsignMessage = 'That callsign is already taken in this mission. Choose another.';
export class GameRequestError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

// The synchronous gate also covers repeated form events before React repaints
// the disabled button. A rejected request releases it for an editable retry.
export class MissionEntryRequest {
  pending = false;

  async submit(token: string | null, callsign: string, mode: MissionMode = 'authored'): Promise<Session | null> {
    if (this.pending) return null;
    this.pending = true;
    try {
      const response = await fetch(token ? `/api/missions/${encodeURIComponent(token)}/join` : '/api/missions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(token ? { callsign } : { callsign, mode }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new GameRequestError(result.code === 'callsign_taken' ? duplicateCallsignMessage
        : typeof result.detail === 'string' ? result.detail : 'Enter a callsign of 1–24 characters.', response.status);
      return result;
    } finally { this.pending = false; }
  }
}

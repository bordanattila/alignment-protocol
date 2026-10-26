import type { Session } from './types';

export const duplicateCallsignMessage = 'That callsign is already taken in this mission. Choose another.';

// The synchronous gate also covers repeated form events before React repaints
// the disabled button. A rejected request releases it for an editable retry.
export class MissionEntryRequest {
  pending = false;

  async submit(token: string | null, callsign: string): Promise<Session | null> {
    if (this.pending) return null;
    this.pending = true;
    try {
      const response = await fetch(token ? `/api/missions/${encodeURIComponent(token)}/join` : '/api/missions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ callsign }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.code === 'callsign_taken' ? duplicateCallsignMessage
        : typeof result.detail === 'string' ? result.detail : 'Enter a callsign of 1–24 characters.');
      return result;
    } finally { this.pending = false; }
  }
}

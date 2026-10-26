import type { LobbyState } from './types';

// Transport ordering only; never merge or locally reconstruct mission history.
export class SnapshotOrder {
  private revision = -1;
  accept(snapshot: LobbyState): boolean {
    if (snapshot.revision === undefined) return this.revision < 0; // legacy snapshot
    if (!Number.isSafeInteger(snapshot.revision) || snapshot.revision <= this.revision) return false;
    this.revision = snapshot.revision;
    return true;
  }
}

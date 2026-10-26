import type { LobbyState } from './types';

type Message = LobbyState['chat'][number];
export const CHAT_BOTTOM_TOLERANCE = 40;

// View bookkeeping only: authoritative messages continue to live in useLobby.
export class ChatScrollController {
  private following = true;
  private initialized = false;
  private seen = new Set<string>();
  private newestTimestamp = -Infinity;
  private unread = 0;

  constructor(private history: Pick<HTMLElement, 'scrollTop' | 'scrollHeight' | 'clientHeight'>,
    private you: string, private onUnread: (count: number) => void) {}

  private clearUnread() {
    if (this.unread) { this.unread = 0; this.onUnread(0); }
  }

  jumpToLatest = () => {
    this.following = true;
    // Direct assignment affects this container only; no outer scroll or focus.
    this.history.scrollTop = Math.max(0, this.history.scrollHeight - this.history.clientHeight);
    this.clearUnread();
  };

  onScroll = () => {
    this.following = this.history.scrollHeight - this.history.clientHeight - this.history.scrollTop <= CHAT_BOTTOM_TOLERANCE;
    if (this.following) this.clearUnread();
  };

  onResize = () => { if (this.following) this.jumpToLatest(); };

  update(messages: Message[]) {
    const incoming = messages.filter(message => !this.seen.has(message.id) && message.timestamp >= this.newestTimestamp);
    // A bounded identity cache covers current/replayed snapshots. The watermark
    // excludes older backfill even after an ID has left the cache.
    for (const message of messages) this.seen.add(message.id);
    while (this.seen.size > 200) this.seen.delete(this.seen.values().next().value!);
    for (const message of messages) this.newestTimestamp = Math.max(this.newestTimestamp, message.timestamp);
    if (!this.initialized) {
      this.initialized = true;
      this.jumpToLatest();
    } else if (incoming.length) {
      // An own message in an authoritative snapshot is confirmation, unlike
      // sendIntent's boolean (which only confirms local socket dispatch).
      if (this.following || incoming.some(message => message.sender_id === this.you)) this.jumpToLatest();
      else { this.unread = Math.min(messages.length, this.unread + incoming.length); this.onUnread(this.unread); }
    }
  }
}

export function observeChatHistory(history: HTMLElement, contents: HTMLElement, controller: ChatScrollController) {
  history.addEventListener('scroll', controller.onScroll, { passive: true });
  // Observe both wrapping/content height and the viewport (including keyboard
  // resizing). Never follow a resize while the reader is looking further back.
  const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(controller.onResize);
  observer?.observe(history);
  observer?.observe(contents);
  return () => {
    history.removeEventListener('scroll', controller.onScroll);
    observer?.disconnect();
  };
}

import { SnapshotOrder } from './snapshotOrder';
import type { LobbyState, MissionIntent, Session } from './types';

export type ConnectionStatus = 'Connecting' | 'Connected' | 'Reconnected'
  | 'Connection lost — reconnecting' | 'Connection unavailable — continuing to retry'
  | 'Session no longer recoverable' | 'Sign in required';

type Callbacks = {
  status: (status: ConnectionStatus) => void;
  snapshot: (mission: LobbyState) => void;
  error: (message: string) => void;
  checkAccess?: () => Promise<boolean | null>;
  accessLost?: () => void;
};
type Runtime = {
  socket: (url: string) => WebSocket;
  later: (callback: () => void, delay: number) => ReturnType<typeof setTimeout>;
  cancel: (timer: ReturnType<typeof setTimeout>) => void;
  random: () => number;
};
const browserRuntime: Runtime = {
  socket: url => new WebSocket(url),
  later: (callback, delay) => setTimeout(callback, delay),
  cancel: timer => clearTimeout(timer),
  random: () => Math.random(),
};

// Owns one transport and retry loop for one mounted mission session. Never queues
// gameplay intents: a new transport must deliver a fresh snapshot before sending.
export class MissionConnection {
  private socket: WebSocket | null = null;
  private retry?: ReturnType<typeof setTimeout>;
  private watchdog?: ReturnType<typeof setTimeout>;
  private stopped = true;
  private ready = false;
  private failures = 0;
  private interrupted = false;
  private attempt = 0;
  private readonly snapshots = new SnapshotOrder();

  constructor(private session: Session, private url: string, private callbacks: Callbacks,
    private runtime: Runtime = browserRuntime) {}

  start() {
    if (!this.stopped) return;
    this.stopped = false;
    this.connect();
  }

  stop() {
    this.attempt++;
    this.stopped = true;
    this.ready = false;
    this.clearTimers();
    this.retireSocket();
  }

  private clearTimers() {
    if (this.retry !== undefined) this.runtime.cancel(this.retry);
    if (this.watchdog !== undefined) this.runtime.cancel(this.watchdog);
    this.retry = this.watchdog = undefined;
  }

  private retireSocket() {
    const socket = this.socket;
    this.socket = null;
    if (!socket) return;
    socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
    try { socket.close(); } catch { /* A failed handshake may already be closed. */ }
  }

  private failed(terminal = false) {
    if (this.stopped) return;
    this.ready = false;
    this.interrupted = true;
    this.clearTimers();
    this.retireSocket();
    this.failures += 1;
    if (this.callbacks.checkAccess && (terminal || this.failures >= 3)) {
      const attempt = ++this.attempt;
      this.callbacks.status('Connection unavailable — continuing to retry');
      void Promise.resolve().then(() => this.callbacks.checkAccess!()).catch(() => null).then(access => {
        if (this.stopped || this.attempt !== attempt) return;
        if (access === false) {
          this.stopped = true;
          this.callbacks.status('Sign in required');
          this.callbacks.accessLost?.();
        } else if (terminal && access === true) this.rejectSeat();
        else this.retryConnection();
      });
      return;
    }
    if (terminal) { this.rejectSeat(); return; }
    this.retryConnection();
  }

  private rejectSeat() {
    this.stopped = true;
    this.callbacks.status('Session no longer recoverable');
  }

  private retryConnection() {
    this.callbacks.status(this.failures >= 3
      ? 'Connection unavailable — continuing to retry' : 'Connection lost — reconnecting');
    // Equal jitter: 0.5–1s initially, capped at 5–10s. No retry limit.
    const ceiling = Math.min(1000 * 2 ** Math.min(this.failures - 1, 4), 10000);
    this.retry = this.runtime.later(() => {
      this.retry = undefined;
      this.connect();
    }, ceiling * (0.5 + this.runtime.random() * 0.5));
  }

  private connect() {
    if (this.stopped || this.socket) return;
    this.attempt++;
    let socket: WebSocket;
    try { socket = this.runtime.socket(this.url); }
    catch { this.failed(); return; }
    this.socket = socket;
    const current = () => !this.stopped && this.socket === socket;
    // A dev proxy/network can leave CONNECTING open without error or close.
    // Also bound authentication: OPEN alone does not authorize gameplay.
    this.watchdog = this.runtime.later(() => { if (current()) this.failed(); }, 15000);
    socket.onopen = () => {
      if (!current()) return;
      try { socket.send(JSON.stringify({ type: 'authenticate', credential: this.session.credential })); }
      catch { this.failed(); }
    };
    socket.onmessage = event => {
      if (!current()) return;
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'state') {
          if (message.mission.token !== this.session.token || !this.snapshots.accept(message.mission)) return;
          this.clearTimers();
          this.ready = true;
          this.failures = 0;
          this.callbacks.snapshot(message.mission);
          this.callbacks.status(this.interrupted ? 'Reconnected' : 'Connected');
        } else if (message.type === 'error') this.callbacks.error(message.detail);
      } catch { this.failed(); }
    };
    socket.onerror = () => { if (current()) this.failed(); };
    socket.onclose = event => { if (current()) this.failed(event.code === 1008); };
  }

  send(intent: MissionIntent): boolean {
    if (!this.ready || this.socket?.readyState !== 1) return false;
    try { this.socket.send(JSON.stringify(intent)); return true; }
    catch { this.failed(); return false; }
  }
}

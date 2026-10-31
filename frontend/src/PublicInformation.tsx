export function PublicInformation() {
  return <section className="panel public-instructions" aria-labelledby="how-to-play">
    <p className="eyebrow">Mission protocol</p><h2 id="how-to-play">Bring your team. Combine your intelligence.</h2>
    <ol>
      <li>Gather 2–4 players, each using their own device or browser profile. Sign in with ChatGPT and choose a callsign of 1–24 characters. No separate game account or password.</li>
      <li>The host creates a mission and shares its invite link. Teammates open it, sign in and join. The host starts once every occupied seat is connected.</li>
      <li>Compare the public briefing and AI recommendation with your own private intelligence. Use team chat during the 60-second discussion, then submit a hidden vote.</li>
      <li>The choice with the most votes wins. A top tie opens a 20-second Consensus Window and a new vote. If that vote is still tied, the AI recommendation executes.</li>
      <li>Survive ten authored crises together. Review the shared consequences and final score. Live LLM generation is disabled.</li>
    </ol>
    <h3>Keep your seat</h3>
    <p>Keep the same browser profile and invite link to reconnect. Signing in on a different device does not recover your seat. Tabs in one profile may share a seat and private intelligence.</p>
    <p>Players who disconnect permanently cannot currently be removed or replaced. If someone cannot return, the team may need to create a new mission. There is no automatic five-minute seat removal.</p>
    <p>Share invites only with your team. Keep private intelligence off shared screens. Private votes become part of the recorded outcome after voting resolves.</p>
  </section>;
}

export function safeContact(value: string): string | null {
  if (!value || /[\x00-\x20]/.test(value)) return null;
  try {
    const url = new URL(value);
    if (url.protocol === 'https:' && !url.username && !url.password) return url.href;
    if (url.protocol === 'mailto:' && /^[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(url.pathname) && !url.search && !url.hash) return url.href;
  } catch { /* Configuration is public text, never executable markup. */ }
  return null;
}

export function DataPrivacy({ contact = import.meta.env?.VITE_OWNER_CONTACT_URL ?? '',
  backupPolicy = import.meta.env?.VITE_BACKUP_RETENTION_NOTICE ?? '' }: { contact?: string; backupPolicy?: string }) {
  const owner = safeContact(contact);
  return <details id="data-privacy" className="panel data-privacy">
    <summary>Data, privacy and saved seats</summary>
    <p>Callsigns, team chat, votes, civilization metrics and mission history are saved on the game server. Team members see shared chat and outcomes; each player receives only their assigned private intelligence. Votes stay hidden until resolution. Do not enter sensitive personal information.</p>
    <p>Sites handles ChatGPT sign-in. The relay uses a Site-scoped account identifier for pseudonymous abuse limits. It does not forward your account ID, email, name or sign-in cookies to the game backend, or show them to teammates. Sites and the hosting provider also process requests under their own policies.</p>
    <p>This browser remembers a secret that restores your seat. Sign-in alone cannot recover a lost secret. Clearing storage, forgetting seats or changing browser profiles may make that seat irrecoverable. A person with access to this browser profile may be able to reuse it.</p>
    <p>When everyone is offline, inactive lobbies expire after 24 hours, unfinished missions after 7 days, and finished or failed missions after 30 days. Returning or accepted activity can extend these periods. Missions do not expire while anyone remains connected. Cleanup runs periodically; these are not exact deletion times.</p>
    <p>Forgetting seats removes this browser’s credentials only; it does not delete shared server history. There is no self-service server deletion tool. Encrypted operator backups are separate copies and are not erased by mission expiry.</p>
    {owner ? <p><a href={owner} rel="noreferrer">Contact the game owner about data or access</a></p>
      : <p className="release-dependency">Owner contact is not yet configured. Public participation is pending this information.</p>}
    {backupPolicy.trim() ? <p>Backup retention: {backupPolicy}</p>
      : <p className="release-dependency">The operator backup-retention policy is not yet published. This is a preview, not a public participation release.</p>}
  </details>;
}

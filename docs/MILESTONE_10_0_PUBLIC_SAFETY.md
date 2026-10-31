# Milestone 10.0 — Public Access Security & Data Protection

Prepared October 30, 2026. **Local implementation only; not deployed.** The
owner-private Sites audience, Render service/disk, live missions, live database,
LLM settings, manual-deploy settings and deployed source are unchanged. No
commit, tag, merge or push was made. The user reports a successful hosted
three-player browser test of the previously deployed version; that evidence is
preserved and is not presented as acceptance of this new code.

## 1. Existing security mechanisms

- A server-only gateway key and exact Origin check guard the deployed backend.
  The public health endpoint contains no mission data. The gateway is a relay
  trust boundary, not player authorization.
- Invite tokens contain 24 random bytes (192 bits). Seat credentials contain
  32 random bytes (256 bits), are compared through constant-time digests and
  are stored as hashes. Credentials are sent in the first WebSocket frame,
  not a URL. There is no mission-list/enumeration endpoint.
- Every host action and player action is authorized against mission membership
  and its separate credential. Role IDs supplied by visitors do not grant roles.
- `MissionStore.project()` allowlists public fields and only the recipient's
  private intelligence and own vote. Unresolved other-player votes, future
  scenarios, credentials and internal generation metadata remain server-side.
- Pydantic rejects unknown/incorrect action fields. Callsigns are bounded to
  24 characters, chat to 500 characters and its history to 100 messages. React
  escapes rendered text. Invalid phases, duplicate votes and stale result IDs
  are rejected. Recorded resolutions remain immutable and idempotent.
- One process owns SQLite through a POSIX lock. The database uses WAL,
  `synchronous=FULL`, foreign keys, aggregate checksums and a separately checked
  resolution index. Accepted changes commit before broadcast; failed writes
  restore the in-memory aggregate.

## 2. Confirmed gaps and remaining risks

The pre-change implementation had no mission expiry, mission-count cap,
per-visitor creation/join budget, socket-attempt/concurrency quota, chat rate
budget or bounded HTTP body read. It checked WebSocket character counts rather
than UTF-8 byte counts. Therefore a gateway-admitted visitor could consume
unbounded disk/memory or amplify broadcasts without stealing anyone's seat.

Forwarding a shared proxy IP as the player identity would either group all
Sites visitors together or let visitors rotate a spoofed forwarding header.
Previously there was no authenticated visitor claim for backend abuse controls.

Broadcast delivery was serial per socket and shared a cross-mission lock, with
an unbounded retry loop on failures. The scheduler deep-copied/serialized idle
retained aggregates every 100 ms. Both added avoidable resource-exhaustion paths.
The existing backup documentation did not provide a dedicated verified online
backup/isolated-restore tool.

The controls below bound application resources; they do not guarantee fairness
or availability against account farms, coordinated traffic or volumetric DDoS.
Gateway-key compromise still permits relay impersonation; seat credentials
continue to be required for existing-player actions. Keep gateway secrets
server-side and use platform access controls/edge protection. Long-lived
authenticated connections can pin retained missions, but total admissions stay
bounded. No CAPTCHA, accounts service, Redis, telemetry service or paid resource
has been added.

The relay still requires an authenticated Sites identity. Changing the audience
alone will not enable anonymous play. Before public access, decide the visitor
policy and verify Sites strips/replaces visitor-supplied identity headers. Do
not weaken that boundary to make anonymous requests pass. This milestone does
not change Sites sharing, add login screens, or authorize external visitors.

## 3. Proposed retention periods and rate thresholds

These are the local code defaults, **proposed for approval before deployment**.
All backend values below accept positive integer environment overrides named
`CONSENSUS_SAFETY_<UPPERCASE_FIELD>`, for example
`CONSENSUS_SAFETY_LOBBY_RETENTION_SECONDS=86400`. Invalid settings stop startup.
Retention/startup grace values cannot be shorter than 300 seconds.

| Field | Default | Meaning |
| --- | ---: | --- |
| `lobby_retention_seconds` | 86400 | 24 hours, all seats offline |
| `unfinished_retention_seconds` | 604800 | 7 days, all seats offline |
| `completed_retention_seconds` | 2592000 | 30 days for victories and defeats, all seats offline |
| `startup_cleanup_grace_seconds` | 300 | At least five minutes after restart before cleanup starts |
| `cleanup_interval_seconds` | 60 | Maintenance interval |
| `cleanup_batch` | 10 | Maximum missions removed in one pass |
| `create_per_10min` | 5 | Creation attempts per visitor; token-bucket refill |
| `create_global_per_minute` | 30 | Global creation attempts |
| `joins_per_minute` | 30 | Join/HTTP credential-restore attempts per visitor |
| `http_per_minute` | 120 | Other HTTP admission/credential-validation budget per visitor |
| `http_concurrent` | 32 | Concurrent HTTP operations, excluding health |
| `ws_attempts_per_minute` | 60 | WebSocket attempts per visitor, including bad credentials |
| `ws_global_per_minute` | 300 | Global WebSocket attempts |
| `sockets_total` | 128 | All pending and authenticated sockets |
| `sockets_per_visitor` | 16 | Pending/authenticated sockets per visitor |
| `sockets_per_seat` | 3 | Authenticated sockets for one seat |
| `frames_per_10sec` | 30 | Post-authentication frames per visitor, including invalid actions |
| `chat_per_10sec` | 10 | Accepted chat-attempt budget per seat, shared across tabs |
| `missions_total` | 200 | All retained missions, including completed results |
| `missions_per_creator` | 8 | Retained missions created by a visitor |
| `limiter_keys` | 4096 | Maximum bucket entries; inactive keys reclaimed after 20 minutes |
| `http_body_bytes` | 4096 | Maximum buffered HTTP body |
| `websocket_bytes` | 4096 | UTF-8 frame limit, including first-frame authentication |
| `body_timeout_seconds` | 5 | Bounded HTTP body-read time |
| `database_max_bytes` | 268435456 | Stop new missions at 256 MiB of main database plus WAL |
| `disk_reserve_bytes` | 67108864 | Stop new missions below 64 MiB free filesystem space |

The relay independently applies a 4096-byte/five-second HTTP body bound. The
existing Uvicorn frame limit remains 4096 bytes. If backend byte limits are
changed, coordinate the relay and Uvicorn limits; the effective bound is the
smallest layer. These quotas are independent token buckets, not strict calendar
windows. Invalid/rejected admission attempts consume the applicable budget.
One account using multiple browser profiles shares its visitor quota; separate
authenticated visitors behind the same proxy receive independent quotas.

## 4. Implemented protection and compatibility

The relay derives `X-Consensus-Visitor` as HMAC-SHA256 of the platform-provided
account identity using the server-only gateway key. It overwrites any
visitor-supplied value and does not forward raw account IDs, cookies,
authorization, `Forwarded`, `X-Forwarded-For` or `X-Real-IP`. The production
gateway requires the relay key and a valid 64-hex-character visitor claim before
setting a trusted ASGI scope identity. It strips those private headers before
game handlers run. This claim identifies rate budgets only; it cannot grant a
seat or host rights. Rotating the gateway key also changes visitor pseudonyms.

The Docker command disables Uvicorn proxy-header interpretation. Direct/local
test deployments use their actual ASGI peer, never a caller's forwarding
header; production must retain the guarded factory, not `app.main:app`.

Admission and rate decisions run in the single event loop; mission capacity
and creation are serialized with the existing game-state lock. HTTP excess
gets 429/Retry-After, large bodies get 413, timed-out bodies get 408, and capacity
gets a sanitized 429/503. Socket excess uses a retryable 1013 close (a denied
pre-upgrade connection is represented by an HTTP handshake rejection).
The frontend's existing reconnect loop retries transient closes with jitter.
An excess tab cannot mark a successfully connected seat offline. Chat-rate
rejections do not append chat, bump revisions or broadcast unchanged state.

Broadcasts now use per-mission ordering locks and concurrent bounded sends.
There are at most two failure/republication waves per call; unresolved work is
retried by the scheduler. Slow clients in one mission cannot hold another
mission's delivery lock. Expiry removes the associated pending/ordering state.
The scheduler first checks due timestamps and does not serialize idle missions.
Voting, plurality/tie-breaking, 60/20/30-second timers, roles, consequences,
campaign selection and balance are unchanged.

Activity is authoritative server wall-clock metadata in an optional additive
`mission_activity` table. `PRAGMA user_version` remains 2 and aggregate format
remains 1: existing game JSON, checksums and finalized result hashes are not
rewritten by metadata adoption. Existing version-1 migration tests still pass.
Older binaries ignore the extra table. New/legacy missions missing metadata
receive a full initial retention interval on first adoption; a restart alone
does not reset already-recorded activity.

Accepted player actions and connect/disconnect transitions update activity in
the same transaction as the mission. Invalid credentials/intents, rate-limited
actions, broadcasts, clock ticks and background timer transitions do not renew
activity. Duplicate acknowledgements do not extend it. Finalization starts its
own minimum result-retention interval. Time moving backwards cannot shorten the
stored activity timestamp.

No mission with a connected player is deleted. Reconnects refresh the offline
baseline without reallocating a seat or role; all categories retain at least
five minutes. Expiration atomically removes the entire mission and its result
index and activity row, only then evicting cache entries. Cleanup failure retains
both database and cache. No retained result can be individually changed or
removed. At the approved expiry, the invite/seat/history stop being available;
30-day retention is not indefinite archival. Export/backup requirements must be
agreed before enabling it in production.

Local sanitized rejection counters are available through
`app.state.safety.diagnostics()` and sampled `consensus.safety` logs. Only fixed
categories/counts appear; no tokens, credentials, addresses, account IDs, chat,
votes, private intelligence, prompts or database payloads. There is no public
diagnostics/admin/backup endpoint. Retention logs only the removed count.

## 5. Disk-growth assessment

A temporary synthetic database containing 200 started two-player authored
missions measured 18,092,032 bytes of database and 4,190,072 bytes of WAL
(approximately 21.25 MiB together). Aggregate serialized payloads totaled
17,818,547 bytes. The test process peaked at 107,052 KiB (104.54 MiB) RSS and
constructed this fixture in 1.886 seconds. These are initial-briefing fixtures,
not maximum chat/history or sustained-network-load measurements.

Existing chat/content/campaign bounds, the 200-mission cap and admission
headroom checks bound further growth conservatively. The 256 MiB threshold is
an admission safeguard, not a filesystem quota: already-admitted missions can
still write, and backup files consume disk too. Previously existing missions
above a configured cap are preserved; new admissions are refused.

Maintenance attempts nonblocking passive checkpoints. Deleted SQLite pages are
reused rather than immediately reducing the main file. A focused test verified
freelist reclamation, refused online compaction while the server's ownership
lock was held, and verified actual file shrinkage and valid records after
offline VACUUM. Automatic VACUUM is intentionally avoided during gameplay.

Use `app.backup --status` below plus Render's disk graph and `df -h /data` to
review database, WAL, reusable pages, backups and free space. The CLI reports a
warning below 128 MiB free. Review at 80% disk use, abnormal WAL growth, frequent
storage-capacity rejection or before an event. This milestone does not create
a monitor, schedule, paid storage, or alert subscription. Never delete the
live WAL to reclaim space. Move verified backups off disk promptly; keep at
most two local copies and ensure compaction has another database-sized amount
of free space plus the safety reserve.

## 6. Tested backup and isolated recovery procedure

The operator tool uses Python's supported SQLite online backup API from a
read-only source connection, not a copy of the live main file. Committed WAL
transactions are included in the snapshot. Source connections and file handles
are closed deterministically. Destinations are exclusive/no-overwrite, mode
0600, inside a mode-0700 directory and outside Git/Sites source trees. A failed
backup removes its new incomplete destination. A backup has a 60-second time
budget and requires snapshot-size disk headroom plus 64 MiB.

Verification runs integrity and foreign-key checks, schema-version checks,
existing aggregate validation and immutable resolution-index validation. The
isolated restore check creates a new private temporary database and compares
mission, result-index and optional activity rows. It cannot select a production
restore destination. Tests verified active, victory and defeat snapshots,
roles, credentials, metrics, finalized results, history and unchanged live test
aggregates. The local container additionally exercised online backup and an
isolated restore while its synthetic backend was running.

**The commands below are for a future approved deployment of this module. They
have not been run against production.** For the backup required BEFORE that
deployment, use the standalone `deploy/backup_current.py` and the gated procedure
in [the follow-up rollout plan](MILESTONE_10_0_ROLLOUT_PLAN.md). It works with the
currently deployed container and does not require `app.backup` to exist there.
Authenticate using the owner's existing
Render SSH/Shell access. No app HTTP token substitutes for operator access:

```sh
umask 077
python -m app.backup --source /data/consensus-engine.sqlite3 --status
backup_path="/data/operator-backups/consensus-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
python -m app.backup --source /data/consensus-engine.sqlite3 --output "$backup_path"
python -m app.backup --source "$backup_path" --verify
python -m app.backup --source "$backup_path" --restore-check
```

Only the produced snapshot is a standalone file suitable for transfer. Transfer
it over authenticated SFTP/SCP to an owner-controlled encrypted local location,
never through Sites, a chat attachment or the source repository. For example,
from the operator's machine, using their configured Render SSH authentication:

```sh
umask 077
scp -s 'srv-dbif74flk1mc73ek1i90@ssh.virginia.render.com:/data/operator-backups/SELECTED-SNAPSHOT.sqlite3' ./SELECTED-SNAPSHOT.sqlite3
chmod 600 ./SELECTED-SNAPSHOT.sqlite3
```

Replace the selected snapshot filename; compare SHA-256 on both ends and run
`--verify`/`--restore-check` on the transferred snapshot using this application
version. Verify the host key and operator destination. Do not paste a key,
database or backup into chat. The snapshot contains private game state and
credential hashes even though CLI output is sanitized. Take backups before
deployments and after important sessions. Render's daily disk snapshots are
not a substitute for this application-consistent procedure.

For actual disaster recovery, obtain separate authorization, stop the service,
retain the damaged database/WAL for investigation, verify a snapshot on an
isolated path, and plan an explicit replacement. This milestone implements no
live restore command. Offline compaction likewise requires an approved
maintenance window, a verified off-disk backup, sufficient temporary space and
the service fully stopped. `--compact-offline` refuses an active owner lock or
missing source. It preserves schema and validated mission/result counts.

SQLite references: [online backup API](https://www.sqlite.org/backup.html),
[Python Connection.backup](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup),
[WAL handling](https://www.sqlite.org/wal.html).

Follow-up runtime review: Debian's published `3.46.1-7+deb13u2` patch series does
not contain the upstream WAL-reset fix. The Dockerfile now builds a pinned
upstream SQLite 3.51.3 library, verifies the published amalgamation hash and exact
runtime source ID, and retains Python's stdlib driver and schema/aggregate format.
Python's dynamic binding and database read/write compatibility in both directions
were verified locally. Keep the single writer and read-only backup source as
well. See [provenance, verification and production gates](MILESTONE_10_0_ROLLOUT_PLAN.md).
No production library upgrade was performed. On 2026-10-31 the owner reported
successful production snapshot validation and encrypted off-disk transfer. The
downloaded file's checksum, application/integrity validation and identical-row
isolated restoration were then independently verified locally. See the follow-up
rollout plan for that completed gate; detailed production-backup evidence remains
in private operator records and is excluded from published source.

## 7. Verification results

| Check | Before | Local after |
| --- | --- | --- |
| Backend pytest | 673 passed | 700 passed, including 27 focused safety cases |
| Frontend ordinary suite | 105 passed, 4 optional skips | 105 passed, same 4 skips |
| Frontend with captured chat/restart/review/expansion fixtures | Earlier evidence preserved | 109 passed, no skips |
| Relay tests | 5 passed | 8 passed |
| TypeScript/Vite build | Previously passing | Passed |
| Real Chromium acceptance | Prior historical evidence preserved | Realistic-delay and fast regression passed, zero findings |
| Local network/recovery suite | Prior historical evidence preserved | Eight existing smokes passed |
| Dependency consistency | Existing environment | `pip check` passed |
| Hardened Docker image | Existing deployment image preserved | Built; local 512 MiB / 0.5 CPU check passed |
| Historical files | Fingerprinted before new test runs | 608 files unchanged |

Final machine-readable results and commands are in
`docs/evidence/milestone_10_0/verification.json` and `commands.json`. Browser
screenshots/private fixture databases stay in temporary local directories; no
database or backup is exported into evidence. Prior fixed-name temporary
captures were copied privately before tests and restored afterward.

The browser runner initially could not start Chromium without its existing
supplemental NSS/NSPR library path. Reusing the documented local libraries
resolved this; no app dependency or system package was installed. An initial
container test harness waited for a snapshot it had already consumed; it was
stopped, corrected and rerun successfully. Neither is reported as an application
failure. The sole backend warning is the existing Starlette/httpx deprecation.

Existing persistence failure-injection doubles now accept the metadata keyword;
their rollback assertions are unchanged. The mode-validation fixture gets an
explicit larger creation budget to exercise invalid modes in one burst. Actual
abuse budgets are covered separately. Controlled clocks drive local rule and
network fixtures; no production timer constants were changed. Browser tests
use fake providers only and made zero real provider requests. No live data,
physical-device, public-audience, or hosted-new-version test was performed.

## 8. Monitoring, private rollout and rollback

Nothing here grants deployment approval. After the user approves the proposed
values, keep Sites owner-private and preserve the existing resources and keys:

1. Complete the production backup and verified encrypted off-disk retention using
   the pre-upgrade standalone procedure in the follow-up rollout plan; do not
   copy only the live main database or assume the new module is already deployed.
2. Deploy the updated Sites relay first. The older backend safely ignores the
   added visitor header; the newer backend requires it. Reversing this order
   would temporarily deny legitimate clients. Do not rotate keys unnecessarily.
3. Deploy the backend manually, retaining `/data`, one worker/instance and LLM
   generation disabled. Existing records get full first-adoption retention.
4. Check owner entry, three real browsers, trusted visitor isolation, rejected
   direct access, normal plurality/ties, reconnect, restart, restored history,
   disk status and rejection counters. Check that user-supplied forwarding and
   identity headers cannot rotate quotas through the actual Sites edge.
5. Before changing audience, review competition identity policy, bot exposure,
   quotas, runtime SQLite patch status, backup ownership and retention notice.

For rollback, restore the prior backend application version first, then the
prior relay if needed. Preserve the volume; application rollback does not undo
retention deletions and is not database restoration. Older code ignores the
additive activity table but will not maintain activity timestamps. If an older
writer runs for a long period, reassess metadata/grace before re-enabling
cleanup; do not blindly apply old activity ages to recently played missions.
Any data restoration requires its own approved offline procedure. Do not delete
the database to fix startup, force a second writer, upgrade resources or enable
automatic deployments during recovery.

Review sampled safety logs and the operator status command during the first
private event. Repeated rate/capacity rejections, abnormal free-space/WAL trends,
or reconnect failures require investigation. No global hard bandwidth-spend cap
is introduced: rejected responses and snapshots still consume metered egress.

## 9. Exact changed-file inventory

Application and deployment:

- `.gitignore` — excludes common database/backup artifacts.
- `Dockerfile` — disables proxy-header trust; pins and verifies upstream SQLite
  3.51.3 while preserving Python's driver, worker, database format and resources.
- `deploy/backup_current.py` — standalone pre-upgrade operator snapshot and
  isolated restore using tooling already present in the deployed container.
- `backend/app/safety.py` — settings, bounded buckets, diagnostics, ASGI limits.
- `backend/app/retention.py` — private typed activity metadata.
- `backend/app/backup.py` — operator-only online backup, validation, isolated
  restore check, disk status and ownership-locked offline compaction.
- `backend/app/main.py` — guarded admission, chat/frame limits and maintenance.
- `backend/app/missions.py` — transactional activity, quotas and whole-mission expiry.
- `backend/app/persistence.py` — optional metadata table, atomic expiry and checkpoints.
- `backend/app/connections.py` — seat cap, parallel sends, isolated ordered bounded retry.
- `backend/app/railway.py` — production trusted-visitor enforcement and header stripping.
- `deploy/sites/worker.mjs` — pseudonymous identity, bounded bodies, Retry-After relay.

Tests:

- `backend/tests/test_public_safety.py` — 27 focused regression cases.
- `backend/tests/test_deployed_backup.py` — pre-upgrade backup regression cases.
- `backend/tests/test_adaptive_narrative.py`
- `backend/tests/test_durable_generation_diagnostics.py`
- `backend/tests/test_generation_diagnostics.py`
- `backend/tests/test_generation_responsiveness.py`
- `backend/tests/test_live_generation.py`
- `backend/tests/test_persistence.py`
- `backend/tests/test_railway_deployment.py`
- `deploy/sites/worker.test.mjs`

Reports/evidence:

- `docs/MILESTONE_10_0_PUBLIC_SAFETY.md`
- `docs/MILESTONE_10_0_ROLLOUT_PLAN.md`
- `docs/evidence/milestone_10_0/verification.json`
- `docs/evidence/milestone_10_0/commands.json`

Existing untracked gameplay-evaluation work and prior deployment/acceptance
reports are not part of this milestone's change inventory and were not edited.

## 10. Public-release readiness

**Retention/quota values approved; deployment and public access not authorized.**
The SQLite follow-up has 704 backend tests passing under the patched container,
plus relay and local container checks. The owner's production backup has now
passed final off-disk checksum and isolated-restore verification. Request separate
commit/push and rollout authorization at the deployment checkpoint. The updated
relay and backend must then complete coordinated
owner-private hosted acceptance. Confirm the competition visitor identity policy
and backup/monitoring ownership before considering public access.
No additional paid infrastructure is required by this implementation.

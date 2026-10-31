# Milestone 10.0 — SQLite, production backup and private rollout checkpoint

Prepared 2026-10-30; backup checkpoint updated 2026-10-31. **Not deployment authorization. Nothing has been deployed,
committed, pushed, published, restored to production, or rotated in this follow-up.**

## Current gate status

- Retention and abuse-control values: approved by the owner; unchanged.
- Patched runtime: built and locally verified, including Python's actual dynamic
  library binding, source ID, old-database compatibility and rollback compatibility.
- Pre-upgrade backup tooling: rehearsed in the old container with synthetic data;
  no installation or new application module is needed in the deployed container.
- On 2026-10-31 the owner reported successful production snapshot creation,
  integrity/application validation, identical-row isolated restoration and
  transfer to encrypted local storage. These are owner-reported results, not a
  claim that this agent performed those operations. **Final off-disk verification
  subsequently passed on 2026-10-31:** the downloaded file matches the owner's
  Render-original SHA-256, passes integrity/foreign-key/application validation
  under SQLite 3.51.3, and produces an identical-row isolated restore. There are
  2 missions and 11 finalized results in the 323,584-byte snapshot. The input was
  mounted read-only; its checksum was unchanged afterward. Temporary restored
  data was created only on the owner's encrypted storage and removed afterward.
  Detailed production-backup evidence remains in the owner's private operator
  records and is excluded from Git and Sites source publication.
  Encryption is owner-confirmed, not independently audited. Do not create another
  production snapshot or change production to repeat completed work.
- The owner confirmed SSH works with `UpdateHostKeys=no` while retaining
  `StrictHostKeyChecking=yes`. Keep host verification enabled; do not rotate or
  create SSH/gateway credentials. Render MCP still cannot execute shell commands.
- Hosted acceptance of the changed application: intentionally not attempted before
  deployment authorization. Existing hosted-playtest evidence covers the old version.

## Runtime decision and provenance

The published [Debian patch series for 3.46.1-7+deb13u2](https://sources.debian.org/patches/sqlite3/3.46.1-7%2Bdeb13u2/)
contains no WAL-reset correction. The additional security patches affect expression
handling, initialization and FTS5, not the WAL implementation. This package is not
an acceptable patched runtime for this rollout.

[SQLite's WAL documentation](https://www.sqlite.org/wal.html#walreset) identifies
the affected range as 3.7.0 through 3.51.2 and the first fixed release as 3.51.3,
with designated backports 3.44.6 and 3.50.7. The trigger involves multiple
connections writing/checkpointing the same WAL database concurrently. Retain the
single application writer and read-only backup source even after upgrading.

Recommendation: compile the official **SQLite 3.51.3** amalgamation in a Docker
builder stage and copy only its shared library into the existing Python 3.12
runtime. Keep Python's stdlib `sqlite3` driver, the FastAPI application, schema
version 2, aggregate format 1, existing SQLite files, disk, and single worker.
No new database service, Python database driver, schema conversion, or provider
request is required. This is a pinned known-fixed release, not a claim to be the
newest SQLite release.

The [official release record](https://www.sqlite.org/releaselog/3_51_3.html)
publishes the amalgamation SHA3-256 and source ID. Dockerfile checks enforce:

| Artifact | Verification |
| --- | --- |
| Official archive | `https://www.sqlite.org/2026/sqlite-autoconf-3510300.tar.gz` |
| Archive SHA-256, calculated from that download and pinned | `81f5be397049b0cae1b167f2225af7646fc0f82e4a9b3c48c9ea3a533e21d77a` |
| `sqlite3.c` SHA3-256, matched against upstream publication | `32d5424f97e0a7fc5ed2f6335afbb58be4e0298bd7117a34e39d345ff13d859e` |
| Source ID | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| Python dynamic binding, checked with `ldd` | `/opt/sqlite/lib/libsqlite3.so.0` |
| Python runtime | SQLite `3.51.3`; `threadsafety=3` |

The Debian package inventory can continue to report 3.46.1: Python intentionally
loads the verified library above through `LD_LIBRARY_PATH`. The build fails if
Python reports a different runtime or source ID. Recheck the actual live Python
process environment and SQLite source ID after the authorized deployment.

Local tests used synthetic lobby, active and completed ten-crisis missions. An
old 3.46.1 database remained readable/writable under 3.51.3, then under the old
application again after the optional activity table was added. Finalized result
rows/hashes, schema and aggregate meaning were preserved. An acknowledged-result
set can serialize in a different order between Python processes; that is not a
change to the records or game rules. No format migration was performed.

## Backup using tooling available before deployment

`deploy/backup_current.py` is a standalone operator script. It uses stdlib Python,
`sqlite3.Connection.backup()` and the **already deployed** `app.persistence`
validator. It does not import the new `app.backup` module, install packages, run
the application, or acquire a second application-writer lock.

The source is opened with `mode=ro`. SQLite's online backup API incorporates
committed WAL contents into a consistent snapshot while the application retains
writer ownership. Only the NEW destination is checkpointed and switched to DELETE
journaling to make the transfer artifact self-contained. Production journal mode,
records and application ownership remain untouched.

Each run creates a unique mode-0700 directory under `/data/operator-backups` and
an exclusive mode-0600 snapshot. It requires two snapshots' logical size plus
64 MiB free space, limits each copy to 60 seconds, fsyncs the snapshot and checksum
manifest, and removes an incomplete snapshot directory on failure. Verification:

1. Full `integrity_check`, `foreign_key_check`, schema version 2.
2. Existing domain validation, aggregate checksums, immutable result-index hashes
   and resolution counts.
3. A second database created at a fresh temporary path, checked independently;
   all mission, resolution and optional activity rows and table definitions must
   match the snapshot. The temporary restore is removed afterward.
4. SHA-256 recorded for the verified standalone file, with sanitized counts,
   size, runtime version/source ID and verification status. No private game
   content, mission identifiers or credentials appear in the report.

Execute through the existing service's authenticated SSH connection, from this
checkout (the file is streamed; it does not need to be deployed):

```sh
ssh -o StrictHostKeyChecking=yes -o UpdateHostKeys=no \
  srv-dbif74flk1mc73ek1i90@ssh.virginia.render.com \
  'cd /app && python -' < deploy/backup_current.py
```

First verify the host key against [Render's published Virginia key](https://render.com/docs/ssh#renders-public-key-fingerprints).
Use a temporary pinned known-hosts file if needed; never disable verification.
The script may also be pasted into the existing service's Dashboard Shell as a
Python heredoc. Do not use an ephemeral instance or a one-off job: those cannot
access this disk and may add charges.

## Secure retention away from the Render disk

**An on-disk snapshot alone does not satisfy the deployment gate.** The owner
must identify an existing encrypted, access-controlled local volume/directory.
No additional storage account, paid service, key creation or secret rotation is
part of this plan. Encryption of an unspecified local directory is not assumed.

Transfer only the produced snapshot and `SHA256SUMS` using authenticated
[SFTP/SCP](https://render.com/docs/disks#transferring-files), into an exclusive
private directory on that encrypted destination. Compare both SHA-256 values and
repeat application validation and the isolated-restore check on the downloaded
file under the patched runtime. Mount the off-disk backup read-only when using a
local verification container; write the temporary restore elsewhere. Never add
the database to Git, a Sites source archive, chat attachments or public links.

Record only sanitized verification evidence in the repository. Keep backup
contents and credentials on the private destination. The proposed backup
retention is through rollout acceptance plus a seven-day rollback window, then
delete according to the owner's encrypted-storage policy; confirm this with the
owner. Do not treat the live game's 30-day retention as permission for indefinite
backup archival. Take a fresh snapshot close to the eventual rollout if play has
continued since this checkpoint.

Retain the selected operator snapshot on `/data` during this rollout. Removing
backup artifacts later requires the owner's retention decision; never delete
production database, WAL, SHM or ownership-lock files. Secure retention remains manual;
there is no new scheduled job, public backup endpoint, telemetry store or paid
backup service. Transfers use existing metered bandwidth.

## Frozen resource and security configuration

| Setting | Preserve |
| --- | --- |
| Workspace | `consensus engine` / `tea-dbiehfugekts73ado260` |
| Render service | `srv-dbif74flk1mc73ek1i90`, Virginia, Docker |
| Compute | One `0.5c-512mb` instance; 0.5 CPU / 512 MB; one Uvicorn worker |
| Disk | Existing `dsk-dbif74nlk1mc73ek1j80`, 1 GB at `/data` |
| Database | `/data/consensus-engine.sqlite3`, version 2 / aggregate format 1 |
| Deployment | Manual only; automatic deploys and PR previews off |
| Health | `/api/health`, public health only, no mission data |
| Gateway | Existing matching secret and exact Sites origin; no key rotation |
| Sites | Existing `appgprj_6ae4eb0c13cc8191ad3f7fe36e793414`; owner-private |
| Generation | `CONSENSUS_LLM_ENABLED=false`; no provider key |
| Retention | Disconnected lobby 24 h, unfinished 7 d, completed 30 d; connected missions exempt |
| Admission | Approved limits including 200 missions, 256 MiB DB+WAL threshold, 64 MiB free reserve |

Read-only platform checks confirmed the compute/disk/manual deployment settings
and Sites custom access with one allowed owner and zero external visitors.
Gateway and provider secrets were neither retrieved nor changed in this follow-up.
Do not reapply the Blueprint or its `generateValue` gateway declaration. Update
the existing services only. The existing base charge remains the approved $7.25
per month, excluding tax and usage overages; this plan requests no paid additions.
Builds use included pipeline minutes only, with the owner's $0 additional-build
spending limit. If those minutes are unavailable, stop; do not change billing.

## Rollout sequence — requires separate explicit authorization

1. Complete the production backup, encrypted off-disk transfer and verified
   isolated restore. Capture the live Render deploy ID, exact commit, resource
   settings and private Sites version/environment revision. Confirm rollback
   artifact availability and no active human mission before the maintenance window.
2. Review and authorize the exact deployment-source commit/push separately; no
   commit exists for these changes yet. Prepare the Sites source package through
   its supported workflow only after that authorization, excluding unrelated
   untracked gameplay work, databases, backup artifacts and secrets.
3. **Sites relay first:** update the existing owner-private Site using the
   private-deployment operation, retaining existing runtime credentials. The relay
   derives the pseudonymous visitor claim from authenticated Sites identity and
   ignores caller-supplied identity/forwarding headers. Verify owner access and
   HTTPS/WSS intents against the old backend, which ignores the added header.
   Confirm anonymous/nonowner access is denied. If this stage fails, stop before
   touching Render and restore the previous private Sites version if necessary.
4. **Render second:** manually deploy the reviewed commit to the existing service,
   preserving its disk, secrets, origin, disabled generation and resource settings.
   Expect a short outage: [disk-backed services do not support zero-downtime deploys](https://render.com/docs/deploys).
   No pre-deploy task may access the disk or run migrations. Check successful build,
   `live` deploy status, health, runtime source ID and absence of recovery errors.
5. Conduct private hosted acceptance. Use the owner's authenticated browser
   contexts for separate player seats; do not broaden access just to obtain
   three players. Verify three-player role allocation/filtering, chat/presence,
   hidden votes, plurality, top tie, Consensus Window revote and AI tie-break,
   ten-crisis completion/endgame history, refresh/reconnect identity, rejection
   of wrong seat/host credentials, and unauthorized direct Render HTTP/WSS access.
   Verify quotas cannot be bypassed with spoofed visitor/forwarding headers.
6. Verify existing and new history survive the deployment/reconnect. If an extra
   restart is included in the owner's rollout authorization, perform it only
   without active human missions and repeat reconnect/history/integrity checks.
   Read the live database through a consistent read transaction or another
   verified snapshot; never open a second mission writer.
7. Confirm adoption metadata gives old records full initial retention, connected
   missions are exempt, limits match approved values and cleanup is healthy.
   Exact 24 h / 7 d / 30 d expiry is covered with injected-clock local tests;
   never shorten production TTLs, change its clock or delete real missions to
   accelerate hosted acceptance. Record naturally due cleanup when observable.
8. Check sanitized rejection/cleanup counters, memory/disk/WAL and available
   bandwidth. Stop on integrity, private-information, authorization or reconnect
   failures. Keep owner-private regardless of test outcome; public access needs
   another approval.

## Rollback

- Before rollout, retain the current Sites version and the live Render build
  artifact. Prefer a rollback of application changes **while retaining the patched
  SQLite library**. A local image using the baseline application's exact commit
  plus the pinned runtime is prepared for compatibility rehearsal; it is not
  pushed or deployed. Publishing such a rollback commit/image also needs approval.
- If the new backend fails, roll back the **backend first**, leaving the new
  compatible relay in place. Confirm healthy old-app behavior, then revert the
  Sites relay only if needed. Reverting the relay first would remove a claim the
  new backend requires and deny legitimate requests.
- A rapid Render rollback to the original retained build also restores its older
  SQLite runtime. That is a temporary private-only recovery option, not the
  preferred steady state. Keep one writer, do not add an online checkpointer,
  and schedule the fixed-runtime application rollback if needed.
- [Render rollback](https://render.com/docs/rollbacks) restores the target build's
  start/health/environment settings, while disk contents remain current. Verify
  the resulting gateway/origin, LLM-off, instance count, health path and manual
  deployment settings rather than assuming all settings were unchanged.
- The older application ignores the optional activity table. It must be re-aged
  conservatively before cleanup is re-enabled after an extended rollback, since
  the old writer does not refresh those timestamps. Preserve all existing data.
- Code rollback cannot undo retention deletions. **No production database restore
  or overwrite is authorized.** If corruption/data recovery is needed, stop and
  obtain approval for a separate offline recovery plan, preserving the original
  database and sidecars. Never delete the live database to resolve startup failure.
- Do not resize, add services, rotate secrets, enable automatic deploys, change
  gameplay or make the Site public during recovery.

## Authorization checkpoint

The off-disk backup gate is complete against the owner's supplied original
checksum. On 2026-10-31 the owner explicitly authorized the scoped commit/push
and coordinated owner-private rollout described above, with no additional
deliberate restart, paid resources or public access. Private approval and backup
records stay outside the published source. Record actual rollout results
separately; authorization alone is not evidence of a successful deployment.

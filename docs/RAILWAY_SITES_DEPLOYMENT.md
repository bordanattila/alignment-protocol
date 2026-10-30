# Railway backend + private Sites frontend

Prepared October 30, 2026. Configuration is ready for review; nothing has been
deployed. No Railway service, volume, domain, subscription, or Sites project has
been created. No hosting charges or paid inference requests were initiated.

## Architecture

```text
Authorized browser
  → owner-private ChatGPT Site (existing React frontend)
  → same-origin /api relay, including WebSocket upgrade
  → HTTPS Railway endpoint guarded by a server-only key
  → one Uvicorn/FastAPI process and existing authoritative engine
  → SQLite on a persistent Railway volume mounted at /data
```

The Site serves the original Vite output and forwards intents and snapshots.
It does not own missions, count votes, change roles, run timers, or store history.
The frontend components, styles, request paths, seat credentials, and reconnect
loop are unchanged. No CORS configuration or browser-visible backend key is
needed. The relay verifies Sites' authenticated visitor header and the browser
Origin before forwarding. Sites' owner-private access policy remains required.

The Railway URL is internet-routable for communication from Sites, but game
endpoints reject requests without the server-only gateway key. `/api/health`
alone remains available for readiness checks and exposes no mission state.
This setup is a protected preview, not approval to make the game publicly
playable. Provisioning even that protected internet endpoint awaits approval.

## Prepared files

| File | Purpose |
| --- | --- |
| `Dockerfile`, `.dockerignore` | Python 3.12 backend image; no frontend, local database, credentials, or evidence files copied. |
| `railway.toml` | Docker build, one replica, required `/data` mount, health check, no sleeping or overlapping deployments. |
| `backend/app/railway.py` | Deployment-only ASGI factory wrapping the existing app with gateway access control. |
| `deploy/railway.env.example` | Backend configuration names; no actual secrets. |
| `deploy/sites/worker.mjs` | Fixed-upstream HTTP/WebSocket relay and serving of original built frontend assets. |
| `deploy/sites/build.mjs` | Produces Worker ESM at repository-root `dist/server/index.js`; embeds only frontend build assets. |
| `deploy/sites/hosting.example.json` | Storage-binding template; deliberately contains no invented Site ID. |
| root `package.json`, `package-lock.json` | Dependency-free entry point for the Sites build helper. Existing frontend dependency files stay intact. |
| `backend/tests/test_railway_deployment.py`, `backend/tests/smoke_railway.py`, `deploy/sites/worker.test.mjs` | Access, configuration, persistence, relay, and full authored-mission checks. |

The backend factory refuses an unmounted storage directory or a database outside
the mounted volume. It refuses enabled LLM generation and additionally supplies
disabled generation settings directly to the existing application factory.
Generated mission creation therefore remains rejected server-side even if a
visitor sends that mode manually. The original local entry point is unchanged.

## Account connection and approval boundaries

1. **Connect your Railway account:** install/authorize the available Railway
   plugin, or authenticate the Railway CLI yourself. Do not paste Railway
   tokens into chat or commit them. Account access has not been confirmed.
   Connecting an account does not authorize resource creation or spending.
2. **Approve hosting resources and cost before creating anything:** choose the
   Railway workspace, plan, region, and spending limit. Review current pricing
   and account credits. Service compute, persistent volume storage, and network
   traffic may incur charges; this preparation does not assume they are free.
3. **Approve the protected preview deployment:** this includes source upload,
   the Railway service/volume and TLS endpoint, and owner-private Sites
   deployment. Do not connect a repository in a way that immediately starts an
   unapproved build/deployment. Keep automatic deployments disabled until
   explicitly authorized. This runbook is not that approval.
4. **Approve external visitors separately:** owner-private Sites cannot be
   opened by remote teammates. After owner review, explicitly allow selected
   visitors using the supported Sites access controls. Do not switch to public
   access to perform the playtest. Availability of external visitor invitations
   must be checked in the actual workspace.

## Deployment procedure after those approvals

### 1. Establish the private Site identity

Register a new owner-private Site once, or reuse a subsequently created real
`.openai/hosting.json` identity. Do not create duplicate Sites. Record the exact
returned project ID at the **repository root**, using Sites' project-ID helper,
with the `d1` and `r2` values from `deploy/sites/hosting.example.json` left null.
Do not set `static.directory`: this deployment uses a Worker ESM wrapper to
serve the existing Vite assets and relay the API. Record the exact returned
Sites origin; a repository URL is not that origin.

No manifest with a real project ID is present now. `npm run build -- --local`
verifies the Worker without creating a fake identity or deployable manifest.
The local build is not a hosted preview.

### 2. Configure Railway without changing the game

Use this repository as the build context (root directory `/`), `Dockerfile` as
the build file, and `/railway.toml` as configuration. Do not select `backend/`
as the service root: the root Dockerfile copies `backend/app` explicitly.
Keep one service, one replica, one region, and one Uvicorn worker. Do not override
the Docker start command with the unguarded `app.main:app` development command.

Attach a persistent Railway volume at **`/data`**. Volume provisioning is an
account operation; the configuration file does not create it. Set these private
service variables before allowing deployment:

| Variable | Value |
| --- | --- |
| `CONSENSUS_DB_PATH` | `/data/consensus-engine.sqlite3` |
| `CONSENSUS_LLM_ENABLED` | `false` |
| `CONSENSUS_SITE_ORIGIN` | Exact returned HTTPS Sites origin, without trailing slash or path |
| `CONSENSUS_GATEWAY_KEY` | Strong randomly generated server-only key, at least 32 printable ASCII characters |

Do not supply LLM endpoint, model, or API key settings. Railway supplies `PORT`
and the volume mount metadata. The container binds `0.0.0.0:$PORT`. Its mounted
directory must be writable by the container; never solve a startup error by
falling back to ephemeral storage or deleting an existing database.

After deployment is approved, provision a Railway HTTPS endpoint targeting the
service port. Its protected API is the relay's upstream. Neither browser CORS
nor public game access is required. Keep automatic redeploys off for this
initial playtest unless separately authorized.

### 3. Configure Sites server-only runtime values

Use native Sites runtime environment settings:

| Variable | Value |
| --- | --- |
| `CONSENSUS_BACKEND_ORIGIN` | Railway's HTTPS origin only, no path, query, user information, or trailing API prefix |
| `CONSENSUS_GATEWAY_KEY` | Same private key as the backend |

Never use `VITE_` for these values. Do not put them in the hosting manifest,
frontend bundle, source archive, prompts, or logs. The relay strips visitor
cookies, authorization, and Sites identity headers before forwarding and
supplies its own gateway key. The backend still requires the existing separate
seat credential for every player action; the gateway does not replace seat
authorization.

### 4. Build, save source, and deploy owner-private

Install the retained frontend dependencies with `npm --prefix frontend ci`.
From the repository root, run the Sites source helper with ordered remaining
commands:

```json
[
  ["npm", "--prefix", "frontend", "ci"],
  ["npm", "run", "test:relay"],
  ["node", "<installed Sites plugin root>/scripts/build-site.mjs"]
]
```

Use the actual installed absolute helper path in execution. Keep the **entire
repository** as the source checkout, because the build references the existing
`frontend/` source. The archive contains the built Worker and manifest, not the
Python backend or crisis catalog. Only upload source after source synchronization
is authorized; the Sites helper commits/pushes to its private source repository.
No commit or push was performed during preparation.

Save the exact pushed source/version and use the owner-private deployment
operation. Retain the existing audience. Poll nonterminal deployment status,
then open its returned URL for owner review. A deployment URL does not imply
permission to grant public access.

## Verification performed

- Backend regression suite: **673 passed**, one existing dependency warning.
- Existing frontend suite: **105 passed, 4 skipped**, no failures.
- Relay tests: **5 passed**, covering asset serving, credential forwarding and
  stripping, sign-in and Origin checks, configuration failures, sanitized
  errors, and preservation of the runtime's upgrade response.
- Strict TypeScript/Vite build and local Sites Worker build passed. Existing
  frontend bundle filenames/hashes remain the same as before adaptation.
- Production Docker image built successfully. A localhost container test used
  a temporary mounted directory and a nondefault `PORT`; it checked health,
  private access, disabled generation, two real WebSocket clients, ten-crisis
  campaign length, role privacy, and identity/role persistence after stopping
  and recreating the container. Containers and temporary databases were removed.
- `smoke_railway.py` completed all ten authored crises with three real local
  WebSocket clients through the ASGI gateway, including initial tie, Consensus
  Window, fresh final vote, conditional authored follow-ups, synchronized
  metrics/history, privacy, idempotent acknowledgements, and process restart.
  That fixture uses an injected clock, leaving production timings unchanged.

Reproduce the local checks (no Railway account or hosted service needed):

```sh
CONSENSUS_LLM_ENABLED=false .venv/bin/python -m pytest backend/tests -q
CONSENSUS_LLM_ENABLED=false .venv/bin/python backend/tests/smoke_railway.py
npm --prefix frontend test
npm run test:relay
npm run build -- --local
docker build -t consensus-engine-railway:local .
```

**Remote HTTPS/WSS and actual Sites-edge acceptance remain unverified.** Node's
relay test uses a status-101 sentinel because Node cannot construct a Worker
WebSocket response; that test does not prove hosted upgrades. No browser preview
or hosted URL exists yet. Verify the actual Sites runtime forwards the upgrade
and supplies its authenticated visitor header on the WebSocket handshake before
declaring the preview playable. If not, stop and report the hosting limitation;
do not replace real multiplayer with a simulation or silently change transport.

## Hosted acceptance and operations

Before owner acceptance, verify that an unsigned visitor cannot access the
private Site, direct Railway game HTTP and WebSocket requests are rejected, and
the owner can create and restore a seat through Sites. Confirm capabilities
report generated missions disabled. Then, after selected test visitors are
approved, use separate browsers/devices to verify 2–4-player create/join,
capacity, public AI recommendations, role-private network payloads, chat,
presence, hidden votes, 2-1-1 plurality, first tie and second-tie AI fallback,
refresh/reconnect, ten-crisis completion, endgame review, and phone layout.
Exercise normal production timers. Restart the Railway service with the same
volume and check seat/history recovery through the same Sites URL.

Keep the Sites hostname stable: browser seat credentials are origin-scoped.
Back up SQLite with its backup API or stop the service before copying; never
copy only the live main file while WAL is active. Preserve the volume on
redeploy and rollback. A volume-backed Railway service has deployment downtime;
the existing reconnect behavior handles interruptions, but a restart is not a
zero-downtime guarantee. Do not roll back to application code unable to read
the saved database format. Rotate the gateway key in both services together.

Deployment preserves the current implemented rules, including the existing
30-second voting rounds and fixed final crisis. It does not add five-minute
seat expiry/role redistribution or weakest-metric finale selection, which were
not implemented in this checkout. Authored scenarios and deterministic endings
remain in use; optional live generation stays off.

## Official references checked

- [Railway FastAPI deployment](https://docs.railway.com/guides/fastapi)
- [Railway configuration as code](https://docs.railway.com/config-as-code/reference)
- [Railway configuration schema](https://railway.com/railway.schema.json)
- [Railway persistent volumes and deployment constraints](https://docs.railway.com/volumes/reference)
- [Railway HTTPS/WebSocket support](https://docs.railway.com/networking/public-networking/specs-and-limits)
- [Railway pricing](https://railway.com/pricing)

Sites runtime and artifact requirements were checked against the installed
Sites skill, Worker ESM starter, storage/identity references, and packaging
helpers. See `SITES_DEPLOYMENT_ASSESSMENT.md` for the initial compatibility
assessment; this runbook records the subsequent choice of Railway.

# Render + owner-private Sites: provisioning review

Prepared October 30, 2026. The user approved the architecture and local
preparation, not billable resources or deployment. No Render resource or Site
has been created. Render installation/authorization is pending user interaction;
account access has not been confirmed.

Connection update: Render is now installed and authenticated workspace discovery
succeeded. It lists a workspace named `consensus engine`; selection awaits user
confirmation before workspace-scoped reads. The prepared Blueprint passed the
current public Render JSON Schema using the system validator. The connected
tool surface does not expose billing-plan/payment/spend-limit reads or Blueprint
API validation. Account billing controls therefore still require Dashboard
verification; schema validation must not be described as provider API acceptance.

Workspace confirmation: the user authorized read-only checks in `consensus
engine`. Listing services including previews succeeded and returned no services.
No workspace settings were modified. Provisioning/deployment remain unauthorized.

## Authorized deployment attempt

The user subsequently explicitly authorized exactly the $7 service, $0.25
1 GB disk, guarded backend, and owner-private Sites deployment. Hobby and the
$0 additional pipeline spending limit were confirmed by the user. This
supersedes earlier approval-pending statements above; the resource scope and
ban on public access or extra paid resources remain in force.

Sites registration succeeded and was persisted in `.openai/hosting.json`:
`appgprj_6ae4eb0c13cc8191ad3f7fe36e793414`. Expected origin:
`https://consensus-engine-playtest.justfrog18.chatgpt.site`. Access inspection
confirmed only the owner, zero external visitors and no groups. Both live and
preview deployment URLs remain null: registration is not deployment. Reuse this
identity; do not create a second Site.

The configured GitHub remote is `bordanattila/alignment-protocol`. Deployment
files are uncommitted locally and absent from the remote default branch.
An explicit request to authorize a dedicated `codex/render-deploy` branch
commit/push is pending because repository instructions require that permission.
No commit, push or source upload has been performed in this attempt.

The user subsequently explicitly authorized committing and pushing the reviewed
deployment source on `codex/render-deploy` to the existing GitHub repository,
without merging into the default branch. Unrelated untracked gameplay-evaluation
work is excluded from the deployment commit. The branch preserves the current
locally verified game revision; the remote default branch has an older game.

The Render connector exposes service creation but not attached-disk creation
or Blueprint application. Windows Dashboard automation failed at initialization
with `sandboxCwd is not a local file URI` for this WSL checkout, including one
reset/retry; no Dashboard input occurred. Do not create the backend without a
verified route to provision its required disk. The Render Dashboard Blueprint
flow can create the approved service and disk together once source is pushed,
or the user can attach the approved disk to a connector-created service. No
Render service or disk has been created yet.

Source handoff update: deployment source was committed and pushed to
`codex/render-deploy`. The Blueprint explicitly selects that branch and the
registered private Sites origin. Render generates the initial gateway key, so
no key needs to be entered or shared during Blueprint creation. After the
service exists, the deployment agent can set a fresh matching key on Render
and Sites through their native secret-setting tools before preview deployment.
Do not disclose either key in chat. In the Dashboard, create a Blueprint from
this repository, select `codex/render-deploy`, review exactly one $7 service
and one 1 GB $0.25 disk, and apply the already authorized configuration. Do not
use the older default branch. The missing step is Dashboard interaction, not
additional resource authorization.

## Prepared configuration

`render.yaml` defines exactly one Docker web service, plan `0.5c-512mb`, one
instance, region Virginia, health check `/api/health`, and one 1 GB disk mounted
at `/data`. Auto-deploys and Blueprint previews are disabled. The existing
Docker CMD binds `0.0.0.0:$PORT`, uses one Uvicorn worker, and runs the guarded
application factory. Do not override it with the unguarded development entry
point. Applying the Blueprint still creates resources and starts an initial
deployment; do not apply it before separate approval.

Reuse the existing Dockerfile, Sites build and relay, game engine, authored
content, SQLite schema and persistence. `railway.toml` is unused on Render.
The existing Railway-named factory defaults to `/data` without Railway
metadata; no renaming or architecture change is necessary. Leave
`RAILWAY_VOLUME_MOUNT_PATH` unset. `deploy/render.env.example` lists the
required runtime variables without storing real credentials.

Set `CONSENSUS_DB_PATH=/data/consensus-engine.sqlite3`,
`CONSENSUS_LLM_ENABLED=false`, the exact private Sites origin, and a strong
random server-only gateway key shared with Sites. Supply no provider API key.
Configure Sites' `CONSENSUS_BACKEND_ORIGIN` to the returned Render HTTPS origin.
Keep the gateway key out of source and all browser-visible/VITE settings.

No database was copied or migrated. Selection of an existing database to retain
must be explicit before any later transfer; do not silently seed the disk from
local development data. Render's disk is unavailable during builds/pre-deploy
commands. Keep database initialization in the existing runtime lifecycle.

## Cost and safeguards

Published USD full-month base: Hobby workspace $0 + compute $7 + allocated
1 GB disk $0.25 = **$7.25/month**, before taxes, overages, or any Sites/account
charges. This is not an all-inclusive spending cap.

Hobby includes 5 GB/month outbound bandwidth across the workspace. Public
outbound traffic above that costs $0.15/GB, including HTTP and WebSocket
responses to Sites. For example, 10 GB total means $0.75 overage and an $8.00
Render base-plus-bandwidth total before tax, assuming no build overage.
Rejected requests can still consume outbound traffic; the gateway is access
control, not a billing cap.

Hobby includes 500 standard pipeline minutes/month. Additional minutes are
priced at $5/1,000 minutes. Before deploying, set the account's additional
pipeline spend limit to $0 if supported by its settings, and verify the saved
value. This control applies to builds, not bandwidth, compute, or disk fees.
No account billing safeguard has yet been applied or verified. Do not promise
a hard $7.25 ceiling: the reviewed documentation describes automatic bandwidth
overage billing with a payment method and does not establish a configurable
hard bandwidth cap.

Before provisioning, inspect the connected workspace's plan, shared usage,
payment settings, pipeline limit and notification options. Propose a separate
bandwidth allowance for the user's approval; it has not been approved yet.
Keep one instance, a 1 GB disk, manual deployments, no preview duplicates, no
extra services or provider credentials. Any notifications/monitoring must be
configured only with authorization; none were scheduled during preparation.

## Local capacity and access verification

The existing production image ran successfully with Docker limits of 512 MiB
RAM, no extra swap, and 0.5 CPU, using PORT 10000 and a temporary disk mounted
at `/data`. Four real WebSocket clients joined one authored ten-crisis mission,
started it, and received the briefing with one private role each. Observed
Docker memory use after the check was **44.93 MiB / 512 MiB**, CPU **4.16%**;
the container reported no OOM kill. This is a small functional sample, not
peak-memory measurement or a sustained multi-mission capacity guarantee.
The temporary container and database were cleaned up.

Ten gateway regression tests and five relay tests passed. Regression coverage
now explicitly checks that direct create/join requests with a known invite,
spoofed valid Origin, absent key or wrong key are rejected. WebSocket access
without gateway authorization is also rejected. Existing gateway verification
from the Railway preparation already exercised full ten-crisis play and restart
recovery locally; that is not evidence of hosted Render/Sites acceptance.

Both transports require the server-only gateway key before the existing game
handlers run. Invite tokens, spoofed Origin headers, and seat credentials alone
cannot bypass this boundary. Only GET `/api/health` is deliberately exempt and
contains no mission data. Once through the gateway, existing seat authorization
still applies. The Sites relay requires its authenticated visitor header and
checks Origin; Sites' owner-private access policy remains mandatory.

This protects direct backend game access provided the real key stays secret,
the guarded factory remains the entry point, and Sites access is configured
correctly. It is not an absolute guarantee against a leaked key or an incorrect
deployment. The Render HTTPS hostname itself is internet-routable so Sites can
reach it; private-preview access means game operations are protected, not that
the backend has no public network endpoint.

## Remaining gates

1. User installs/authorizes Render; inspect account state read-only.
2. Validate the Blueprint using the connected Render validation facility and
   confirm current plan price and billing controls. Local parsing alone is not
   provider validation.
3. Ask separately for approval of resource provisioning and protected-preview
   deployment, stating the $7.25 base, taxes/exclusions, and agreed bandwidth
   exposure. Do not treat architecture approval as permission to apply YAML.
4. Only after that approval, create service/disk, configure server-only secrets,
   and deploy Sites owner-private. Reuse the source workflow in
   `RAILWAY_SITES_DEPLOYMENT.md`, substituting Render as the upstream.
5. Verify hosted private access, blocked direct create/join/WebSocket attempts,
   disabled generation, HTTPS/WSS upgrades through Sites, remote create/join,
   votes/ties, chat/presence, reconnect, complete mission and persistent restart
   recovery. Disk-backed redeploys interrupt connections; test that recovery.
   Granting external visitor access or public publication needs separate approval.

## Official references

- [Pricing](https://render.com/pricing)
- [Outbound bandwidth](https://render.com/docs/outbound-bandwidth)
- [Pipeline spend limits](https://render.com/docs/build-pipeline)
- [Blueprint fields](https://render.com/docs/blueprint-spec)
- [Persistent disk restrictions](https://render.com/docs/disks)
- [WebSocket hosting](https://render.com/docs/websocket)

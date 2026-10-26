# AGENTS.md — Consensus Engine

## Project Identity

This repository contains **Consensus Engine**, a real-time cooperative multiplayer web game for 2–4 players.

**Pitch:** A team jointly supervises a powerful AI during cascading near-future civic crises. The AI proposes an action, each player receives different private intelligence, the team discusses and votes, and everyone shares the consequences.

**Tagline:** *Intelligence proposes. Humanity decides.*

The current target is **Consensus Engine v0.1 MVP**.

---

## Product Priorities

Optimize for these priorities in order:

1. Multiplayer correctness and synchronization
2. A complete playable game loop
3. Clear information privacy boundaries
4. Reliable reconnect behavior
5. Simple join flow
6. Responsive usability
7. Visual polish
8. Automated tests
9. Extensibility for future LLM-generated crises
10. Additional features

Do not sacrifice multiplayer reliability for decorative features.

Favor a small, finished, deployable game over an ambitious incomplete system.

---

## Required MVP Behavior

The MVP must support:

- 2–4 players
- Browser-based play
- Host-created missions
- Invite-link joining
- QR-code joining
- No accounts or passwords
- Callsign/display-name entry
- Automatic role assignment
- Four roles/domains:
  - Infrastructure
  - Community
  - Economy
  - Safety
- Authored/scripted crises
- Exactly three authored choices per crisis
- One explicitly marked AI recommendation
- Role-specific private intelligence
- Built-in real-time text chat
- 60-second discussion period
- Hidden voting
- Plurality winner
- 20-second Consensus Window only when the highest vote count is tied
- Revote during Consensus Window
- AI recommendation executes if the second vote remains tied
- Four shared metrics:
  - Infrastructure
  - Public Trust
  - Economy
  - Safety
- Each metric begins at 70
- Immediate loss if any metric reaches 0
- Team victory after surviving all crises
- Final Consensus Score = average of final metrics
- Approximately 10 crises per run
- Variable crisis order
- Final crisis selected from the team's weakest metric
- Five-minute player reconnection grace period
- Game continues after timeout if at least 2 players remain
- Orphaned roles are redistributed after disconnect timeout
- Replay/new mission
- Phone and laptop support

---

## Voting Rules

Do not implement strict-majority voting.

Use **plurality voting**.

A choice wins if it has more votes than either other choice.

Examples:

- 4 players: `2-1-1` is a valid win.
- 4 players: `2-2-0` is a tie.
- 3 players: `2-1-0` is a valid win.
- 3 players: `1-1-1` is a tie.
- 2 players: `2-0-0` is a valid win.
- 2 players: `1-1-0` is a tie.

If the top vote is tied:

1. Start a 20-second Consensus Window.
2. Clear votes.
3. Allow discussion/chat.
4. Revote.
5. If one option has a unique plurality, execute it.
6. If the top result is still tied, execute the AI-recommended option.

Vote contents must remain private until the vote resolves.

Clients may see whether another player has voted, but not what they chose.

---

## Player/Role Rules

Roles are assigned automatically.

- 4 players → one role each
- 3 players → one player receives two roles
- 2 players → each player receives two roles

A player sees private intelligence for every role assigned to them.

Do not expose another player's private intelligence to the client.

Do not rely on CSS/DOM hiding for secret information. The backend should send each client only the private information that client is entitled to receive.

---

## Disconnect/Reconnect Rules

Connectivity loss is expected and must be handled deliberately.

When a player disconnects during a match:

1. Mark them disconnected.
2. Notify remaining players.
3. Preserve their identity, seat, roles, and game membership.
4. Start a five-minute grace period.
5. Pause forward progression when necessary to avoid resolving a round without the missing participant.
6. Allow reconnection using a stable client/session identity.

If the player reconnects within five minutes:

- Restore the same identity
- Restore the same roles
- Restore the current authoritative state
- Resume play

If the player does not reconnect within five minutes:

- Remove them from the active-player set
- Notify remaining players
- Redistribute the departed player's role(s) among remaining players
- Continue if at least two active players remain

If fewer than two active players remain, end the session gracefully.

A browser refresh must not create a duplicate player.

---

## Product Architecture

Preferred stack:

### Frontend

- React
- Vite
- TypeScript
- Responsive CSS
- WebSocket client

### Backend

- FastAPI
- Python
- WebSockets
- Server-authoritative game state

### Storage

For v0.1, active mission state may be held in memory.

Do not introduce PostgreSQL, Redis, authentication providers, or other infrastructure unless a demonstrated requirement makes them necessary.

Structure state access so persistence can be added later.

### Deployment

Prefer a simple deployment model.

A good default is:

- Vite builds the React frontend.
- FastAPI serves the built frontend/static assets.
- FastAPI owns APIs and WebSocket connections.

Do not split the deployment into multiple services without a concrete benefit.

---

## Server Authority

The server is the source of truth.

The client must not independently decide:

- phase transitions
- final vote result
- timer completion
- role assignment
- metric changes
- win/loss state
- crisis order
- final-crisis selection
- disconnect timeout resolution

Clients send intents. The server validates them and broadcasts authoritative state.

Use explicit state transitions.

Recommended phases:

- `lobby`
- `briefing`
- `discussion`
- `voting`
- `consensus_window`
- `resolution`
- `reconnect_wait`
- `completed`
- `failed`

Equivalent naming is acceptable if behavior remains explicit and testable.

---

## Timer Rules

Timers should be based on server-authoritative deadlines/timestamps rather than independent per-client countdown logic.

Clients may animate local countdowns from a server deadline.

Critical transitions must be decided by the backend.

This applies to:

- 60-second discussion
- 20-second Consensus Window
- 5-minute reconnect grace period
- short resolution/result display where applicable

---

## Crisis Content Architecture

MVP crises are authored/scripted.

Do not call an LLM during v0.1 gameplay.

However, the long-term product must support LLM-generated scenarios.

Therefore:

- Keep crisis content separate from engine logic.
- Use a structured schema.
- Avoid switch statements keyed to specific crisis IDs for general behavior.
- Make scenario pools easy to expand.
- Keep metrics, private intelligence, choices, AI recommendation, and consequences data-driven.

A conceptual crisis structure:

```json
{
  "id": "grid-under-pressure",
  "title": "Grid Under Pressure",
  "briefing": "...",
  "ai_recommendation_choice_id": "A",
  "private_intelligence": {
    "infrastructure": "...",
    "community": "...",
    "economy": "...",
    "safety": "..."
  },
  "choices": [
    {
      "id": "A",
      "title": "...",
      "description": "...",
      "consequence": "...",
      "metric_deltas": {
        "infrastructure": 0,
        "public_trust": 0,
        "economy": 0,
        "safety": 0
      }
    }
  ]
}
```

The exact schema may evolve, but the separation of content and engine is mandatory.

---

## Crisis Design Rules

Every normal crisis must contain exactly three choices.

One choice is the AI recommendation.

The AI recommendation must not always be:

- the best answer
- the worst answer
- the safest answer
- the highest-scoring answer

Do not train the player to automatically accept or reject the AI.

Good scenarios create genuine tradeoffs between roles and metrics.

Private intelligence should materially affect how a player evaluates the choices.

Avoid trivia questions with an objectively obvious answer.

Avoid moral choices where one option is cartoonishly evil.

The desired question is:

> "Given our incomplete and conflicting information, which tradeoff can the group accept?"

---

## Crisis Order

Runs should not always use the same order.

For v0.1:

- Select approximately 9 normal crises from the authored pool.
- Randomize their order.
- Do not repeat a crisis within one run.
- Use a final crisis chosen according to the weakest civilization metric.

The final crisis should make the session feel connected to prior decisions.

---

## Civilization Metrics

Canonical shared metrics:

- `infrastructure`
- `public_trust`
- `economy`
- `safety`

Starting value:

`70`

Recommended bounds:

`0..100`

After resolution, clamp values if needed.

If any metric reaches zero:

- transition immediately to failed/loss state

If all intended crises are completed and no metric is zero:

- transition to completed/victory state

Final Consensus Score:

```text
(infrastructure + public_trust + economy + safety) / 4
```

---

## Mission Joining

Do not use a visible four-digit room-code UX.

Mission creation should generate an invite token/identifier suitable for a shareable URL.

The player-facing flow is:

1. Create Mission
2. Copy invite link or show QR code
3. Invitee opens link
4. Invitee enters callsign
5. Invitee joins lobby

No login is required.

Mission tokens should be difficult to guess.

Do not expose internal sequential database IDs as invite identifiers.

---

## Chat

v0.1 requires only simple real-time text chat.

Keep it focused:

- callsign
- message
- timestamp/order
- broadcast to active players

No voice/video.

Do not turn chat into a large standalone subsystem.

---

## Visual Direction

The visual target is:

**Near-future civic command center**

Use a serious, polished operations-console aesthetic.

Desired qualities:

- dark interface
- restrained telemetry
- high readability
- clear hierarchy
- civic/institutional rather than military-hacker cliché
- modern typography
- subtle animation
- clear status changes
- obvious separation of public vs private information
- responsive layouts
- accessible contrast

Avoid:

- neon cyberpunk overload
- Matrix-style code rain
- "evil red AI" clichés
- unnecessary glassmorphism everywhere
- tiny unreadable HUD text
- decorative animation that delays interaction

The UI should look like software people might plausibly use to coordinate a complex city-scale system in the near future.

---

## Responsive UX

The game must work on both laptops and phones.

Design mobile intentionally rather than shrinking the desktop UI.

Prioritize:

1. current crisis
2. private intelligence
3. action choices
4. timer
5. shared metrics
6. chat

Make voting controls touch-friendly.

Do not rely solely on hover.

---

## Security and Privacy Boundaries

This is not a high-security application, but multiplayer boundaries still matter.

At minimum:

- validate every player action server-side
- authorize actions against mission/player identity
- do not trust role IDs supplied by clients
- do not send other players' secret intelligence to the browser
- do not reveal hidden votes before resolution
- use hard-to-guess invite tokens
- sanitize/escape chat rendering
- constrain callsign/message lengths
- reject malformed WebSocket messages
- reject actions inconsistent with current phase
- avoid exposing stack traces to players

Do not add heavy authentication for the MVP unless required.

---

## Testing Expectations

Add automated tests for core rules.

At minimum test:

- role assignment for 2, 3, and 4 players
- mission capacity
- joining flow
- duplicate/reconnect identity handling
- phase transitions
- private-information filtering
- plurality outcomes
- `2-1-1` resolves immediately
- top ties trigger Consensus Window
- second tied vote selects AI recommendation
- metric updates
- metric clamping
- loss at zero
- victory after final crisis
- randomized non-duplicate crisis selection
- weakest-metric final-crisis selection
- disconnect grace period
- reconnect within grace period
- disconnect timeout and role redistribution
- unauthorized/invalid actions
- WebSocket broadcast state consistency where practical

Prefer deterministic unit tests for core game logic.

Avoid tests that depend on arbitrary sleeps when timestamps/clocks can be injected or controlled.

---

## Coding Standards

- Prefer straightforward code over clever abstractions.
- Use descriptive names.
- Keep pure game-rule logic separate from transport/WebSocket code.
- Keep content data separate from engine logic.
- Keep server state mutations centralized.
- Use typed models/schemas.
- Validate external input.
- Avoid giant components and giant route handlers.
- Avoid premature infrastructure.
- Document non-obvious multiplayer/state-machine decisions.
- Do not duplicate logic across client and server when the server should be authoritative.

---

## Change Discipline

Before making substantial changes:

1. Inspect the repository.
2. Identify the current architecture and relevant files.
3. Reuse existing patterns where sensible.
4. Do not assume the repository matches this document if later code has evolved.
5. Explain any architectural deviation that materially changes the MVP.

When implementing a scoped task:

- Change only what is required plus necessary supporting code.
- Do not perform broad unrelated refactors.
- Preserve working behavior.
- Add/update tests.
- Run relevant checks before reporting completion.

Do not create commits unless explicitly asked to commit.

Do not push to a remote unless explicitly asked.

---

## Suggested Implementation Order

Unless repository evidence suggests otherwise:

1. Scaffold React/Vite + FastAPI
2. Define typed game models
3. Implement mission manager/in-memory state
4. Implement invite/join flow
5. Implement WebSocket connection lifecycle
6. Implement lobby synchronization
7. Implement automatic role assignment
8. Define crisis schema/content loader
9. Implement server state machine
10. Implement public/private state projection
11. Implement discussion phase/timer
12. Implement text chat
13. Implement hidden voting
14. Implement plurality resolution
15. Implement Consensus Window
16. Implement metric consequences
17. Implement win/loss state
18. Implement randomized crisis sequence
19. Implement weakest-metric final crisis
20. Implement reconnect/grace-period behavior
21. Implement responsive UI polish
22. Add/complete automated tests
23. Harden deployment

---

## Definition of Done for MVP

Do not call v0.1 complete until:

- two real browsers/devices can join the same mission
- all connected players stay synchronized
- role-private information stays private
- a complete multi-round run can be played
- voting rules work exactly as specified
- consequences update consistently
- win/loss works
- reconnect behavior works
- phone layout is usable
- automated tests cover core game rules
- the application can be deployed publicly

---

## Core Product Principle

All implementation decisions should preserve this:

> **The game is not about blindly trusting or distrusting AI. It is about whether humans can combine incomplete information well enough to decide when an AI recommendation is appropriate, incomplete, or dangerous.**

When in doubt, choose the implementation that strengthens that experience.

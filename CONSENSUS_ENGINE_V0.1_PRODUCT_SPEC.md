# Consensus Engine v0.1 — Product Specification

## 1. Product Summary

**Consensus Engine** is a real-time cooperative multiplayer decision game for **2–4 players**.

Players jointly supervise a powerful AI responsible for helping manage a near-future society during a sequence of escalating civic crises. The AI recommends an action for each crisis, but every player receives different role-specific intelligence. The team must discuss what it knows, vote on one of three authored responses, and live with the shared consequences.

There are no individual winners. The team succeeds or fails together.

**One-sentence pitch:**  
*A real-time co-op game where 2–4 players jointly supervise a powerful AI during cascading civic crises and only win if they keep society stable together.*

**Tagline:**  
*Intelligence proposes. Humanity decides.*

---

## 2. Product Goals

### Primary goals

1. Deliver a polished, replayable multiplayer game that can be opened from a public URL.
2. Make cooperation necessary by giving players asymmetric information.
3. Make AI recommendations credible but imperfect rather than predictably right or wrong.
4. Keep the rules easy to understand while creating difficult tradeoffs.
5. Support fast entry: no account, no installation, no password.
6. Keep a typical session to approximately **10–15 minutes**.
7. Prioritize reliability, synchronization, and a strong user experience over feature breadth.

### Secondary goals

1. Create a project that demonstrates real-time multiplayer engineering.
2. Establish an architecture that can later support LLM-generated crises.
3. Make the visual identity distinctive and cohesive.
4. Encourage replay by varying crisis order and final outcomes.

---

## 3. MVP Scope

Consensus Engine v0.1 includes:

- 2–4 player real-time multiplayer
- Browser-based gameplay
- Publicly shareable game URL
- Mission creation
- Invite-link joining
- QR-code joining
- Callsign/name entry
- No user accounts
- Automatic role assignment
- Four information domains:
  - Infrastructure
  - Community
  - Economy
  - Safety
- Authored crisis scenarios
- Three authored choices per crisis
- One clearly identified AI-recommended choice
- Role-specific private intelligence
- Built-in text chat
- 60-second discussion phase
- Hidden simultaneous voting
- Plurality-based decision resolution
- 20-second Consensus Window for tied votes
- AI recommendation as the fallback after a second tied vote
- Shared civilization metrics
- Consequence resolution after every crisis
- Approximately 10 crises per session
- Variable crisis order
- Dynamic final crisis based on the team's weakest metric
- Reconnection support
- Five-minute disconnect grace period
- Continued play if a disconnected player does not return
- Cooperative win/loss state
- Final Consensus Score
- Replay/new-mission flow
- Responsive interface for phones and laptops

---

## 4. Non-Goals for v0.1

The following are explicitly outside the MVP unless the core game is complete and stable ahead of schedule:

- Voice chat
- Video chat
- Matchmaking
- User accounts
- Persistent player profiles
- Leaderboards
- Achievements
- Social graph/friends system
- Native mobile apps
- Native desktop apps
- Persistent game-history database
- Complex character/avatar systems
- Procedurally simulated world systems
- Free-form player-authored policy responses
- LLM-generated live crises
- LLM-generated live consequences
- Custom AI agents for individual roles
- Paid features
- Spectator mode

---

## 5. Future Product Direction

The MVP uses **scripted/authored crises** for reliability, balancing, cost control, and predictable testing.

The intended post-MVP product must support an **LLM-driven scenario-generation system**. The long-term system should be able to generate new crises, role-specific intelligence, authored response options, and consequences while remaining constrained by game rules and balance requirements.

The v0.1 architecture should therefore avoid hard-coding gameplay logic to one fixed set of scenarios. Crisis content should be data-driven so authored JSON/YAML/database content can later be replaced or supplemented by an LLM-backed generation pipeline.

---

# 6. Core Game Model

## 6.1 Player Count

- Minimum: **2 players**
- Maximum: **4 players**

A game may begin once at least 2 players are present.

## 6.2 Roles

The game always represents four domains:

1. **Infrastructure**
2. **Community**
3. **Economy**
4. **Safety**

Roles are assigned automatically.

### Role distribution

- **4 players:** one role per player
- **3 players:** two players receive one role each; one player receives two roles
- **2 players:** each player receives two roles

A player holding multiple roles sees the private intelligence for all roles assigned to that player.

Role assignment should be automatic rather than player-selected for the MVP.

---

# 7. Mission Creation and Joining

## 7.1 Create Mission

The home screen includes a prominent **Create Mission** action.

Creating a mission generates a private mission identifier/token and a public invite URL.

Example conceptual form:

`https://consensus-engine.example/mission/<token>`

Players should never need to type or remember a numeric room code.

## 7.2 Invite

The host lobby displays:

- Copy Invite Link
- QR code
- Current player list
- Ready/connected state
- Start Game button

## 7.3 Join

A joining player:

1. Opens the invite URL or scans the QR code.
2. Enters a callsign/display name.
3. Joins the lobby.
4. Waits for the host to start.

No registration, email address, password, or app installation is required.

---

# 8. Core Round Loop

Every normal crisis follows this sequence:

1. **Public Briefing**
2. **Private Intelligence**
3. **Discussion — 60 seconds**
4. **Hidden Vote**
5. **Consensus Window — only if tied**
6. **Resolution**
7. **Metric Changes**
8. **Short Result Display**
9. **Next Crisis**

---

# 9. Crisis Structure

Every crisis contains:

- Crisis ID
- Title
- Public briefing
- AI recommendation
- Exactly three authored response choices
- Role-specific private intelligence for all four roles
- Consequence text for each choice
- Metric deltas for each choice
- Optional metadata/tags used for ordering or final-crisis selection

One of the three choices must be explicitly marked as the **AI recommendation**.

The other two choices are authored human alternatives or compromises.

The AI recommendation must not be systematically correct or systematically wrong. Players should not be able to win by blindly obeying or rejecting the AI.

---

# 10. Voting

## 10.1 Hidden Vote

During the vote phase, every active player chooses one of the three authored actions.

Players may see that another player **has voted**, but they may not see which option that player selected until the vote resolves.

## 10.2 Plurality Rule

The option receiving **more votes than any other option** wins immediately.

Examples with four active players:

- 4–0–0 → leading option wins
- 3–1–0 → leading option wins
- 2–1–1 → leading option wins
- 2–2–0 → tied; Consensus Window begins

Examples with three active players:

- 3–0–0 → leading option wins
- 2–1–0 → leading option wins
- 1–1–1 → tied; Consensus Window begins

Examples with two active players:

- 2–0–0 → leading option wins
- 1–1–0 → tied; Consensus Window begins

## 10.3 Consensus Window

If the highest vote total is tied:

1. Start a **20-second Consensus Window**.
2. Notify all players that the vote is deadlocked.
3. Keep text chat available.
4. Clear the prior votes.
5. Allow every active player to vote again.

If the revote produces a unique plurality winner, that option executes.

If the top result is still tied after the revote, the **AI-recommended action executes automatically**.

This fallback is a core thematic mechanic.

---

# 11. Communication

Consensus Engine v0.1 includes a simple built-in **text chat**.

Requirements:

- Available during gameplay
- Synchronized in real time
- Clear sender callsign
- Ordered messages
- Suitable for phone and laptop layouts
- No voice or video in v0.1

Players may use external voice communication if they choose, but the game must remain playable using only the browser and built-in chat.

---

# 12. Civilization State

The shared civilization has four health metrics:

- **Infrastructure**
- **Public Trust**
- **Economy**
- **Safety**

Each metric begins at:

**70 / 100**

Each crisis resolution applies authored positive and/or negative deltas.

Metrics are clamped to an appropriate valid range, recommended:

**0–100**

## 12.1 Loss Condition

If any civilization metric reaches **0**, the team immediately loses.

## 12.2 Win Condition

If the team survives all crises without any metric reaching 0, the team wins.

## 12.3 Consensus Score

At the end of a completed run:

**Consensus Score = average of the four final civilization metrics**

The score is presented as a percentage or integer out of 100.

---

# 13. Session Length and Crisis Order

Target session length:

**10–15 minutes**

Target crisis count:

**10 crises**

The order should change between sessions.

Recommended MVP behavior:

- Draw the first 9 crises from an authored scenario pool in randomized order.
- Avoid duplicate crises within one session.
- Select the 10th/final crisis dynamically based on the civilization's weakest metric.

Example final-crisis mapping:

- Lowest Infrastructure → cascading systems failure
- Lowest Public Trust → legitimacy/civil-unrest crisis
- Lowest Economy → resource/supply collapse
- Lowest Safety → emergency-services breakdown

Ties between weakest metrics may be resolved randomly or through deterministic priority rules.

The implementation should make scenario ordering data-driven and easy to expand.

---

# 14. Disconnect and Reconnection Behavior

Real-world connectivity interruptions must not immediately destroy a match.

## 14.1 On Disconnect

When an active player disconnects:

1. Mark the player as disconnected.
2. Notify the remaining players.
3. Pause forward round progression if necessary.
4. Start a **5-minute reconnection grace period**.
5. Preserve the disconnected player's seat and assigned roles.
6. Allow the player to reconnect using their existing browser/session identity.

The interface should clearly communicate:

- Which player disconnected
- That the game is waiting
- Time remaining in the grace period
- That play will continue if the player does not return

## 14.2 Successful Reconnection

If the player returns within 5 minutes:

- Restore the same player identity
- Restore the same role assignment
- Restore current game state
- Resume play

## 14.3 Reconnection Timeout

If the player does not return within 5 minutes:

- Remove them from the active-player count
- Notify the remaining players
- Continue the match
- Reassign the departed player's role(s) among the remaining players so all four information domains remain represented

The game must continue down to the original minimum of 2 active players.

If fewer than 2 active players remain, the session may end because cooperative play is no longer viable.

---

# 15. Crisis 01 Reference Scenario

## Grid Under Pressure

### Public Briefing

**EXTREME HEAT EVENT**

Record temperatures have pushed the electrical grid to 96% capacity. Engineers predict a major cascading failure within two hours if demand is not reduced.

### AI Recommendation

**Cut residential power to District 7 for six hours.**

### Private Intelligence

**Infrastructure**  
The shutdown reduces estimated grid-failure probability from 72% to 18%. District 7 represents one of the easiest loads to isolate.

**Community**  
District 7 contains 12,400 residents, three senior-care facilities, and a large low-income housing complex.

**Economy**  
A residential shutdown costs relatively little economically. Curtailing the commercial district instead would cause roughly $2.1M in losses.

**Safety**  
One hospital serving District 7 has backup power for only about three hours. Emergency generators could be relocated, but not immediately.

### Choices

**A — Follow the AI Recommendation**  
Cut residential power in District 7 for six hours.

**B — Distribute the Burden**  
Perform rotating three-hour outages across residential, commercial, and industrial zones.

**C — Preserve Service**  
Avoid forced outages and rely on reserve generation plus voluntary conservation.

### Design Intent

No choice should be obviously correct.

Different roles possess information that materially changes how attractive each action appears.

The strongest gameplay should come from players revealing, withholding, prioritizing, and reconciling their private information.

---

# 16. Initial Crisis Themes

The authored MVP pool should cover approximately these themes:

1. Grid Under Pressure
2. Water Contamination
3. Hospital Capacity
4. Supply Chain Breakdown
5. Automated Transit Failure
6. Misinformation Surge
7. Food Shortage
8. Cyberattack
9. Climate Evacuation
10. Final system-level emergency variants

Additional authored crises may be added if time permits.

---

# 17. Visual Direction

**Near-future civic command center**

The product should feel like a serious shared operations console for managing a society, not a cyberpunk hacker interface and not an "evil AI" parody.

Visual characteristics:

- Dark command-center environment
- Restrained, readable telemetry
- Strong information hierarchy
- Clear role identity
- Subtle system-status animation
- Civic/institutional tone
- Modern typography
- Responsive layouts
- Clear distinction between public information and private role intelligence
- Accessible contrast
- Minimal visual clutter
- Deliberate tension without visual chaos

The interface should feel polished on both laptop and phone.

---

# 18. Recommended Technical Architecture

## Frontend

- React
- Vite
- TypeScript preferred
- Responsive CSS
- WebSocket client for synchronized state

## Backend

- FastAPI
- Python
- WebSocket endpoints
- Server-authoritative game state

## MVP State Storage

Use in-memory server state for active rooms/missions.

A persistent database is not required for v0.1.

The application should be structured so persistence can be introduced later without rewriting the core game model.

## Deployment Shape

Prefer one deployable web application:

- Vite builds the frontend
- FastAPI serves the built frontend/static assets
- FastAPI owns HTTP APIs and WebSockets

A different deployment split is acceptable if it materially improves reliability or hosting simplicity.

---

# 19. Multiplayer Architecture Principles

1. The server is authoritative for game state.
2. Clients submit intents/actions rather than independently mutating canonical state.
3. Every state-changing event is validated server-side.
4. Every connected client receives synchronized authoritative updates.
5. Private intelligence must only be sent to players entitled to see it.
6. Votes remain private until resolution.
7. Reconnection must restore authoritative current state.
8. Timers must be server-authoritative enough to prevent clients drifting materially out of sync.
9. A client refresh must not create a duplicate player.
10. Mission tokens must be impractical to guess.

---

# 20. Suggested Game-State Phases

Recommended finite-state machine:

- `lobby`
- `briefing`
- `discussion`
- `voting`
- `consensus_window`
- `resolution`
- `reconnect_wait`
- `completed`
- `failed`

The exact implementation may vary, but phase transitions should be explicit and centrally controlled.

---

# 21. Suggested Data Model

A crisis should be representable approximately as:

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
      "title": "Follow the AI Recommendation",
      "description": "...",
      "consequence": "...",
      "metric_deltas": {
        "infrastructure": 8,
        "public_trust": -8,
        "economy": 2,
        "safety": -6
      }
    }
  ]
}
```

Exact values and schema may change during balancing, but scenario content must remain separate from game-engine logic.

---

# 22. Privacy and Information Boundaries

The asymmetric-information mechanic is central to the game.

Therefore:

- Public briefing is visible to everyone.
- Shared civilization metrics are visible to everyone.
- A player's private role intelligence is visible only to that player.
- If a player owns two roles, they see both assigned intelligence cards.
- Other players must not receive private role text in hidden DOM/state that could trivially expose it.
- Vote selections remain private until resolution.
- Chat messages are public to all active players.

---

# 23. UX Requirements

The MVP must make the following states obvious:

- Creating a mission
- Joining a mission
- Waiting in lobby
- Role assignment
- Current crisis
- Current round number
- Current civilization metrics
- AI recommendation
- Player's private intelligence
- Discussion timer
- Chat
- Whether each player has voted
- Consensus deadlock
- Consensus Window timer
- Resolution
- Metric changes
- Disconnect state
- Reconnection countdown
- Game won
- Game lost
- Final Consensus Score
- Replay/new mission

Players should never need developer knowledge to understand what to do next.

---

# 24. Accessibility and Device Requirements

- Must work on modern desktop and mobile browsers.
- Touch targets must be usable on phones.
- Do not rely solely on color to convey game state.
- Use readable contrast.
- Timers should have text/numeric representation.
- Important state changes should use visible text, not animation alone.
- Avoid tiny telemetry text.
- Layout must remain usable at common mobile widths.

---

# 25. Error Handling

At minimum, handle:

- Invalid/expired mission invite
- Mission already completed
- Mission full
- Duplicate callsign if disallowed
- WebSocket connection failure
- Temporary WebSocket disconnect
- Player reconnection
- Host disconnect
- Attempted actions in the wrong game phase
- Duplicate votes
- Vote submission after phase close
- Client refresh
- Server-side validation failure

Errors should be understandable to nontechnical players.

---

# 26. Acceptance Criteria for v0.1

The MVP is considered complete when all of the following are true:

1. A player can create a mission from the public homepage.
2. The host can share an invite link and QR code.
3. A second player can join from another browser/device without an account.
4. The lobby supports 2–4 players.
5. Roles are assigned automatically according to player count.
6. All players enter the same synchronized match.
7. Every player sees the same public crisis briefing.
8. Each player sees only the private intelligence for their assigned role(s).
9. Text chat works in real time.
10. Discussion timing is synchronized.
11. Players can privately select one of three choices.
12. Vote status is visible without exposing vote contents before resolution.
13. A unique plurality executes immediately.
14. A tied top vote starts a 20-second Consensus Window.
15. A tied second vote executes the AI recommendation.
16. Consequences update the four shared metrics consistently for every client.
17. Any metric reaching zero causes immediate team loss.
18. Surviving all ten crises causes team victory.
19. The final Consensus Score is calculated from final metric values.
20. Crisis order varies between sessions.
21. The final crisis responds to the team's weakest metric.
22. A disconnected player is given a five-minute reconnection window.
23. Remaining players are visibly notified during the wait.
24. Reconnection restores the same player and role assignment.
25. Failure to reconnect within five minutes allows the game to continue with roles redistributed.
26. Refreshing a page does not duplicate a player.
27. The game remains usable on phone and laptop layouts.
28. A completed game can start a new mission/replay.
29. Core flows have automated tests.
30. The game can be deployed to a public URL and played by multiple real devices.

---

# 27. Build Priorities

Implement in this order unless repository findings justify a change:

1. Project scaffold
2. Shared game/domain models
3. Mission creation and invite joining
4. Lobby synchronization
5. Role assignment
6. Crisis content schema
7. Core server-authoritative state machine
8. Public/private information delivery
9. Discussion timer
10. Text chat
11. Voting and plurality resolution
12. Consensus Window
13. Consequence/metric engine
14. Win/loss logic
15. Crisis sequencing
16. Final-crisis selection
17. Reconnection/grace-period behavior
18. Responsive visual polish
19. Automated tests
20. Deployment hardening

---

# 28. Product Principle

The central design principle is:

> **The challenge is not whether players trust or distrust AI. The challenge is whether humans can combine incomplete information well enough to decide when the AI recommendation is appropriate, incomplete, or dangerous.**

Every major gameplay decision should reinforce that idea.

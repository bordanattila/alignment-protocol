# Milestone 6.1 — Post-game review UI polish

## Scope and reconnaissance

Read AGENTS.md, the Milestone 6.1 request, MissionReview.tsx, review/global responsive CSS, rendered review tests, frontend package/test conventions and the Milestone 6 verification report before editing. The working tree was clean. This change is presentation-only: no backend files, history contracts, scores, game rules, timers, chat, reconnect or WebSocket logic changed. No dependencies were added or updated.

Root causes:

1. `.metrics-trend` forced a **560px minimum width** inside a horizontally scrolling chart. Mobile users could not see all crises at once. A fixed 720-unit viewBox also made simple shrinking an unsuitable fix: text and chart height would become too small.
2. Tables had a 360px minimum width without useful per-column widths or nowrap headings. They inherited `.panel { overflow-wrap: anywhere; }`, allowing mid-word heading breaks. Values were left-aligned.
3. History deltas were inline spans with the same color as surrounding text, lacking consistent grouping or positive/negative/neutral styling.
4. Expanded prose had general wrapping but needed explicit shrinkable grid children, compact wrapped metric groups and bounded table overflow. The existing native details control and global focus styling already worked and are retained.

## Files changed

- `frontend/src/MissionReview.tsx` — responsive chart geometry/measurement, complete point titles, accessible table hints and reusable signed metric badges.
- `frontend/src/styles.css` — scoped chart/table sizing, metric badge colors, history wrapping, legend layout and return-navigation touch target.
- `frontend/tests/missionReview.test.tsx` — update the former chart-scroll contract and delta typography expectations; add responsive/full-data/sign/layout tests.
- `docs/MILESTONE_6_1_UI_POLISH.md` — this report.

Backend, types, score implementation, snapshot ordering, session and chat code remain untouched.

## Responsive chart strategy

A layout effect measures the actual chart container before paint. ResizeObserver updates width after resizing; a window-resize fallback is installed only when ResizeObserver is unavailable. Cleanup disconnects the observer/removes the fallback listener. Empty-to-populated timelines also initialize measurement correctly.

The single SVG uses that measured width as its viewBox width, retaining a 250-unit height. The SVG has width 100% and no fixed minimum width, so its chart fits the card instead of requiring horizontal scrolling or compressing typography. Font sizes remain **12px for compact charts and 16px for wider charts**. The vertical scale and every recorded value are unchanged.

Below 600px of chart width, tick-label density follows available horizontal space. Start and the final crisis are always labeled; intermediate labels are spaced, and a label too close to the final label is omitted. Only labels are reduced. All four complete polylines and all point circles/titles remain, including intermediate unlabeled crises. Wider charts retain every crisis label. Existing Infrastructure/Public Trust/Economy/Safety colors and solid/dashed patterns remain. Legend SVGs have their own viewBox so the full line sample fits the compact legend layout. Non-scaling line strokes retain visual weight.

Tests caught final-tick crowding at the modeled 375px viewport and it was corrected, rather than reducing the spacing assertion. They also found the previous multi-child SVG point-title markup rendered empty in React SSR. Point titles now use one text string and every title/value is asserted.

Explicit geometry models used by tests (not actual browser measurements):

| Viewport | Modeled inner chart width | Tick labels for Start + 10 crises | Font |
|---|---|---|---|
| 320px | 238px | Start, 4, 10 | 12px |
| 375px | 293px | Start, 3, 6, 10 | 12px |
| 390px | 308px | Start, 2, 4, 6, 8, 10 | 12px |
| 430px | 348px | Start, 2, 4, 6, 8, 10 | 12px |
| 768px | 662px | Start and every crisis | 16px |
| 1120px | 1014px | Start and every crisis | 16px |

The models deduct existing main/card padding and borders. Production uses actual `clientWidth`, not these estimates. Tests check complete ordered coordinates inside chart bounds, readable font sizes, retained endpoint labels and at least 48px between compact tick labels for these cases. They do not prove browser geometry or visual readability.

## Tables and expanded history

Both progression and per-crisis metric tables remain semantic captioned tables with scoped row/column headers. Their dedicated labeled, keyboard-focusable scroll regions retain horizontal overflow locally. Tables use a 36rem minimum width, minimum cell widths and a wider first column; headers explicitly prohibit wrapping and override inherited word-breaking. Numerical values are right-aligned with tabular numerals. No values, columns or metric names are hidden or truncated.

A restrained mobile hint says to swipe/scroll sideways for all columns. Desktop tables use the available width without forced scrolling when that width accommodates their contents. Table focus outlines have padding inside the scroll region. Chart scrolling has been removed; table scrolling remains deliberate.

Review grid items and expanded records explicitly allow shrinking within their parent. Long public context/choice text wraps, tally spans wrap as units, and summary metric badges form a wrapping flex row. The compact legend uses two columns on phones. Existing single-column final metrics/statistics below 400px and the native summary's 48px minimum touch target remain. The return link receives a 48px minimum target and its footer can wrap. All new CSS is scoped to the post-game review and its footer.

## Metric delta treatment

One `MetricDelta` component formats existing `applied_deltas` consistently in the collapsed summary and expanded before/after table:

- Positive: restrained teal, explicit `+` sign, metric name.
- Negative: restrained warm warning styling, explicit typographic `−` sign, metric name.
- Zero: neutral styling, explicit `0`, metric name.

Compact bordered badges wrap naturally; values use tabular numerals. Colors reuse the current dark theme's success/warning/neutral palette. Names and signs convey meaning without color. The typographic minus changes display only; original historical numbers, ordering and score remain untouched. Before/after values still come directly from the authoritative record, with no recomputed deltas.

## Accessibility

The exact-value progression table remains available for every series/point. Chart labels, line patterns, legend names and per-point titles supplement color. SVG margins keep chart labels/points within bounds; responsive label reduction does not remove data. Tables remain keyboard-scrollable labeled regions.

Expansion still uses native `details`/`summary`, closed by default, without removing native keyboard activation or adding custom event handlers. Global visible focus outlines remain. Non-interactive metric badges do not add tab stops. Prose/choices/tallies wrap and expanded table content stays in its own scroll region. The authoritative victory/defeat header, score, final metric values, team counts and navigation are preserved.

## Verification commands and results

All commands run from repository root. Final results:

| Command | Result |
|---|---|
| `npm --prefix frontend test` | **57 passed, 2 optional acceptance cases skipped** (59 total) |
| `MISSION_REVIEW_FILE=/tmp/ce-m6-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json npm --prefix frontend test` | **59 passed**, no skips |
| `npm --prefix frontend run typecheck` | Passed |
| `npm --prefix frontend run build` | Passed; 41 modules |
| `.venv/bin/python -m pytest backend/tests -q` | **182 passed**, one existing Starlette/httpx TestClient deprecation warning |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `git diff --check` | Passed |
| `git diff --exit-code -- backend frontend/src/types.ts frontend/src/useLobby.ts frontend/src/snapshotOrder.ts` | Passed; authoritative logic/contracts/synchronization untouched |

Existing frontend tests remain, with the former forced-chart-scroll assertion replaced by the requested fitting-chart contract and negative delta expectations updated to the typographic minus. Eleven additional tests cover sign/style semantics, identical summary/detail applied badges, all six requested width models, complete series/point/title/color/pattern preservation, table scroll/heading/numeric alignment, long expanded content and native keyboard/focus affordances. Victory, defeat, optional-data safety, reconnection equality and authoritative score tests continue to pass.

The acceptance run re-renders **existing captured** Milestone 6 live victory/defeat snapshots and Milestone 5.1 chat snapshots. It proves compatibility with those recorded payloads; no fresh multiplayer/network run is claimed for this frontend-only milestone. The captured victory score stays 55.75 and the defeat score stays 54.5, with ten/four history records respectively. Ordinary tests do not require `/tmp` fixtures; only the two optional cases are skipped without their environment variables.

## Browser/mobile evidence and remaining acceptance

No screenshots or new manual browser/mobile inspection were performed. No Linux Chromium/Chrome executable or browser automation tool was available in this session. Node tests use React server rendering, production coordinate functions and CSS contract assertions; they do not run browser layout, ResizeObserver scheduling, touch, focus or native keyboard toggling. The width models above are explicitly simulated, not physical viewport checks.

Before closing manual acceptance, inspect victory and early-defeat reviews at **320, 375, 390, 430, 768px and desktop**:

1. All chart series and recorded points fit at once; Start/final labels and reduced intermediate labels remain legible after resize/rotation.
2. Metric table headings stay intact; only the table scrolls horizontally; every number is visible on scrolling.
3. Positive/negative/zero badges retain name/sign and wrap in summaries and expanded details.
4. Long briefing/choice text, voting totals, outcome heading, score, metric/statistic grids and return navigation do not cause page-level overflow.
5. Native expansion works by keyboard and touch, focus outlines stay visible, and zoom/text scaling retains access to all content.

The history's existing memory-only lifecycle and other deferred MVP features are unchanged. No backend/gameplay changes, new libraries, commits, tags or pushes were made.

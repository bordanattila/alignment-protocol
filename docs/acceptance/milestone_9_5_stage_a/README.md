# Stage A baseline — real provider, six attempts

These files preserve the unoptimized Milestone 9.5 Stage A batch. Exactly four crisis and two endgame requests were attempted using `gpt-6-luna`, a 60-second timeout, no retries and operator-supplied USD pricing. All six were accepted. No human scores are assigned.

- [Open public review](review.html): public crisis choices/history and the two real endgames rendered by the unchanged React `MissionReview` component.
- [Fill the human review sheet](human-review.json): existing nine-criterion five-point anchors, blank scores/notes and pending continuity classifications. Human browser acceptance remains outstanding.
- [Sanitized evaluation](evaluation.json), [individual diagnostics](diagnostics.json) and [attempt journal](attempt-journal.json): actual outcomes, measured stages, reported usage and cost calculated at operator-supplied rates.
- [Public review data](public-review.json): accepted public content and executed synthetic historical decisions, separate from diagnostic records.
- [Automated projection/hash checks](automated-checks.json), [restart checks](restart-checks.json), [existing-component render checks](review.html.checks.json) and [production-source integrity](source-integrity.json).
- [Original preflight checkpoint](PREFLIGHT.md): preserved historical planning report. Its pending-authorization status predates the later explicit execution approval.
- [Baseline checksums](SHA256SUMS.json): hashes of the eleven archived baseline files; this explanatory README and the main report are outside the baseline checksum set.

The shared packet excludes prompts, raw provider responses, private role intelligence, player identities and credentials. Role-relevance review cannot be completed from this public packet alone; authorized role-specific inspection remains pending. The isolated private SQLite fixture is retained under `/tmp/ce95-stage-a-live-20261029/isolated.sqlite3`, outside this public archive and version control. It must not be served publicly.

Scores and notes should be filled by a human. Do not treat an accurate reference list as proof of meaningful continuity. Endgame tradeoff/role criteria may be marked not applicable by the reviewer with a reason, rather than assigned invented ratings.

No Stage B optimization or paid replacement batch was performed. See [the main Stage A report](../../MILESTONE_9_5_LLM_ACCEPTANCE.md).

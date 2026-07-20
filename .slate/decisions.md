---
slate_doc: decisions
slate_generated: false
slate_synced_commit: 21e62de
slate_synced_at: 2026-07-20T11:45:06+00:00
slate_synced_digest: e3b0c44298fc1c14
slate_watches:
---

# Decision log

Append-only. One entry per decision that a future reader (or AI)
would otherwise re-litigate.

```
Date: YYYY-MM-DD
Decision:
Rationale:
Trade-off:
Revisit trigger:
```

The full strategic log lives in `slate-product-doc.md` §14; entries here are
the repo-level calls an AI session needs at hand.

```
Date: 2026-07-15
Decision: Pivot — Slate is a repo-local context control plane CLI; the entire
          hosted stack (Spring API, workers, Postgres, dashboard) was deleted.
Rationale: Stale-context pain is universal and day-one; the debugger wedge
          needed production traffic before delivering value.
Trade-off: Revenue deferred to the team layer (Phase 4).
Revisit trigger: Freshness signal doesn't change user behavior after ~8 weeks.

Date: 2026-07-15
Decision: Zero runtime dependencies; freshness derived from git at read time,
          never stored; no LLM anywhere in the trust math.
Rationale: Trust signals must be reproducible, explainable, and free.
Trade-off: Hand-rolled frontmatter + glob matching (~120 lines, tested).
Revisit trigger: Real need for full YAML or gitignore-style negation.

Date: 2026-07-15
Decision: The local freshness gate is a pre-PUSH hook, not pre-commit.
Rationale: Syncing is two commits (code, then re-anchored docs); a pre-commit
          gate fails exactly when committing the code. Push time checks the
          branch tip — the same contract CI enforces.
Trade-off: Staleness caught minutes later than commit time.
Revisit trigger: Anchoring by content hash instead of commit SHA.

Date: 2026-07-15
Decision: LLM prose (`sync --prose`) is an injected callback that can only
          prepend prose above the scanned facts; failures degrade to plain sync.
Rationale: Keeps the §8 boundary mechanical — the model cannot alter facts,
          statuses, or scores by construction.
Trade-off: raw urllib, no SDK conveniences.
Revisit trigger: Prose grows beyond one paragraph per doc.
```

```
Date: 2026-07-16
Decision: Agent integration = MCP stdio server + two-layer consent: editor prompts per call, .slate/agent-access is the read-default capability ceiling
Rationale: MCP is what coding agents already speak; a server-side ceiling caps the blast radius of an over-eager always-allow and is committable team policy
Trade-off: Two config surfaces to explain (editor allowlist + access file)
Revisit trigger: MCP framing churn, or read-default friction blocking adoption
```

```
Date: 2026-07-20
Decision: Freshness hardened against the two premortem failure modes: (1) stale
          requires proof of impact — if a fresh scan regenerates the identical
          auto-block and no human section references a changed path, the doc is
          fresh (content-verified), changed paths kept as evidence; (2) every
          stamp records slate_synced_digest (sha256 of watched files' content),
          and an orphaned commit anchor falls back to it — match = fresh,
          mismatch = stale, absent = needs-verification.
Rationale: (1) Broad watch globs flagged ~half of all commits; an always-yellow
          signal gets ignored and the sync ritual becomes noise. (2) Squash-merge
          (the GitHub default) orphaned every anchor, degrading the whole layer
          to a 0.25-capped rumor in every fresh clone and CI checkout.
Trade-off: status may run a repo scan when watched paths changed (still
          sub-second); digest mismatch can't enumerate committed paths.
Revisit trigger: Any observed false fresh from content verification; digest
          hashing felt (>1s) on large repos.
```

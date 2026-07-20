# Slate benchmark — `Slate` @ `a43a2f7`

Slate vs. the manual workflow ("tell the AI to write/update .md files"),
measured on this repository's real files and real git history.
Assumptions for estimates: 4 chars/token; $3.0/M input, $15.0/M output tokens (Claude Sonnet list price).

## 1. Session start: what the agent must ingest (measured sizes)

| Approach | Tokens | Cost/session | vs Slate |
|---|---|---|---|
| **Slate** (`slate_read`: 6 docs + trust labels) | **2,066** | $0.0062 | 1× |
| Guided exploration (7 files + file tree) | 20,629 | $0.0619 | 10.0× more |
| Full repo dump (49 text files) | 54,701 | $0.1641 | 26.5× more |

Every session pays this cost. Over 100 sessions the exploration baseline
spends ~$5.57 more than Slate on input tokens alone —
before counting the model's slower time-to-first-useful-action on a
context window that large, and with zero trust labels attached.

## 2. Slate operations (measured wall-clock, this machine)

| Operation | Time |
|---|---|
| `slate status` (freshness derivation) | 268.7 ms |
| `slate verify` (trust scores) | 399.3 ms |
| full repo scan | 11.8 ms |
| MCP `slate_read` (full tool round-trip) | 668.8 ms |
| `slate sync` (regenerate all auto-blocks) | 43.0 ms |

All operations are deterministic, local, and free — 0 tokens.

## 3. Maintenance replay: 14 real commits since `0344044`

- **7 of 14 commits (50%) invalidated at least one context doc.** In the manual workflow every one of those is silent rot — no signal exists.
- The repo's actual history contains 4 `slate sync` commits: each staling change was caught and healed, gated by CI.

Cost to keep the docs true across those commits:

| Workflow | Input tokens | Output tokens | Cost |
|---|---|---|---|
| Manual: AI re-reads docs+changes, rewrites docs | 105,366 | 5,592 | $0.40 |
| **Slate: deterministic `sync`** | **0** | **0** | **$0.00** (≈43.0 ms each) |

And the manual number is the *best case* — it assumes the developer
remembers to ask after every staling commit. Skip any of them and the
cost doesn't disappear; it converts into the failure mode Slate exists
to prevent: an AI acting confidently on false context.

## Reproduce

```bash
python benchmarks/benchmark.py          # this report
python benchmarks/benchmark.py --json   # raw numbers
```

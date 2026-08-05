# Slate benchmark — `Slate` @ `d3a3b5c`

Slate vs. the manual workflow ("tell the AI to write/update .md files"),
measured on this repository's real files and real git history.
Assumptions for estimates: 4 chars/token; $3.0/M input, $15.0/M output tokens (Claude Sonnet list price).


> **Read this before quoting any number below.**
>
> **It is self-referential.** Every figure is Slate measured on Slate's own
> repository. That is a real repo with real history, so the numbers are real —
> but a project that builds a context tool is not a representative user of one.
> For agent *behaviour* claims, use `benchmarks/agentbench/` (Flask, real
> headless sessions) instead; this file measures sizes, timings and history,
> never what a model did.
>
> **The session-start advantage has fallen sharply, and that is the finding.**
> The previous run of this benchmark (at `a43a2f7`) reported 10.0x and 26.5x
> against the two baselines. It is now 2.0x and 9.6x — not because Slate got
> worse, but because *this repo's own layer bloated*: `read-next.md` is 34 KB
> and `decisions.md` is 74 KB, against ~2 KB for each generated doc. A layer
> billed as "the smallest useful context" is now 28,210 tokens.
>
> The lesson is a product one, not a measurement one: **the human-owned docs
> grow without bound unless somebody prunes them**, and nothing in Slate prunes
> them. `read-next` is meant to be rewritten when the focus changes, not
> appended to forever; `decisions` is append-only by design and will only ever
> grow. Neither is capped, and the session-start cost is paid every session.

## 1. Session start: what the agent must ingest (measured sizes)

| Approach | Tokens | Cost/session | vs Slate |
|---|---|---|---|
| **Slate** (`slate_read`: 6 docs + trust labels) | **28,210** | $0.0846 | 1× |
| Guided exploration (7 files + file tree) | 56,104 | $0.1683 | 2.0× more |
| Full repo dump (236 text files) | 271,037 | $0.8131 | 9.6× more |

Every session pays this cost. Over 100 sessions the exploration baseline
spends ~$8.37 more than Slate on input tokens alone —
before counting the model's slower time-to-first-useful-action on a
context window that large, and with zero trust labels attached.

## 2. Slate operations (measured wall-clock, this machine)

| Operation | Time |
|---|---|
| `slate status` (freshness derivation) | 671.3 ms |
| `slate verify` (trust scores) | 911.1 ms |
| full repo scan | 29.0 ms |
| MCP `slate_read` (full tool round-trip) | 1689.0 ms |
| `slate sync` (regenerate all auto-blocks) | 110.2 ms |

All operations are deterministic, local, and free — 0 tokens.

## 3. Maintenance replay: 102 real commits since `0344044`

- **70 of 102 commits (69%) invalidated at least one context doc.** In the manual workflow every one of those is silent rot — no signal exists.
- The repo's actual history contains 11 `slate sync` commits: each staling change was caught and healed, gated by CI.

Cost to keep the docs true across those commits:

| Workflow | Input tokens | Output tokens | Cost |
|---|---|---|---|
| Manual: AI re-reads docs+changes, rewrites docs | 8,541,751 | 617,243 | $34.88 |
| **Slate: deterministic `sync`** | **0** | **0** | **$0.00** (≈110.2 ms each) |

And the manual number is the *best case* — it assumes the developer
remembers to ask after every staling commit. Skip any of them and the
cost doesn't disappear; it converts into the failure mode Slate exists
to prevent: an AI acting confidently on false context.

## Reproduce

```bash
python benchmarks/benchmark.py          # this report
python benchmarks/benchmark.py --json   # raw numbers
```

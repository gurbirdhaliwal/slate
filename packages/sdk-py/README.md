# slate-sdk

Open-source step-graph capture for multi-step AI agents. When a run fails,
Slate pinpoints the origin step, classifies the failure, and reports what it
cost — see the [product doc](../../slate-product-doc.md).

Design principles (§11):

1. **Zero behavior change to your agent.** Capture buffers in-process and
   flushes async in batches — it never blocks or fails your agent's own calls.
2. **Three integration tiers:** framework auto-instrumentation (LangGraph
   first), a manual step API, and an OTel bridge.
3. **Cost capture is not optional.** Every step records token counts; the
   server computes dollar cost at ingest.

## Quickstart (manual step API)

```python
import slate

slate.init(api_key=os.environ["SLATE_API_KEY"], project_id="proj_abc123")

run = slate.start_agent_run(agent_id="support-agent", agent_version=GIT_SHA)

retrieval = run.step(type="retrieval", name="fetch_docs")
retrieval.set_input(user_question)
passages = vector_store.search(user_question)
retrieval.set_output(passages)
retrieval.end()

draft = run.step(type="llm", name="draft_answer", parents=[retrieval])
draft.set_input({"question": user_question, "passages": passages})
resp = anthropic.messages.create(model="claude-haiku-4-5", messages=[...])
draft.set_output(resp.content)
draft.end(model="claude-haiku-4-5",
          input_tokens=resp.usage.input_tokens,
          output_tokens=resp.usage.output_tokens)

if answer_rejected:
    run.fail(reason="user thumbs-down")   # <- triggers the diagnosis
else:
    run.succeed(final_output=resp.content)
```

Set `enabled=False` in local dev; captured runs are dropped without network calls.

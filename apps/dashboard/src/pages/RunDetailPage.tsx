import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { getDiagnosis } from "../lib/api";

/**
 * Run timeline + diagnosis view (§14 Phase 1): origin step highlighted,
 * failure class, evidence, wasted cost, and the fix-rate feedback button.
 * The step timeline fills in once the dashboard steps endpoint lands.
 */
export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const { data, isLoading } = useQuery({
    queryKey: ["diagnosis", runId],
    queryFn: () => getDiagnosis(runId!),
    enabled: !!runId,
    refetchInterval: (query) =>
      query.state.data && "status" in query.state.data ? 5_000 : false, // poll while analyzing
  });

  if (isLoading) return <p className="text-sm text-zinc-500">Loading diagnosis…</p>;

  if (data && "status" in data) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
        Analyzing run {data.run_id} — verdicts are fanning out, the diagnosis
        lands in under 90 seconds.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Run {runId}</h1>

      {data ? (
        <div className="rounded-xl border border-red-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-3">
            <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-700">
              {data.failure_class}
            </span>
            <span className="text-xs text-zinc-500">
              method: {data.method}
              {data.wasted_cost_usd && ` · wasted cost: $${data.wasted_cost_usd}`}
            </span>
          </div>
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="font-medium text-zinc-700">Origin step</dt>
              <dd className="text-zinc-600">{data.origin_step_id ?? "not localized"}</dd>
            </div>
            {data.evidence && (
              <div>
                <dt className="font-medium text-zinc-700">Evidence</dt>
                <dd className="whitespace-pre-wrap rounded-md bg-zinc-50 p-3 font-mono text-xs text-zinc-600">
                  {data.evidence}
                </dd>
              </div>
            )}
            {data.explanation && (
              <div>
                <dt className="font-medium text-zinc-700">Explanation</dt>
                <dd className="text-zinc-600">{data.explanation}</dd>
              </div>
            )}
          </dl>
          <div className="mt-6 border-t border-zinc-100 pt-4 text-sm">
            <p className="mb-2 text-zinc-700">Did the fix land at this step?</p>
            {/* TODO: POST feedback -> diagnoses.confirmed_by_user (fix-rate metric, §14) */}
            <div className="flex gap-2">
              <button className="rounded-md border border-zinc-300 px-3 py-1 hover:bg-zinc-50">
                Yes
              </button>
              <button className="rounded-md border border-zinc-300 px-3 py-1 hover:bg-zinc-50">
                No
              </button>
            </div>
          </div>
        </div>
      ) : (
        <p className="text-sm text-zinc-500">No diagnosis for this run.</p>
      )}

      <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-8 text-center text-sm text-zinc-500">
        Step timeline renders here — origin step highlighted, per-step verdicts
        and cost annotated.
      </div>
    </div>
  );
}

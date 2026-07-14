import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AgentRunSummary, api } from "../lib/api";

/**
 * Failed-run list — the dashboard's entry point (§14 Phase 1). The dashboard
 * runs listing endpoint lands with the JWT chain; until then this renders the
 * empty state.
 */
export function RunsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["runs"],
    queryFn: () => api<{ runs: AgentRunSummary[] }>("/v1/runs?status=failed"),
  });

  return (
    <div>
      <div className="mb-6 flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Failed runs</h1>
        <p className="text-sm text-zinc-500">Diagnoses attach per run; verdicts and cost per step</p>
      </div>

      {isLoading && <p className="text-sm text-zinc-500">Loading runs…</p>}
      {isError && (
        <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-10 text-center text-sm text-zinc-500">
          No runs yet. Instrument your agent with the Slate SDK — the first
          failed run appears here with its diagnosis.
        </div>
      )}

      {data && (
        <table className="w-full border-separate border-spacing-0 overflow-hidden rounded-lg border border-zinc-200 bg-white text-sm">
          <thead className="bg-zinc-100 text-left text-zinc-600">
            <tr>
              <th className="px-4 py-2 font-medium">Agent</th>
              <th className="px-4 py-2 font-medium">Version</th>
              <th className="px-4 py-2 font-medium">Steps</th>
              <th className="px-4 py-2 font-medium">Cost</th>
              <th className="px-4 py-2 font-medium">Started</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.map((run) => (
              <tr key={run.id} className="border-t border-zinc-100 hover:bg-zinc-50">
                <td className="px-4 py-2">
                  <Link to={`/runs/${run.id}`} className="font-medium text-blue-700 hover:underline">
                    {run.agent_id}
                  </Link>
                </td>
                <td className="px-4 py-2 text-zinc-500">{run.agent_version ?? "—"}</td>
                <td className="px-4 py-2">{run.step_count}</td>
                <td className="px-4 py-2">${run.total_cost_usd}</td>
                <td className="px-4 py-2 text-zinc-500">
                  {new Date(run.started_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

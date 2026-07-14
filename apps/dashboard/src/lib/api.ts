import { useAuthStore } from "../stores/auth";

/** Server DTOs (snake_case — the Spring API serializes with SNAKE_CASE). */
export interface AgentRunSummary {
  id: string;
  agent_id: string;
  agent_version: string | null;
  status: "running" | "succeeded" | "failed";
  step_count: number;
  total_cost_usd: string;
  started_at: string;
  ended_at: string | null;
}

export interface AgentStep {
  id: string;
  seq: number;
  parent_step_ids: string[];
  step_type: "llm" | "tool" | "retrieval" | "handoff";
  name: string;
  model: string | null;
  cost_usd: string | null;
  latency_ms: number | null;
}

export interface Diagnosis {
  run_id: string;
  origin_step_id: string | null;
  propagated_step_ids: string[];
  failure_class: string;
  evidence: string | null;
  explanation: string | null;
  method: "deterministic" | "escalated";
  wasted_cost_usd: string | null;
  confirmed_by_user: boolean | null;
  created_at: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Thin fetch wrapper; TanStack Query owns caching/retries above this. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = useAuthStore.getState().token;
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (response.status === 401) {
    useAuthStore.getState().logout();
    throw new ApiError(401, "Session expired");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return (await response.json()) as T;
}

export const getDiagnosis = (runId: string) =>
  api<Diagnosis | { run_id: string; status: "analyzing" }>(`/v1/runs/${runId}/diagnosis`);

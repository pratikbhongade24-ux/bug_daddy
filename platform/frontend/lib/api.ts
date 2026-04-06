import { AgentRuntime, DashboardSummary, Issue, IssueDetail, Scenario, TriggerEvent } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function getWsBaseUrl(): string {
  return API_BASE_URL.replace(/^http/, "ws");
}

async function fetchJson<T>(path: string, init?: RequestInit, fallback?: T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      cache: "no-store",
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (fallback !== undefined) {
      return fallback;
    }
    throw error;
  }
}

export function emptyDashboardSummary(): DashboardSummary {
  return {
    metrics: {
      resolved_issues: 0,
      running_issues: 0,
      open_issues: 0,
      total_triggers: 0,
      mean_time_to_resolve_seconds: null,
      auto_pull_requests: 0,
      jira_actions: 0,
      estimated_engineer_hours_saved: 0,
    },
    recent_issues: [],
    trigger_breakdown: [],
    service_hotspots: [],
    live_runs: [],
    recent_events: [],
    guardrails: [],
    second_pair_of_eyes: [],
    agent_runtimes: [],
    connectors: [],
  };
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  return fetchJson<DashboardSummary>("/api/dashboard/summary", undefined, emptyDashboardSummary());
}

export async function getScenarios(): Promise<Scenario[]> {
  return fetchJson<Scenario[]>("/api/triggers/scenarios", undefined, []);
}

export async function getIssues(): Promise<Issue[]> {
  return fetchJson<Issue[]>("/api/issues", undefined, []);
}

export async function getIssueDetail(issueId: string): Promise<IssueDetail | null> {
  return fetchJson<IssueDetail | null>(`/api/issues/${issueId}`, undefined, null);
}

export async function getAgents(): Promise<AgentRuntime[]> {
  return fetchJson<AgentRuntime[]>("/api/agents", undefined, []);
}

export async function getTriggers(): Promise<TriggerEvent[]> {
  return fetchJson<TriggerEvent[]>("/api/triggers", undefined, []);
}

export async function launchScenario(scenarioId: string): Promise<{ issue_id: number; run_id: number }> {
  return fetchJson<{ issue_id: number; run_id: number }>(
    "/api/triggers/simulate",
    {
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId }),
    },
  );
}

export async function retryIssue(issueId: number): Promise<{ issue_id: number; run_id: number }> {
  return fetchJson<{ issue_id: number; run_id: number }>(
    `/api/issues/${issueId}/retry`,
    {
      method: "POST",
      body: JSON.stringify({ preserve_history: true }),
    },
  );
}

export async function replayIssue(issueId: number): Promise<{ issue_id: number; run_id: number }> {
  return fetchJson<{ issue_id: number; run_id: number }>(
    `/api/issues/${issueId}/replay`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

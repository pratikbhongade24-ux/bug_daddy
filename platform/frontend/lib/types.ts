export type IssueStatus = "queued" | "running" | "resolved" | "failed" | "needs_review" | "open";

export interface Artifact {
  id: number;
  artifact_type: string;
  title: string;
  external_ref: string | null;
  url: string | null;
  payload_json: Record<string, unknown>;
  created_at: string;
}

export interface RunEvent {
  id: number;
  sequence: number;
  event_type: string;
  node_name: string;
  title: string;
  detail: string;
  status: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface Run {
  id: number;
  run_key: string;
  status: string;
  current_agent: string | null;
  started_at: string;
  updated_at: string;
  ended_at: string | null;
  outcome: string | null;
  duration_seconds: number | null;
  events: RunEvent[];
}

export interface Issue {
  id: number;
  external_id: string;
  title: string;
  description: string;
  issue_type: string;
  source: string;
  trigger_name: string;
  service_name: string;
  severity: string;
  status: IssueStatus;
  owner: string | null;
  summary: string | null;
  resolution_summary: string | null;
  blast_radius: string | null;
  guardrail_state: string;
  confidence_score: number;
  recurrence_count: number;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  latest_run?: Run | null;
  latest_artifacts?: Artifact[];
}

export interface TriggerEvent {
  id: number;
  source: string;
  trigger_name: string;
  service_name: string;
  payload_json: Record<string, unknown>;
  status: string;
  created_at: string;
}

export interface AgentRuntime {
  id: number;
  name: string;
  runtime_arn: string | null;
  runtime_id: string | null;
  status: string;
  average_latency_ms: number | null;
  success_rate: number | null;
  version: string;
  last_invoked_at: string | null;
}

export interface ConnectorHealth {
  id: number;
  name: string;
  status: string;
  detail: string;
  checked_at: string;
}

export interface LiveRunSummary {
  run_id: number;
  run_key: string;
  issue_id: number;
  status: string;
  current_agent: string | null;
  started_at: string;
  updated_at: string;
}

export interface SummaryEvent {
  run_id: number;
  issue_id: number;
  node_name: string;
  title: string;
  detail: string;
  status: string;
  created_at: string;
}

export interface GuardrailInsight {
  issue_id: number;
  external_id: string;
  state: string;
  message: string;
}

export interface SecondPairInsight {
  issue_id: number;
  message: string;
  node_name: string;
}

export interface Scenario {
  id: string;
  title: string;
  summary: string;
  issue_type: string;
  source: string;
  trigger_name: string;
  service_name: string;
  severity: string;
  blast_radius: string;
  recurrence_count: number;
}

export interface IssueDetail extends Issue {
  logs: string[];
  telemetry: Record<string, unknown>;
  kb_context: string | null;
  source_payload: Record<string, unknown>;
  triggers: TriggerEvent[];
  runs: Run[];
  artifacts: Artifact[];
}

export interface DashboardSummary {
  metrics: Record<string, number | string | null>;
  recent_issues: Issue[];
  trigger_breakdown: Array<{ source: string; count: number }>;
  service_hotspots: Array<{ service_name: string; count: number }>;
  live_runs: LiveRunSummary[];
  recent_events: SummaryEvent[];
  guardrails: GuardrailInsight[];
  second_pair_of_eyes: SecondPairInsight[];
  agent_runtimes: AgentRuntime[];
  connectors: ConnectorHealth[];
}

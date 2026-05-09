export type RoleName = 'admin' | 'user' | string;
export type UserStatus = 'active' | 'inactive' | 'locked' | string;

export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string | null;
  role: RoleName;
  status: UserStatus;
  is_email_verified: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface DashboardSummary {
  total: number;
  backlog: number;
  wip: number;
  review: number;
  resolved: number;
  no_action: number;
  critical: number;
}

export interface ServiceChartRow {
  service_name: string;
  total: number;
  backlog: number;
  wip: number;
  resolved: number;
}

export interface SourceChartRow {
  source: string;
  total: number;
}

export interface IssueTypeChartRow {
  issue_type: string;
  total: number;
}

export interface DashboardCharts {
  services: ServiceChartRow[];
  sources: SourceChartRow[];
  issue_types: IssueTypeChartRow[];
}

export interface FeedItem {
  id: number;
  jiraId: string;
  event_type: string;
  title: string;
  meta: string;
  time: string | null;
}

export interface Issue {
  id: number;
  jiraId: string;
  fingerprint: string;
  service: string;
  shortSvc: string;
  type: string;
  source: string;
  description: string | null;
  err: string;
  stack_trace: string | null;
  frequency: number;
  freq: number;
  criticality: 'Critical' | 'High' | 'Medium' | 'Low' | string;
  agent_target: string;
  workflow_key: string;
  status: string;
  tab: 'backlog' | 'wip' | 'review' | 'resolved' | string;
  owner: string;
  resolution_pr: string | null;
  resolution_jira: string | null;
  request_id: string | null;
  entire_execution_logs: string | null;
  first_seen: string | null;
  last_seen: string | null;
  created_at: string | null;
  resolved_at: string | null;
  latest_execution_session_id: string | null;
  execution_session_id: string | null;
  eta?: string;
  origin?: string;
}

export interface ListResponse<T> {
  items: T[];
}

export interface WorkflowNode {
  id: string;
  label: string;
  type?: string;
  x: number;
  y: number;
  color?: string;
  icon?: string;
  sub?: string;
}

export interface WorkflowEdgeObject {
  from: string;
  to: string;
}

export type WorkflowEdge = WorkflowEdgeObject | [string, string];

export interface WorkflowGraph {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  graph_json?: WorkflowGraph;
  workflow_key?: string;
}

export interface ExecutionEvent {
  id: number;
  event_type: string;
  node_id: string | null;
  node_name: string | null;
  agent_name: string | null;
  status: string | null;
  level: string | null;
  title: string | null;
  description: string | null;
  reasoning_summary: string | null;
  input_summary: string | null;
  output_summary: string | null;
  error_message: string | null;
  tool_name: string | null;
  created_at: string | null;
}

export interface ExecutionSession {
  session_id: string;
  issue_id: number | null;
  workflow_key: string;
  workflow_version: string;
  agent_target: string;
  status: string;
  created_at?: string;
}

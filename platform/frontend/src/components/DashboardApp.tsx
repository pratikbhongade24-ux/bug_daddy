'use client';

import clsx from 'clsx';
import {
  Activity,
  Bot,
  Brain,
  Bug,
  CircleHelp,
  ClipboardList,
  ClipboardPenLine,
  Cloud,
  Code2,
  Database,
  Download,
  ExternalLink,
  FileJson,
  FlaskConical,
  Gauge,
  GitBranch,
  GitPullRequest,
  HardHat,
  LayoutDashboard,
  ListFilter,
  LogOut,
  MessageCircle,
  Play,
  RefreshCcw,
  Search,
  Shield,
  ShieldCheck,
  Siren,
  Target,
  Users,
  X,
  Zap,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FormEvent, MouseEvent, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, apiJson, errorMessage, logoutRequest } from '@/lib/api';
import { TAB_KEY, VIEW_KEY, clearSession, getStoredUser } from '@/lib/storage';
import type {
  DashboardCharts,
  DashboardSummary,
  ExecutionEvent,
  FeedItem,
  Issue,
  ListResponse,
  SonarInvokeResponse,
  SonarReportUrl,
  SonarStatus,
  User,
  WorkflowEdge,
  WorkflowGraph,
  WorkflowNode,
} from '@/lib/types';

type ViewName = 'dashboard' | 'issues' | 'sonar' | 'admin';
type IssueTab = 'backlog' | 'wip' | 'review' | 'resolved';
type ToastKind = 'ok' | 'err' | 'inf';

interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
}

const emptySummary: DashboardSummary = { total: 0, backlog: 0, wip: 0, review: 0, resolved: 0, no_action: 0, critical: 0 };
const emptyCharts: DashboardCharts = { services: [], sources: [], issue_types: [] };
const emptyIssues: Issue[] = [];
const chartColors = ['#00d4aa', '#ff4060', '#3b9eff', '#ffaa00', '#b667ff', '#ff6b35'];

const archNodes: WorkflowNode[] = [
  { id: 'cw', x: 100, y: 20, icon: 'CW', label: 'CloudWatch', sub: 'Microservices', color: '#ff6b35', type: 'trigger' },
  { id: 'sq', x: 250, y: 20, icon: 'SQ', label: 'SonarQube', sub: 'Code Quality', color: '#3b9eff', type: 'trigger' },
  { id: 'cve', x: 400, y: 20, icon: 'CV', label: 'CVE Monitor', sub: 'Security', color: '#ff6b35', type: 'trigger' },
  { id: 'jira', x: 550, y: 20, icon: 'JR', label: 'JIRA Backlogs', sub: 'Tech Debt', color: '#b667ff', type: 'trigger' },
  { id: 'slk', x: 700, y: 20, icon: 'SL', label: 'Slack Incident', sub: 'Communication', color: '#3b9eff', type: 'trigger' },
  { id: 'db', x: 380, y: 120, icon: 'DB', label: 'Issues Tracker', sub: 'PostgreSQL', color: '#00d4aa', type: 'agent' },
  { id: 'esc', x: 380, y: 220, icon: 'ES', label: 'Escalation Agent', sub: 'triage + route', color: '#3b9eff', type: 'agent' },
  { id: 'jag', x: 580, y: 220, icon: 'JA', label: 'Jira Agent', sub: 'Jira Update', color: '#b667ff', type: 'agent' },
  { id: 'inc', x: 110, y: 385, icon: 'ID', label: 'Incident Daddy', sub: 'Orchestrator', color: '#ff4060', type: 'daddy' },
  { id: 'sme', x: 310, y: 390, icon: 'SM', label: 'SME', sub: 'Knowledge Base', color: '#ffaa00', type: 'agent' },
  { id: 'bug', x: 700, y: 310, icon: 'BD', label: 'Bug Daddy', sub: 'Orchestrator', color: '#00d4aa', type: 'daddy' },
  { id: 'ctx', x: 760, y: 455, icon: 'CX', label: 'Context Analyser', sub: 'Analysis', color: '#ffaa00', type: 'agent' },
  { id: 'crit_ctx', x: 760, y: 595, icon: 'CC', label: 'Context Critique', sub: 'Review Analysis', color: '#ff6b35', type: 'agent' },
  { id: 'strat', x: 560, y: 455, icon: 'PL', label: 'Planner', sub: 'Plan', color: '#3b9eff', type: 'agent' },
  { id: 'crit_strat', x: 560, y: 595, icon: 'PC', label: 'Planner Critique', sub: 'Review Plan', color: '#ff6b35', type: 'agent' },
  { id: 'code', x: 960, y: 455, icon: 'CD', label: 'Coder', sub: 'Write Fix', color: '#00d4aa', type: 'agent' },
  { id: 'crit_code', x: 910, y: 595, icon: 'RC', label: 'Coder Critique', sub: 'Review Code', color: '#ff6b35', type: 'agent' },
  { id: 'jprf', x: 1060, y: 595, icon: 'GH', label: 'GitHub', sub: 'Pull Request', color: '#3b9eff', type: 'agent' },
  { id: 'rev', x: 1240, y: 310, icon: 'RD', label: 'Reviewer Daddy', sub: 'AI Reviewer', color: '#b667ff', type: 'daddy' },
];

const archEdges: WorkflowEdge[] = [
  ['cw', 'db'],
  ['sq', 'db'],
  ['cve', 'db'],
  ['jira', 'db'],
  ['slk', 'db'],
  ['db', 'esc'],
  ['esc', 'jag'],
  ['esc', 'inc'],
  ['esc', 'bug'],
  ['bug', 'sme'],
  ['bug', 'strat'],
  ['strat', 'crit_strat'],
  ['crit_strat', 'strat'],
  ['bug', 'ctx'],
  ['ctx', 'crit_ctx'],
  ['crit_ctx', 'ctx'],
  ['bug', 'code'],
  ['code', 'crit_code'],
  ['crit_code', 'code'],
  ['code', 'jprf'],
  ['bug', 'rev'],
];

const nodeStyleById = Object.fromEntries(archNodes.map((node) => [node.id, { ...node }]));
const nodeAliases: Record<string, string> = {
  crit1: 'crit_strat',
  crit2: 'crit_code',
  airev: 'rev',
  jrf: 'jag',
};

function withEta(items: Issue[]) {
  return items.map((issue, index) => ({ ...issue, eta: eta(index + 1), origin: issue.source }));
}

function eta(pos: number) {
  const minutes = pos * 15;
  return minutes < 60 ? `~${minutes}m` : `~${(minutes / 60).toFixed(1)}h`;
}

function hasPermission(user: User | null, permission: string) {
  if (!user) return false;
  try {
    const token = localStorage.getItem('bugDaddyAccessToken');
    if (!token) return false;
    const encoded = token.split('.')[1];
    const padded = encoded + '='.repeat((4 - (encoded.length % 4)) % 4);
    const payload = JSON.parse(atob(padded.replace(/-/g, '+').replace(/_/g, '/')));
    return Array.isArray(payload.permissions) && payload.permissions.includes(permission);
  } catch {
    return false;
  }
}

function issueStatusLabel(tab: IssueTab) {
  return { backlog: 'Backlog', wip: 'WIP', review: 'Code Review', resolved: 'Resolved' }[tab];
}

function normalizeEdge(edge: WorkflowEdge): [string, string] {
  return Array.isArray(edge) ? [edge[0], edge[1]] : [edge.from, edge.to];
}

function canonicalNodeId(id: string | undefined) {
  if (!id) return '';
  return nodeAliases[id] || id;
}

function uniqueEdges(edges: [string, string][]) {
  const seen = new Set<string>();
  return edges.filter(([from, to]) => {
    const key = `${from}-${to}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function normalizeNodeType(type: string | undefined) {
  if (type === 'agent' || type === 'daddy' || type === 'trigger' || type === 'tool' || type === 'store' || type === 'output') return type;
  return 'agent';
}

function nodeColor(node: WorkflowNode) {
  if (node.color) return node.color;
  const id = node.id.toLowerCase();
  if (id.includes('inc')) return '#ff4060';
  if (id.includes('bug') || id.includes('code')) return '#00d4aa';
  if (id.includes('sme') || id.includes('ctx')) return '#ffaa00';
  if (id.includes('rev') || id.includes('jira')) return '#b667ff';
  if (id.includes('cve') || id.includes('crit')) return '#ff6b35';
  return '#3b9eff';
}

function nodeIcon(node: WorkflowNode) {
  if (node.icon) return node.icon;
  const label = `${node.id} ${node.label}`.toLowerCase();
  if (label.includes('cloud')) return 'CL';
  if (label.includes('sonar')) return 'SQ';
  if (label.includes('cve')) return 'CV';
  if (label.includes('jira')) return 'JR';
  if (label.includes('slack')) return 'SL';
  if (label.includes('incident')) return 'IN';
  if (label.includes('bug')) return 'BD';
  if (label.includes('sme')) return 'SM';
  if (label.includes('code')) return 'CD';
  if (label.includes('review')) return 'RV';
  return 'AG';
}

function renderNodeIcon(node: WorkflowNode) {
  const iconProps = { size: node.type === 'daddy' ? 22 : 17, strokeWidth: 2.2 };
  switch (canonicalNodeId(node.id)) {
    case 'cw':
      return <Cloud {...iconProps} />;
    case 'sq':
      return <FlaskConical {...iconProps} />;
    case 'cve':
      return <ShieldCheck {...iconProps} />;
    case 'jira':
      return <ClipboardList {...iconProps} />;
    case 'slk':
      return <MessageNodeIcon />;
    case 'db':
      return <Database {...iconProps} />;
    case 'esc':
      return <Zap {...iconProps} />;
    case 'jag':
      return <ClipboardPenLine {...iconProps} />;
    case 'inc':
      return <Siren {...iconProps} />;
    case 'sme':
      return <Brain {...iconProps} />;
    case 'bug':
      return <Bug {...iconProps} />;
    case 'ctx':
      return <Search {...iconProps} />;
    case 'crit_ctx':
    case 'crit_strat':
    case 'crit_code':
      return <Target {...iconProps} />;
    case 'strat':
      return <Bot {...iconProps} />;
    case 'code':
      return <Code2 {...iconProps} />;
    case 'jprf':
      return <GitPullRequest {...iconProps} />;
    case 'rev':
      return <HardHat {...iconProps} />;
    default:
      return node.icon ? <span className="nd-icon-text">{node.icon}</span> : <CircleHelp {...iconProps} />;
  }
}

function MessageNodeIcon() {
  return <MessageCircle size={17} strokeWidth={2.2} />;
}

function normalizeNodeModel(node: WorkflowNode): WorkflowNode {
  const id = canonicalNodeId(node.id);
  const style = nodeStyleById[id];
  return {
    ...node,
    ...style,
    id,
    type: normalizeNodeType(style?.type || node.type),
    icon: style?.icon || node.icon || nodeIcon({ ...node, id }),
    color: style?.color || node.color || nodeColor({ ...node, id }),
    sub: style?.sub || node.sub,
    x: Number.isFinite(Number(style?.x)) ? Number(style?.x) : Number(node.x || 0),
    y: Number.isFinite(Number(style?.y)) ? Number(style?.y) : Number(node.y || 0),
  };
}

function normalizeWorkflowGraph(graph: WorkflowGraph | undefined): WorkflowGraph {
  const rawNodes = Array.isArray(graph?.nodes) ? graph.nodes : archNodes;
  const rawEdges = Array.isArray(graph?.edges) ? graph.edges : archEdges;
  const architectureGraph = rawNodes.some((node) => ['esc', 'db', 'bug', 'inc', 'rev'].includes(canonicalNodeId(node.id)));

  if (architectureGraph) {
    const rawById = new Map(rawNodes.map((node) => [canonicalNodeId(node.id), node]));
    const nodes = archNodes.map((style) => normalizeNodeModel({ ...rawById.get(style.id), ...style }));
    const nodeIds = new Set(nodes.map((node) => node.id));
    const edges = archEdges.map(normalizeEdge).filter(([from, to]) => nodeIds.has(from) && nodeIds.has(to));
    return { nodes, edges: uniqueEdges(edges) };
  }

  const nodes = rawNodes.map(normalizeNodeModel);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = rawEdges
    .map(normalizeEdge)
    .map(([from, to]) => [canonicalNodeId(from), canonicalNodeId(to)] as [string, string])
    .filter(([from, to]) => nodeIds.has(from) && nodeIds.has(to));
  return { nodes, edges: uniqueEdges(edges) };
}

function getNodeSize(node: WorkflowNode) {
  if (node.type === 'agent' || node.type === 'tool' || node.type === 'store') return { w: 140, h: 44 };
  if (node.type === 'daddy') return { w: 58, h: 58 };
  return { w: 52, h: 52 };
}

function getNodeCenter(node: WorkflowNode) {
  const size = getNodeSize(node);
  return { x: node.x + size.w / 2, y: node.y + size.h / 2 };
}

function edgePath(from: WorkflowNode, to: WorkflowNode, allEdges: [string, string][]) {
  const fromCenter = getNodeCenter(from);
  const toCenter = getNodeCenter(to);
  const fromSize = getNodeSize(from);
  const toSize = getNodeSize(to);
  const dx = toCenter.x - fromCenter.x;
  const dy = toCenter.y - fromCenter.y;
  let x1: number;
  let y1: number;
  let x2: number;
  let y2: number;

  if (Math.abs(dy) > Math.abs(dx) * 0.6) {
    x1 = fromCenter.x;
    y1 = fromCenter.y + (dy > 0 ? fromSize.h / 2 : -fromSize.h / 2);
    x2 = toCenter.x;
    y2 = toCenter.y + (dy > 0 ? -toSize.h / 2 : toSize.h / 2);
  } else {
    x1 = fromCenter.x + (dx > 0 ? fromSize.w / 2 : -fromSize.w / 2);
    y1 = fromCenter.y;
    x2 = toCenter.x + (dx > 0 ? -toSize.w / 2 : toSize.w / 2);
    y2 = toCenter.y;
  }

  let cpx1 = x1;
  let cpx2 = x2;
  let cpy1 = y1 + (y2 - y1) * 0.4;
  let cpy2 = y1 + (y2 - y1) * 0.6;
  const hasReturnEdge = allEdges.some(([candidateFrom, candidateTo]) => candidateFrom === to.id && candidateTo === from.id);
  if (hasReturnEdge) {
    const offset = from.id < to.id ? -18 : 18;
    if (Math.abs(dy) > Math.abs(dx) * 0.6) {
      cpx1 += offset;
      cpx2 += offset;
    } else {
      cpy1 += offset;
      cpy2 += offset;
    }
  }
  return `M${x1},${y1} C${cpx1},${cpy1} ${cpx2},${cpy2} ${x2},${y2}`;
}

function activePathForWorkflow(workflowKey: string) {
  return workflowKey === 'incident_daddy'
    ? ['db', 'esc', 'jag', 'inc']
    : ['db', 'esc', 'jag', 'bug', 'sme', 'strat', 'crit_strat', 'ctx', 'crit_ctx', 'code', 'crit_code', 'jprf', 'rev'];
}

function initialGraphNodeStates(workflowKey: string, isSummary: boolean) {
  const triggerStates = Object.fromEntries(['cw', 'sq', 'cve', 'jira', 'slk'].map((id) => [id, 'done']));
  if (!isSummary) return triggerStates;
  return { ...triggerStates, ...Object.fromEntries(activePathForWorkflow(workflowKey).map((id) => [id, 'done'])) };
}

export function DashboardApp() {
  const queryClient = useQueryClient();
  const [authUser, setAuthUser] = useState<User | null>(() => getStoredUser());
  const [view, setViewState] = useState<ViewName>('dashboard');
  const [tab, setTabState] = useState<IssueTab>('backlog');
  const [roleView, setRoleView] = useState('Developer');
  const [search, setSearch] = useState('');
  const [serviceFilter, setServiceFilter] = useState('');
  const [criticalityFilter, setCriticalityFilter] = useState('');
  const [originFilter, setOriginFilter] = useState('');
  const [sortKey, setSortKey] = useState<'id' | 'freq'>('id');
  const [sortDir, setSortDir] = useState(-1);
  const [prioritizeLoading, setPrioritizeLoading] = useState<Record<number, string>>({});
  const [modalIssue, setModalIssue] = useState<{ issue: Issue; summary: boolean; sessionId?: string } | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  function toast(message: string, kind: ToastKind = 'inf') {
    const id = Date.now() + Math.random();
    setToasts((items) => [...items, { id, message, kind }]);
    setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 3400);
  }

  function setView(nextView: ViewName) {
    if (nextView === 'admin' && !hasPermission(authUser, 'users.read')) {
      toast('Admin access required', 'err');
      return;
    }
    localStorage.setItem(VIEW_KEY, nextView);
    setViewState(nextView);
  }

  function setTab(nextTab: IssueTab) {
    localStorage.setItem(TAB_KEY, nextTab);
    setTabState(nextTab);
  }

  const meQuery = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: () => apiJson<User>('/auth/me'),
    retry: false,
  });

  useEffect(() => {
    if (meQuery.isError) {
      clearSession();
      window.location.href = '/login';
      return;
    }
    if (meQuery.data) {
      setAuthUser(meQuery.data);
      localStorage.setItem('bugDaddyUser', JSON.stringify(meQuery.data));
      const savedView = localStorage.getItem(VIEW_KEY) as ViewName | null;
      const savedTab = localStorage.getItem(TAB_KEY) as IssueTab | null;
      if (savedView) setViewState(savedView);
      if (savedTab) setTabState(savedTab);
    }
  }, [meQuery.data, meQuery.isError]);

  const summaryQuery = useQuery({ queryKey: ['dashboard', 'summary'], queryFn: () => apiJson<DashboardSummary>('/dashboard/summary'), refetchInterval: 30_000 });
  const chartsQuery = useQuery({ queryKey: ['dashboard', 'charts'], queryFn: () => apiJson<DashboardCharts>('/dashboard/charts'), refetchInterval: 30_000 });
  const feedQuery = useQuery({ queryKey: ['dashboard', 'feed'], queryFn: () => apiJson<ListResponse<FeedItem>>('/dashboard/feed?limit=12'), refetchInterval: 30_000 });
  const sonarQuery = useQuery({ queryKey: ['sonar', 'status'], queryFn: () => apiJson<SonarStatus>('/sonar/status?limit=12'), refetchInterval: 30_000 });
  const issuesQuery = useQuery({
    queryKey: ['issues'],
    queryFn: async () => withEta((await apiJson<ListResponse<Issue>>('/issues?limit=200')).items || []),
    refetchInterval: 30_000,
  });
  const usersQuery = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => apiJson<ListResponse<User>>('/admin/users'),
    enabled: view === 'admin' && hasPermission(authUser, 'users.read'),
  });

  const summary = summaryQuery.data || emptySummary;
  const charts = chartsQuery.data || emptyCharts;
  const issues = issuesQuery.data || emptyIssues;
  const feed = feedQuery.data?.items || [];
  const isAdmin = authUser?.role === 'admin' && hasPermission(authUser, 'users.read');

  const stats = useMemo(
    () => ({
      total: summary.total || issues.length,
      backlog: summary.backlog || issues.filter((item) => item.tab === 'backlog').length,
      wip: summary.wip || issues.filter((item) => item.tab === 'wip').length,
      review: summary.review || issues.filter((item) => item.tab === 'review').length,
      resolved: summary.resolved || issues.filter((item) => item.tab === 'resolved').length,
      critical: summary.critical || issues.filter((item) => item.criticality === 'Critical').length,
    }),
    [issues, summary],
  );

  const services = useMemo(() => [...new Set(issues.map((issue) => issue.service))].sort(), [issues]);
  const filteredIssues = useMemo(() => {
    const q = search.toLowerCase();
    return issues
      .filter((issue) => issue.tab === tab)
      .filter((issue) => !q || issue.jiraId.toLowerCase().includes(q) || issue.err.toLowerCase().includes(q) || issue.shortSvc.toLowerCase().includes(q))
      .filter((issue) => !serviceFilter || issue.service === serviceFilter)
      .filter((issue) => !criticalityFilter || issue.criticality === criticalityFilter)
      .filter((issue) => !originFilter || issue.origin === originFilter)
      .sort((a, b) => ((a[sortKey] as number) > (b[sortKey] as number) ? sortDir : -sortDir));
  }, [criticalityFilter, issues, originFilter, search, serviceFilter, sortDir, sortKey, tab]);

  async function refreshDashboard() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      queryClient.invalidateQueries({ queryKey: ['issues'] }),
      queryClient.invalidateQueries({ queryKey: ['admin'] }),
    ]);
  }

  const updateIssueMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => apiJson<Issue>(`/issues/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
    onSuccess: async (_data, variables) => {
      toast(`Issue marked as ${variables.status.replace('_', ' ')}`, 'ok');
      await refreshDashboard();
    },
    onError: (error) => toast(errorMessage(error, 'Issue update failed'), 'err'),
  });
  const invokeSonarMutation = useMutation({
    mutationFn: () => apiJson<SonarInvokeResponse>('/sonar/invoke', { method: 'POST', body: JSON.stringify({ reason: 'manual-ui-trigger' }) }),
    onSuccess: async (data) => {
      toast(data.message, 'ok');
      await queryClient.invalidateQueries({ queryKey: ['sonar'] });
    },
    onError: (error) => toast(errorMessage(error, 'Could not invoke SonarQube'), 'err'),
  });

  async function openSonarReport(reportDate: string) {
    try {
      const data = await apiJson<SonarReportUrl>(`/sonar/reports/${reportDate}/url`);
      window.open(data.url, '_blank', 'noopener,noreferrer');
      toast(`Presigned URL ready for ${reportDate}`, 'ok');
    } catch (error) {
      toast(errorMessage(error, 'Could not open Sonar report'), 'err');
    }
  }

  async function prioritize(issue: Issue) {
    setPrioritizeLoading((state) => ({ ...state, [issue.id]: 'invoke' }));
    try {
      const prioritized = await apiJson<Issue>(`/issues/${issue.id}/prioritize`, { method: 'POST' });
      setPrioritizeLoading((state) => ({ ...state, [issue.id]: 'refresh' }));
      const invoke = await apiFetch('/agent/invoke', {
        method: 'POST',
        body: JSON.stringify({
          issue_id: issue.id,
          target: prioritized.agent_target || issue.agent_target,
          service_name: issue.service,
          incident_summary: issue.description || issue.err,
          source: 'platform',
          metadata: { jira_id: issue.jiraId, workflow_key: prioritized.workflow_key || issue.workflow_key },
        }),
      });
      const data = await invoke.json().catch(() => ({}));
      if (!invoke.ok) {
        toast(data.detail || 'Agent invoke failed', 'err');
        return;
      }
      toast(`Routed to ${data.target || prioritized.agent_target || issue.agent_target}`, 'ok');
      await refreshDashboard();
      setModalIssue({ issue: prioritized, summary: false, sessionId: data.session_id });
    } catch (error) {
      toast(errorMessage(error, 'Prioritize failed'), 'err');
    } finally {
      setPrioritizeLoading((state) => {
        const next = { ...state };
        delete next[issue.id];
        return next;
      });
    }
  }

  async function escalateAll() {
    const criticals = issues.filter((issue) => issue.criticality === 'Critical' && issue.tab !== 'resolved');
    let updated = 0;
    for (const issue of criticals) {
      const response = await apiFetch(`/issues/${issue.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'in_progress' }) });
      if (response.ok) updated += 1;
    }
    await refreshDashboard();
    toast(`${updated} critical issues escalated -> Incident Daddy`, updated ? 'err' : 'inf');
  }

  function exportCSV() {
    const rows = [['JIRA ID', 'Service', 'Error', 'Freq', 'Criticality', 'Owner', 'Tab', 'ETA']];
    issues.forEach((issue) => rows.push([issue.jiraId, issue.shortSvc, `"${issue.err.replace(/"/g, '""')}"`, String(issue.freq), issue.criticality, issue.owner, issue.tab, issue.eta || '']));
    const blob = new Blob([rows.map((row) => row.join(',')).join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'grabhack_issues.csv';
    anchor.click();
    URL.revokeObjectURL(url);
    toast('CSV exported', 'ok');
  }

  if (meQuery.isLoading && !authUser) return <main className="boot-screen">Loading Bug Daddy...</main>;

  return (
    <main className="bd-shell">
      <Topbar stats={stats} roleView={roleView} setRoleView={setRoleView} authUser={authUser} onLogout={logoutRequest} />
      <div className="app">
        <Sidebar view={view} setView={setView} isAdmin={isAdmin} stats={stats} />
        <section className="main">
          {view === 'dashboard' ? (
            <DashboardOverview
              stats={stats}
              charts={charts}
              issues={issues}
              feed={feed}
              onExport={exportCSV}
              onEscalate={escalateAll}
              setView={setView}
              setServiceFilter={setServiceFilter}
              openGraph={(issue, summaryView) => setModalIssue({ issue, summary: summaryView })}
              toast={toast}
            />
          ) : null}
          {view === 'issues' ? (
            <IssuesView
              stats={stats}
              tab={tab}
              setTab={setTab}
              search={search}
              setSearch={setSearch}
              serviceFilter={serviceFilter}
              setServiceFilter={setServiceFilter}
              criticalityFilter={criticalityFilter}
              setCriticalityFilter={setCriticalityFilter}
              originFilter={originFilter}
              setOriginFilter={setOriginFilter}
              services={services}
              issues={filteredIssues}
              loading={issuesQuery.isLoading}
              sortBy={(key) => {
                setSortKey(key);
                setSortDir((dir) => dir * -1);
              }}
              prioritizeLoading={prioritizeLoading}
              prioritize={prioritize}
              openGraph={(issue, summaryView) => setModalIssue({ issue, summary: summaryView })}
              onExport={exportCSV}
            />
          ) : null}
          {view === 'sonar' ? (
            <SonarView
              status={sonarQuery.data}
              loading={sonarQuery.isLoading}
              refreshing={sonarQuery.isFetching}
              invoking={invokeSonarMutation.isPending}
              onInvoke={() => invokeSonarMutation.mutate()}
              onRefresh={() => sonarQuery.refetch()}
              onOpenReport={openSonarReport}
            />
          ) : null}
          {view === 'admin' ? <AdminView users={usersQuery.data?.items || []} loading={usersQuery.isLoading} toast={toast} refresh={() => usersQuery.refetch()} /> : null}
        </section>
      </div>
      {modalIssue ? (
        <ExecutionGraphModal
          key={`${modalIssue.issue.id}-${modalIssue.sessionId || modalIssue.issue.latest_execution_session_id || ''}-${modalIssue.summary}`}
          issue={modalIssue.issue}
          isSummary={modalIssue.summary}
          explicitSessionId={modalIssue.sessionId}
          onClose={() => setModalIssue(null)}
          onComplete={(issueId) => updateIssueMutation.mutate({ id: issueId, status: 'in_review' })}
        />
      ) : null}
      <ToastContainer toasts={toasts} />
    </main>
  );
}

function Topbar({ stats, roleView, setRoleView, authUser, onLogout }: { stats: Record<string, number>; roleView: string; setRoleView: (role: string) => void; authUser: User | null; onLogout: () => void }) {
  const [clock, setClock] = useState('');
  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString('en-IN', { hour12: false }));
    tick();
    const timer = setInterval(tick, 30_000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="topbar">
      <div className="logo">
        <span className="logo-g">BUG</span> DADDY <span className="logo-tag">AI OPS</span>
      </div>
      <div className="tb-sep" />
      <div className="live-ind"><span className="live-dot" /> LIVE</div>
      <div className="tb-pills" role="status" aria-label="System metrics">
        <Metric label="Total" value={stats.total} />
        <Metric label="Critical" value={stats.critical} tone="red" />
        <Metric label="WIP" value={stats.wip} tone="amb" />
        <Metric label="Resolved" value={stats.resolved} tone="grn" />
      </div>
      <div className="tb-right">
        {authUser ? <div className="tb-user">USER {authUser.username} / {authUser.role}</div> : null}
        {['Developer', 'SRE', 'Manager'].map((role) => (
          <button key={role} className={clsx('role-btn', roleView === role && 'on')} onClick={() => setRoleView(role)}>
            {role}
          </button>
        ))}
        <time className="tb-clock">{clock}</time>
        <button className="btn" onClick={onLogout} title="Logout"><LogOut size={14} /> Logout</button>
      </div>
    </header>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return <div className="tb-pill"><div className={clsx('tb-pill-val', tone)}>{value}</div><div className="tb-pill-lbl">{label}</div></div>;
}

function Sidebar({ view, setView, isAdmin, stats }: { view: ViewName; setView: (view: ViewName) => void; isAdmin: boolean; stats: Record<string, number> }) {
  return (
    <aside className="sidebar">
      <div className="sb-sec">Navigation</div>
      <button className={clsx('nav-item', view === 'dashboard' && 'active')} onClick={() => setView('dashboard')}><LayoutDashboard size={16} /> Dashboard <span className="ni-badge g">{stats.total}</span></button>
      <button className={clsx('nav-item', view === 'issues' && 'active')} onClick={() => setView('issues')}><Bug size={16} /> Issues <span className="ni-badge r">{stats.backlog}</span></button>
      <button className={clsx('nav-item', view === 'sonar' && 'active')} onClick={() => setView('sonar')}><ShieldCheck size={16} /> SonarQube</button>
      {isAdmin ? <button className={clsx('nav-item', view === 'admin' && 'active')} onClick={() => setView('admin')}><Users size={16} /> Admin</button> : null}
      <div className="sb-filters">
        <div className="sec-label">Runtime</div>
        <div className="health-card"><span>Bug Daddy</span><strong>Idle</strong><div className="hbar"><div className="hbar-f" style={{ width: '8%', background: 'var(--c3)' }} /></div></div>
        <div className="health-card"><span>Incident Daddy</span><strong>Ready</strong><div className="hbar"><div className="hbar-f" style={{ width: '62%', background: 'var(--c1)' }} /></div></div>
        <div className="health-card"><span>Reviewer Daddy</span><strong>Ready</strong><div className="hbar"><div className="hbar-f" style={{ width: '45%', background: 'var(--c5)' }} /></div></div>
      </div>
    </aside>
  );
}

function DashboardOverview({ stats, charts, issues, feed, onExport, onEscalate, setView, setServiceFilter, openGraph, toast }: {
  stats: Record<string, number>;
  charts: DashboardCharts;
  issues: Issue[];
  feed: FeedItem[];
  onExport: () => void;
  onEscalate: () => void;
  setView: (view: ViewName) => void;
  setServiceFilter: (service: string) => void;
  openGraph: (issue: Issue, summary: boolean) => void;
  toast: (message: string, kind?: ToastKind) => void;
}) {
  const escalation = issues.filter((issue) => issue.frequency > 400 && issue.status !== 'resolved').sort((a, b) => b.frequency - a.frequency).slice(0, 8);
  return (
    <div className="view active">
      <PanelHeader title="Command Center" subtitle="Live agentic issue intelligence" icon={<Gauge size={18} />} actions={<><button className="btn" onClick={onExport}><Download size={14} /> Export CSV</button><button className="btn danger" onClick={onEscalate}><Zap size={14} /> Escalate All Critical</button></>} />
      <div className="dash-scroll">
        <div className="kpi-grid">
          <Kpi label="Total Issues" value={stats.total} color="var(--c3)" onClick={() => setView('issues')} />
          <Kpi label="Critical" value={stats.critical} color="var(--c2)" onClick={() => setView('issues')} />
          <Kpi label="Work In Progress" value={stats.wip} color="var(--c4)" onClick={() => setView('issues')} />
          <Kpi label="Resolved" value={stats.resolved} color="var(--c1)" onClick={() => setView('issues')} />
        </div>
        <div className="sec-label">Service Distribution</div>
        <div className="hcharts-grid">
          <HorizontalChart title="Backlog by Service" rows={charts.services.map((row) => ({ label: row.service_name, value: Number(row.backlog || 0), service: row.service_name }))} onService={(service) => { setServiceFilter(service); setView('issues'); }} />
          <HorizontalChart title="WIP by Service" rows={charts.services.map((row) => ({ label: row.service_name, value: Number(row.wip || 0), service: row.service_name }))} onService={(service) => { setServiceFilter(service); setView('issues'); }} />
        </div>
        <div className="bottom-row">
          <section className="esc-card">
            <div className="esc-card-head"><div><div className="esc-head-title">Escalation Queue</div><div className="esc-head-sub">High frequency unresolved issues</div></div><div className="esc-count-badge">{escalation.length}</div></div>
            <div className="esc-list">
              {escalation.map((issue) => <button key={issue.id} className="esc-item" onClick={() => openGraph(issue, issue.tab === 'resolved')}><span className="esc-severity" /><span className="esc-content"><strong>{issue.shortSvc}</strong><em>{issue.err}</em></span><span className="esc-right"><b>{issue.frequency}</b><small>{issue.eta}</small></span></button>)}
              {!escalation.length ? <div className="empty-state">No critical escalations.</div> : null}
            </div>
          </section>
          <section className="feed-card">
            <div className="esc-card-head"><div><div className="esc-head-title">Live Feed</div><div className="esc-head-sub">Latest platform events</div></div></div>
            <div className="feed-list">
              {feed.map((item, idx) => <button key={`${item.id}-${item.event_type}`} className={clsx('feed-item', idx === 0 && 'new')} onClick={() => toast(item.title, 'inf')}><Activity size={15} /><span><strong>{item.title}</strong><em>{item.meta}</em></span></button>)}
              {!feed.length ? <div className="empty-state">No feed events.</div> : null}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function PanelHeader({ title, subtitle, icon, actions }: { title: string; subtitle: string; icon: React.ReactNode; actions?: React.ReactNode }) {
  return <div className="ph"><div className="ph-left"><h2>{icon}{title}</h2><div className="ph-sub">{subtitle}</div></div><div className="ph-right">{actions}</div></div>;
}

function Kpi({ label, value, color, onClick }: { label: string; value: number; color: string; onClick: () => void }) {
  return <button className="kpi-card" style={{ '--kc': color } as React.CSSProperties} onClick={onClick}><div className="kpi-label">{label}</div><div className="kpi-val">{value}</div><div className="kpi-footer"><span className="kpi-sub">live</span><span className="kpi-trend up">sync</span></div></button>;
}

function HorizontalChart({ title, rows, onService }: { title: string; rows: { label: string; value: number; service: string }[]; onService: (service: string) => void }) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return <section className="hchart-card"><div className="hcc-header"><div className="hcc-title">{title}</div><div className="hcc-total">{rows.reduce((sum, row) => sum + row.value, 0)} total</div></div><div className="hbar-chart">{rows.map((row, index) => <button key={row.service} className="hbc-row" onClick={() => onService(row.service)}><span className="hbc-label">{row.label.replace('grabhack-', '')}</span><span className="hbc-track" data-tip={row.value}><span className="hbc-fill" style={{ width: `${(row.value / max) * 100}%`, background: chartColors[index % chartColors.length] }} /></span><span className="hbc-val">{row.value}</span></button>)}</div></section>;
}

function IssuesView(props: {
  stats: Record<string, number>;
  tab: IssueTab;
  setTab: (tab: IssueTab) => void;
  search: string;
  setSearch: (value: string) => void;
  serviceFilter: string;
  setServiceFilter: (value: string) => void;
  criticalityFilter: string;
  setCriticalityFilter: (value: string) => void;
  originFilter: string;
  setOriginFilter: (value: string) => void;
  services: string[];
  issues: Issue[];
  loading: boolean;
  sortBy: (key: 'id' | 'freq') => void;
  prioritizeLoading: Record<number, string>;
  prioritize: (issue: Issue) => void;
  openGraph: (issue: Issue, summary: boolean) => void;
  onExport: () => void;
}) {
  const tabs: IssueTab[] = ['backlog', 'wip', 'review', 'resolved'];
  return (
    <div className="view active">
      <PanelHeader title="Issue Workbench" subtitle="Search, route, and inspect issue execution" icon={<ListFilter size={18} />} actions={<button className="btn" onClick={props.onExport}><Download size={14} /> Export CSV</button>} />
      <div className="table-controls">
        <div className="srch-box"><Search size={15} /><input value={props.search} onChange={(event) => props.setSearch(event.target.value)} placeholder="Search ID or description..." /></div>
        <select className="tc-sel" value={props.serviceFilter} onChange={(event) => props.setServiceFilter(event.target.value)}><option value="">All Services</option>{props.services.map((service) => <option key={service} value={service}>{service}</option>)}</select>
        <select className="tc-sel" value={props.criticalityFilter} onChange={(event) => props.setCriticalityFilter(event.target.value)}><option value="">All Criticality</option><option>Critical</option><option>High</option><option>Medium</option><option>Low</option></select>
        <select className="tc-sel" value={props.originFilter} onChange={(event) => props.setOriginFilter(event.target.value)}><option value="">All Origins</option><option>CloudWatch</option><option>CVE</option><option>SonarQube</option><option>JIRA</option></select>
        <div className="tbl-count">{props.loading ? 'Loading...' : `${props.issues.length} issues`}</div>
      </div>
      <div className="tabs">{tabs.map((tab) => <button key={tab} className={clsx('tab', props.tab === tab && 'active')} onClick={() => props.setTab(tab)}>{issueStatusLabel(tab)} <span className="tc">{props.stats[tab]}</span></button>)}</div>
      <div className="table-wrap"><table className="issues-table"><thead><tr><th onClick={() => props.sortBy('id')}>JIRA ID</th><th>Service</th><th>Error</th><th onClick={() => props.sortBy('freq')}>Frequency</th><th>Criticality</th><th>Owner</th><th>ETA</th><th>Action</th></tr></thead><tbody>{props.issues.map((issue) => <IssueRow key={issue.id} issue={issue} tab={props.tab} loading={props.prioritizeLoading[issue.id]} prioritize={props.prioritize} openGraph={props.openGraph} />)}</tbody></table>{!props.issues.length ? <div className="empty-state">No issues match the selected filters.</div> : null}</div>
    </div>
  );
}

function IssueRow({ issue, tab, loading, prioritize, openGraph }: { issue: Issue; tab: IssueTab; loading?: string; prioritize: (issue: Issue) => void; openGraph: (issue: Issue, summary: boolean) => void }) {
  return <tr><td className="td-id">{issue.jiraId}</td><td className="td-own">{issue.shortSvc}</td><td className="td-desc" title={issue.err}>{issue.err}</td><td><span className={clsx('freq', issue.frequency > 400 ? 'hi' : issue.frequency > 100 ? 'med' : 'low')}>{issue.frequency}</span></td><td><span className={clsx('badge', issue.criticality.toLowerCase())}>{issue.criticality}</span></td><td className="td-own">{issue.owner}</td><td className="td-own">{issue.eta}</td><td>{tab === 'backlog' ? <button className={clsx('act-btn pri-btn', loading && 'loading')} disabled={Boolean(loading)} onClick={() => prioritize(issue)}>{loading ? loading : 'Prioritize'}</button> : tab === 'resolved' ? <button className="act-btn sum-btn" onClick={() => openGraph(issue, true)}>Summary</button> : <button className="act-btn live-btn" onClick={() => openGraph(issue, false)}>{tab === 'review' ? 'Reviewing' : 'Live Graph'}</button>}</td></tr>;
}

function formatBytes(size: number) {
  if (!size) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  return `${(size / Math.pow(1024, index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function SonarView({ status, loading, refreshing, invoking, onInvoke, onRefresh, onOpenReport }: {
  status?: SonarStatus;
  loading: boolean;
  refreshing: boolean;
  invoking: boolean;
  onInvoke: () => void;
  onRefresh: () => void;
  onOpenReport: (reportDate: string) => void;
}) {
  const reports = status?.reports || [];
  const latest = status?.latest_report;
  return (
    <div className="view active">
      <PanelHeader
        title="SonarQube"
        subtitle="Run code-quality scans and open generated S3 reports"
        icon={<ShieldCheck size={18} />}
        actions={<><button className="btn" onClick={onRefresh} disabled={refreshing}><RefreshCcw size={14} /> {refreshing ? 'Refreshing' : 'Refresh'}</button><button className="btn pri" onClick={onInvoke} disabled={invoking}><Play size={14} /> {invoking ? 'Starting' : 'Run Scan'}</button></>}
      />
      <div className="dash-scroll">
        <div className="sonar-grid">
          <section className="sonar-card">
            <div className="sonar-card-head"><Cloud size={17} /><span>Report Bucket</span></div>
            <strong>{status?.bucket || 'bugdaddy-sonar-reports'}</strong>
            <em>{status?.region || 'ap-south-1'}</em>
          </section>
          <section className="sonar-card">
            <div className="sonar-card-head"><Bot size={17} /><span>Trigger Lambda</span></div>
            <strong>{status?.lambda_name || 'bugdaddy-sonar-scan-trigger'}</strong>
            <em>SSM Run Command</em>
          </section>
          <section className="sonar-card">
            <div className="sonar-card-head"><FileJson size={17} /><span>Latest Report</span></div>
            <strong>{latest?.date || 'No reports yet'}</strong>
            <em>{latest ? formatBytes(latest.size) : loading ? 'Loading...' : 'Run the first scan'}</em>
          </section>
        </div>

        <section className="admin-card sonar-reports">
          <div className="sonar-list-head">
            <div>
              <div className="esc-head-title">S3 Reports</div>
              <div className="esc-head-sub">Presigned links are generated on demand</div>
            </div>
            <div className="tbl-count">{loading ? 'Loading...' : `${reports.length} reports`}</div>
          </div>
          <div className="table-wrap">
            <table className="admin-table">
              <thead><tr><th>Date</th><th>S3 Key</th><th>Size</th><th>Updated</th><th>Action</th></tr></thead>
              <tbody>
                {reports.map((report) => (
                  <tr key={report.key}>
                    <td className="td-id">{report.date}</td>
                    <td className="td-desc" title={report.key}>{report.key}</td>
                    <td className="td-own">{formatBytes(report.size)}</td>
                    <td className="td-own">{report.last_modified || '-'}</td>
                    <td><button className="act-btn live-btn" onClick={() => onOpenReport(report.date)}><ExternalLink size={12} /> Open</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!reports.length ? <div className="empty-state">No Sonar reports found in S3.</div> : null}
          </div>
        </section>
      </div>
    </div>
  );
}

function AdminView({ users, loading, toast, refresh }: { users: User[]; loading: boolean; toast: (message: string, kind?: ToastKind) => void; refresh: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ username: '', email: '', full_name: '', password: '', role_name: 'user', status: 'active' });
  const createMutation = useMutation({
    mutationFn: () => apiJson<User>('/admin/users', { method: 'POST', body: JSON.stringify({ ...form, full_name: form.full_name || null }) }),
    onSuccess: async (user) => { toast(`Created user ${user.username}`, 'ok'); setForm({ username: '', email: '', full_name: '', password: '', role_name: 'user', status: 'active' }); await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] }); },
    onError: (error) => toast(errorMessage(error, 'Could not create user'), 'err'),
  });

  async function toggleUser(user: User) {
    try {
      const data = await apiJson<User>('/admin/users/' + user.id, { method: 'PATCH', body: JSON.stringify({ status: user.status === 'active' ? 'inactive' : 'active' }) });
      toast(`User ${data.username} is now ${data.status}`, 'ok');
      await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    } catch (error) {
      toast(errorMessage(error, 'Status update failed'), 'err');
    }
  }

  async function resetPassword(user: User) {
    const newPassword = window.prompt('Enter a new password for ' + user.username);
    if (!newPassword) return;
    try {
      await apiJson('/admin/users/' + user.id + '/password', { method: 'PATCH', body: JSON.stringify({ new_password: newPassword }) });
      toast('Password updated for ' + user.username, 'ok');
    } catch (error) {
      toast(errorMessage(error, 'Password reset failed'), 'err');
    }
  }

  return (
    <div className="view active">
      <PanelHeader title="Admin Console" subtitle="User provisioning and access controls" icon={<Shield size={18} />} actions={<button className="btn" onClick={refresh}><RefreshCcw size={14} /> Refresh Users</button>} />
      <div className="admin-grid">
        <form className="admin-card admin-form" onSubmit={(event: FormEvent) => { event.preventDefault(); createMutation.mutate(); }}>
          <div className="admin-card-head">Create User</div>
          <label>Username<input required value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} /></label>
          <label>Email<input required type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
          <label>Full Name<input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} /></label>
          <label>Password<input required type="password" minLength={8} value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
          <label>Role<select value={form.role_name} onChange={(event) => setForm({ ...form, role_name: event.target.value })}><option value="user">User</option><option value="admin">Admin</option></select></label>
          <label>Status<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}><option value="active">Active</option><option value="inactive">Inactive</option><option value="locked">Locked</option></select></label>
          <div className="admin-actions"><button className="btn pri" type="submit" disabled={createMutation.isPending}>Create User</button><button className="btn" type="button" onClick={() => setForm({ username: '', email: '', full_name: '', password: '', role_name: 'user', status: 'active' })}>Clear</button></div>
        </form>
        <section className="admin-card admin-list-card"><div className="admin-card-head">Users</div><div className="admin-list-wrap"><table className="admin-table"><thead><tr><th>Username</th><th>Email</th><th>Role</th><th>Status</th><th>Last Login</th><th>Actions</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td>{user.username}</td><td>{user.email}</td><td><span className="admin-badge">{user.role}</span></td><td><span className="badge med">{user.status}</span></td><td>{user.last_login_at ? new Date(user.last_login_at).toLocaleString('en-IN') : 'Never'}</td><td><button className="act-btn sum-btn" onClick={() => resetPassword(user)}>Reset Password</button><button className="act-btn pri-btn" onClick={() => toggleUser(user)}>{user.status === 'active' ? 'Deactivate' : 'Activate'}</button></td></tr>)}</tbody></table>{loading ? <div className="empty-state">Loading users...</div> : null}{!loading && !users.length ? <div className="empty-state">No users found.</div> : null}</div></section>
      </div>
    </div>
  );
}

function ExecutionGraphModal({ issue, isSummary, explicitSessionId, onClose, onComplete }: { issue: Issue; isSummary: boolean; explicitSessionId?: string; onClose: () => void; onComplete: (issueId: number) => void }) {
  const [zoom, setZoom] = useState(0.55);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const sessionId = explicitSessionId || issue.latest_execution_session_id || issue.execution_session_id || '';
  const workflowKey = issue.workflow_key || issue.agent_target || 'bug_daddy';
  const [nodeStates, setNodeStates] = useState<Record<string, string>>(() => initialGraphNodeStates(workflowKey, isSummary));
  const afterIdRef = useRef(0);
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null);

  const graphQuery = useQuery({
    queryKey: ['workflow-graph', sessionId || workflowKey],
    queryFn: async () => {
      if (sessionId) {
        const data = await apiJson<{ workflow?: { graph_json?: WorkflowGraph }; graph_json?: WorkflowGraph; nodes?: WorkflowNode[]; edges?: WorkflowEdge[] }>(`/agent/executions/${sessionId}/graph`);
        return data.workflow?.graph_json || data.graph_json || (data as WorkflowGraph);
      }
      const data = await apiJson<{ workflow?: { graph_json?: WorkflowGraph }; graph_json?: WorkflowGraph; nodes?: WorkflowNode[]; edges?: WorkflowEdge[] }>(`/agent/workflows/${workflowKey}`);
      return data.workflow?.graph_json || data.graph_json || (data as WorkflowGraph);
    },
    retry: false,
  });

  const graph = useMemo(() => normalizeWorkflowGraph(graphQuery.data as WorkflowGraph | undefined), [graphQuery.data]);
  const edges = useMemo(() => graph.edges.map(normalizeEdge), [graph.edges]);
  const nodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const activePath = useMemo(() => activePathForWorkflow(workflowKey), [workflowKey]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    afterIdRef.current = 0;
    if (sessionId || isSummary) return;

    const timers: ReturnType<typeof setTimeout>[] = [];
    activePath.forEach((nodeId, index) => {
      timers.push(setTimeout(() => setNodeStates((state) => ({ ...state, [nodeId]: 'active' })), 450 + index * 620));
      timers.push(setTimeout(() => setNodeStates((state) => ({ ...state, [nodeId]: 'done' })), 880 + index * 620));
    });
    return () => timers.forEach(clearTimeout);
  }, [activePath, isSummary, issue.id, sessionId]);

  useEffect(() => {
    if (!sessionId || isSummary) return;
    let stopped = false;
    async function poll() {
      try {
        const data = await apiJson<ListResponse<ExecutionEvent>>(`/agent/executions/${sessionId}/events?after_id=${afterIdRef.current}&limit=200`);
        if (stopped || !data.items.length) return;
        setEvents((items) => [...items, ...data.items]);
        afterIdRef.current = Math.max(afterIdRef.current, ...data.items.map((item) => item.id || 0));
        const nextStates: Record<string, string> = {};
        data.items.forEach((ev) => {
          if (!ev.node_id) return;
          const nodeId = canonicalNodeId(ev.node_id);
          if (ev.event_type.endsWith('.started') || ev.status === 'running') nextStates[nodeId] = 'active';
          if (ev.event_type.endsWith('.completed') || ev.status === 'succeeded') nextStates[nodeId] = 'done';
          if (ev.event_type.endsWith('.failed') || ev.status === 'failed') nextStates[nodeId] = 'error';
          if (ev.event_type === 'session.completed') onComplete(issue.id);
        });
        if (Object.keys(nextStates).length) setNodeStates((state) => ({ ...state, ...nextStates }));
      } catch {
        // Keep modal open if polling has a transient failure.
      }
    }
    void poll();
    const timer = setInterval(poll, 1500);
    return () => { stopped = true; clearInterval(timer); };
  }, [isSummary, issue.id, onComplete, sessionId]);

  const activeEdges = new Set(edges.filter(([from, to]) => nodeStates[from] || nodeStates[to]).map(([from, to]) => `${from}-${to}`));

  function handleWheel(event: React.WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    if (event.ctrlKey || event.metaKey) {
      setZoom((value) => Math.max(0.3, Math.min(2.5, value - event.deltaY * 0.005)));
      return;
    }
    setPan((value) => ({ x: value.x - event.deltaX, y: value.y - event.deltaY }));
  }

  function beginPan(event: React.MouseEvent<HTMLDivElement>) {
    if (event.target instanceof Element && event.target.closest('.n8n-node')) return;
    dragRef.current = { startX: event.clientX, startY: event.clientY, panX: pan.x, panY: pan.y };
  }

  function movePan(event: React.MouseEvent<HTMLDivElement>) {
    if (!dragRef.current) return;
    setPan({
      x: dragRef.current.panX + event.clientX - dragRef.current.startX,
      y: dragRef.current.panY + event.clientY - dragRef.current.startY,
    });
  }

  function endPan() {
    dragRef.current = null;
  }

  return (
    <div className="modal-ov" role="dialog" aria-modal="true" onMouseDown={(event: MouseEvent<HTMLDivElement>) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="modal">
        <div className="modal-hdr"><div><div className="modal-title"><GitBranch size={18} /> {isSummary ? 'Execution Summary' : 'Live Execution Graph'} <span>{issue.jiraId}</span></div><div className="modal-sub">{issue.shortSvc} / freq={issue.freq} / {issue.criticality} / {sessionId || 'workflow preview'}</div></div><button className="modal-close" onClick={onClose}><X size={14} /> Close</button></div>
        <div className="modal-body">
          <div className="n8n-canvas" onWheel={handleWheel} onMouseDown={beginPan} onMouseMove={movePan} onMouseUp={endPan} onMouseLeave={endPan}>
            <div className="n8n-canvas-inner" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
              <GroupBox label="Incident Route" x={40} y={330} w={210} h={170} color="#ff4060" />
              <GroupBox label="Knowledge Base" x={285} y={340} w={190} h={145} color="#ffaa00" />
              <GroupBox label="Remediation Pipeline" x={510} y={280} w={700} h={390} color="#00d4aa" />
              <GroupBox label="Review Pipeline" x={1220} y={280} w={210} h={160} color="#b667ff" />
              <svg className="n8n-edges" viewBox="0 0 1500 900" preserveAspectRatio="none">
                {edges.map(([from, to]) => {
                  const source = nodeById.get(from);
                  const target = nodeById.get(to);
                  if (!source || !target) return null;
                  const path = edgePath(source, target, edges);
                  const active = activeEdges.has(`${from}-${to}`);
                  return (
                    <g key={`${from}-${to}`} className={clsx('edge-group', active && 'active')}>
                      <path d={path} style={{ stroke: nodeColor(source) }} />
                      {active ? <circle r="3" fill={nodeColor(target)}><animateMotion dur="2s" repeatCount="indefinite" path={path} /></circle> : null}
                    </g>
                  );
                })}
              </svg>
              {graph.nodes.map((node) => <GraphNode key={node.id} node={node} state={nodeStates[node.id]} />)}
            </div>
            <div className="n8n-zoom"><button onClick={() => setZoom((z) => Math.min(2.5, z + 0.1))}>+</button><div className="n8n-zoom-level">{Math.round(zoom * 100)}%</div><button onClick={() => setZoom((z) => Math.max(0.3, z - 0.1))}>-</button><button onClick={() => { setZoom(0.55); setPan({ x: 0, y: 0 }); }}>Reset</button></div>
          </div>
          <div className="n8n-right"><div className="n8n-log-stream">{events.length ? events.map((event, index) => <LogEntry key={event.id} event={event} showConnector={index > 0} />) : <FallbackLogs issue={issue} isSummary={isSummary} />}</div></div>
        </div>
      </div>
    </div>
  );
}

function GroupBox({ label, x, y, w, h, color }: { label: string; x: number; y: number; w: number; h: number; color: string }) {
  return (
    <div className="group-box" style={{ left: x, top: y, width: w, height: h, '--group-color': color } as React.CSSProperties}>
      <span>{label}</span>
    </div>
  );
}

function GraphNode({ node, state }: { node: WorkflowNode; state?: string }) {
  const color = nodeColor(node);
  const isAgent = node.type === 'agent' || node.type === 'tool' || node.type === 'store';
  const ring = isAgent ? { vb: '0 0 140 44', cx: 70, cy: 22, r: 70 } : node.type === 'daddy' ? { vb: '0 0 82 82', cx: 41, cy: 41, r: 38 } : { vb: '0 0 82 82', cx: 41, cy: 41, r: 36 };

  return (
    <div
      className={clsx('n8n-node', `type-${isAgent ? 'agent' : node.type || 'agent'}`, state)}
      style={{ left: node.x, top: node.y, '--nd-color': color, '--nd-bg': `${color}14`, '--nd-border': `${color}44` } as React.CSSProperties}
      role="img"
      aria-label={node.label}
    >
      <div className="exec-ring"><svg viewBox={ring.vb}><circle cx={ring.cx} cy={ring.cy} r={ring.r} className="exec-ring-arc" /></svg></div>
      <div className="nd-icon">{renderNodeIcon(node)}</div>
      {isAgent ? <div className="nd-agent-name">{node.label}</div> : null}
      <div className="nd-title">{node.label}{node.sub ? <span className="nd-subtitle">{node.sub}</span> : null}</div>
      <div className="nd-port port-left" />
      <div className="nd-port port-right" />
      <div className="nd-port port-bottom" />
      <div className="nd-done-mark">v</div>
      <div className="nd-err-mark">x</div>
    </div>
  );
}

function LogEntry({ event, showConnector }: { event: ExecutionEvent; showConnector: boolean }) {
  const [expanded, setExpanded] = useState(Boolean(event.error_message || event.output_summary));
  const status = event.status === 'failed' ? 'error' : event.status === 'running' ? 'active' : 'done';
  const entries = [
    ['Description', event.description],
    ['Input', event.input_summary],
    ['Output', event.output_summary],
    ['Reasoning', event.reasoning_summary],
    ['Error', event.error_message],
    ['Tool', event.tool_name],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));

  return (
    <>
      {showConnector ? <div className="log-connector" /> : null}
      <div className={clsx('log-entry', status, expanded && 'expanded', entries.length && 'has-details')}>
        <button className="log-entry-header" onClick={() => setExpanded((value) => !value)}>
          <div className="log-status-dot">{status === 'active' ? 'o' : status === 'error' ? 'x' : 'v'}</div>
          <div className="log-thought-label">{event.node_name ? `${event.node_name}: ` : ''}{event.title || event.event_type}<span className="log-ts-label">{event.created_at ? new Date(event.created_at).toLocaleTimeString('en-IN', { hour12: false }) : ''}</span></div>
          {entries.length ? <div className="log-chevron">›</div> : null}
        </button>
        {entries.length ? (
          <div className="log-thought-body">
            <div className="log-details-grid">
              {entries.map(([label, value]) => <div key={label} className={clsx('log-detail-item', (label === 'Input' || label === 'Output') && 'important')}><div className="log-detail-label">{label}</div><div className="log-detail-value">{value}</div></div>)}
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}

function FallbackLogs({ issue, isSummary }: { issue: Issue; isSummary: boolean }) {
  const steps = issue.workflow_key === 'incident_daddy'
    ? ['Issues Tracker', 'Escalation Agent', 'Jira Agent', 'Incident Daddy']
    : ['Issues Tracker', 'Escalation Agent', 'Jira Agent', 'Bug Daddy', 'SME Agent', 'Planner', 'Planner Critique', 'Context Analyser', 'Context Critique', 'Coder', 'Coder Critique', 'GitHub', 'Reviewer Daddy'];

  return (
    <>
      <div className="execution-note">{isSummary ? 'Execution summary preview' : 'Waiting for backend execution events. Local workflow animation is shown on the canvas.'}</div>
      {steps.map((step, index) => (
        <div key={step} className={clsx('log-step-group', index > 1 && !isSummary && 'collapsed')}>
          <div className="log-step-header">
            <span className="step-chevron">▾</span>
            <span className="step-icon">{String(index + 1).padStart(2, '0')}</span>
            <span className="step-name">{step}</span>
            <span className={clsx('step-status n8n-step-chip', isSummary || index < 2 ? 'done' : 'running')}>{isSummary || index < 2 ? 'DONE' : 'READY'}</span>
          </div>
          <div className="log-step-body">
            <div className="log-entry info"><strong>{step}</strong><p>{issue.jiraId} / {issue.shortSvc} / freq={issue.frequency}</p></div>
          </div>
        </div>
      ))}
    </>
  );
}

function ToastContainer({ toasts }: { toasts: ToastItem[] }) {
  return <div className="toastc" aria-live="polite">{toasts.map((toast) => <div key={toast.id} className={clsx('toast', toast.kind)}><span>{toast.kind === 'ok' ? 'v' : toast.kind === 'err' ? 'x' : 'i'}</span>{toast.message}</div>)}</div>;
}

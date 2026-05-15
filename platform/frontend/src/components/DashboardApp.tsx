'use client';

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, apiJson, errorMessage, logoutRequest } from '@/lib/api';
import { TAB_KEY, VIEW_KEY, clearSession, getStoredUser } from '@/lib/storage';
import type {
  DashboardCharts,
  DashboardSummary,
  FeedItem,
  Issue,
  ListResponse,
  SonarInvokeResponse,
  SonarReportUrl,
  SonarStatus,
  User,
  ViewName,
  IssueTab,
  ToastKind,
  ToastItem,
} from '@/lib/types';

import { Topbar } from './layout/Topbar';
import { Sidebar } from './layout/Sidebar';
import { DashboardOverview } from './dashboard/DashboardOverview';
import { IssuesView } from './issues/IssuesView';
import { SonarView } from './sonar/SonarView';
import { AdminView } from './admin/AdminView';
import { SecurityScannerView } from './security/SecurityScannerView';
import { ExecutionGraphModal } from './graph/ExecutionGraphModal';
import { ToastContainer } from './shared/ToastContainer';
import { CommandPalette } from './shared/CommandPalette';
import { DemoTourBanner } from './shared/DemoTourBanner';
import { AiThinkingBadge } from './shared/AiThinkingBadge';

const emptySummary: DashboardSummary = { total: 0, backlog: 0, wip: 0, review: 0, resolved: 0, no_action: 0, critical: 0 };
const emptyCharts: DashboardCharts = { services: [], sources: [], issue_types: [] };
const emptyIssues: Issue[] = [];

function eta(pos: number) {
  const minutes = pos * 15;
  return minutes < 60 ? `~${minutes}m` : `~${(minutes / 60).toFixed(1)}h`;
}

function withEta(items: Issue[]) {
  return items.map((issue, index) => ({ ...issue, eta: eta(index + 1), origin: issue.source }));
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

export function DashboardApp() {
  const queryClient = useQueryClient();
  const [mounted, setMounted] = useState(false);
  const [authUser, setAuthUser] = useState<User | null>(null);
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
  const [commandOpen, setCommandOpen] = useState(false);
  const [agentActive, setAgentActive] = useState(false);

  // Hydrate client-only state after mount (avoids SSR mismatch)
  useEffect(() => {
    const storedUser = getStoredUser();
    if (storedUser) setAuthUser(storedUser);
    const savedView = localStorage.getItem(VIEW_KEY) as ViewName | null;
    const savedTab = localStorage.getItem(TAB_KEY) as IssueTab | null;
    if (savedView) setViewState(savedView);
    if (savedTab) setTabState(savedTab);
    setMounted(true);
  }, []);

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
    }
  }, [meQuery.data, meQuery.isError]);

  const summaryQuery = useQuery({ queryKey: ['dashboard', 'summary'], queryFn: () => apiJson<DashboardSummary>('/dashboard/summary'), refetchInterval: 30_000 });
  const chartsQuery = useQuery({ queryKey: ['dashboard', 'charts'], queryFn: () => apiJson<DashboardCharts>('/dashboard/charts'), refetchInterval: 30_000 });
  const feedQuery = useQuery({ queryKey: ['dashboard', 'feed'], queryFn: () => apiJson<ListResponse<FeedItem>>('/dashboard/feed?limit=12'), refetchInterval: 30_000 });
  const sonarQuery = useQuery({ queryKey: ['sonar', 'status'], queryFn: () => apiJson<SonarStatus>('/sonar/status?limit=12'), refetchInterval: 30_000 });
  const issuesQuery = useQuery({
    queryKey: ['issues'],
    queryFn: async () => withEta((await apiJson<ListResponse<Issue>>('/issues?limit=2000')).items || []),
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
      .filter((issue) => !q || String(issue.id).includes(q) || issue.jiraId.toLowerCase().includes(q) || issue.err.toLowerCase().includes(q) || issue.shortSvc.toLowerCase().includes(q))
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
    setAgentActive(true);
    setPrioritizeLoading((state) => ({ ...state, [issue.id]: 'invoke' }));
    try {
      const prioritized = await apiJson<Issue>(`/issues/${issue.id}/prioritize`, { method: 'POST' });
      setPrioritizeLoading((state) => ({ ...state, [issue.id]: 'refresh' }));
      const invoke = await apiFetch('/agent/invoke', {
        method: 'POST',
        body: JSON.stringify({
          issue_id: issue.id,
          target: 'classifier',
          service_name: issue.service,
          incident_summary: issue.description || issue.err,
          source: 'platform',
          metadata: {
            issue_id: issue.id,
            workflow_key: prioritized.workflow_key || issue.workflow_key,
            suggested_agent_target: prioritized.agent_target || issue.agent_target,
          },
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

  function onModalClose() {
    setModalIssue(null);
    setAgentActive(false);
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
    const rows = [['Issue ID', 'Service', 'Error', 'Freq', 'Criticality', 'Owner', 'Tab', 'ETA']];
    issues.forEach((issue) => rows.push([String(issue.id), issue.shortSvc, `"${issue.err.replace(/"/g, '""')}"`, String(issue.freq), issue.criticality, issue.owner, issue.tab, issue.eta || '']));
    const blob = new Blob([rows.map((row) => row.join(',')).join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'grabhack_issues.csv';
    anchor.click();
    URL.revokeObjectURL(url);
    toast('CSV exported', 'ok');
  }

  // Show boot screen until client has mounted (ensures server/client HTML match)
  if (!mounted || (meQuery.isLoading && !authUser)) return <main className="boot-screen">Loading Bug Daddy...</main>;

  return (
    <main className="bd-shell">
      <Topbar
        stats={stats}
        roleView={roleView}
        setRoleView={setRoleView}
        authUser={authUser}
        onLogout={logoutRequest}
        onOpenCommandPalette={() => setCommandOpen(true)}
        isAgentActive={agentActive}
      />
      <DemoTourBanner />
      <div className="app">
        <Sidebar view={view} setView={setView} isAdmin={isAdmin} stats={stats} />
        <section className="main">
          {view === 'dashboard' ? (
            <DashboardOverview
              stats={stats}
              charts={charts}
              issues={issues}
              feed={feed}
              loading={issuesQuery.isLoading || summaryQuery.isLoading}
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
              inProgress={sonarQuery.data?.in_progress ?? false}
              onInvoke={() => invokeSonarMutation.mutate()}
              onRefresh={() => sonarQuery.refetch()}
              onOpenReport={openSonarReport}
            />
          ) : null}
          {view === 'security' ? (
            <SecurityScannerView addToast={toast} />
          ) : null}
          {view === 'admin' && isAdmin ? (
            <AdminView users={usersQuery.data?.items || []} loading={usersQuery.isLoading} toast={toast} refresh={() => usersQuery.refetch()} />
          ) : null}
        </section>
      </div>
      <CommandPalette isOpen={commandOpen} setIsOpen={setCommandOpen} setView={setView} onEscalate={escalateAll} issues={issues} />
      <AiThinkingBadge isActive={agentActive} />
      {modalIssue ? (
        <ExecutionGraphModal
          issue={modalIssue.issue}
          isSummary={modalIssue.summary}
          explicitSessionId={modalIssue.sessionId}
          onClose={onModalClose}
          onComplete={async () => {
            toast('Execution completed ✓', 'ok');
            setAgentActive(false);
            await refreshDashboard();
          }}
        />
      ) : null}
      <ToastContainer toasts={toasts} />
    </main>
  );
}

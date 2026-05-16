'use client';

import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dynamic from 'next/dynamic';
import { apiFetch, apiJson, errorMessage, logoutRequest } from '@/lib/api';
import { TAB_KEY, VIEW_KEY, clearSession, getStoredUser } from '@/lib/storage';
import type {
  DashboardCharts,
  DashboardSummary,
  FeedItem,
  Issue,
  ListResponse,
  SonarInvokeResponse,
  SonarStatus,
  User,
  ViewName,
  IssueTab,
  ToastKind,
  ToastItem,
  AiQueueStatus,
} from '@/lib/types';

import { Topbar } from './layout/Topbar';
import { Sidebar } from './layout/Sidebar';
import { ToastContainer } from './shared/ToastContainer';

const sectionSkeleton = <div className="view-skeleton" aria-busy="true" />;
const DashboardOverview = dynamic(() => import('./dashboard/DashboardOverview').then((mod) => mod.DashboardOverview), { ssr: false, loading: () => sectionSkeleton });
const IssuesView = dynamic(() => import('./issues/IssuesView').then((mod) => mod.IssuesView), { ssr: false, loading: () => sectionSkeleton });
const SonarView = dynamic(() => import('./sonar/SonarView').then((mod) => mod.SonarView), { ssr: false, loading: () => sectionSkeleton });
const SonarReportModal = dynamic(() => import('./sonar/SonarReportModal').then((mod) => mod.SonarReportModal), { ssr: false, loading: () => null });
import type { SonarReport } from './sonar/SonarReportModal';
const AdminView = dynamic(() => import('./admin/AdminView').then((mod) => mod.AdminView), { ssr: false, loading: () => sectionSkeleton });
const AiQueueView = dynamic(() => import('./admin/AiQueueView').then((mod) => mod.AiQueueView), { ssr: false, loading: () => sectionSkeleton });
const SecurityScannerView = dynamic(() => import('./security/SecurityScannerView').then((mod) => mod.SecurityScannerView), { ssr: false, loading: () => sectionSkeleton });
const GrafanaView = dynamic(() => import('./grafana/GrafanaView').then((mod) => mod.GrafanaView), { ssr: false, loading: () => sectionSkeleton });
const KibanaView = dynamic(() => import('./kibana/KibanaView').then((mod) => mod.KibanaView), { ssr: false, loading: () => sectionSkeleton });
const ExecutionGraphModal = dynamic(() => import('./graph/ExecutionGraphModal').then((mod) => mod.ExecutionGraphModal), { ssr: false, loading: () => null });
const CommandPalette = dynamic(() => import('./shared/CommandPalette').then((mod) => mod.CommandPalette), { ssr: false, loading: () => null });
const DemoTourBanner = dynamic(() => import('./shared/DemoTourBanner').then((mod) => mod.DemoTourBanner), { ssr: false, loading: () => null });
const AiThinkingBadge = dynamic(() => import('./shared/AiThinkingBadge').then((mod) => mod.AiThinkingBadge), { ssr: false, loading: () => null });
const SupportChatWidget = dynamic(() => import('./support/SupportChatWidget').then((mod) => mod.SupportChatWidget), { ssr: false, loading: () => null });

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

export function DashboardApp() {
  const queryClient = useQueryClient();
  const [mounted, setMounted] = useState(false);
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [view, setViewState] = useState<ViewName>('dashboard');
  const [tab, setTabState] = useState<IssueTab>('backlog');
  const [search, setSearch] = useState('');
  const [serviceFilter, setServiceFilter] = useState('');
  const [criticalityFilter, setCriticalityFilter] = useState('');
  const [originFilter, setOriginFilter] = useState('');
  const [sortKey, setSortKey] = useState<'id' | 'freq'>('id');
  const [sortDir, setSortDir] = useState(-1);
  const [prioritizeLoading, setPrioritizeLoading] = useState<Record<number, string>>({});
  const [modalIssue, setModalIssue] = useState<{ issue: Issue; summary: boolean; sessionId?: string } | null>(null);
  const [sonarReportModal, setSonarReportModal] = useState<{ date: string; report: SonarReport | null; loading: boolean; error?: string } | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [commandOpen, setCommandOpen] = useState(false);
  const [agentActive, setAgentActive] = useState(false);
  const [syncingIssueIds, setSyncingIssueIds] = useState<number[]>([]);
  const prioritizeControllersRef = useRef<Record<number, AbortController>>({});
  const escalateControllerRef = useRef<AbortController | null>(null);

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
    if ((nextView === 'admin' || nextView === 'ai_queue') && authUser?.role !== 'admin') {
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

  const summaryQuery = useQuery({
    queryKey: ['dashboard', 'summary'],
    queryFn: () => apiJson<DashboardSummary>('/dashboard/summary'),
    refetchInterval: view === 'dashboard' ? 30_000 : false,
  });
  const chartsQuery = useQuery({
    queryKey: ['dashboard', 'charts'],
    queryFn: () => apiJson<DashboardCharts>('/dashboard/charts'),
    refetchInterval: view === 'dashboard' ? 30_000 : false,
  });
  const feedQuery = useQuery({
    queryKey: ['dashboard', 'feed'],
    queryFn: () => apiJson<ListResponse<FeedItem>>('/dashboard/feed?limit=12'),
    refetchInterval: view === 'dashboard' ? 30_000 : false,
  });
  const sonarQuery = useQuery({
    queryKey: ['sonar', 'status'],
    queryFn: () => apiJson<SonarStatus>('/sonar/status?limit=12'),
    refetchInterval: view === 'sonar' ? 30_000 : false,
  });
  const issuesQuery = useQuery({
    queryKey: ['issues'],
    queryFn: async () => withEta((await apiJson<ListResponse<Issue>>('/issues?limit=2000')).items || []),
    refetchInterval: 30_000,
  });
  const usersQuery = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => apiJson<ListResponse<User>>('/admin/users'),
    enabled: view === 'admin' && authUser?.role === 'admin',
  });
  const aiQueueQuery = useQuery({
    queryKey: ['admin', 'ai-queue'],
    queryFn: () => apiJson<AiQueueStatus>('/admin/ai-queue'),
    enabled: (view === 'admin' || view === 'ai_queue') && authUser?.role === 'admin',
    refetchInterval: view === 'admin' || view === 'ai_queue' ? 15_000 : false,
  });

  const summary = summaryQuery.data || emptySummary;
  const charts = chartsQuery.data || emptyCharts;
  const issues = issuesQuery.data || emptyIssues;
  const feed = feedQuery.data?.items || [];
  const isAdmin = authUser?.role === 'admin';
  const dashboardHardError =
    (summaryQuery.isError && !summaryQuery.data) ||
    (chartsQuery.isError && !chartsQuery.data) ||
    (feedQuery.isError && !feedQuery.data) ||
    (issuesQuery.isError && !issuesQuery.data);
  const issuesHardError = issuesQuery.isError && !issuesQuery.data;
  const sonarHardError = sonarQuery.isError && !sonarQuery.data;
  const adminHardError = usersQuery.isError && !usersQuery.data;
  const aiQueueHardError = aiQueueQuery.isError && !aiQueueQuery.data;

  const hasDataError = (
    view === 'dashboard' && dashboardHardError
  ) || (
    view === 'issues' && issuesHardError
  ) || (
    view === 'sonar' && sonarHardError
  ) || (
    view === 'admin' && isAdmin && adminHardError
  ) || (
    view === 'ai_queue' && isAdmin && aiQueueHardError
  );
  const dashboardErrorText = view === 'dashboard' && dashboardHardError
    ? errorMessage(summaryQuery.error || chartsQuery.error || feedQuery.error || issuesQuery.error, 'Dashboard data could not be loaded.')
    : undefined;
  const issuesErrorText = view === 'issues' && issuesHardError
    ? errorMessage(issuesQuery.error, 'Issues could not be loaded.')
    : undefined;
  const sonarErrorText = view === 'sonar' && sonarHardError
    ? errorMessage(sonarQuery.error, 'Sonar data could not be loaded.')
    : undefined;
  const adminErrorText = view === 'admin' && isAdmin && adminHardError
    ? errorMessage(usersQuery.error, 'Admin data could not be loaded.')
    : undefined;
  const aiQueueErrorText = view === 'ai_queue' && isAdmin && aiQueueHardError
    ? errorMessage(aiQueueQuery.error, 'AI queue data could not be loaded.')
    : undefined;
  const deferredSearch = useDeferredValue(search);

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
    const q = deferredSearch.toLowerCase();
    return issues
      .filter((issue) => issue.tab === tab)
      .filter((issue) => !q || String(issue.id).includes(q) || issue.jiraId.toLowerCase().includes(q) || issue.err.toLowerCase().includes(q) || issue.shortSvc.toLowerCase().includes(q))
      .filter((issue) => !serviceFilter || issue.service === serviceFilter)
      .filter((issue) => !criticalityFilter || issue.criticality === criticalityFilter)
      .filter((issue) => !originFilter || issue.origin === originFilter)
      .sort((a, b) => ((a[sortKey] as number) > (b[sortKey] as number) ? sortDir : -sortDir));
  }, [criticalityFilter, deferredSearch, issues, originFilter, serviceFilter, sortDir, sortKey, tab]);

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
    setSonarReportModal({ date: reportDate, report: null, loading: true });
    try {
      const data = await apiJson<SonarReport>(`/sonar/reports/${reportDate}/data`);
      setSonarReportModal({ date: reportDate, report: data, loading: false });
    } catch (error) {
      setSonarReportModal({ date: reportDate, report: null, loading: false, error: errorMessage(error, 'Could not load Sonar report') });
    }
  }

  async function prioritize(issue: Issue) {
    prioritizeControllersRef.current[issue.id]?.abort();
    const controller = new AbortController();
    prioritizeControllersRef.current[issue.id] = controller;
    setAgentActive(true);
    setSyncingIssueIds((current) => (current.includes(issue.id) ? current : [...current, issue.id]));
    setPrioritizeLoading((state) => ({ ...state, [issue.id]: 'invoke' }));
    const previousIssues = queryClient.getQueryData<Issue[]>(['issues']) ?? [];
    queryClient.setQueryData<Issue[]>(['issues'], (existing = []) =>
      existing.map((item) =>
        item.id === issue.id
          ? { ...item, tab: 'wip', status: 'in_progress' }
          : item,
      ),
    );
    try {
      const prioritized = await apiJson<Issue>(`/issues/${issue.id}/prioritize`, {
        method: 'POST',
        signal: controller.signal,
      });
      setPrioritizeLoading((state) => ({ ...state, [issue.id]: 'refresh' }));
      const invoke = await apiFetch('/agent/invoke', {
        method: 'POST',
        signal: controller.signal,
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
        queryClient.setQueryData<Issue[]>(['issues'], previousIssues);
        toast(data.detail || 'Agent invoke failed', 'err');
        return;
      }
      toast(`Routed to ${data.target || prioritized.agent_target || issue.agent_target}`, 'ok');
      await refreshDashboard();
      setModalIssue({ issue: prioritized, summary: false, sessionId: data.session_id });
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      queryClient.setQueryData<Issue[]>(['issues'], previousIssues);
      toast(errorMessage(error, 'Prioritize failed'), 'err');
    } finally {
      delete prioritizeControllersRef.current[issue.id];
      setSyncingIssueIds((current) => current.filter((id) => id !== issue.id));
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
    escalateControllerRef.current?.abort();
    const controller = new AbortController();
    escalateControllerRef.current = controller;
    const criticals = issues.filter((issue) => issue.criticality === 'Critical' && issue.tab !== 'resolved');
    const criticalIds = criticals.map((issue) => issue.id);
    setSyncingIssueIds((current) => [...new Set([...current, ...criticalIds])]);
    const previousIssues = queryClient.getQueryData<Issue[]>(['issues']) ?? [];
    queryClient.setQueryData<Issue[]>(['issues'], (existing = []) =>
      existing.map((item) =>
        item.criticality === 'Critical' && item.tab !== 'resolved'
          ? { ...item, tab: 'wip', status: 'in_progress' }
          : item,
      ),
    );
    let updated = 0;
    try {
      for (const issue of criticals) {
        const response = await apiFetch(`/issues/${issue.id}`, {
          method: 'PATCH',
          signal: controller.signal,
          body: JSON.stringify({ status: 'in_progress' }),
        });
        if (response.ok) updated += 1;
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      queryClient.setQueryData<Issue[]>(['issues'], previousIssues);
      toast(errorMessage(error, 'Escalation failed'), 'err');
      return;
    } finally {
      escalateControllerRef.current = null;
      setSyncingIssueIds((current) => current.filter((id) => !criticalIds.includes(id)));
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
    <main className="bd-shell" id="app-main" tabIndex={-1}>
      <Topbar
        stats={stats}
        onLogout={logoutRequest}
        onOpenCommandPalette={() => setCommandOpen(true)}
        isAgentActive={agentActive}
      />
      <DemoTourBanner />
      {hasDataError ? (
        <div className="app-alert" role="alert">
          Some dashboard data failed to load. We keep retrying in the background.
        </div>
      ) : null}
      <div className="app">
        <Sidebar view={view} setView={setView} isAdmin={isAdmin} stats={stats} />
        <section className="main">
          {view === 'dashboard' ? (
            <DashboardOverview
              stats={stats}
              charts={charts}
              issues={issues}
              feed={feed}
              loadError={dashboardErrorText}
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
              loadError={issuesErrorText}
              syncingIssueIds={syncingIssueIds}
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
              loadError={sonarErrorText}
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
          {view === 'ai_queue' && isAdmin ? (
            <AiQueueView
              aiQueue={aiQueueQuery.data}
              loading={aiQueueQuery.isLoading}
              loadError={aiQueueErrorText}
              toast={toast}
              refresh={() => aiQueueQuery.refetch()}
            />
          ) : null}
          {view === 'grafana' ? (
            <GrafanaView />
          ) : null}
          {view === 'kibana' ? (
            <KibanaView />
          ) : null}
          {view === 'admin' && isAdmin ? (
            <AdminView
              users={usersQuery.data?.items || []}
              aiQueue={aiQueueQuery.data}
              loading={usersQuery.isLoading}
              queueLoading={aiQueueQuery.isLoading}
              loadError={adminErrorText}
              toast={toast}
              refresh={() => {
                usersQuery.refetch();
                aiQueueQuery.refetch();
              }}
            />
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
      {sonarReportModal ? (
        <SonarReportModal
          date={sonarReportModal.date}
          report={sonarReportModal.report}
          loading={sonarReportModal.loading}
          error={sonarReportModal.error}
          onClose={() => setSonarReportModal(null)}
        />
      ) : null}
      <SupportChatWidget />
      <ToastContainer toasts={toasts} />
    </main>
  );
}

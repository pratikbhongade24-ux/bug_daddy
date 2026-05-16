'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  Play,
  AlertTriangle,
  CheckCircle,
  Clock,
  ShieldAlert,
  RefreshCw,
  Search,
  History,
  Radar,
  Shield,
  Bug,
} from 'lucide-react';
import { apiJson } from '@/lib/api';
import type {
  SecurityScanSession,
  SecuritySessionsResponse,
  SecurityFinding,
  SecurityFindingsResponse,
  SecurityPhase,
  ToastItem,
} from '@/lib/types';

// ---------------------------------------------------------------------------
// Phase stepper config
// ---------------------------------------------------------------------------

const PHASES: { key: SecurityPhase; label: string; description: string }[] = [
  { key: 'inventory', label: 'AWS Inventory', description: 'Discovering EC2, Lambda, RDS assets...' },
  { key: 'package_extraction', label: 'Package Extraction', description: 'Extracting Lambda deployment packages...' },
  { key: 'cve_lookup', label: 'CVE Lookup', description: 'Querying NVD & OSV.dev for vulnerabilities...' },
  { key: 'report', label: 'Saving Report', description: 'Writing findings to the database...' },
];

function phaseIndex(phase: SecurityPhase | null): number {
  if (!phase) return -1;
  return PHASES.findIndex(p => p.key === phase);
}

function formatDateTime(value: string | null) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

function formatDate(value: string | null) {
  if (!value) return '—';
  return new Date(value).toLocaleDateString();
}

function formatPhaseLabel(phase: SecurityPhase | null) {
  if (!phase) return 'Waiting to start';
  return PHASES.find((item) => item.key === phase)?.label ?? phase;
}

function statusTone(status: SecurityScanSession['status']) {
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'danger';
  return 'warning';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ScanStepper({ session }: { session: SecurityScanSession }) {
  const current = phaseIndex(session.current_phase);
  const done = session.status === 'completed';
  const failed = session.status === 'failed';

  return (
    <div className="sec-stepper">
      {PHASES.map((phase, idx) => {
        const isActive = !done && !failed && idx === current;
        const isDone = done || idx < current;
        const isFailed = failed && idx === current;
        return (
          <div key={phase.key} className={clsx('sec-step', isActive && 'active', isDone && 'done', isFailed && 'failed')}>
            <div className="sec-step-icon">
              {isDone && !failed ? <CheckCircle size={14} /> : isActive ? <RefreshCw size={14} className="spin" /> : isFailed ? <AlertTriangle size={14} /> : <span className="step-num">{idx + 1}</span>}
            </div>
            <div className="sec-step-body">
              <div className="sec-step-label">{phase.label}</div>
              {isActive && session.phase_detail && (
                <div className="sec-step-detail">{session.phase_detail}</div>
              )}
              {isFailed && session.error_message && (
                <div className="sec-step-detail err">{session.error_message}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const cls = severity.toLowerCase();
  return <span className={clsx('badge', cls, 'sec-severity-badge')}>{severity}</span>;
}

function FindingsTable({
  findings,
  loading,
}: {
  findings: SecurityFinding[];
  loading: boolean;
}) {
  const [q, setQ] = useState('');
  const [svcFilter, setSvcFilter] = useState('');
  const [sevFilter, setSevFilter] = useState('');

  const services = useMemo(() => [...new Set(findings.map(f => f.service_name))].sort(), [findings]);

  const filtered = useMemo(() => {
    return findings.filter((finding) => {
      if (sevFilter && finding.severity !== sevFilter) return false;
      if (svcFilter && finding.service_name !== svcFilter) return false;
      if (q) {
        const loweredQuery = q.toLowerCase();
        return (
          finding.cve_id?.toLowerCase().includes(loweredQuery) ||
          (finding.description ?? '').toLowerCase().includes(loweredQuery) ||
          finding.service_name.toLowerCase().includes(loweredQuery)
        );
      }
      return true;
    });
  }, [findings, q, sevFilter, svcFilter]);

  if (loading) {
    return <div className="sec-empty">Loading findings...</div>;
  }

  if (findings.length === 0) {
    return (
      <div className="sec-empty">
        <ShieldAlert size={32} style={{ opacity: 0.3 }} />
        <p>No findings yet. Run a scan to discover CVEs across your AWS services.</p>
      </div>
    );
  }

  return (
    <div className="sec-findings" aria-busy={loading}>
      <div className="sec-findings-toolbar">
        <label className="sec-search">
          <Search size={16} />
          <input
            className="cmd-input sec-search-input"
            placeholder="Search CVE ID, service, description..."
            value={q}
            onChange={e => setQ(e.target.value)}
          />
        </label>
        <select className="filter-select" value={svcFilter} onChange={e => setSvcFilter(e.target.value)}>
          <option value="">All services</option>
          {services.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="filter-select" value={sevFilter} onChange={e => setSevFilter(e.target.value)}>
          <option value="">All severities</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
        <span className="sec-findings-count">{filtered.length} of {findings.length} findings</span>
      </div>
      <div className="tbl-wrap sec-findings-scroll">
        <table className="issues-tbl sec-findings-table">
          <caption className="sr-only">Security CVE findings table</caption>
          <colgroup>
            <col className="sec-col-severity" />
            <col className="sec-col-cve" />
            <col className="sec-col-service" />
            <col className="sec-col-component" />
            <col className="sec-col-description" />
            <col className="sec-col-last-seen" />
            <col className="sec-col-status" />
          </colgroup>
          <thead>
            <tr>
              <th>Severity</th>
              <th>CVE ID</th>
              <th>Service</th>
              <th>Component</th>
              <th>Description</th>
              <th>Last Seen</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(f => (
              <tr key={f.id}>
                <td><SeverityBadge severity={f.severity} /></td>
                <td className="mono sec-cve-id">{f.cve_id}</td>
                <td className="td-svc">{f.service_name}</td>
                <td className="td-svc sec-component">
                  {f.issue_type.replace('cve_', '')}
                </td>
                <td className="sec-finding-desc">
                  {f.description || '-'}
                </td>
                <td className="sec-date-cell">
                  {formatDate(f.last_seen)}
                </td>
                <td>
                  <span className={clsx('badge', f.status === 'open' ? 'medium' : 'low')}>
                    {f.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SessionHistoryRow({ session, onSelect, active }: {
  session: SecurityScanSession;
  onSelect: () => void;
  active: boolean;
}) {
  const isProcessing = session.status === 'processing';
  return (
    <button
      className={clsx('sec-history-row', active && 'active')}
      onClick={onSelect}
    >
      <span className={clsx('sec-hist-dot', session.status)} />
      <span className="sec-history-copy">
        <span className="sec-hist-date">{formatDateTime(session.started_at)}</span>
        {isProcessing ? (
          <span className="sec-hist-phase">{formatPhaseLabel(session.current_phase)}</span>
        ) : session.status === 'completed' ? (
          <span className="sec-hist-counts">
            <span>{session.critical_count} critical</span>
            <span>{session.high_count} high</span>
            <span>{session.findings_count} total</span>
          </span>
        ) : (
          <span className="sec-hist-failed">Scan failed</span>
        )}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main view
// ---------------------------------------------------------------------------

export function SecurityScannerView({ addToast }: { addToast: (msg: string, kind: ToastItem['kind']) => void }) {
  const queryClient = useQueryClient();
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [liveSession, setLiveSession] = useState<SecurityScanSession | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const toastRef = useRef(addToast);
  const toastedRef = useRef<string | null>(null); // tracks which session we already toasted for
  useEffect(() => { toastRef.current = addToast; }, [addToast]);

  // Fetch session list (history)
  const { data: sessionsData, refetch: refetchSessions } = useQuery<SecuritySessionsResponse>({
    queryKey: ['security-sessions'],
    queryFn: () => apiJson('/security/sessions'),
    refetchInterval: 30_000,
  });

  // Fetch findings
  const { data: findingsData, isLoading: findingsLoading, refetch: refetchFindings } = useQuery<SecurityFindingsResponse>({
    queryKey: ['security-findings'],
    queryFn: () => apiJson('/security/findings'),
    refetchInterval: 60_000,
  });

  // Start scan mutation
  const startScan = useMutation({
    mutationFn: () => apiJson<{ session_id: string }>('/security/invoke', { method: 'POST', body: JSON.stringify({}) }),
    onSuccess: (data) => {
      toastRef.current('Security scan started', 'ok');
      toastedRef.current = null; // reset so completion toast fires for the new session
      setActiveSessionId(data.session_id);
      refetchSessions();
    },
    onError: (err: Error) => {
      toastRef.current(err.message || 'Failed to start scan', 'err');
    },
  });

  // Poll active session for live progress
  const pollProgress = useCallback(async (sessionId: string) => {
    try {
      const data = await apiJson<SecurityScanSession>(`/security/sessions/${sessionId}/progress`);
      setLiveSession(data);
      if (data.status !== 'processing') {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        refetchSessions();
        refetchFindings();
        // Only toast once per session completion
        if (toastedRef.current !== sessionId) {
          toastedRef.current = sessionId;
          if (data.status === 'completed') {
            toastRef.current(`Scan complete — ${data.findings_count} CVE(s) found`, 'ok');
          } else {
            toastRef.current('Scan failed: ' + (data.error_message ?? 'unknown error'), 'err');
          }
        }
      }
    } catch {
      // keep polling
    }
  }, [refetchSessions, refetchFindings]); // addToast intentionally excluded — accessed via ref

  // Start polling when activeSessionId changes
  useEffect(() => {
    if (!activeSessionId) return;
    if (pollRef.current) clearInterval(pollRef.current);
    void pollProgress(activeSessionId);
    pollRef.current = setInterval(() => void pollProgress(activeSessionId), 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeSessionId, pollProgress]);

  // Auto-select the in-progress session if one exists on mount
  useEffect(() => {
    if (!sessionsData) return;
    const inProgress = sessionsData.sessions.find(s => s.status === 'processing');
    if (inProgress && !activeSessionId) {
      setActiveSessionId(inProgress.session_id);
      setLiveSession(inProgress);
    }
  }, [sessionsData, activeSessionId]);

  const sessions = sessionsData?.sessions ?? [];
  const inProgress = sessionsData?.in_progress ?? false;
  const findings = findingsData?.items ?? [];
  const latestSession = sessions[0] ?? null;
  const criticalFindings = findings.filter((item) => item.severity === 'CRITICAL').length;
  const activeServices = new Set(findings.map((item) => item.service_name)).size;

  // The session to display in stepper — live data takes priority
  const displaySession = liveSession && liveSession.session_id === activeSessionId
    ? liveSession
    : sessions.find(s => s.session_id === activeSessionId) ?? latestSession;

  return (
    <div className="sec-scanner-view">
      <section className="sec-hero">
        <div className="sec-hero-copy">
          <span className="sec-eyebrow">
            <Radar size={14} />
            Cloud exposure audit
          </span>
          <h1 className="sec-hero-title">Security scanner command center</h1>
          <p className="sec-hero-text">
            Launch on-demand scans, monitor the live pipeline, and review findings in one scrollable workspace.
          </p>
          <div className="sec-hero-meta">
            <span className={clsx('sec-status-chip', displaySession && statusTone(displaySession.status))}>
              {displaySession ? (displaySession.status === 'processing' ? 'Scan running' : displaySession.status) : 'Ready to scan'}
            </span>
            <span className="sec-hero-note">
              {displaySession
                ? `Last activity ${formatDateTime(displaySession.started_at)}`
                : 'No security scans have been recorded yet'}
            </span>
          </div>
        </div>
        <div className="sec-hero-actions">
          <button
            className={clsx('btn pri', inProgress && 'disabled')}
            disabled={inProgress || startScan.isPending}
            onClick={() => startScan.mutate()}
          >
            {inProgress || startScan.isPending ? (
              <><RefreshCw size={14} className="spin" /> Scanning...</>
            ) : (
              <><Play size={14} /> Run Scan</>
            )}
          </button>
          <p className="sec-hero-help">
            {inProgress ? 'A scan is already in progress. Live updates refresh automatically.' : 'Kick off a fresh inventory and CVE sweep across connected AWS assets.'}
          </p>
        </div>
      </section>

      <section className="sec-summary-grid">
        <article className="sec-stat-card">
          <div className="sec-stat-icon critical">
            <ShieldAlert size={18} />
          </div>
          <div className="sec-stat-copy">
            <span className="sec-stat-label">Critical findings</span>
            <strong className="sec-stat-value">{criticalFindings}</strong>
            <span className="sec-stat-note">Open issues needing immediate review</span>
          </div>
        </article>
        <article className="sec-stat-card">
          <div className="sec-stat-icon accent">
            <Bug size={18} />
          </div>
          <div className="sec-stat-copy">
            <span className="sec-stat-label">Total findings</span>
            <strong className="sec-stat-value">{findings.length}</strong>
            <span className="sec-stat-note">Results currently stored in the platform</span>
          </div>
        </article>
        <article className="sec-stat-card">
          <div className="sec-stat-icon success">
            <Shield size={18} />
          </div>
          <div className="sec-stat-copy">
            <span className="sec-stat-label">Services covered</span>
            <strong className="sec-stat-value">{activeServices}</strong>
            <span className="sec-stat-note">Unique AWS services represented in findings</span>
          </div>
        </article>
      </section>

      <div className="sec-body">
        <aside className="sec-sidebar">
          <div className="sec-sidebar-head">
            <div>
              <div className="sec-sidebar-title">Scan history</div>
              <p className="sec-sidebar-subtitle">Select a run to inspect its status and outcome.</p>
            </div>
            <History size={16} />
          </div>
          <div className="sec-history-list">
            {sessions.length === 0 ? (
              <div className="sec-empty-small">No scans yet</div>
            ) : (
              sessions.map(s => (
                <SessionHistoryRow
                  key={s.session_id}
                  session={s}
                  active={s.session_id === displaySession?.session_id}
                  onSelect={() => {
                    setActiveSessionId(s.session_id);
                    setLiveSession(null);
                  }}
                />
              ))
            )}
          </div>
        </aside>

        <div className="sec-detail">
          <section className="sec-progress-card">
            <div className="sec-progress-header">
              <div>
                <div className="sec-card-label">Active session</div>
                <h2 className="sec-card-title">
                  {displaySession
                    ? displaySession.status === 'processing'
                      ? 'Scan in progress'
                      : displaySession.status === 'completed'
                        ? 'Latest scan complete'
                        : 'Latest scan failed'
                    : 'No scan selected'}
                </h2>
              </div>
              {displaySession ? (
                <span className={clsx('sec-status-chip', statusTone(displaySession.status))}>
                  <Clock size={14} />
                  {displaySession.status}
                </span>
              ) : null}
            </div>

            {displaySession ? (
              <>
                <div className="sec-session-meta">
                  <div className="sec-session-meta-item">
                    <span className="sec-meta-label">Started</span>
                    <span className="sec-meta-value">{formatDateTime(displaySession.started_at)}</span>
                  </div>
                  <div className="sec-session-meta-item">
                    <span className="sec-meta-label">Current phase</span>
                    <span className="sec-meta-value">{formatPhaseLabel(displaySession.current_phase)}</span>
                  </div>
                  <div className="sec-session-meta-item">
                    <span className="sec-meta-label">Triggered by</span>
                    <span className="sec-meta-value">{displaySession.triggered_by || 'System'}</span>
                  </div>
                </div>
                <ScanStepper session={displaySession} />
                {displaySession.phase_detail ? (
                  <div className="sec-session-note">{displaySession.phase_detail}</div>
                ) : null}
                {displaySession.status === 'completed' ? (
                  <div className="sec-summary-pills">
                    <span className="sec-pill critical">{displaySession.critical_count} Critical</span>
                    <span className="sec-pill high">{displaySession.high_count} High</span>
                    <span className="sec-pill total">{displaySession.findings_count} Total</span>
                  </div>
                ) : null}
                {displaySession.status === 'failed' && displaySession.error_message ? (
                  <div className="sec-session-error">
                    <AlertTriangle size={16} />
                    <span>{displaySession.error_message}</span>
                  </div>
                ) : null}
              </>
            ) : (
              <div className="sec-empty left">
                <ShieldAlert size={32} style={{ opacity: 0.3 }} />
                <p>Start a scan to populate live progress and historical results.</p>
              </div>
            )}
          </section>

          <section className="sec-findings-section">
            <div className="sec-section-title">
              <div>
                <div className="sec-card-label">Findings explorer</div>
                <h2 className="sec-card-title">CVE findings</h2>
              </div>
              {findings.length > 0 && (
                <span className="ni-badge r">{findings.length}</span>
              )}
            </div>
            <FindingsTable findings={findings} loading={findingsLoading} />
          </section>
        </div>
      </div>
    </div>
  );
}

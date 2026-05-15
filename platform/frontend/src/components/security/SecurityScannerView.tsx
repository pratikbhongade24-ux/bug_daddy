'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { ScanSearch, Play, AlertTriangle, CheckCircle, Clock, ShieldAlert, RefreshCw } from 'lucide-react';
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
  return <span className={clsx('badge', cls)}>{severity}</span>;
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

  const services = [...new Set(findings.map(f => f.service_name))].sort();

  const filtered = findings.filter(f => {
    if (sevFilter && f.severity !== sevFilter) return false;
    if (svcFilter && f.service_name !== svcFilter) return false;
    if (q) {
      const lq = q.toLowerCase();
      return (
        f.cve_id?.toLowerCase().includes(lq) ||
        (f.description ?? '').toLowerCase().includes(lq) ||
        f.service_name.toLowerCase().includes(lq)
      );
    }
    return true;
  });

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
    <div className="sec-findings">
      <div className="sec-findings-toolbar">
        <input
          className="cmd-input"
          placeholder="Search CVE ID, service, description..."
          value={q}
          onChange={e => setQ(e.target.value)}
          style={{ flex: 1, maxWidth: 320 }}
        />
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
        <span className="sec-findings-count">{filtered.length} / {findings.length}</span>
      </div>
      <div className="tbl-wrap">
        <table className="issues-tbl">
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
                <td className="mono" style={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}>{f.cve_id}</td>
                <td className="td-svc">{f.service_name}</td>
                <td className="td-svc" style={{ color: 'var(--t2)', fontSize: '0.75rem' }}>
                  {f.issue_type.replace('cve_', '')}
                </td>
                <td className="td-desc" title={f.description ?? ''}>
                  {(f.description ?? '').slice(0, 120)}{(f.description ?? '').length > 120 ? '…' : ''}
                </td>
                <td style={{ whiteSpace: 'nowrap', fontSize: '0.75rem', color: 'var(--t2)' }}>
                  {f.last_seen ? new Date(f.last_seen).toLocaleDateString() : '—'}
                </td>
                <td>
                  <span className={clsx('badge', f.status === 'open' ? 'medium' : 'low')} style={{ fontSize: '0.65rem' }}>
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
      <span className="sec-hist-date">
        {session.started_at ? new Date(session.started_at).toLocaleString() : '—'}
      </span>
      {isProcessing ? (
        <span className="sec-hist-phase">{session.current_phase ?? 'starting'}</span>
      ) : session.status === 'completed' ? (
        <span className="sec-hist-counts">
          <span style={{ color: 'var(--c2)' }}>{session.critical_count}C</span>
          {' / '}
          <span style={{ color: 'var(--c4)' }}>{session.high_count}H</span>
          {' · '}
          {session.findings_count} total
        </span>
      ) : (
        <span style={{ color: 'var(--c2)', fontSize: '0.72rem' }}>failed</span>
      )}
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

  // The session to display in stepper — live data takes priority
  const displaySession = liveSession && liveSession.session_id === activeSessionId
    ? liveSession
    : sessions.find(s => s.session_id === activeSessionId) ?? null;

  return (
    <div className="sec-scanner-view">
      {/* Header */}
      <div className="panel-header">
        <div className="ph-left">
          <ScanSearch size={18} style={{ color: 'var(--c6)' }} />
          <span className="ph-title">Security Scanner</span>
          <span className="ph-sub">CVE detection across your AWS infrastructure</span>
        </div>
        <div className="ph-right">
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
        </div>
      </div>

      <div className="sec-body">
        {/* Left: session history */}
        <div className="sec-sidebar">
          <div className="sec-sidebar-title">Scan History</div>
          {sessions.length === 0 ? (
            <div className="sec-empty-small">No scans yet</div>
          ) : (
            sessions.map(s => (
              <SessionHistoryRow
                key={s.session_id}
                session={s}
                active={s.session_id === activeSessionId}
                onSelect={() => {
                  setActiveSessionId(s.session_id);
                  setLiveSession(null);
                }}
              />
            ))
          )}
        </div>

        {/* Right: detail panel */}
        <div className="sec-detail">
          {/* Live progress stepper */}
          {displaySession && (displaySession.status === 'processing' || activeSessionId === displaySession.session_id) && (
            <div className="sec-progress-card">
              <div className="sec-progress-header">
                <Clock size={14} />
                <span>
                  {displaySession.status === 'processing'
                    ? 'Scan in progress'
                    : displaySession.status === 'completed'
                    ? `Completed — ${displaySession.findings_count} finding(s)`
                    : 'Scan failed'}
                </span>
                {displaySession.triggered_by && (
                  <span style={{ marginLeft: 'auto', color: 'var(--t3)', fontSize: '0.72rem' }}>
                    by {displaySession.triggered_by}
                  </span>
                )}
              </div>
              <ScanStepper session={displaySession} />
              {displaySession.status === 'completed' && (
                <div className="sec-summary-pills">
                  <span className="sec-pill critical">{displaySession.critical_count} Critical</span>
                  <span className="sec-pill high">{displaySession.high_count} High</span>
                  <span className="sec-pill total">{displaySession.findings_count} Total</span>
                </div>
              )}
            </div>
          )}

          {/* Findings table */}
          <div className="sec-findings-section">
            <div className="sec-section-title">
              CVE Findings
              {findings.length > 0 && (
                <span className="ni-badge r" style={{ marginLeft: 8 }}>{findings.length}</span>
              )}
            </div>
            <FindingsTable findings={findings} loading={findingsLoading} />
          </div>
        </div>
      </div>
    </div>
  );
}

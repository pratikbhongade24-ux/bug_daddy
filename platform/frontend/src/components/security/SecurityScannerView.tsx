'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  AlertTriangle,
  Boxes,
  Bug,
  CheckCircle,
  Clock,
  Database,
  GitBranch,
  History,
  Network,
  PackageSearch,
  Play,
  Radar,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
} from 'lucide-react';
import { apiJson } from '@/lib/api';
import type {
  SecurityFinding,
  SecurityFindingsResponse,
  SecurityPhase,
  SecurityScanSession,
  SecuritySessionsResponse,
  SecurityToolResult,
  ToastItem,
} from '@/lib/types';

const PHASES: { key: SecurityPhase; label: string; description: string }[] = [
  { key: 'inventory', label: 'Inventory', description: 'AWS asset and graph discovery' },
  { key: 'package_extraction', label: 'Packages', description: 'Lambda dependency extraction' },
  { key: 'cve_lookup', label: 'Vulnerabilities', description: 'OSV, NVD, and Inspector checks' },
  { key: 'report', label: 'Report', description: 'Deduping and saving findings' },
];

const severityOrder: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };

function phaseIndex(phase: SecurityPhase | null): number {
  if (!phase) return -1;
  return PHASES.findIndex(p => p.key === phase);
}

function formatDateTime(value: string | null) {
  if (!value) return '-';
  return new Date(value).toLocaleString();
}

function formatDate(value: string | null) {
  if (!value) return '-';
  return new Date(value).toLocaleDateString();
}

function formatPhaseLabel(phase: SecurityPhase | null) {
  if (!phase) return 'Waiting';
  return PHASES.find((item) => item.key === phase)?.label ?? phase;
}

function statusTone(status: SecurityScanSession['status']) {
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'danger';
  return 'warning';
}

function toolLabel(tool: string) {
  const key = tool.toLowerCase();
  if (key === 'osv') return 'OSV';
  if (key === 'nvd') return 'NVD';
  if (key.includes('inspector')) return 'AWS Inspector';
  if (key.includes('inventory')) return 'AWS Inventory';
  if (key.includes('lambda_package')) return 'Lambda Packages';
  if (key.includes('osv_nvd')) return 'OSV / NVD';
  return tool.replaceAll('_', ' ').toUpperCase();
}

function SeverityBadge({ severity }: { severity: string }) {
  return <span className={clsx('badge', severity.toLowerCase(), 'sec-severity-badge')}>{severity}</span>;
}

function ToolIcon({ tool }: { tool: string }) {
  const key = tool.toLowerCase();
  if (key.includes('inventory')) return <Network size={16} />;
  if (key.includes('lambda_package')) return <PackageSearch size={16} />;
  if (key.includes('inspector')) return <ShieldAlert size={16} />;
  if (key.includes('osv') || key.includes('nvd')) return <Bug size={16} />;
  return <Shield size={16} />;
}

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
              <div className="sec-step-detail">{isActive && session.phase_detail ? session.phase_detail : phase.description}</div>
              {isFailed && session.error_message ? <div className="sec-step-detail err">{session.error_message}</div> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SessionHistoryRow({ session, onSelect, active }: {
  session: SecurityScanSession;
  onSelect: () => void;
  active: boolean;
}) {
  return (
    <button className={clsx('sec-history-row', active && 'active')} onClick={onSelect}>
      <span className={clsx('sec-hist-dot', session.status)} />
      <span className="sec-history-copy">
        <span className="sec-hist-date">{formatDateTime(session.started_at)}</span>
        {session.status === 'processing' ? (
          <span className="sec-hist-phase">{formatPhaseLabel(session.current_phase)}</span>
        ) : session.status === 'completed' ? (
          <span className="sec-hist-counts">
            <span>{session.assets_count ?? 0} assets</span>
            <span>{session.findings_count} findings</span>
            <span>{session.critical_count} critical</span>
          </span>
        ) : (
          <span className="sec-hist-failed">Scan failed</span>
        )}
      </span>
    </button>
  );
}

function ToolBreakdown({ tools, findings }: { tools: SecurityToolResult[]; findings: SecurityFinding[] }) {
  const findingRows = useMemo(() => {
    const grouped = new Map<string, SecurityToolResult>();
    findings.forEach((finding) => {
      const key = finding.tool_name || finding.source || 'unknown';
      const row = grouped.get(key) ?? {
        tool: key,
        category: 'vulnerability_source',
        status: 'ok',
        findings: 0,
        critical: 0,
        high: 0,
      };
      row.findings = (row.findings ?? 0) + 1;
      row.critical = (row.critical ?? 0) + (finding.severity === 'CRITICAL' ? 1 : 0);
      row.high = (row.high ?? 0) + (finding.severity === 'HIGH' ? 1 : 0);
      grouped.set(key, row);
    });
    return [...grouped.values()];
  }, [findings]);

  const rows = [...tools, ...findingRows].filter((row, idx, arr) => (
    arr.findIndex((candidate) => candidate.tool === row.tool && candidate.category === row.category) === idx
  ));

  if (rows.length === 0) {
    return <div className="sec-empty compact">No tool output has been recorded yet.</div>;
  }

  return (
    <div className="sec-tools-grid">
      {rows.map((tool) => (
        <article key={`${tool.tool}-${tool.category}`} className={clsx('sec-tool-card', tool.status === 'error' && 'error')}>
          <div className="sec-tool-head">
            <span className="sec-tool-icon"><ToolIcon tool={tool.tool} /></span>
            <div>
              <h3>{toolLabel(tool.tool)}</h3>
              <p>{tool.category?.replaceAll('_', ' ') || 'scanner tool'}</p>
            </div>
            <span className={clsx('sec-mini-status', tool.status === 'error' ? 'danger' : 'success')}>
              {tool.status}
            </span>
          </div>
          <div className="sec-tool-metrics">
            <span><strong>{tool.assets ?? 0}</strong> assets</span>
            <span><strong>{tool.edges ?? 0}</strong> edges</span>
            <span><strong>{tool.packages ?? 0}</strong> packages</span>
            <span><strong>{tool.findings ?? 0}</strong> findings</span>
          </div>
          {tool.message ? <div className="sec-tool-message">{tool.message}</div> : null}
        </article>
      ))}
    </div>
  );
}

function DependencyPreview({ session }: { session: SecurityScanSession | null }) {
  const edges = session?.report?.dependencies ?? [];
  if (edges.length === 0) {
    return <div className="sec-empty compact">No dependency edges available for this run yet.</div>;
  }
  return (
    <div className="sec-edge-list">
      {edges.slice(0, 8).map((edge, idx) => (
        <div className="sec-edge-row" key={`${edge.source}-${edge.target}-${idx}`}>
          <span className="sec-edge-node">{edge.source}</span>
          <span className="sec-edge-rel">{edge.relationship}</span>
          <span className="sec-edge-node target">{edge.target}</span>
        </div>
      ))}
      {edges.length > 8 ? <div className="sec-edge-more">{edges.length - 8} more edges captured in the scan report</div> : null}
    </div>
  );
}

function FindingsTable({ findings, loading }: { findings: SecurityFinding[]; loading: boolean }) {
  const [q, setQ] = useState('');
  const [svcFilter, setSvcFilter] = useState('');
  const [sevFilter, setSevFilter] = useState('');
  const [toolFilter, setToolFilter] = useState('');

  const services = useMemo(() => [...new Set(findings.map(f => f.service_name))].sort(), [findings]);
  const tools = useMemo(() => [...new Set(findings.map(f => f.tool_name || f.source || 'unknown'))].sort(), [findings]);

  const filtered = useMemo(() => {
    return findings
      .filter((finding) => {
        if (sevFilter && finding.severity !== sevFilter) return false;
        if (svcFilter && finding.service_name !== svcFilter) return false;
        if (toolFilter && (finding.tool_name || finding.source) !== toolFilter) return false;
        if (!q) return true;
        const loweredQuery = q.toLowerCase();
        return (
          finding.cve_id?.toLowerCase().includes(loweredQuery) ||
          (finding.description ?? '').toLowerCase().includes(loweredQuery) ||
          finding.service_name.toLowerCase().includes(loweredQuery) ||
          finding.component?.toLowerCase().includes(loweredQuery) ||
          finding.asset_id?.toLowerCase().includes(loweredQuery)
        );
      })
      .sort((a, b) => (severityOrder[a.severity] ?? 4) - (severityOrder[b.severity] ?? 4));
  }, [findings, q, sevFilter, svcFilter, toolFilter]);

  if (loading) return <div className="sec-empty">Loading findings...</div>;
  if (findings.length === 0) {
    return (
      <div className="sec-empty">
        <ShieldAlert size={32} style={{ opacity: 0.3 }} />
        <p>No findings yet. Run a scan to discover vulnerabilities across connected AWS assets.</p>
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
            placeholder="Search CVE, service, asset, component..."
            value={q}
            onChange={e => setQ(e.target.value)}
          />
        </label>
        <select className="filter-select" value={toolFilter} onChange={e => setToolFilter(e.target.value)}>
          <option value="">All tools</option>
          {tools.map(tool => <option key={tool} value={tool}>{toolLabel(tool)}</option>)}
        </select>
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
        <span className="sec-findings-count">{filtered.length} of {findings.length}</span>
      </div>
      <div className="tbl-wrap sec-findings-scroll">
        <table className="issues-tbl sec-findings-table">
          <caption className="sr-only">Security findings table</caption>
          <thead>
            <tr>
              <th>Severity</th>
              <th>Tool</th>
              <th>CVE</th>
              <th>Service / Asset</th>
              <th>Component</th>
              <th>Fix</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(f => (
              <tr key={f.id}>
                <td><SeverityBadge severity={f.severity} /></td>
                <td className="sec-tool-cell">{toolLabel(f.tool_name || f.source)}</td>
                <td className="mono sec-cve-id">{f.cve_id}</td>
                <td className="td-svc">
                  <div className="sec-main-cell">{f.service_name}</div>
                  <div className="sec-sub-cell">{f.asset_type || 'asset'} {f.asset_id || ''}</div>
                </td>
                <td>
                  <div className="sec-main-cell">{f.component || '-'}</div>
                  <div className="sec-sub-cell">{f.affected_version || f.component_type || '-'}</div>
                </td>
                <td className="sec-sub-cell">{f.fixed_version || '-'}</td>
                <td>
                  <span className={clsx('badge', f.status === 'open' ? 'medium' : 'low')}>
                    {f.status}
                  </span>
                  <div className="sec-sub-cell">{formatDate(f.last_seen)}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function SecurityScannerView({ addToast }: { addToast: (msg: string, kind: ToastItem['kind']) => void }) {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [liveSession, setLiveSession] = useState<SecurityScanSession | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const toastRef = useRef(addToast);
  const toastedRef = useRef<string | null>(null);
  useEffect(() => { toastRef.current = addToast; }, [addToast]);

  const { data: sessionsData, refetch: refetchSessions } = useQuery<SecuritySessionsResponse>({
    queryKey: ['security-sessions'],
    queryFn: () => apiJson('/security/sessions'),
    refetchInterval: 30_000,
  });

  const { data: findingsData, isLoading: findingsLoading, refetch: refetchFindings } = useQuery<SecurityFindingsResponse>({
    queryKey: ['security-findings'],
    queryFn: () => apiJson('/security/findings'),
    refetchInterval: 60_000,
  });

  const startScan = useMutation({
    mutationFn: () => apiJson<{ session_id: string }>('/security/invoke', { method: 'POST', body: JSON.stringify({}) }),
    onSuccess: (data) => {
      toastRef.current('Security scan started', 'ok');
      toastedRef.current = null;
      setActiveSessionId(data.session_id);
      refetchSessions();
    },
    onError: (err: Error) => {
      toastRef.current(err.message || 'Failed to start scan', 'err');
    },
  });

  const pollProgress = useCallback(async (sessionId: string) => {
    try {
      const data = await apiJson<SecurityScanSession>(`/security/sessions/${sessionId}/progress`);
      setLiveSession(data);
      if (data.status !== 'processing') {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        refetchSessions();
        refetchFindings();
        if (toastedRef.current !== sessionId) {
          toastedRef.current = sessionId;
          if (data.status === 'completed') {
            toastRef.current(`Scan complete - ${data.findings_count} unique finding(s)`, 'ok');
          } else {
            toastRef.current('Scan failed: ' + (data.error_message ?? 'unknown error'), 'err');
          }
        }
      }
    } catch {
      // Keep polling; transient auth/network errors should not collapse the live view.
    }
  }, [refetchSessions, refetchFindings]);

  useEffect(() => {
    if (!activeSessionId) return;
    if (pollRef.current) clearInterval(pollRef.current);
    void pollProgress(activeSessionId);
    pollRef.current = setInterval(() => void pollProgress(activeSessionId), 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeSessionId, pollProgress]);

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
  const displaySession = liveSession && liveSession.session_id === activeSessionId
    ? liveSession
    : sessions.find(s => s.session_id === activeSessionId) ?? latestSession;

  const criticalFindings = findings.filter((item) => item.severity === 'CRITICAL' && item.status === 'open').length;
  const activeServices = new Set(findings.map((item) => item.service_name)).size;
  const tools = displaySession?.tools ?? [];

  return (
    <div className="sec-scanner-view">
      <section className="sec-hero">
        <div className="sec-hero-copy">
          <span className="sec-eyebrow"><Radar size={14} /> Cloud dependency monitor</span>
          <h1 className="sec-hero-title">Security scanner command center</h1>
          <p className="sec-hero-text">
            Crawl AWS assets, map dependency edges, dedupe vulnerability sources, and review findings by tool.
          </p>
          <div className="sec-hero-meta">
            <span className={clsx('sec-status-chip', displaySession && statusTone(displaySession.status))}>
              {displaySession ? (displaySession.status === 'processing' ? 'Scan running' : displaySession.status) : 'Ready to scan'}
            </span>
            <span className="sec-hero-note">
              {displaySession ? `Last activity ${formatDateTime(displaySession.started_at)}` : 'No security scans recorded yet'}
            </span>
          </div>
        </div>
        <div className="sec-hero-actions">
          <button
            className={clsx('btn pri', inProgress && 'disabled')}
            disabled={inProgress || startScan.isPending}
            onClick={() => startScan.mutate()}
          >
            {inProgress || startScan.isPending ? <><RefreshCw size={14} className="spin" /> Scanning...</> : <><Play size={14} /> Run Scan</>}
          </button>
          <p className="sec-hero-help">
            {inProgress ? 'A scan is in progress. Live updates refresh automatically.' : 'Runs inventory, graph discovery, package extraction, OSV/NVD, Inspector, and dedupe.'}
          </p>
        </div>
      </section>

      <section className="sec-summary-grid wide">
        <article className="sec-stat-card">
          <div className="sec-stat-icon critical"><ShieldAlert size={18} /></div>
          <div className="sec-stat-copy">
            <span className="sec-stat-label">Open critical</span>
            <strong className="sec-stat-value">{criticalFindings}</strong>
            <span className="sec-stat-note">Deduped by vulnerability, asset, and component</span>
          </div>
        </article>
        <article className="sec-stat-card">
          <div className="sec-stat-icon accent"><Database size={18} /></div>
          <div className="sec-stat-copy">
            <span className="sec-stat-label">Assets scanned</span>
            <strong className="sec-stat-value">{displaySession?.assets_count ?? 0}</strong>
            <span className="sec-stat-note">{activeServices} services currently represented in findings</span>
          </div>
        </article>
        <article className="sec-stat-card">
          <div className="sec-stat-icon success"><GitBranch size={18} /></div>
          <div className="sec-stat-copy">
            <span className="sec-stat-label">Dependency edges</span>
            <strong className="sec-stat-value">{displaySession?.dependencies_count ?? 0}</strong>
            <span className="sec-stat-note">API, event, load balancer, ECS, and workflow links</span>
          </div>
        </article>
        <article className="sec-stat-card">
          <div className="sec-stat-icon neutral"><Boxes size={18} /></div>
          <div className="sec-stat-copy">
            <span className="sec-stat-label">Unique findings</span>
            <strong className="sec-stat-value">{findings.length}</strong>
            <span className="sec-stat-note">Grouped across OSV, NVD, Inspector, and package extraction</span>
          </div>
        </article>
      </section>

      <div className="sec-body">
        <aside className="sec-sidebar">
          <div className="sec-sidebar-head">
            <div>
              <div className="sec-sidebar-title">Scan history</div>
              <p className="sec-sidebar-subtitle">Select a run to inspect progress, tools, and graph output.</p>
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
                  {displaySession ? displaySession.status === 'processing' ? 'Scan in progress' : displaySession.status === 'completed' ? 'Scan complete' : 'Scan failed' : 'No scan selected'}
                </h2>
              </div>
              {displaySession ? (
                <span className={clsx('sec-status-chip', statusTone(displaySession.status))}>
                  <Clock size={14} /> {displaySession.status}
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
                {displaySession.phase_detail ? <div className="sec-session-note">{displaySession.phase_detail}</div> : null}
                {displaySession.status === 'failed' && displaySession.error_message ? (
                  <div className="sec-session-error"><AlertTriangle size={16} /><span>{displaySession.error_message}</span></div>
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
                <div className="sec-card-label">Tool results</div>
                <h2 className="sec-card-title">Source breakdown</h2>
              </div>
              {tools.length > 0 ? <span className="ni-badge r">{tools.length}</span> : null}
            </div>
            <ToolBreakdown tools={tools} findings={findings} />
          </section>

          <section className="sec-findings-section">
            <div className="sec-section-title">
              <div>
                <div className="sec-card-label">Dependency graph</div>
                <h2 className="sec-card-title">Runtime edges</h2>
              </div>
              {displaySession?.dependencies_count ? <span className="ni-badge r">{displaySession.dependencies_count}</span> : null}
            </div>
            <DependencyPreview session={displaySession ?? null} />
          </section>

          <section className="sec-findings-section">
            <div className="sec-section-title">
              <div>
                <div className="sec-card-label">Findings explorer</div>
                <h2 className="sec-card-title">Deduped vulnerabilities</h2>
              </div>
              {findings.length > 0 ? <span className="ni-badge r">{findings.length}</span> : null}
            </div>
            <FindingsTable findings={findings} loading={findingsLoading} />
          </section>
        </div>
      </div>
    </div>
  );
}

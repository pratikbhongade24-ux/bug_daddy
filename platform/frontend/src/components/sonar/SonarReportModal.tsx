'use client';

import React, { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  ShieldCheck,
  Bug,
  ShieldAlert,
  AlertTriangle,
  Code,
  ChevronDown,
  ChevronRight,
  Search,
  FileCode,
  Loader2,
} from 'lucide-react';

// ── Types ────────────────────────────────────────────────────────────────────

interface SonarFlow {
  locations?: { component?: string; msg?: string; textRange?: { startLine?: number } }[];
}

export interface SonarIssue {
  key: string;
  component: string;
  type: 'BUG' | 'VULNERABILITY' | 'CODE_SMELL' | string;
  severity: 'BLOCKER' | 'CRITICAL' | 'MAJOR' | 'MINOR' | 'INFO' | string;
  message: string;
  rule: string;
  line?: number;
  creationDate?: string;
  flows?: SonarFlow[];
}

export interface SonarReport {
  date?: string;
  issues?: SonarIssue[];
}

interface SonarReportModalProps {
  date: string;
  report: SonarReport | null;
  loading: boolean;
  error?: string;
  onClose: () => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const SEVERITY_ORDER: Record<string, number> = { BLOCKER: 0, CRITICAL: 1, MAJOR: 2, MINOR: 3, INFO: 4 };

function severityClass(severity: string) {
  switch (severity) {
    case 'BLOCKER': return 'snr-sev blocker';
    case 'CRITICAL': return 'snr-sev critical';
    case 'MAJOR': return 'snr-sev major';
    case 'MINOR': return 'snr-sev minor';
    default: return 'snr-sev info';
  }
}

function typeIcon(type: string) {
  switch (type) {
    case 'BUG': return <Bug size={13} />;
    case 'VULNERABILITY': return <ShieldAlert size={13} />;
    default: return <Code size={13} />;
  }
}

function typeClass(type: string) {
  switch (type) {
    case 'BUG': return 'snr-type bug';
    case 'VULNERABILITY': return 'snr-type vuln';
    default: return 'snr-type smell';
  }
}

function shortComponent(component: string) {
  const path = component.includes(':') ? component.split(':')[1] : component;
  const parts = path.split('/');
  return parts.length > 2 ? '…/' + parts.slice(-2).join('/') : path;
}

// ── Summary bar ──────────────────────────────────────────────────────────────

function SummaryBar({ issues }: { issues: SonarIssue[] }) {
  const bugs = issues.filter((i) => i.type === 'BUG').length;
  const vulns = issues.filter((i) => i.type === 'VULNERABILITY').length;
  const smells = issues.filter((i) => i.type === 'CODE_SMELL').length;
  const blocker = issues.filter((i) => i.severity === 'BLOCKER').length;
  const critical = issues.filter((i) => i.severity === 'CRITICAL').length;
  const major = issues.filter((i) => i.severity === 'MAJOR').length;
  const minor = issues.filter((i) => i.severity === 'MINOR').length;

  return (
    <div className="snr-summary">
      <div className="snr-summary-group">
        <div className="snr-stat-card bug">
          <Bug size={16} />
          <span className="snr-stat-num">{bugs}</span>
          <span className="snr-stat-lbl">Bugs</span>
        </div>
        <div className="snr-stat-card vuln">
          <ShieldAlert size={16} />
          <span className="snr-stat-num">{vulns}</span>
          <span className="snr-stat-lbl">Vulnerabilities</span>
        </div>
        <div className="snr-stat-card smell">
          <Code size={16} />
          <span className="snr-stat-num">{smells}</span>
          <span className="snr-stat-lbl">Code Smells</span>
        </div>
      </div>
      <div className="snr-sev-strip">
        {blocker > 0 && <span className="snr-sev blocker">{blocker} Blocker</span>}
        {critical > 0 && <span className="snr-sev critical">{critical} Critical</span>}
        {major > 0 && <span className="snr-sev major">{major} Major</span>}
        {minor > 0 && <span className="snr-sev minor">{minor} Minor</span>}
      </div>
    </div>
  );
}

// ── Issue row ─────────────────────────────────────────────────────────────────

function IssueRow({ issue }: { issue: SonarIssue }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr
        className={`snr-row${expanded ? ' expanded' : ''}`}
        onClick={() => setExpanded((prev) => !prev)}
        style={{ cursor: 'pointer' }}
      >
        <td className="snr-td-sev">
          <span className={severityClass(issue.severity)}>{issue.severity}</span>
        </td>
        <td className="snr-td-type">
          <span className={typeClass(issue.type)}>
            {typeIcon(issue.type)} {issue.type.replace('_', ' ')}
          </span>
        </td>
        <td className="snr-td-msg" title={issue.message}>
          <span className="snr-msg-text">{issue.message}</span>
        </td>
        <td className="snr-td-file" title={issue.component}>
          <span className="snr-file-path">
            <FileCode size={11} style={{ flexShrink: 0 }} />
            {shortComponent(issue.component)}
            {issue.line ? <em>:{issue.line}</em> : null}
          </span>
        </td>
        <td className="snr-td-rule" title={issue.rule}>
          <code className="snr-rule">{issue.rule}</code>
        </td>
        <td className="snr-td-expand">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </td>
      </tr>
      {expanded && (
        <tr className="snr-detail-row">
          <td colSpan={6}>
            <div className="snr-detail-body">
              <div className="snr-detail-grid">
                <div>
                  <div className="snr-detail-label">Full Component</div>
                  <code className="snr-detail-val">{issue.component}{issue.line ? `:${issue.line}` : ''}</code>
                </div>
                <div>
                  <div className="snr-detail-label">Rule</div>
                  <code className="snr-detail-val">{issue.rule}</code>
                </div>
                {issue.creationDate && (
                  <div>
                    <div className="snr-detail-label">Found On</div>
                    <span className="snr-detail-val">{new Date(issue.creationDate).toLocaleDateString()}</span>
                  </div>
                )}
              </div>
              <div className="snr-detail-label" style={{ marginTop: '0.75rem' }}>Message</div>
              <div className="snr-detail-message">{issue.message}</div>
              {issue.flows && issue.flows.length > 0 && (
                <>
                  <div className="snr-detail-label" style={{ marginTop: '0.75rem' }}>Data Flows</div>
                  <div className="snr-flows">
                    {issue.flows.slice(0, 3).map((flow, fi) =>
                      (flow.locations || []).slice(0, 5).map((loc, li) => (
                        <div key={`${fi}-${li}`} className="snr-flow-loc">
                          <FileCode size={11} />
                          <code>{loc.component}{loc.textRange?.startLine ? `:${loc.textRange.startLine}` : ''}</code>
                          {loc.msg && <span>— {loc.msg}</span>}
                        </div>
                      ))
                    )}
                  </div>
                </>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Modal ────────────────────────────────────────────────────────────────────

const TYPE_FILTERS = ['ALL', 'BUG', 'VULNERABILITY', 'CODE_SMELL'] as const;
const SEV_FILTERS = ['ALL', 'BLOCKER', 'CRITICAL', 'MAJOR', 'MINOR', 'INFO'] as const;

export function SonarReportModal({ date, report, loading, error, onClose }: SonarReportModalProps) {
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<typeof TYPE_FILTERS[number]>('ALL');
  const [sevFilter, setSevFilter] = useState<typeof SEV_FILTERS[number]>('ALL');

  const allIssues = report?.issues ?? [];

  const filtered = useMemo(() => {
    let items = allIssues;
    if (typeFilter !== 'ALL') items = items.filter((i) => i.type === typeFilter);
    if (sevFilter !== 'ALL') items = items.filter((i) => i.severity === sevFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter(
        (i) =>
          i.message.toLowerCase().includes(q) ||
          i.component.toLowerCase().includes(q) ||
          i.rule.toLowerCase().includes(q),
      );
    }
    return [...items].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));
  }, [allIssues, typeFilter, sevFilter, search]);

  // Close on backdrop click
  function onBackdropClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === e.currentTarget) onClose();
  }

  // Close on Escape
  React.useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  return (
    <div className="modal-ov" onClick={onBackdropClick} role="dialog" aria-modal="true" aria-label="Sonar Report">
      <motion.div
        className="modal snr-modal"
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 12 }}
        transition={{ duration: 0.2 }}
      >
        {/* Header */}
        <div className="modal-hdr">
          <div className="modal-title">
            <ShieldCheck size={18} style={{ color: 'var(--c3)' }} />
            SonarQube Report
            <span>{date}</span>
            {!loading && allIssues.length > 0 && (
              <em style={{ fontSize: '0.8rem', color: 'var(--t2)', fontWeight: 500 }}>
                {allIssues.length} issues
              </em>
            )}
          </div>
          <button className="modal-close" onClick={onClose}>
            <X size={14} /> Close
          </button>
        </div>

        {/* Body */}
        <div className="snr-modal-body">
          {loading ? (
            <div className="snr-center-state">
              <Loader2 size={28} className="spin" style={{ color: 'var(--c3)' }} />
              <p>Loading report…</p>
            </div>
          ) : error ? (
            <div className="snr-center-state">
              <AlertTriangle size={28} style={{ color: 'var(--c2)' }} />
              <p style={{ color: 'var(--c2)' }}>{error}</p>
            </div>
          ) : allIssues.length === 0 ? (
            <div className="snr-center-state">
              <ShieldCheck size={32} style={{ color: 'var(--c1)' }} />
              <p>No issues found — clean scan!</p>
            </div>
          ) : (
            <>
              <SummaryBar issues={allIssues} />

              {/* Filters */}
              <div className="snr-filters">
                <div className="snr-search-wrap">
                  <Search size={14} className="snr-search-icon" />
                  <input
                    className="snr-search"
                    placeholder="Search message, file, rule…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <div className="snr-filter-chips">
                  {TYPE_FILTERS.map((t) => (
                    <button
                      key={t}
                      className={`snr-chip${typeFilter === t ? ' active' : ''}`}
                      onClick={() => setTypeFilter(t)}
                    >
                      {t === 'ALL' ? 'All Types' : t.replace('_', ' ')}
                    </button>
                  ))}
                </div>
                <div className="snr-filter-chips">
                  {SEV_FILTERS.map((s) => (
                    <button
                      key={s}
                      className={`snr-chip snr-chip-sev${sevFilter === s ? ' active' : ''} ${s.toLowerCase()}`}
                      onClick={() => setSevFilter(s)}
                    >
                      {s === 'ALL' ? 'All Severities' : s}
                    </button>
                  ))}
                </div>
                <span className="snr-result-count">{filtered.length} shown</span>
              </div>

              {/* Table */}
              <div className="snr-table-wrap">
                <table className="snr-table">
                  <thead>
                    <tr>
                      <th>Severity</th>
                      <th>Type</th>
                      <th>Message</th>
                      <th>File</th>
                      <th>Rule</th>
                      <th style={{ width: 32 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((issue) => (
                      <IssueRow key={issue.key} issue={issue} />
                    ))}
                  </tbody>
                </table>
                {filtered.length === 0 && (
                  <div className="empty-state">No issues match your filters.</div>
                )}
              </div>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}

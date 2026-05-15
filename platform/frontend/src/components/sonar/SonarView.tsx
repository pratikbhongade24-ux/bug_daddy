import React from 'react';
import { ShieldCheck, RefreshCcw, Play, Cloud, Bot, FileJson, ExternalLink, Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { SonarScanSession, SonarStatus } from '@/lib/types';
import { PanelHeader } from '../shared/PanelHeader';
import { motion } from 'framer-motion';

function formatBytes(size: number) {
  if (!size) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  return `${(size / Math.pow(1024, index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function SessionStatusBadge({ status }: { status: SonarScanSession['status'] }) {
  if (status === 'processing') {
    return (
      <span className="badge badge-info" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <Loader2 size={11} className="spin" /> Processing
      </span>
    );
  }
  if (status === 'completed') {
    return (
      <span className="badge badge-ok" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <CheckCircle2 size={11} /> Completed
      </span>
    );
  }
  return (
    <span className="badge badge-err" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <XCircle size={11} /> Failed
    </span>
  );
}

export function SonarView({
  status,
  loading,
  refreshing,
  invoking,
  inProgress,
  onInvoke,
  onRefresh,
  onOpenReport,
}: {
  status?: SonarStatus;
  loading: boolean;
  refreshing: boolean;
  invoking: boolean;
  inProgress: boolean;
  onInvoke: () => void;
  onRefresh: () => void;
  onOpenReport: (reportDate: string) => void;
}) {
  const reports = status?.reports || [];
  const sessions = status?.sessions || [];
  const latest = status?.latest_report;
  const scanDisabled = invoking || inProgress;

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="view active">
      <PanelHeader
        title="SonarQube"
        subtitle="Run code-quality scans and open generated S3 reports"
        icon={<ShieldCheck size={18} />}
        actions={
          <>
            <button className="btn" onClick={onRefresh} disabled={refreshing}>
              <RefreshCcw size={14} /> {refreshing ? 'Refreshing' : 'Refresh'}
            </button>
            <button
              className="btn pri"
              onClick={onInvoke}
              disabled={scanDisabled}
              title={inProgress ? 'A scan is already in progress' : undefined}
            >
              <Play size={14} /> {invoking ? 'Starting…' : inProgress ? 'Scan in Progress' : 'Run Scan'}
            </button>
          </>
        }
      />
      <div className="dash-scroll">
        <div className="sonar-grid">
          <section className="sonar-card">
            <div className="sonar-card-head">
              <Cloud size={17} />
              <span>Report Bucket</span>
            </div>
            <strong>{status?.bucket || 'bugdaddy-sonar-reports'}</strong>
            <em>{status?.region || 'ap-south-1'}</em>
          </section>
          <section className="sonar-card">
            <div className="sonar-card-head">
              <Bot size={17} />
              <span>Trigger Lambda</span>
            </div>
            <strong>{status?.lambda_name || 'bugdaddy-sonar-scan-trigger'}</strong>
            <em>SSM Run Command</em>
          </section>
          <section className="sonar-card">
            <div className="sonar-card-head">
              <FileJson size={17} />
              <span>Latest Report</span>
            </div>
            <strong>{latest?.date || 'No reports yet'}</strong>
            <em>{latest ? formatBytes(latest.size) : loading ? 'Loading…' : 'Run the first scan'}</em>
          </section>
        </div>

        <section className="admin-card sonar-reports">
          <div className="sonar-list-head">
            <div>
              <div className="esc-head-title">Scan Sessions</div>
              <div className="esc-head-sub">Real-time status of each scan invocation</div>
            </div>
            <div className="tbl-count">{loading ? 'Loading…' : `${sessions.length} sessions`}</div>
          </div>
          <div className="table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Session ID</th>
                  <th>Status</th>
                  <th>Triggered By</th>
                  <th>Reason</th>
                  <th>Started</th>
                  <th>Completed</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.session_id}>
                    <td className="td-id" title={s.session_id}>{s.session_id.slice(0, 8)}…</td>
                    <td><SessionStatusBadge status={s.status} /></td>
                    <td className="td-own">{s.triggered_by || '-'}</td>
                    <td className="td-desc">{s.reason || '-'}</td>
                    <td className="td-own">{s.started_at ? new Date(s.started_at).toLocaleString() : '-'}</td>
                    <td className="td-own">{s.completed_at ? new Date(s.completed_at).toLocaleString() : s.status === 'processing' ? <span style={{ color: 'var(--c-info)' }}>Running…</span> : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!sessions.length ? <div className="empty-state">No scan sessions yet. Run the first scan.</div> : null}
          </div>
        </section>

        <section className="admin-card sonar-reports">
          <div className="sonar-list-head">
            <div>
              <div className="esc-head-title">S3 Reports</div>
              <div className="esc-head-sub">Presigned links are generated on demand</div>
            </div>
            <div className="tbl-count">{loading ? 'Loading…' : `${reports.length} reports`}</div>
          </div>
          <div className="table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>S3 Key</th>
                  <th>Size</th>
                  <th>Updated</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((report) => (
                  <tr key={report.key}>
                    <td className="td-id">{report.date}</td>
                    <td className="td-desc" title={report.key}>
                      {report.key}
                    </td>
                    <td className="td-own">{formatBytes(report.size)}</td>
                    <td className="td-own">{report.last_modified || '-'}</td>
                    <td>
                      <button className="act-btn live-btn" onClick={() => onOpenReport(report.date)}>
                        <ExternalLink size={12} /> Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!reports.length ? <div className="empty-state">No Sonar reports found in S3.</div> : null}
          </div>
        </section>
      </div>
    </motion.div>
  );
}

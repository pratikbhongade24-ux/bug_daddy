import React from 'react';
import { ShieldCheck, RefreshCcw, Play, Cloud, Bot, FileJson, ExternalLink } from 'lucide-react';
import { SonarStatus } from '@/lib/types';
import { PanelHeader } from '../shared/PanelHeader';
import { motion } from 'framer-motion';

function formatBytes(size: number) {
  if (!size) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  return `${(size / Math.pow(1024, index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

export function SonarView({
  status,
  loading,
  refreshing,
  invoking,
  onInvoke,
  onRefresh,
  onOpenReport,
}: {
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
            <button className="btn pri" onClick={onInvoke} disabled={invoking}>
              <Play size={14} /> {invoking ? 'Starting' : 'Run Scan'}
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

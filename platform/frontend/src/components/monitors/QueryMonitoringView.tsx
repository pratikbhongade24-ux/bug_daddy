'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiJson } from '@/lib/api';
import type { ToastKind } from '@/lib/types';


interface Monitor {
  id: number;
  monitor_name: string;
  description: string;
  severity: 'CRITICAL' | 'WARNING' | 'INFO' | string;
  owner_service: string;
  service: string;
  is_active: boolean;
  last_run_at: string | null;
  last_result: {
    rows?: number;
    sample?: Record<string, unknown>[];
    ran_at?: string;
    error?: string;
  } | null;
  created_at: string;
}

interface IngestedItem {
  fingerprint: string;
  action: 'created' | 'updated';
  id: number;
}

interface MonitorRunResult {
  monitor_id: number;
  monitor_name: string;
  status: 'ok' | 'discrepancy' | 'error';
  rows: number;
  error?: string;
  ingested: IngestedItem[];
}

interface RunSummary {
  ran_at: string;
  monitors_run: number;
  total_discrepancy_rows: number;
  total_ingested: number;
  results: MonitorRunResult[];
}

function severityBadge(severity: string) {
  const cls =
    severity === 'CRITICAL' ? 'badge-critical' :
    severity === 'WARNING'  ? 'badge-warning' :
    'badge-info';
  return <span className={`badge ${cls}`}>{severity}</span>;
}

function statusDot(status: string) {
  const color =
    status === 'discrepancy' ? '#ef4444' :
    status === 'error'       ? '#f97316' :
    '#22c55e';
  return <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: color, marginRight: 6 }} />;
}

export function QueryMonitoringView({ toast }: { toast: (msg: string, kind?: ToastKind) => void }) {
  const queryClient = useQueryClient();
  const [lastRun, setLastRun] = useState<RunSummary | null>(null);
  const [expandedMonitor, setExpandedMonitor] = useState<number | null>(null);

  const monitorsQuery = useQuery({
    queryKey: ['monitors'],
    queryFn: () => apiJson<{ items: Monitor[] }>('/monitors').then((r) => r.items),
    refetchInterval: 30_000,
  });

  const runMutation = useMutation({
    mutationFn: () => apiJson<RunSummary>('/monitors/run', { method: 'POST' }),
    onSuccess: (data) => {
      setLastRun(data);
      setNextRunIn(CRON_INTERVAL_MS);
      queryClient.invalidateQueries({ queryKey: ['monitors'] });
      queryClient.invalidateQueries({ queryKey: ['issues'] });
      if (data.total_ingested > 0) {
        toast(`Monitor run: ${data.total_ingested} bug(s) ingested from ${data.total_discrepancy_rows} discrepancies`, 'err');
      } else {
        toast(`Monitor run: all ${data.monitors_run} checks passed — no discrepancies`, 'ok');
      }
    },
    onError: () => toast('Monitor run failed', 'err'),
  });

  const monitors = monitorsQuery.data ?? [];

  return (
    <div className="view-root" style={{ padding: '24px 28px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Query Monitoring</h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--muted)' }}>
            Run all system monitor queries manually. Discrepancies are ingested as bugs.
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
        >
          {runMutation.isPending ? 'Running…' : 'Run Now'}
        </button>
      </div>

      {/* Summary bar */}
      {lastRun ? (
        <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
          {[
            { label: 'Monitors run', value: lastRun.monitors_run },
            { label: 'Discrepancy rows', value: lastRun.total_discrepancy_rows, alert: lastRun.total_discrepancy_rows > 0 },
            { label: 'Bugs ingested', value: lastRun.total_ingested, alert: lastRun.total_ingested > 0 },
            { label: 'Last ran at', value: new Date(lastRun.ran_at).toLocaleTimeString() },
          ].map((item) => (
            <div
              key={item.label}
              style={{
                background: item.alert ? 'rgba(239,68,68,0.08)' : 'var(--card-bg, #1a1a2e)',
                border: `1px solid ${item.alert ? '#ef4444' : 'var(--border)'}`,
                borderRadius: 8,
                padding: '10px 18px',
                minWidth: 130,
              }}
            >
              <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{item.label}</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: item.alert ? '#ef4444' : 'inherit', marginTop: 2 }}>{item.value}</div>
            </div>
          ))}
        </div>
      ) : null}

      {/* Monitor list */}
      {monitorsQuery.isLoading ? (
        <div className="view-skeleton" aria-busy="true" />
      ) : monitors.length === 0 ? (
        <p style={{ color: 'var(--muted)', fontSize: 14 }}>No monitors configured.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {monitors.map((monitor) => {
            const runResult = lastRun?.results.find((r) => r.monitor_id === monitor.id);
            const isExpanded = expandedMonitor === monitor.id;
            const hasDiscrepancy = runResult?.status === 'discrepancy';
            const lastResultRows = monitor.last_result?.rows ?? 0;

            return (
              <div
                key={monitor.id}
                style={{
                  background: 'var(--card-bg, #1a1a2e)',
                  border: `1px solid ${hasDiscrepancy ? '#ef4444' : 'var(--border)'}`,
                  borderRadius: 10,
                  padding: '16px 20px',
                }}
              >
                {/* Monitor header row */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      {runResult ? statusDot(runResult.status) : null}
                      <strong style={{ fontSize: 15 }}>{monitor.monitor_name}</strong>
                      {severityBadge(monitor.severity)}
                      <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                        {monitor.service} · {monitor.owner_service}
                      </span>
                    </div>
                    <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--muted)', maxWidth: 700, lineHeight: 1.5 }}>
                      {monitor.description}
                    </p>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                    {hasDiscrepancy ? (
                      <span style={{ fontSize: 13, color: '#ef4444', fontWeight: 600 }}>
                        {runResult!.rows} discrepanc{runResult!.rows === 1 ? 'y' : 'ies'}
                      </span>
                    ) : runResult?.status === 'ok' ? (
                      <span style={{ fontSize: 13, color: '#22c55e' }}>Clean</span>
                    ) : null}
                    {lastResultRows > 0 || runResult ? (
                      <button
                        className="btn btn-sm"
                        onClick={() => setExpandedMonitor(isExpanded ? null : monitor.id)}
                      >
                        {isExpanded ? 'Hide' : 'Details'}
                      </button>
                    ) : null}
                  </div>
                </div>

                {/* Last run metadata */}
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--muted)', display: 'flex', gap: 16 }}>
                  {monitor.last_run_at ? (
                    <span>Last run: {new Date(monitor.last_run_at).toLocaleString()}</span>
                  ) : (
                    <span>Never run</span>
                  )}
                  {runResult?.ingested?.length ? (
                    <span style={{ color: '#f97316' }}>
                      {runResult.ingested.filter((i) => i.action === 'created').length} new bug(s) created ·{' '}
                      {runResult.ingested.filter((i) => i.action === 'updated').length} updated
                    </span>
                  ) : null}
                </div>

                {/* Expanded detail: discrepancy rows */}
                {isExpanded && runResult?.rows ? (
                  <div style={{ marginTop: 14, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                      Discrepancy rows ({runResult.rows})
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr>
                            {monitor.last_result?.sample?.[0]
                              ? Object.keys(monitor.last_result.sample[0]).map((col) => (
                                  <th key={col} style={{ textAlign: 'left', padding: '4px 10px', borderBottom: '1px solid var(--border)', color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                                    {col}
                                  </th>
                                ))
                              : null}
                          </tr>
                        </thead>
                        <tbody>
                          {(monitor.last_result?.sample ?? []).map((row, idx) => (
                            <tr key={idx} style={{ background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)' }}>
                              {Object.values(row).map((val, ci) => (
                                <td key={ci} style={{ padding: '5px 10px', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap' }}>
                                  {val === null ? <span style={{ color: 'var(--muted)' }}>null</span> : String(val)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {runResult.rows > 5 ? (
                        <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>
                          Showing 5 of {runResult.rows} rows. Full detail in Issues view.
                        </p>
                      ) : null}
                    </div>

                    {/* Ingested bugs */}
                    {runResult.ingested.length > 0 ? (
                      <div style={{ marginTop: 12 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Ingested bugs</div>
                        {runResult.ingested.map((item) => (
                          <div key={item.fingerprint} style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 3 }}>
                            <span style={{ color: item.action === 'created' ? '#ef4444' : '#f97316', fontWeight: 600, marginRight: 6 }}>
                              [{item.action.toUpperCase()}]
                            </span>
                            Issue #{item.id} · fingerprint: {item.fingerprint}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {/* Error state */}
                {isExpanded && runResult?.status === 'error' ? (
                  <div style={{ marginTop: 12, padding: '10px 14px', background: 'rgba(249,115,22,0.08)', borderRadius: 6, fontSize: 13, color: '#f97316' }}>
                    Error: {runResult.error}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

'use client';

import React, { useState } from 'react';
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
  check_query: string | null;
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

export function QueryMonitoringView({ toast }: { toast: (msg: string, kind?: ToastKind) => void }) {
  const queryClient = useQueryClient();
  const [lastRun, setLastRun] = useState<RunSummary | null>(null);
  const [expandedQuery, setExpandedQuery] = useState<number | null>(null);

  const monitorsQuery = useQuery({
    queryKey: ['monitors'],
    queryFn: () => apiJson<{ items: Monitor[] }>('/monitors').then((r) => r.items),
    refetchInterval: 30_000,
  });

  const runMutation = useMutation({
    mutationFn: () => apiJson<RunSummary>('/monitors/run', { method: 'POST' }),
    onSuccess: (data) => {
      setLastRun(data);
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Query Monitoring</h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--muted)' }}>
            System monitor queries — discrepancies are ingested as bugs.
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

      {lastRun ? (
        <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
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
                padding: '8px 16px',
                minWidth: 120,
              }}
            >
              <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{item.label}</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: item.alert ? '#ef4444' : 'inherit', marginTop: 2 }}>{item.value}</div>
            </div>
          ))}
        </div>
      ) : null}

      {monitorsQuery.isLoading ? (
        <div className="view-skeleton" aria-busy="true" />
      ) : monitors.length === 0 ? (
        <p style={{ color: 'var(--muted)', fontSize: 14 }}>No monitors configured.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['ID', 'Monitor Name', 'Severity', 'Service', 'Owner', 'Active', 'Last Run', 'Last Result', 'SQL'].map((col) => (
                  <th key={col} style={{ textAlign: 'left', padding: '8px 12px', color: 'var(--muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            {monitors.map((monitor, idx) => {
              const runResult = lastRun?.results.find((r) => r.monitor_id === monitor.id);
              const isQueryOpen = expandedQuery === monitor.id;
              const rowBg = idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)';

              return (
                <tbody key={monitor.id}>
                  <tr style={{ background: rowBg, borderBottom: isQueryOpen ? 'none' : '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--muted)', whiteSpace: 'nowrap' }}>{monitor.id}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ fontWeight: 600 }}>{monitor.monitor_name}</div>
                      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2, maxWidth: 320 }}>{monitor.description}</div>
                    </td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>{severityBadge(monitor.severity)}</td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', color: 'var(--muted)' }}>{monitor.service}</td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', color: 'var(--muted)' }}>{monitor.owner_service}</td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                      <span style={{ color: monitor.is_active ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                        {monitor.is_active ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', color: 'var(--muted)', fontSize: 12 }}>
                      {monitor.last_run_at ? new Date(monitor.last_run_at).toLocaleString() : '—'}
                    </td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                      {runResult ? (
                        runResult.status === 'discrepancy' ? (
                          <span style={{ color: '#ef4444', fontWeight: 600 }}>{runResult.rows} row{runResult.rows !== 1 ? 's' : ''}</span>
                        ) : runResult.status === 'error' ? (
                          <span style={{ color: '#f97316' }}>Error</span>
                        ) : (
                          <span style={{ color: '#22c55e' }}>Clean</span>
                        )
                      ) : monitor.last_result?.rows != null ? (
                        <span style={{ color: monitor.last_result.rows > 0 ? '#ef4444' : '#22c55e', fontWeight: monitor.last_result.rows > 0 ? 600 : 400 }}>
                          {monitor.last_result.rows > 0 ? `${monitor.last_result.rows} row${monitor.last_result.rows !== 1 ? 's' : ''}` : 'Clean'}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--muted)' }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                      {monitor.check_query ? (
                        <button
                          className="btn btn-sm"
                          style={{ fontSize: 11 }}
                          onClick={() => setExpandedQuery(isQueryOpen ? null : monitor.id)}
                        >
                          {isQueryOpen ? 'Hide' : 'View'}
                        </button>
                      ) : '—'}
                    </td>
                  </tr>
                  {isQueryOpen && monitor.check_query ? (
                    <tr style={{ background: rowBg, borderBottom: '1px solid var(--border)' }}>
                      <td colSpan={9} style={{ padding: '0 12px 14px 12px' }}>
                        <pre style={{
                          background: 'rgba(0,0,0,0.3)',
                          border: '1px solid var(--border)',
                          borderRadius: 6,
                          padding: '12px 14px',
                          fontSize: 12,
                          lineHeight: 1.6,
                          overflowX: 'auto',
                          whiteSpace: 'pre',
                          color: '#a5f3fc',
                          margin: 0,
                        }}>
                          {monitor.check_query}
                        </pre>
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              );
            })}
          </table>
        </div>
      )}
    </div>
  );
}

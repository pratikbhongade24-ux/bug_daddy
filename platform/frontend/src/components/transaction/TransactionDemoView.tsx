'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiJson, errorMessage } from '@/lib/api';
import type { TransactionBugStatus, TransactionDemoAnalysis, TransactionDemoMetrics, TransactionDemoReport, TransactionVerifyFix } from '@/lib/types';

export function TransactionDemoView({ addToast }: { addToast: (msg: string, kind?: 'ok' | 'err' | 'inf') => void }) {
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [verifyResult, setVerifyResult] = useState<TransactionVerifyFix | null>(null);

  const reportsQuery = useQuery({
    queryKey: ['transaction-demo', 'reports'],
    queryFn: () => apiJson<{ items: TransactionDemoReport[] }>('/demo/transaction/reports?limit=50'),
    refetchInterval: 20_000,
  });

  const metricsQuery = useQuery({
    queryKey: ['transaction-demo', 'metrics'],
    queryFn: () => apiJson<TransactionDemoMetrics>('/demo/transaction/metrics'),
    refetchInterval: 20_000,
  });

  const bugStatusQuery = useQuery({
    queryKey: ['transaction-demo', 'bug-status'],
    queryFn: () => apiJson<TransactionBugStatus>('/demo/transaction/bug-status'),
    refetchInterval: 20_000,
  });

  const analysisQuery = useQuery({
    queryKey: ['transaction-demo', 'analysis', selectedReportId],
    queryFn: () => apiJson<TransactionDemoAnalysis>(`/demo/transaction/reports/${selectedReportId}/analysis`),
    enabled: !!selectedReportId,
  });

  const bugFixMutation = useMutation({
    mutationFn: () => apiJson('/demo/transaction/bug/fix', { method: 'POST' }),
    onSuccess: async () => {
      addToast('Logical API bug fixed by BugDaddy action', 'ok');
      await bugStatusQuery.refetch();
    },
    onError: (e) => addToast(errorMessage(e, 'Bug fix failed'), 'err'),
  });

  const reconMutation = useMutation({
    mutationFn: () => apiJson<{ report: TransactionDemoReport; analysis: TransactionDemoAnalysis }>('/demo/transaction/reconciliation/run', { method: 'POST' }),
    onSuccess: async (data) => {
      addToast('Reconciliation completed', 'ok');
      setSelectedReportId(data.report.id);
      await reportsQuery.refetch();
      await metricsQuery.refetch();
    },
    onError: (e) => addToast(errorMessage(e, 'Reconciliation failed'), 'err'),
  });

  const verifyMutation = useMutation({
    mutationFn: () => apiJson<TransactionVerifyFix>('/demo/transaction/verify-fix', { method: 'POST' }),
    onSuccess: (data) => {
      setVerifyResult(data);
      addToast('Before vs after verification completed', 'ok');
    },
    onError: (e) => addToast(errorMessage(e, 'Verification failed'), 'err'),
  });

  const reports = reportsQuery.data?.items || [];
  const selected = useMemo(() => reports.find((r) => r.id === selectedReportId) || reports[0], [reports, selectedReportId]);

  return (
    <section className="tx-demo-view">
      <header className="panel-header">
        <div>
          <div className="ph-title">Transaction Data Integrity</div>
          <div className="ph-sub">Continuously validate transactional data quality and detect cross-system inconsistencies</div>
        </div>
        <div className="tx-actions">
          <button className="btn" type="button" onClick={() => bugFixMutation.mutate()} disabled={bugFixMutation.isPending}>Run BugDaddy Fix</button>
          <button className="btn" type="button" onClick={() => verifyMutation.mutate()} disabled={verifyMutation.isPending}>Before vs After</button>
          <button className="btn pri" type="button" onClick={() => reconMutation.mutate()} disabled={reconMutation.isPending}>Run Reconciliation</button>
        </div>
      </header>

      <div className="tx-grid">
        <article className="tx-card">
          <h3>Metrics</h3>
          <p>Transfers: <b>{metricsQuery.data?.transfers_created ?? 0}</b></p>
          <p>Recon runs: <b>{metricsQuery.data?.reconciliation_runs ?? 0}</b></p>
          <p>Mismatches: <b>{metricsQuery.data?.mismatches_detected ?? 0}</b></p>
          <p>DB slow queries: <b>{metricsQuery.data?.db_slow_queries ?? 0}</b></p>
        </article>

        <article className="tx-card">
          <h3>API Bug Status</h3>
          <p>Bug active: <b>{bugStatusQuery.data?.beneficiary_routing_bug_active ? 'Yes' : 'No'}</b></p>
          <p>{bugStatusQuery.data?.description || 'Checking status...'}</p>
        </article>
      </div>

      <div className="tx-split">
        <article className="tx-card tx-reports">
          <h3>Reconciliation Reports</h3>
          <div className="tx-report-list">
            {reports.map((r) => (
              <button key={r.id} type="button" className={`tx-report-row ${selected?.id === r.id ? 'active' : ''}`} onClick={() => setSelectedReportId(r.id)}>
                <span>{r.report_ref}</span>
                <span className="badge">{r.mismatch_count} mismatches</span>
              </button>
            ))}
            {reports.length === 0 ? <div className="tx-empty">No reports yet. Run reconciliation.</div> : null}
          </div>
        </article>

        <article className="tx-card tx-analysis">
          <h3>RCA Analysis</h3>
          {analysisQuery.isLoading ? <div className="tx-empty">Loading analysis...</div> : null}
          {analysisQuery.data ? (
            <>
              <p className="tx-summary">{analysisQuery.data.summary}</p>
              <div>
                <h4>Root Causes</h4>
                <ul>
                  {analysisQuery.data.root_causes.map((rc) => <li key={rc}>{rc}</li>)}
                </ul>
              </div>
              <div>
                <h4>Impacted Services</h4>
                <ul>
                  {analysisQuery.data.impacted_services.map((svc) => <li key={svc}>{svc}</li>)}
                </ul>
              </div>
            </>
          ) : null}
          {!analysisQuery.data && !analysisQuery.isLoading ? <div className="tx-empty">Select a report to view analysis.</div> : null}
        </article>
      </div>

      {verifyResult ? (
        <article className="tx-card">
          <h3>Fix Verification</h3>
          <p>Before mismatches: <b>{verifyResult.before.mismatch_count}</b> (report #{verifyResult.before.report_id})</p>
          <p>After mismatches: <b>{verifyResult.after.mismatch_count}</b> (report #{verifyResult.after.report_id})</p>
          <p>Bug active after fix: <b>{verifyResult.bug_active_after ? 'Yes' : 'No'}</b></p>
          {verifyResult.code_change ? (
            <>
              <p>File: <b>{verifyResult.code_change.file}</b> | Function: <b>{verifyResult.code_change.function}</b></p>
              <div className="tx-grid">
                <article className="tx-card">
                  <h4>Before Code</h4>
                  <pre className="tx-code">{verifyResult.code_change.before}</pre>
                </article>
                <article className="tx-card">
                  <h4>After Code</h4>
                  <pre className="tx-code">{verifyResult.code_change.after}</pre>
                </article>
              </div>
              <p><b>Fix Action:</b> {verifyResult.code_change.fix_action}</p>
            </>
          ) : null}
        </article>
      ) : null}
    </section>
  );
}

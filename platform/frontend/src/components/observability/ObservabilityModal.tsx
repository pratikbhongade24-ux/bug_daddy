'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  X, Activity, ChevronDown, ChevronRight, Clock, CheckCircle2, XCircle, Loader2,
  GitBranch, Layers, Zap, Timer, AlertTriangle, Copy, Check,
} from 'lucide-react';
import { apiJson } from '@/lib/api';
import { Issue, ExecutionEvent } from '@/lib/types';

interface ObservabilitySession {
  session_id: string;
  issue_id: number | null;
  workflow_key: string;
  workflow_version: string;
  agent_target: string;
  status: string;
  started_by: string | null;
  started_at: string | null;
  ended_at: string | null;
  summary: string | null;
  error_message: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string | null;
}

interface ObservabilityData {
  session: ObservabilitySession;
  workflow: { graph_json?: unknown; workflow_key: string; workflow_version: string } | null;
  events: ExecutionEvent[];
}

function statusIcon(status: string | null) {
  if (status === 'succeeded' || status === 'completed') return <CheckCircle2 size={14} className="obs-status-icon succeeded" />;
  if (status === 'failed') return <XCircle size={14} className="obs-status-icon failed" />;
  if (status === 'running') return <Loader2 size={14} className="obs-status-icon running obs-spin" />;
  return <Clock size={14} className="obs-status-icon pending" />;
}

function sessionStatusBadge(status: string) {
  const cls = status === 'completed' || status === 'succeeded' ? 'succeeded'
    : status === 'failed' ? 'failed'
    : status === 'running' || status === 'in_progress' ? 'running'
    : 'pending';
  return <span className={clsx('obs-session-badge', cls)}>{status}</span>;
}

function formatTs(value: string | null | undefined) {
  if (!value) return '—';
  return new Date(value).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

function durationLabel(startedAt: string | null, endedAt: string | null) {
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : Date.now();
  const ms = end - start;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
}

function groupEventsByNode(events: ExecutionEvent[]): { nodeId: string; nodeName: string; events: ExecutionEvent[] }[] {
  const groups: Map<string, { nodeId: string; nodeName: string; events: ExecutionEvent[] }> = new Map();
  const order: string[] = [];
  for (const ev of events) {
    const key = ev.node_id || '__session__';
    if (!groups.has(key)) {
      groups.set(key, { nodeId: key, nodeName: ev.node_name || ev.agent_name || key, events: [] });
      order.push(key);
    }
    groups.get(key)!.events.push(ev);
  }
  return order.map((key) => groups.get(key)!);
}

function NodeGroup({ group }: { group: { nodeId: string; nodeName: string; events: ExecutionEvent[] } }) {
  const [expanded, setExpanded] = useState(true);
  const lastStatus = group.events[group.events.length - 1]?.status || null;
  const durationMs = group.events.reduce((sum, ev) => sum + (ev.duration_ms ?? 0), 0);
  return (
    <div className={clsx('obs-node-group', lastStatus === 'failed' ? 'failed' : lastStatus === 'succeeded' ? 'succeeded' : 'running')}>
      <button className="obs-node-header" onClick={() => setExpanded((v) => !v)}>
        <span className="obs-node-icon">{statusIcon(lastStatus)}</span>
        <span className="obs-node-name">{group.nodeName}</span>
        <span className="obs-node-count">{group.events.length} event{group.events.length !== 1 ? 's' : ''}</span>
        {durationMs > 0 ? <span className="obs-node-dur"><Timer size={11} />{durationMs}ms</span> : null}
        <span className="obs-node-chevron">{expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</span>
      </button>
      {expanded ? (
        <div className="obs-event-list">
          {group.events.map((ev, idx) => <EventRow key={ev.id ?? idx} event={ev} />)}
        </div>
      ) : null}
    </div>
  );
}

function EventRow({ event }: { event: ExecutionEvent }) {
  const [expanded, setExpanded] = useState(false);
  const details = [
    ['Description', event.description],
    ['Input', event.input_summary],
    ['Output', event.output_summary],
    ['Reasoning', event.reasoning_summary],
    ['Tool', event.tool_name],
    ['Error', event.error_message],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));

  return (
    <div className={clsx('obs-event-row', event.status === 'failed' ? 'failed' : event.status === 'running' ? 'running' : 'done', expanded && 'expanded', details.length && 'has-details')}>
      <button className="obs-event-header" onClick={() => details.length && setExpanded((v) => !v)}>
        <span className="obs-event-dot">{statusIcon(event.status)}</span>
        <span className="obs-event-type">{event.event_type}</span>
        {event.title ? <span className="obs-event-title">{event.title}</span> : null}
        {event.duration_ms != null ? <span className="obs-event-dur">{event.duration_ms}ms</span> : null}
        <span className="obs-event-ts">{event.created_at ? new Date(event.created_at).toLocaleTimeString('en-IN', { hour12: false }) : ''}</span>
        {details.length ? <span className="obs-event-chevron"><ChevronDown size={12} /></span> : null}
      </button>
      {expanded && details.length ? (
        <div className="obs-event-details">
          {details.map(([label, value]) => (
            <div key={label} className="obs-detail-row">
              <span className="obs-detail-label">{label}</span>
              <span className="obs-detail-value">{value}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function MetricCard({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="obs-metric-card">
      <span className="obs-metric-icon">{icon}</span>
      <div>
        <div className="obs-metric-value">{value}</div>
        <div className="obs-metric-label">{label}</div>
      </div>
    </div>
  );
}

export function ObservabilityModal({ issue, onClose }: { issue: Issue; onClose: () => void }) {
  const sessionId = issue.latest_execution_session_id || issue.execution_session_id;
  const [copied, setCopied] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const query = useQuery({
    queryKey: ['observability', sessionId || `issue-${issue.id}`],
    queryFn: async (): Promise<ObservabilityData | null> => {
      if (!sessionId) {
        const executions = await apiJson<{ items: ObservabilitySession[] }>(`/agent/executions?issue_id=${issue.id}&limit=1`);
        const latest = executions.items[0];
        if (!latest) return null;
        const data = await apiJson<ObservabilityData>(`/agent/executions/${latest.session_id}/graph`);
        return data;
      }
      return apiJson<ObservabilityData>(`/agent/executions/${sessionId}/graph`);
    },
    refetchInterval: (query) => {
      const status = query.state.data?.session?.status;
      if (status === 'running' || status === 'in_progress' || status === 'queued') return 3000;
      return false;
    },
    retry: 1,
  });

  useEffect(() => {
    function onKey(ev: KeyboardEvent) { if (ev.key === 'Escape') onClose(); }
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); if (pollingRef.current) clearInterval(pollingRef.current); };
  }, [onClose]);

  const data = query.data;
  const session = data?.session;
  const events = data?.events ?? [];
  const nodeGroups = groupEventsByNode(events);

  const succeededCount = events.filter((ev) => ev.status === 'succeeded').length;
  const failedCount = events.filter((ev) => ev.status === 'failed').length;
  const totalDurationMs = events.reduce((sum, ev) => sum + (ev.duration_ms ?? 0), 0);

  function copyTrace() {
    const lines: string[] = [
      `=== Observability Trace ===`,
      `Issue: ${issue.id} | ${issue.shortSvc} | ${issue.err}`,
      `Session: ${session?.session_id ?? 'N/A'}`,
      `Workflow: ${session?.workflow_key ?? 'N/A'} v${session?.workflow_version ?? '?'}`,
      `Status: ${session?.status ?? 'N/A'}`,
      `Started: ${session?.started_at ?? 'N/A'}`,
      `Ended: ${session?.ended_at ?? 'N/A'}`,
      `Events: ${events.length} | Succeeded: ${succeededCount} | Failed: ${failedCount}`,
      '',
    ];
    events.forEach((ev, idx) => {
      lines.push(`[${idx + 1}] ${ev.node_name || ev.node_id || ''} | ${ev.event_type} | ${ev.status || ''} | ${ev.created_at ? new Date(ev.created_at).toLocaleTimeString('en-IN', { hour12: false }) : ''}`);
      if (ev.title) lines.push(`  Title: ${ev.title}`);
      if (ev.description) lines.push(`  Desc: ${ev.description}`);
      if (ev.input_summary) lines.push(`  Input: ${ev.input_summary}`);
      if (ev.output_summary) lines.push(`  Output: ${ev.output_summary}`);
      if (ev.reasoning_summary) lines.push(`  Reasoning: ${ev.reasoning_summary}`);
      if (ev.error_message) lines.push(`  Error: ${ev.error_message}`);
      if (ev.tool_name) lines.push(`  Tool: ${ev.tool_name}`);
      if (ev.duration_ms != null) lines.push(`  Duration: ${ev.duration_ms}ms`);
    });
    navigator.clipboard.writeText(lines.join('\n')).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div
      className="modal-ov"
      role="dialog"
      aria-modal="true"
      onMouseDown={(ev) => { if (ev.target === ev.currentTarget) onClose(); }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.88, y: 24 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.92, y: 16 }}
        transition={{ type: 'spring', damping: 22, stiffness: 280 }}
        className="modal obs-modal"
      >
        {/* Header */}
        <div className="modal-hdr">
          <div>
            <div className="modal-title">
              <Activity size={18} /> Agent Observability
              <span>Issue {issue.id}</span>
              {session ? sessionStatusBadge(session.status) : null}
            </div>
            <div className="modal-sub">
              {issue.shortSvc} / {issue.err} / {session?.workflow_key ?? 'no session'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button className="modal-close" onClick={copyTrace} style={{ opacity: copied ? 0.75 : 1 }}>
              {copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied!' : 'Copy Trace'}
            </button>
            <button className="modal-close" onClick={onClose}><X size={14} /> Close</button>
          </div>
        </div>

        <div className="obs-body">
          {/* Session metadata */}
          {session ? (
            <div className="obs-session-meta">
              <MetricCard label="Workflow" value={`${session.workflow_key} v${session.workflow_version}`} icon={<GitBranch size={14} />} />
              <MetricCard label="Duration" value={durationLabel(session.started_at, session.ended_at) ?? '—'} icon={<Timer size={14} />} />
              <MetricCard label="Events" value={String(events.length)} icon={<Layers size={14} />} />
              <MetricCard label="Succeeded" value={String(succeededCount)} icon={<CheckCircle2 size={14} />} />
              {failedCount > 0 ? <MetricCard label="Failed" value={String(failedCount)} icon={<AlertTriangle size={14} />} /> : null}
              {totalDurationMs > 0 ? <MetricCard label="Agent Time" value={`${totalDurationMs}ms`} icon={<Zap size={14} />} /> : null}
            </div>
          ) : null}

          {session ? (
            <div className="obs-session-info">
              <span><strong>Session:</strong> {session.session_id}</span>
              <span><strong>Started:</strong> {formatTs(session.started_at)}</span>
              {session.ended_at ? <span><strong>Ended:</strong> {formatTs(session.ended_at)}</span> : null}
              {session.started_by ? <span><strong>By:</strong> {session.started_by}</span> : null}
              {session.error_message ? <span className="obs-session-error"><AlertTriangle size={12} /> {session.error_message}</span> : null}
              {session.summary ? <span className="obs-session-summary">{session.summary}</span> : null}
            </div>
          ) : null}

          {/* Trace */}
          <div className="obs-trace">
            {query.isLoading ? (
              <div className="obs-empty"><Loader2 size={20} className="obs-spin" /> Loading trace…</div>
            ) : !session ? (
              <div className="obs-empty">
                <Activity size={20} />
                <div>No execution session found for this issue.</div>
                <div className="obs-empty-sub">Use <strong>Invoke AI</strong> to start an agent execution.</div>
              </div>
            ) : events.length === 0 ? (
              <div className="obs-empty">
                <Activity size={20} />
                <div>No execution events recorded yet.</div>
                {session.status === 'running' || session.status === 'in_progress' ? (
                  <div className="obs-empty-sub"><Loader2 size={14} className="obs-spin" /> Agent is running — events will appear shortly.</div>
                ) : null}
              </div>
            ) : (
              <div className="obs-node-list">
                {nodeGroups.map((group) => <NodeGroup key={group.nodeId} group={group} />)}
              </div>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  );
}

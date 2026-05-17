'use client';

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import {
  X, Activity, ChevronDown, ChevronRight, Clock, CheckCircle2, XCircle,
  Loader2, GitBranch, Layers, Timer, AlertTriangle, Copy, Check, Coins,
  ArrowDownToLine, ArrowUpFromLine, Zap, User,
} from 'lucide-react';
import { apiJson } from '@/lib/api';
import { Issue, ExecutionEvent } from '@/lib/types';

interface ObsSession {
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
}

interface ObsData {
  session: ObsSession;
  workflow: unknown;
  events: ExecutionEvent[];
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtTs(v: string | null | undefined) {
  if (!v) return '—';
  return new Date(v).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
}

function fmtDuration(startedAt: string | null, endedAt: string | null) {
  if (!startedAt) return null;
  const ms = (endedAt ? new Date(endedAt) : new Date()).getTime() - new Date(startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
}

function fmtTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function statusMeta(status: string | null): { icon: React.ReactNode; cls: string } {
  if (status === 'succeeded' || status === 'completed')
    return { icon: <CheckCircle2 size={13} />, cls: 'obs-s-succeeded' };
  if (status === 'failed')
    return { icon: <XCircle size={13} />, cls: 'obs-s-failed' };
  if (status === 'running' || status === 'in_progress')
    return { icon: <Loader2 size={13} className="obs-spin" />, cls: 'obs-s-running' };
  return { icon: <Clock size={13} />, cls: 'obs-s-pending' };
}

function groupByNode(events: ExecutionEvent[]) {
  const map = new Map<string, { key: string; name: string; events: ExecutionEvent[] }>();
  const order: string[] = [];
  for (const ev of events) {
    const key = ev.node_id || '__session__';
    if (!map.has(key)) {
      map.set(key, { key, name: ev.node_name || ev.agent_name || key, events: [] });
      order.push(key);
    }
    map.get(key)!.events.push(ev);
  }
  return order.map((k) => map.get(k)!);
}

// ── Sub-components ─────────────────────────────────────────────────────────

function StatPill({
  icon, label, value, sub, accent,
}: { icon: React.ReactNode; label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className={clsx('obs-stat', accent && `obs-stat-${accent}`)}>
      <span className="obs-stat-icon">{icon}</span>
      <div className="obs-stat-body">
        <span className="obs-stat-value">{value}</span>
        {sub ? <span className="obs-stat-sub">{sub}</span> : null}
        <span className="obs-stat-label">{label}</span>
      </div>
    </div>
  );
}

function EventRow({ event }: { event: ExecutionEvent }) {
  const [open, setOpen] = useState(false);
  const details: [string, string][] = [
    ['Description', event.description!],
    ['Input', event.input_summary!],
    ['Output', event.output_summary!],
    ['Reasoning', event.reasoning_summary!],
    ['Tool', event.tool_name!],
    ['Error', event.error_message!],
  ].filter((d): d is [string, string] => Boolean(d[1]));

  const { icon, cls } = statusMeta(event.status);
  const hasTokens = event.input_tokens != null || event.output_tokens != null;

  return (
    <div className={clsx('obs-ev', cls, open && 'obs-ev-open', details.length && 'obs-ev-expandable')}>
      <button className="obs-ev-hdr" onClick={() => details.length && setOpen((v) => !v)}>
        <span className={clsx('obs-ev-icon', cls)}>{icon}</span>
        <span className="obs-ev-type">{event.event_type}</span>
        {event.title ? <span className="obs-ev-title">{event.title}</span> : null}
        <span className="obs-ev-right">
          {hasTokens ? (
            <span className="obs-ev-tokens">
              {event.input_tokens != null ? <span className="obs-tok-in"><ArrowDownToLine size={10} />{fmtTokens(event.input_tokens)}</span> : null}
              {event.output_tokens != null ? <span className="obs-tok-out"><ArrowUpFromLine size={10} />{fmtTokens(event.output_tokens)}</span> : null}
            </span>
          ) : null}
          {event.duration_ms != null ? <span className="obs-ev-dur">{event.duration_ms}ms</span> : null}
          {event.created_at ? <span className="obs-ev-ts">{new Date(event.created_at).toLocaleTimeString('en-IN', { hour12: false })}</span> : null}
          {details.length ? <span className="obs-ev-chevron">{open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</span> : null}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && details.length ? (
          <motion.div
            key="details"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="obs-ev-details"
          >
            {details.map(([lbl, val]) => (
              <div key={lbl} className="obs-detail-row">
                <span className="obs-detail-lbl">{lbl}</span>
                <span className="obs-detail-val">{val}</span>
              </div>
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function NodeGroup({ group }: { group: { key: string; name: string; events: ExecutionEvent[] } }) {
  const [open, setOpen] = useState(true);
  const last = group.events[group.events.length - 1];
  const { icon, cls } = statusMeta(last?.status ?? null);
  const totalDur = group.events.reduce((s, e) => s + (e.duration_ms ?? 0), 0);
  const inTok = group.events.reduce((s, e) => s + (e.input_tokens ?? 0), 0);
  const outTok = group.events.reduce((s, e) => s + (e.output_tokens ?? 0), 0);
  const hasTokens = inTok > 0 || outTok > 0;

  return (
    <div className={clsx('obs-ng', cls)}>
      <button className="obs-ng-hdr" onClick={() => setOpen((v) => !v)}>
        <span className={clsx('obs-ng-icon', cls)}>{icon}</span>
        <span className="obs-ng-name">{group.name}</span>
        <span className="obs-ng-meta">
          {hasTokens ? (
            <span className="obs-ng-tokens">
              <Coins size={11} />
              <span className="obs-tok-in">{fmtTokens(inTok)} in</span>
              <span className="obs-tok-out">{fmtTokens(outTok)} out</span>
            </span>
          ) : null}
          {totalDur > 0 ? <span className="obs-ng-dur"><Timer size={11} />{totalDur}ms</span> : null}
          <span className="obs-ng-count">{group.events.length} event{group.events.length !== 1 ? 's' : ''}</span>
        </span>
        <span className="obs-ng-chevron">{open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="obs-ng-body"
          >
            {group.events.map((ev, i) => <EventRow key={ev.id ?? i} event={ev} />)}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

// ── Main modal ─────────────────────────────────────────────────────────────

export function ObservabilityModal({ issue, onClose }: { issue: Issue; onClose: () => void }) {
  const sessionId = issue.latest_execution_session_id || issue.execution_session_id;
  const [copied, setCopied] = useState(false);

  const query = useQuery({
    queryKey: ['obs', sessionId || `issue-${issue.id}`],
    queryFn: async (): Promise<ObsData | null> => {
      if (!sessionId) {
        const list = await apiJson<{ items: ObsSession[] }>(`/agent/executions?issue_id=${issue.id}&limit=1`);
        const latest = list.items[0];
        if (!latest) return null;
        return apiJson<ObsData>(`/agent/executions/${latest.session_id}/graph`);
      }
      return apiJson<ObsData>(`/agent/executions/${sessionId}/graph`);
    },
    refetchInterval: (q) => {
      const s = q.state.data?.session?.status;
      return s === 'running' || s === 'in_progress' || s === 'queued' ? 3000 : false;
    },
    retry: 1,
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose(); }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const session = query.data?.session ?? null;
  const events = query.data?.events ?? [];
  const groups = groupByNode(events);

  const totalIn = events.reduce((s, e) => s + (e.input_tokens ?? 0), 0);
  const totalOut = events.reduce((s, e) => s + (e.output_tokens ?? 0), 0);
  const totalTokens = totalIn + totalOut;
  const succeeded = events.filter((e) => e.status === 'succeeded').length;
  const failed = events.filter((e) => e.status === 'failed').length;
  const agentMs = events.reduce((s, e) => s + (e.duration_ms ?? 0), 0);
  const isLive = session?.status === 'running' || session?.status === 'in_progress';

  function copyTrace() {
    const lines = [
      `=== Observability Trace ===`,
      `Issue:    ${issue.id} | ${issue.shortSvc} | ${issue.err}`,
      `Session:  ${session?.session_id ?? 'N/A'}`,
      `Workflow: ${session?.workflow_key ?? 'N/A'} v${session?.workflow_version ?? '?'}`,
      `Status:   ${session?.status ?? 'N/A'}`,
      `Started:  ${session?.started_at ?? 'N/A'}`,
      `Ended:    ${session?.ended_at ?? 'N/A'}`,
      `Tokens:   ${totalIn} in / ${totalOut} out (${totalTokens} total)`,
      `Events:   ${events.length} | OK: ${succeeded} | ERR: ${failed}`,
      '',
    ];
    events.forEach((ev, i) => {
      lines.push(`[${i + 1}] ${ev.node_name || ev.node_id || ''} | ${ev.event_type} | ${ev.status || ''} | ${ev.created_at ? new Date(ev.created_at).toLocaleTimeString('en-IN', { hour12: false }) : ''}`);
      if (ev.title) lines.push(`  Title:     ${ev.title}`);
      if (ev.input_summary) lines.push(`  Input:     ${ev.input_summary}`);
      if (ev.output_summary) lines.push(`  Output:    ${ev.output_summary}`);
      if (ev.reasoning_summary) lines.push(`  Reasoning: ${ev.reasoning_summary}`);
      if (ev.error_message) lines.push(`  Error:     ${ev.error_message}`);
      if (ev.input_tokens != null || ev.output_tokens != null)
        lines.push(`  Tokens:    ${ev.input_tokens ?? 0} in / ${ev.output_tokens ?? 0} out`);
      if (ev.duration_ms != null) lines.push(`  Duration:  ${ev.duration_ms}ms`);
    });
    navigator.clipboard.writeText(lines.join('\n')).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const { cls: sessCls } = statusMeta(session?.status ?? null);

  return (
    <div
      className="modal-ov"
      role="dialog"
      aria-modal="true"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.94, y: 12 }}
        transition={{ type: 'spring', damping: 24, stiffness: 300 }}
        className="modal obs-modal"
      >
        {/* ── Header ── */}
        <div className="obs-hdr">
          <div className="obs-hdr-left">
            <span className="obs-hdr-icon"><Activity size={16} /></span>
            <div>
              <div className="obs-hdr-title">
                Agent Observability
                <span className="obs-hdr-issue">#{issue.id}</span>
                {isLive ? <span className="obs-live-pill"><span className="obs-live-dot" />LIVE</span> : null}
              </div>
              <div className="obs-hdr-sub">{issue.shortSvc} · {issue.err}</div>
            </div>
          </div>
          <div className="obs-hdr-actions">
            <button className="obs-btn-secondary" onClick={copyTrace}>
              {copied ? <Check size={13} /> : <Copy size={13} />}
              {copied ? 'Copied' : 'Copy trace'}
            </button>
            <button className="obs-btn-close" onClick={onClose}><X size={14} /></button>
          </div>
        </div>

        {/* ── Body ── */}
        <div className="obs-body">
          {query.isLoading ? (
            <div className="obs-loading">
              <Loader2 size={22} className="obs-spin" />
              <span>Loading trace…</span>
            </div>
          ) : !session ? (
            <div className="obs-empty">
              <Activity size={28} />
              <div className="obs-empty-title">No execution found</div>
              <div className="obs-empty-sub">Use <strong>Invoke AI</strong> on this issue to start an agent run.</div>
            </div>
          ) : (
            <>
              {/* ── Session card ── */}
              <div className="obs-session-card">
                <div className="obs-sc-row">
                  <span className={clsx('obs-status-badge', sessCls)}>
                    {statusMeta(session.status).icon} {session.status}
                  </span>
                  <span className="obs-sc-workflow"><GitBranch size={12} /> {session.workflow_key} <span className="obs-sc-ver">v{session.workflow_version}</span></span>
                  {session.started_by ? <span className="obs-sc-by"><User size={12} /> {session.started_by}</span> : null}
                </div>
                <div className="obs-sc-times">
                  <span><Clock size={11} /> Started {fmtTs(session.started_at)}</span>
                  {session.ended_at ? <span>· Ended {fmtTs(session.ended_at)}</span> : null}
                  {fmtDuration(session.started_at, session.ended_at) ? <span>· {fmtDuration(session.started_at, session.ended_at)}</span> : null}
                </div>
                {session.summary ? <div className="obs-sc-summary">{session.summary}</div> : null}
                {session.error_message ? (
                  <div className="obs-sc-error"><AlertTriangle size={12} /> {session.error_message}</div>
                ) : null}
              </div>

              {/* ── Stats row ── */}
              {events.length > 0 ? (
                <div className="obs-stats">
                  <StatPill icon={<Layers size={14} />} label="Events" value={String(events.length)} accent="neutral" />
                  <StatPill icon={<CheckCircle2 size={14} />} label="Succeeded" value={String(succeeded)} accent="green" />
                  {failed > 0 ? <StatPill icon={<XCircle size={14} />} label="Failed" value={String(failed)} accent="red" /> : null}
                  {agentMs > 0 ? <StatPill icon={<Zap size={14} />} label="Agent time" value={agentMs >= 1000 ? `${(agentMs / 1000).toFixed(1)}s` : `${agentMs}ms`} accent="blue" /> : null}
                  {totalTokens > 0 ? (
                    <StatPill
                      icon={<Coins size={14} />}
                      label="Total tokens"
                      value={fmtTokens(totalTokens)}
                      sub={`${fmtTokens(totalIn)} in · ${fmtTokens(totalOut)} out`}
                      accent="purple"
                    />
                  ) : null}
                </div>
              ) : null}

              {/* ── Trace ── */}
              <div className="obs-trace">
                {events.length === 0 ? (
                  <div className="obs-empty obs-empty-sm">
                    {isLive
                      ? <><Loader2 size={16} className="obs-spin" /> Agent is running — events will appear shortly.</>
                      : <><Activity size={16} /> No execution events recorded.</>}
                  </div>
                ) : (
                  <div className="obs-groups">
                    {groups.map((g) => <NodeGroup key={g.key} group={g} />)}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}

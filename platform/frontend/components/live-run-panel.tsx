"use client";

import { useEffect, useRef } from "react";

import { Run, RunEvent } from "@/lib/types";

import { StatusPill } from "./status-pill";

const PIPELINE_NODES = [
  { id: "trigger_router", title: "Trigger Router" },
  { id: "incident_daddy", title: "Incident Daddy" },
  { id: "sme_agent", title: "SME Agent" },
  { id: "bug_daddy", title: "Bug Daddy" },
  { id: "reviewer_daddy", title: "Reviewer Daddy" },
  { id: "platform", title: "Platform" },
];

function nodeStats(nodeId: string, events: RunEvent[]) {
  const nodeEvents = events.filter((e) => e.node_name === nodeId);
  const tools = nodeEvents.filter((e) => e.event_type === "tool_call").length;
  const handoffs = nodeEvents.filter((e) => e.event_type === "agent_handoff").length;
  const tokens = nodeEvents.reduce((sum, e) => {
    const usage = e.metadata_json?.token_usage as { total_tokens?: number } | undefined;
    return sum + (typeof usage?.total_tokens === "number" ? usage.total_tokens : 0);
  }, 0);
  return { count: nodeEvents.length, tools, handoffs, tokens };
}

function aggregateStats(events: RunEvent[]) {
  let totalTokens = 0;
  let toolCalls = 0;
  let handoffs = 0;

  for (const e of events) {
    if (e.event_type === "tool_call") toolCalls++;
    if (e.event_type === "agent_handoff") handoffs++;
    const usage = e.metadata_json?.token_usage as { total_tokens?: number } | undefined;
    if (typeof usage?.total_tokens === "number") totalTokens += usage.total_tokens;
  }
  return { totalTokens, toolCalls, handoffs, totalEvents: events.length };
}

function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function EventMeta({ event }: { event: RunEvent }) {
  const meta = event.metadata_json;
  const parts: string[] = [];

  if (typeof meta.thought_summary === "string" && meta.thought_summary.length > 0) {
    parts.push(`Thinking: ${meta.thought_summary}`);
  }
  if (typeof meta.tool_name === "string") {
    let toolLine = `Tool: ${meta.tool_name}`;
    if (meta.arguments && typeof meta.arguments === "object") {
      toolLine += `(${JSON.stringify(meta.arguments)})`;
    }
    parts.push(toolLine);
  }
  if (typeof meta.result_preview === "string") {
    parts.push(`Result: ${meta.result_preview}`);
  }
  if (meta.from && meta.to && typeof meta.from === "string" && typeof meta.to === "string") {
    parts.push(`Handoff: ${meta.from} -> ${meta.to}`);
  }
  if (meta.token_usage && typeof meta.token_usage === "object") {
    const t = meta.token_usage as { input_tokens?: number; output_tokens?: number; total_tokens?: number };
    parts.push(`Tokens: ${t.input_tokens ?? 0} in / ${t.output_tokens ?? 0} out / ${t.total_tokens ?? 0} total`);
  }
  if (typeof meta.latency_ms === "number") {
    parts.push(`Latency: ${meta.latency_ms}ms`);
  }
  if (typeof meta.mode === "string") {
    parts.push(`Mode: ${meta.mode}`);
  }

  if (!parts.length) return null;

  return (
    <div className="live-event__meta">
      {parts.map((part, i) => (
        <span key={i}>{part}</span>
      ))}
    </div>
  );
}

export function LiveRunPanel({ run, issueTitle }: { run: Run; issueTitle?: string | null }) {
  const feedRef = useRef<HTMLDivElement | null>(null);
  const events = [...run.events].sort((a, b) => a.sequence - b.sequence);
  const agg = aggregateStats(events);
  const activeNode = run.current_agent;
  const activeIndex = PIPELINE_NODES.findIndex((n) => n.id === activeNode);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [events.length]);

  return (
    <div className="live-run-panel">
      {/* ── Header ── */}
      <div className="live-run-panel__header">
        <div>
          <span className="section-card__eyebrow">Live orchestration</span>
          <h3>{issueTitle ?? `Run ${run.run_key}`}</h3>
        </div>
        <div className="live-run-panel__status">
          <span className="live-dot" />
          <StatusPill label={run.status} />
          <span>{run.duration_seconds ? `${Math.round(run.duration_seconds)}s` : "streaming"}</span>
        </div>
      </div>

      {/* ── Pipeline strip ── */}
      <div className="live-pipeline">
        {PIPELINE_NODES.map((node, index) => {
          const stats = nodeStats(node.id, events);
          const state =
            activeNode === node.id
              ? "active"
              : activeIndex >= 0 && index < activeIndex
                ? "completed"
                : stats.count > 0
                  ? "completed"
                  : "idle";

          return (
            <div className={`live-pipeline__node live-pipeline__node--${state}`} key={node.id}>
              <div className="live-pipeline__node-header">
                <strong>{node.title}</strong>
                <StatusPill label={stats.count ? state : "idle"} />
              </div>
              <div className="live-pipeline__node-stats">
                <span>{stats.count} events</span>
                <span>{stats.tools} tools</span>
                <span>{stats.tokens} tok</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Aggregate stats bar ── */}
      <div className="live-run-panel__agg">
        <span>{agg.totalEvents} events</span>
        <span>{agg.toolCalls} tool calls</span>
        <span>{agg.handoffs} handoffs</span>
        <span>{agg.totalTokens.toLocaleString()} tokens</span>
      </div>

      {/* ── Live event feed ── */}
      <div className="live-feed" ref={feedRef}>
        {events.length === 0 && (
          <div className="empty-state">Waiting for first event...</div>
        )}
        {events.map((event) => (
          <div className={`live-event live-event--${event.event_type}`} key={event.id}>
            <div className="live-event__header">
              <span className="live-event__time">{formatTime(event.created_at)}</span>
              <span className="live-event__node">{event.node_name}</span>
              <StatusPill label={event.event_type} />
              <StatusPill label={event.status} />
            </div>
            <div className="live-event__body">
              <strong>{event.title}</strong>
              <p>{event.detail}</p>
            </div>
            <EventMeta event={event} />
          </div>
        ))}
      </div>
    </div>
  );
}

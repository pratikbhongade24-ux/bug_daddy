"use client";

import { useMemo, useState } from "react";
import { RunEvent } from "@/lib/types";

type InspectorTab = "overview" | "events" | "tools" | "metrics";

const AGENT_INFO: Record<string, { label: string; subtitle: string }> = {
  trigger_router: { label: "Trigger Router", subtitle: "Normalize & route signals" },
  incident_daddy: { label: "Incident Daddy", subtitle: "Triage, Slack, Jira, escalation" },
  sme_agent: { label: "SME Agent", subtitle: "SOPs, ownership, historical guidance" },
  bug_daddy: { label: "Bug Daddy", subtitle: "Plan, gather, fix, critique" },
  reviewer_daddy: { label: "Reviewer Daddy", subtitle: "Final review, PR or Jira path" },
  platform: { label: "Platform", subtitle: "Finalize artifacts and publish" },
};

function statusColor(status: string): string {
  if (status === "success" || status === "resolved") return "#22c55e";
  if (status === "failed" || status === "error") return "#ef4444";
  if (status === "running" || status === "info") return "#3b82f6";
  return "#52525b";
}

export function NodeInspector({ nodeId, events }: { nodeId: string | null; events: RunEvent[] }) {
  const [tab, setTab] = useState<InspectorTab>("overview");

  const nodeEvents = useMemo(
    () => (nodeId ? events.filter((e) => e.node_name === nodeId) : []),
    [nodeId, events],
  );

  const toolEvents = useMemo(() => nodeEvents.filter((e) => e.event_type === "tool_call"), [nodeEvents]);

  const thinkingEvents = useMemo(
    () => nodeEvents.filter((e) => typeof e.metadata_json?.thought_summary === "string"),
    [nodeEvents],
  );

  const tokenInput = useMemo(
    () =>
      nodeEvents.reduce((s, e) => {
        const u = e.metadata_json?.token_usage as { input_tokens?: number } | undefined;
        return s + (typeof u?.input_tokens === "number" ? u.input_tokens : 0);
      }, 0),
    [nodeEvents],
  );

  const tokenOutput = useMemo(
    () =>
      nodeEvents.reduce((s, e) => {
        const u = e.metadata_json?.token_usage as { output_tokens?: number } | undefined;
        return s + (typeof u?.output_tokens === "number" ? u.output_tokens : 0);
      }, 0),
    [nodeEvents],
  );

  const tokenTotal = useMemo(
    () =>
      nodeEvents.reduce((s, e) => {
        const u = e.metadata_json?.token_usage as { total_tokens?: number } | undefined;
        return s + (typeof u?.total_tokens === "number" ? u.total_tokens : 0);
      }, 0),
    [nodeEvents],
  );

  const latency = useMemo(() => {
    const e = nodeEvents.find((ev) => typeof ev.metadata_json?.latency_ms === "number");
    return e?.metadata_json?.latency_ms as number | undefined;
  }, [nodeEvents]);

  const lastReasoning = useMemo(() => {
    const step = [...nodeEvents]
      .reverse()
      .find((e) => ["agent_step", "review_note", "resolution"].includes(e.event_type));
    return step?.detail ?? null;
  }, [nodeEvents]);

  const lastStatus = nodeEvents.at(-1)?.status ?? "idle";

  if (!nodeId) {
    return (
      <div className="wb-inspector">
        <div className="wb-inspector__empty">Click a node to inspect</div>
      </div>
    );
  }

  const info = AGENT_INFO[nodeId] ?? { label: nodeId, subtitle: "" };

  return (
    <div className="wb-inspector">
      <div className="wb-inspector__head">
        <div className="wb-inspector__name">{info.label}</div>
        <div className="wb-inspector__status-row">
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "999px",
              background: statusColor(lastStatus),
              flexShrink: 0,
            }}
          />
          <span>{lastStatus}</span>
          <span style={{ marginLeft: "auto", color: "#3f3f46" }}>{nodeEvents.length} events</span>
        </div>
      </div>

      <div className="wb-inspector__tabs">
        {(["overview", "events", "tools", "metrics"] as InspectorTab[]).map((t) => (
          <button
            key={t}
            className={`wb-inspector__tab${tab === t ? " wb-inspector__tab--active" : ""}`}
            onClick={() => setTab(t)}
            type="button"
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div className="wb-inspector__content">
        {tab === "overview" && (
          <>
            <div className="wb-inspector__section">
              <div className="wb-inspector__section-title">Summary</div>
              <div className="wb-inspector__stat-row">
                <div className="wb-inspector__stat">
                  <div className="wb-inspector__stat-label">Events</div>
                  <div className="wb-inspector__stat-value">{nodeEvents.length}</div>
                </div>
                <div className="wb-inspector__stat">
                  <div className="wb-inspector__stat-label">Tool calls</div>
                  <div className="wb-inspector__stat-value">{toolEvents.length}</div>
                </div>
                <div className="wb-inspector__stat">
                  <div className="wb-inspector__stat-label">Tokens</div>
                  <div className="wb-inspector__stat-value">{tokenTotal.toLocaleString()}</div>
                </div>
              </div>
            </div>

            {lastReasoning && (
              <div className="wb-inspector__section">
                <div className="wb-inspector__section-title">Reasoning</div>
                <div className="wb-inspector__text">{lastReasoning}</div>
              </div>
            )}

            {thinkingEvents.length > 0 && (
              <div className="wb-inspector__section">
                <div className="wb-inspector__section-title">Thinking</div>
                {thinkingEvents.map((e) => (
                  <div key={e.id} className="wb-inspector__thinking">
                    {e.metadata_json.thought_summary as string}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {tab === "events" &&
          (nodeEvents.length === 0 ? (
            <div style={{ color: "#3f3f46", padding: "20px 0" }}>No events for this agent.</div>
          ) : (
            nodeEvents.map((e) => (
              <div key={e.id} className="wb-inspector__event-card">
                <div className="wb-inspector__event-head">
                  <div className="wb-inspector__event-title">{e.title}</div>
                  <span className={`wb-inspector__event-type wb-inspector__event-type--${e.event_type}`}>
                    {e.event_type.replaceAll("_", " ")}
                  </span>
                </div>
                <div className="wb-inspector__event-detail">{e.detail}</div>
                <div className="wb-inspector__event-meta">{e.created_at}</div>
              </div>
            ))
          ))}

        {tab === "tools" &&
          (toolEvents.length === 0 ? (
            <div style={{ color: "#3f3f46", padding: "20px 0" }}>No tool calls from this agent.</div>
          ) : (
            toolEvents.map((e) => {
              const toolName =
                typeof e.metadata_json?.tool_name === "string" ? e.metadata_json.tool_name : "Tool";
              const args = e.metadata_json?.arguments
                ? JSON.stringify(e.metadata_json.arguments, null, 2)
                : null;
              const result =
                typeof e.metadata_json?.result_preview === "string"
                  ? e.metadata_json.result_preview
                  : null;
              return (
                <div key={e.id} className="wb-inspector__tool-card">
                  <div className="wb-inspector__tool-name">{toolName}</div>
                  {args && <div className="wb-inspector__tool-code">{args}</div>}
                  {result && (
                    <div className="wb-inspector__tool-code wb-inspector__tool-result">→ {result}</div>
                  )}
                  <div className="wb-inspector__event-meta">{e.created_at}</div>
                </div>
              );
            })
          ))}

        {tab === "metrics" && (
          <div className="wb-inspector__section">
            <div className="wb-inspector__section-title">Token Usage</div>
            <div className="wb-inspector__metric-grid">
              <div className="wb-inspector__stat">
                <div className="wb-inspector__stat-label">Input</div>
                <div className="wb-inspector__stat-value">{tokenInput.toLocaleString()}</div>
              </div>
              <div className="wb-inspector__stat">
                <div className="wb-inspector__stat-label">Output</div>
                <div className="wb-inspector__stat-value">{tokenOutput.toLocaleString()}</div>
              </div>
              <div className="wb-inspector__stat">
                <div className="wb-inspector__stat-label">Total</div>
                <div className="wb-inspector__stat-value">{tokenTotal.toLocaleString()}</div>
              </div>
              <div className="wb-inspector__stat">
                <div className="wb-inspector__stat-label">Latency</div>
                <div className="wb-inspector__stat-value">{latency ? `${latency}ms` : "—"}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

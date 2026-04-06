"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { RunEvent } from "@/lib/types";

type ConsoleTab = "terminal" | "events" | "tools" | "tokens";

const AGENT_ORDER = [
  "trigger_router",
  "incident_daddy",
  "sme_agent",
  "bug_daddy",
  "reviewer_daddy",
  "platform",
];

function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function lineClass(eventType: string): string {
  if (eventType === "tool_call") return " wb-console__line--tool";
  if (eventType === "agent_handoff") return " wb-console__line--handoff";
  if (eventType === "resolution") return " wb-console__line--success";
  return "";
}

export function RunConsole({ events }: { events: RunEvent[] }) {
  const [tab, setTab] = useState<ConsoleTab>("terminal");
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [events, tab]);

  const majorEvents = useMemo(
    () =>
      events.filter((e) =>
        ["agent_step", "review_note", "resolution", "trigger_received", "agent_handoff"].includes(
          e.event_type,
        ),
      ),
    [events],
  );

  const toolEvents = useMemo(() => events.filter((e) => e.event_type === "tool_call"), [events]);

  const tokenSummary = useMemo(() => {
    const byAgent: Record<string, { input: number; output: number; total: number }> = {};
    for (const e of events) {
      const usage = e.metadata_json?.token_usage as
        | { input_tokens?: number; output_tokens?: number; total_tokens?: number }
        | undefined;
      if (!usage) continue;
      if (!byAgent[e.node_name]) byAgent[e.node_name] = { input: 0, output: 0, total: 0 };
      byAgent[e.node_name].input += usage.input_tokens ?? 0;
      byAgent[e.node_name].output += usage.output_tokens ?? 0;
      byAgent[e.node_name].total += usage.total_tokens ?? 0;
    }
    return AGENT_ORDER.filter((a) => byAgent[a]).map((a) => ({ agent: a, ...byAgent[a] }));
  }, [events]);

  const totalTokens = tokenSummary.reduce((s, t) => s + t.total, 0);

  const TABS: { key: ConsoleTab; label: string }[] = [
    { key: "terminal", label: "Terminal" },
    { key: "events", label: "Events" },
    { key: "tools", label: "Tool Calls" },
    { key: "tokens", label: "Tokens" },
  ];

  return (
    <div className="wb-console">
      <div className="wb-console__tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`wb-console__tab${tab === t.key ? " wb-console__tab--active" : ""}`}
            onClick={() => setTab(t.key)}
            type="button"
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="wb-console__body" ref={bodyRef}>
        {tab === "terminal" &&
          (events.length === 0 ? (
            <div className="wb-console__empty">Waiting for events...</div>
          ) : (
            events.map((e) => (
              <div key={e.id} className={`wb-console__line${lineClass(e.event_type)}`}>
                <span className="wb-console__ts">{formatTime(e.created_at)}</span>{" "}
                <span className="wb-console__agent">[{e.node_name}]</span>{" "}
                <span className="wb-console__type">{e.event_type}</span> {e.title}
                {e.detail ? ` — ${e.detail}` : ""}
              </div>
            ))
          ))}

        {tab === "events" &&
          (majorEvents.length === 0 ? (
            <div className="wb-console__empty">No major events yet.</div>
          ) : (
            majorEvents.map((e) => (
              <div key={e.id} className={`wb-console__line${lineClass(e.event_type)}`}>
                <span className="wb-console__ts">{formatTime(e.created_at)}</span>{" "}
                <span className="wb-console__agent">[{e.node_name}]</span>{" "}
                <strong>{e.title}</strong> {e.detail}
              </div>
            ))
          ))}

        {tab === "tools" &&
          (toolEvents.length === 0 ? (
            <div className="wb-console__empty">No tool calls recorded.</div>
          ) : (
            toolEvents.map((e) => {
              const toolName =
                typeof e.metadata_json?.tool_name === "string" ? e.metadata_json.tool_name : "unknown";
              const args = e.metadata_json?.arguments ? JSON.stringify(e.metadata_json.arguments) : "";
              const result =
                typeof e.metadata_json?.result_preview === "string"
                  ? e.metadata_json.result_preview
                  : "";
              return (
                <div key={e.id} className="wb-console__line wb-console__line--tool">
                  <span className="wb-console__ts">{formatTime(e.created_at)}</span>{" "}
                  <span className="wb-console__agent">[{e.node_name}]</span>{" "}
                  <strong>{toolName}</strong>
                  {args ? ` args=${args}` : ""}
                  {result ? ` → ${result}` : ""}
                </div>
              );
            })
          ))}

        {tab === "tokens" && (
          <div className="wb-token-grid">
            <div className="wb-token-card">
              <div className="wb-token-card__label">Total tokens</div>
              <div className="wb-token-card__value">{totalTokens.toLocaleString()}</div>
            </div>
            {tokenSummary.map((t) => (
              <div className="wb-token-card" key={t.agent}>
                <div className="wb-token-card__label">{t.agent.replaceAll("_", " ")}</div>
                <div className="wb-token-card__value">{t.total.toLocaleString()}</div>
                <div className="wb-token-card__detail">
                  in: {t.input.toLocaleString()} · out: {t.output.toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

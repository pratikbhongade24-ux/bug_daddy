import { RunEvent } from "@/lib/types";

import { StatusPill } from "./status-pill";

const NODE_ORDER = ["trigger_router", "incident_daddy", "sme_agent", "bug_daddy", "reviewer_daddy", "platform"];

function getSessionId(events: RunEvent[]): string {
  const first = events.find((event) => typeof event.metadata_json.session_id === "string");
  return (first?.metadata_json.session_id as string | undefined) ?? "session-unavailable";
}

function getTokenTotal(events: RunEvent[]): number {
  return events.reduce((total, event) => {
    if (event.event_type !== "agent_step" && event.event_type !== "review_note" && event.event_type !== "resolution") {
      return total;
    }
    const usage = event.metadata_json.token_usage as { total_tokens?: unknown } | undefined;
    return total + (typeof usage?.total_tokens === "number" ? usage.total_tokens : 0);
  }, 0);
}

function getLatestStatus(events: RunEvent[]): string {
  return events.at(-1)?.status ?? "neutral";
}

export function AgentSessionList({ events }: { events: RunEvent[] }) {
  const grouped = NODE_ORDER.map((nodeName) => ({
    nodeName,
    events: events.filter((event) => event.node_name === nodeName),
  })).filter((entry) => entry.events.length > 0);

  if (!grouped.length) {
    return <div className="empty-state">No agent sessions have been recorded for this run yet.</div>;
  }

  return (
    <div className="session-grid">
      {grouped.map((entry) => {
        const toolCount = entry.events.filter((event) => event.event_type === "tool_call").length;
        const handoffCount = entry.events.filter((event) => event.event_type === "agent_handoff").length;

        return (
          <div className="session-card" key={entry.nodeName}>
            <div className="session-card__header">
              <div>
                <span className="section-card__eyebrow">{entry.nodeName.replaceAll("_", " ")}</span>
                <h3>{getSessionId(entry.events)}</h3>
              </div>
              <StatusPill label={getLatestStatus(entry.events)} />
            </div>
            <div className="session-card__metrics">
              <span>{entry.events.length} events</span>
              <span>{toolCount} tools</span>
              <span>{handoffCount} handoffs</span>
              <span>{getTokenTotal(entry.events)} tokens</span>
            </div>
            <div className="session-card__events">
              {entry.events.map((event) => (
                <div className="session-event" key={event.id}>
                  <div className="session-event__header">
                    <strong>{event.title}</strong>
                    <StatusPill label={event.event_type} />
                  </div>
                  <p>{event.detail}</p>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

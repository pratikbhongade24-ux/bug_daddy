import { Run, RunEvent } from "@/lib/types";

import { StatusPill } from "./status-pill";

const NODE_DEFS = [
  { id: "trigger_router", title: "Trigger Router", caption: "Normalize input and choose the execution lane." },
  { id: "incident_daddy", title: "Incident Daddy", caption: "Triage severity, Slack thread, Jira incident context." },
  { id: "sme_agent", title: "SME Agent", caption: "Retrieve SOPs, ownership, historical fixes, and context." },
  { id: "bug_daddy", title: "Bug Daddy", caption: "Gather code and logs, form a remediation, critique it." },
  { id: "reviewer_daddy", title: "Reviewer Daddy", caption: "Decide whether to publish a PR or a Jira-only resolution." },
  { id: "platform", title: "Platform", caption: "Finalize artifacts and publish the run outcome." },
];

function readTokenTotal(event: RunEvent | undefined): number {
  const candidate = event?.metadata_json?.token_usage as { total_tokens?: unknown } | undefined;
  return typeof candidate?.total_tokens === "number" ? candidate.total_tokens : 0;
}

function summarizeNode(nodeId: string, events: RunEvent[]) {
  const nodeEvents = events.filter((event) => event.node_name === nodeId);
  const primaryEvent =
    [...nodeEvents]
      .reverse()
      .find((event) => ["agent_step", "review_note", "resolution", "trigger_received"].includes(event.event_type)) ??
    nodeEvents.at(-1);

  return {
    events: nodeEvents,
    eventCount: nodeEvents.length,
    toolCount: nodeEvents.filter((event) => event.event_type === "tool_call").length,
    handoffCount: nodeEvents.filter((event) => event.event_type === "agent_handoff").length,
    tokenTotal: readTokenTotal(primaryEvent),
    lastDetail: primaryEvent?.detail ?? "No activity yet.",
    status: primaryEvent?.status ?? "neutral",
  };
}

export function RunCanvas({ run }: { run: Run | null | undefined }) {
  const events = run?.events ?? [];
  const activeNode = run?.current_agent ?? null;

  return (
    <div className="run-canvas">
      <div className="run-canvas__header">
        <div>
          <span className="section-card__eyebrow">Invocation graph</span>
          <h3>{run ? `Run ${run.run_key}` : "No active run selected"}</h3>
        </div>
        <div className="run-canvas__meta">
          <StatusPill label={run?.status ?? "idle"} />
          <span>{run?.duration_seconds ? `${Math.round(run.duration_seconds)}s total` : "Live stream"}</span>
        </div>
      </div>

      <div className="run-canvas__grid">
        {NODE_DEFS.map((node, index) => {
          const summary = summarizeNode(node.id, events);
          const state =
            activeNode === node.id ? "active" : summary.eventCount > 0 ? (run?.status === "failed" && node.id === activeNode ? "failed" : "completed") : "idle";

          return (
            <div className={`run-node run-node--${state}`} key={node.id}>
              <div className="run-node__topline">
                <span className="run-node__index">{String(index + 1).padStart(2, "0")}</span>
                <StatusPill label={summary.eventCount ? state : "idle"} />
              </div>
              <strong>{node.title}</strong>
              <p>{node.caption}</p>
              <div className="run-node__metrics">
                <span>{summary.eventCount} events</span>
                <span>{summary.toolCount} tools</span>
                <span>{summary.tokenTotal} tokens</span>
              </div>
              <div className="run-node__detail">{summary.lastDetail}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

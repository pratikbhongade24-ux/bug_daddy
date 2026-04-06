const NODES = [
  { id: "trigger_router", title: "Trigger Router", caption: "Normalize and route incoming signals" },
  { id: "incident_daddy", title: "Incident Daddy", caption: "Triage, Slack, Jira, escalation" },
  { id: "sme_agent", title: "SME Agent", caption: "SOPs, ownership, historical guidance" },
  { id: "bug_daddy", title: "Bug Daddy", caption: "Plan, gather, fix, critique" },
  { id: "reviewer_daddy", title: "Reviewer Daddy", caption: "Final review, PR or Jira path" },
];

export function OrchestrationBoard({
  currentAgent,
  activeIssueTitle,
}: {
  currentAgent?: string | null;
  activeIssueTitle?: string | null;
}) {
  const activeIndex = NODES.findIndex((item) => item.id === currentAgent);

  return (
    <div className="orchestration-board">
      <div className="orchestration-board__meta">
        <div>
          <span className="section-card__eyebrow">Live agent chain</span>
          <h3>{activeIssueTitle ?? "Awaiting next trigger"}</h3>
        </div>
        <span className="orchestration-board__annotation">
          {currentAgent ? `Current focus: ${currentAgent.replaceAll("_", " ")}` : "No run in progress"}
        </span>
      </div>
      <div className="orchestration-board__grid">
        {NODES.map((node, index) => {
          const state =
            currentAgent === node.id ? "active" : activeIndex >= 0 && index < activeIndex ? "completed" : "idle";
          return (
            <div className={`orchestration-node orchestration-node--${state}`} key={node.id}>
              <span className="orchestration-node__step">{index + 1}</span>
              <strong>{node.title}</strong>
              <p>{node.caption}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

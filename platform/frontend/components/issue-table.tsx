import Link from "next/link";

import { Issue } from "@/lib/types";

import { StatusPill } from "./status-pill";

export function IssueTable({ issues }: { issues: Issue[] }) {
  if (!issues.length) {
    return <div className="empty-state">No issues yet. Launch a scenario to watch the control plane animate.</div>;
  }

  return (
    <div className="issue-table">
      <div className="issue-table__header">
        <span>Issue</span>
        <span>Service</span>
        <span>Severity</span>
        <span>Status</span>
        <span>Agent</span>
      </div>
      {issues.map((issue) => (
        <Link className="issue-table__row" href={`/issues/${issue.id}`} key={issue.id}>
          <div>
            <strong>{issue.title}</strong>
            <span>{issue.external_id} · {issue.issue_type}</span>
          </div>
          <span>{issue.service_name}</span>
          <StatusPill label={issue.severity} />
          <StatusPill label={issue.status} />
          <span>{issue.latest_run?.current_agent?.replaceAll("_", " ") ?? "—"}</span>
        </Link>
      ))}
    </div>
  );
}

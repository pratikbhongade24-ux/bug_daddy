type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";

const toneMap: Record<string, StatusTone> = {
  resolved: "success",
  ready: "success",
  running: "info",
  success: "success",
  info: "info",
  queued: "warning",
  open: "warning",
  needs_review: "warning",
  configured: "neutral",
  failed: "danger",
  sev1: "danger",
  sev2: "warning",
  sev3: "neutral",
  development: "neutral",
  safe: "success",
  interrupted: "danger",
  pull_request: "success",
  jira_ticket: "info",
  slack_channel: "neutral",
};

function formatLabel(label: string): string {
  return label.replaceAll("_", " ");
}

export function StatusPill({ label }: { label: string | null | undefined }) {
  const normalized = (label ?? "unknown").toLowerCase();
  const tone = toneMap[normalized] ?? "neutral";
  return <span className={`status-pill status-pill--${tone}`}>{formatLabel(label ?? "unknown")}</span>;
}

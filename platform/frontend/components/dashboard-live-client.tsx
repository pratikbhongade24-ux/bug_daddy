"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { startTransition, useDeferredValue, useEffect, useState } from "react";

import { getDashboardSummary, getIssueDetail, getWsBaseUrl, launchScenario } from "@/lib/api";
import { DashboardSummary, IssueDetail, Scenario, TriggerEvent } from "@/lib/types";

import { IssueTable } from "./issue-table";
import { LiveRunPanel } from "./live-run-panel";
import { MetricCard } from "./metric-card";
import { OrchestrationBoard } from "./orchestration-board";
import { SectionCard } from "./section-card";
import { StatusPill } from "./status-pill";

function formatMetric(value: number | string | null | undefined, suffix = ""): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return `${value}${suffix}`;
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

export function DashboardLiveClient({
  initialSummary,
  scenarios,
  triggers,
}: {
  initialSummary: DashboardSummary;
  scenarios: Scenario[];
  triggers: TriggerEvent[];
}) {
  const router = useRouter();
  const [summary, setSummary] = useState(initialSummary);
  const [launchingScenario, setLaunchingScenario] = useState<string | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [liveIssue, setLiveIssue] = useState<IssueDetail | null>(null);
  const deferredIssues = useDeferredValue(summary.recent_issues);

  const liveRun = summary.live_runs[0] ?? null;
  const liveRunId = liveRun?.run_id ?? null;
  const liveIssueId = liveRun?.issue_id ?? null;
  const topRuntime = summary.agent_runtimes.find((item) => item.name === "reviewer_daddy") ?? summary.agent_runtimes[0] ?? null;

  async function refreshSummary() {
    const next = await getDashboardSummary();
    startTransition(() => {
      setSummary(next);
    });
  }

  async function refreshLiveIssue(issueId: number) {
    const detail = await getIssueDetail(String(issueId));
    if (detail) {
      startTransition(() => {
        setLiveIssue(detail);
      });
    }
  }

  // Dashboard WebSocket — refreshes the summary
  useEffect(() => {
    const socket = new WebSocket(`${getWsBaseUrl()}/ws/dashboard`);
    const heartbeat = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send("ping");
      }
    }, 15000);

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { kind?: string };
        if (payload.kind === "dashboard_refresh") {
          void refreshSummary();
        }
      } catch {
        // Ignore non-JSON control messages.
      }
    };

    return () => {
      window.clearInterval(heartbeat);
      socket.close();
    };
  }, []);

  // Run WebSocket — streams live events for the active run
  useEffect(() => {
    if (!liveRunId || !liveIssueId) {
      setLiveIssue(null);
      return;
    }

    // Fetch the full issue detail immediately
    void refreshLiveIssue(liveIssueId);

    const socket = new WebSocket(`${getWsBaseUrl()}/ws/runs/${liveRunId}`);
    const heartbeat = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send("ping");
      }
    }, 15000);

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { kind?: string };
        if (payload.kind === "run_event") {
          void refreshLiveIssue(liveIssueId);
        }
      } catch {
        // Ignore non-JSON control messages.
      }
    };

    return () => {
      window.clearInterval(heartbeat);
      socket.close();
    };
  }, [liveRunId, liveIssueId]);

  async function handleLaunchScenario(scenarioId: string) {
    setLaunchError(null);
    setLaunchingScenario(scenarioId);
    try {
      const launched = await launchScenario(scenarioId);
      await refreshSummary();
      router.push(`/issues/${launched.issue_id}`);
    } catch (error) {
      setLaunchError(error instanceof Error ? error.message : "Unable to launch scenario.");
    } finally {
      setLaunchingScenario(null);
    }
  }

  // Resolve the active Run object from the fetched issue detail
  const activeRun = liveIssue?.runs?.find((r) => r.id === liveRunId) ?? liveIssue?.latest_run ?? null;

  return (
    <div className="dashboard-stack">
      {/* ── Hero ── */}
      <section className="hero-panel">
        <div className="hero-panel__copy">
          <span className="hero-panel__eyebrow">Production AI operations, made legible</span>
          <h2>Autonomous maintenance and incident review with a UI that stays calm under load.</h2>
          <p>
            Bug Daddy ingests logs, telemetry, Slack incidents, and replayed scenarios, then routes them through
            `incident_daddy`, `sme_agent`, `bug_daddy`, and `reviewer_daddy` with clear evidence, visible guardrails,
            and operator-grade traceability.
          </p>
          <div className="hero-panel__highlights">
            <div>
              <span>Now active</span>
              <strong>{liveRun ? `${String(liveRun.current_agent).replaceAll("_", " ")}` : "Quiet system"}</strong>
            </div>
            <div>
              <span>Resolved</span>
              <strong>{summary.metrics.resolved_issues ?? 0} completed</strong>
            </div>
            <div>
              <span>Reviewer posture</span>
              <strong>{formatPercent(topRuntime?.success_rate)}</strong>
            </div>
          </div>
        </div>

        <div className="hero-panel__rail">
          <div className="hero-panel__signal">
            <span className="live-dot" />
            <span>{summary.metrics.running_issues ? `${summary.metrics.running_issues} runs in flight` : "System ready"}</span>
          </div>
          {!activeRun && (
            <OrchestrationBoard
              currentAgent={liveRun?.current_agent as string | null | undefined}
              activeIssueTitle={liveRun ? summary.recent_issues.find((issue) => issue.id === liveRun.issue_id)?.title ?? summary.recent_issues[0]?.title : summary.recent_issues[0]?.title}
            />
          )}
        </div>
      </section>

      {/* ── Live orchestration panel (shown when a run is active) ── */}
      {activeRun && (
        <SectionCard eyebrow="Live orchestration" title="Active run">
          <LiveRunPanel
            run={activeRun}
            issueTitle={liveIssue?.title}
          />
          <div className="live-run-panel__link">
            <Link href={`/issues/${liveIssueId}`}>Open full issue detail</Link>
          </div>
        </SectionCard>
      )}

      {/* ── Metrics ── */}
      <div className="metric-grid">
        <MetricCard label="Issues resolved" value={summary.metrics.resolved_issues} accent="#1e9571" hint="Autonomous or guided outcomes completed" />
        <MetricCard label="Issues running" value={summary.metrics.running_issues} accent="#1d88c8" hint="Active orchestration sessions right now" />
        <MetricCard label="Total triggers" value={summary.metrics.total_triggers} accent="#ef8f22" hint="Signals normalized into the control plane" />
        <MetricCard label="Auto PRs" value={summary.metrics.auto_pull_requests} accent="#d05931" hint="Remediations converted into pull requests" />
        <MetricCard label="Mean resolve time" value={formatMetric(summary.metrics.mean_time_to_resolve_seconds, "s")} accent="#4d67d0" hint="Average orchestration completion time" />
        <MetricCard label="Engineer hours saved" value={summary.metrics.estimated_engineer_hours_saved} accent="#8c4dd0" hint="Estimated time returned to product teams" />
      </div>

      {/* ── Row 1: Issues + Trust ── */}
      <div className="dashboard-grid dashboard-grid--primary">
        <SectionCard eyebrow="Issue radar" title="Latest issues" subtitle="What was triggered, what resolved, and what still needs attention.">
          <IssueTable issues={deferredIssues} />
        </SectionCard>

        <SectionCard eyebrow="Trust layer" title="Guardrails and review posture">
          <div className="insight-grid">
            <div className="insight-card insight-card--warning">
              <span className="insight-card__label">Guardrail state</span>
              <strong>{summary.guardrails[0]?.state ?? "safe"}</strong>
              <p>{summary.guardrails[0]?.message ?? "Unsafe actions are escalated rather than executed."}</p>
            </div>
            <div className="insight-card insight-card--info">
              <span className="insight-card__label">Second pair of eyes</span>
              <strong>{summary.second_pair_of_eyes.length}</strong>
              <p>Live prompts flag missed dependencies, SOP gaps, and rollback risks.</p>
            </div>
            <div className="insight-card insight-card--success">
              <span className="insight-card__label">Reviewer confidence</span>
              <strong>{formatPercent(summary.agent_runtimes.find((item) => item.name === "reviewer_daddy")?.success_rate)}</strong>
              <p>Reviewer Daddy is the final gate before a PR or Jira resolution is published.</p>
            </div>
          </div>
          {launchError ? <p className="inline-error">{launchError}</p> : null}
        </SectionCard>
      </div>

      {/* ── Row 2: Scenarios + Signal mix ── */}
      <div className="dashboard-grid dashboard-grid--secondary">
        <SectionCard eyebrow="Scenario library" title="Launch a demo scenario">
          <div className="scenario-grid">
            {scenarios.map((scenario) => (
              <button
                className="scenario-card"
                key={scenario.id}
                onClick={() => void handleLaunchScenario(scenario.id)}
                disabled={launchingScenario !== null}
                type="button"
              >
                <div className="scenario-card__header">
                  <span className="scenario-card__label">{scenario.source.replaceAll("_", " ")}</span>
                  <StatusPill label={scenario.severity} />
                </div>
                <strong>{scenario.title}</strong>
                <p>{scenario.summary}</p>
                <div className="scenario-card__meta">
                  <span>{scenario.service_name}</span>
                  <span>{scenario.recurrence_count} repeats</span>
                </div>
                <span className="scenario-card__action">
                  {launchingScenario === scenario.id ? "Launching..." : "Launch scenario"}
                </span>
              </button>
            ))}
          </div>
        </SectionCard>

        <SectionCard eyebrow="Signal mix" title="Where pressure is building">
          <div className="barlist-grid">
            <div>
              <h3 className="mini-heading">By trigger source</h3>
              <div className="bar-list">
                {summary.trigger_breakdown.map((item) => (
                  <div className="bar-row" key={item.source}>
                    <div className="bar-row__copy">
                      <strong>{item.source.replaceAll("_", " ")}</strong>
                      <span>{item.count}</span>
                    </div>
                    <div className="bar-row__track">
                      <div className="bar-row__fill" style={{ width: `${Math.min(item.count * 18, 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3 className="mini-heading">Service hotspots</h3>
              <div className="bar-list">
                {summary.service_hotspots.map((item) => (
                  <div className="bar-row" key={item.service_name}>
                    <div className="bar-row__copy">
                      <strong>{item.service_name}</strong>
                      <span>{item.count}</span>
                    </div>
                    <div className="bar-row__track">
                      <div className="bar-row__fill bar-row__fill--warm" style={{ width: `${Math.min(item.count * 22, 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </SectionCard>
      </div>

      {/* ── Row 3: Reasoning + Runtime fleet + Connectors ── */}
      <div className="dashboard-grid dashboard-grid--tertiary">
        <SectionCard eyebrow="Reasoning log" title="What the system actually did">
          <div className="timeline-list">
            {summary.recent_events.map((event, index) => (
              <div className="timeline-item" key={`${event.run_id}-${event.created_at}-${index}`}>
                <div className="timeline-item__badge">{String(index + 1).padStart(2, "0")}</div>
                <div className="timeline-item__body">
                  <div className="timeline-item__header">
                    <strong>{String(event.title)}</strong>
                    <StatusPill label={String(event.status)} />
                  </div>
                  <p>{String(event.detail)}</p>
                  <span>
                    {String(event.node_name)} · {String(event.created_at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard eyebrow="Runtime fleet" title="Agents and connectors">
          <div className="runtime-grid">
            {summary.agent_runtimes.map((runtime) => (
              <div className="runtime-card" key={runtime.id}>
                <div className="runtime-card__header">
                  <strong>{runtime.name}</strong>
                  <StatusPill label={runtime.status} />
                </div>
                <p>{runtime.runtime_id ?? "Awaiting ARN"}</p>
                <div className="runtime-card__stats">
                  <span>v{runtime.version}</span>
                  <span>Latency {formatMetric(runtime.average_latency_ms, "ms")}</span>
                  <span>Success {formatPercent(runtime.success_rate)}</span>
                </div>
              </div>
            ))}
            {summary.connectors.map((connector) => (
              <div className="runtime-card runtime-card--connector" key={connector.id}>
                <div className="runtime-card__header">
                  <strong>{connector.name}</strong>
                  <StatusPill label={connector.status} />
                </div>
                <p>{connector.detail}</p>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      {/* ── Row 4: Recent triggers feed ── */}
      {triggers.length > 0 && (
        <SectionCard eyebrow="Trigger feed" title="Recent ingested signals">
          <div className="trigger-feed">
            {triggers.slice(0, 6).map((trigger) => (
              <div className="trigger-item" key={trigger.id}>
                <div className="trigger-item__header">
                  <strong>{trigger.trigger_name}</strong>
                  <StatusPill label={trigger.status} />
                </div>
                <p>
                  {trigger.source} · {trigger.service_name}
                </p>
                <div className="code-panel">
                  <pre>{JSON.stringify(trigger.payload_json, null, 2)}</pre>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}

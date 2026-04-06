"use client";

import { useRouter } from "next/navigation";
import { startTransition, useCallback, useEffect, useState } from "react";

import { getIssueDetail, getWsBaseUrl, replayIssue, retryIssue } from "@/lib/api";
import { IssueDetail, Run, RunEvent } from "@/lib/types";

import { NodeInspector } from "./node-inspector";
import { RunConsole } from "./run-console";
import { RunHistoryRail } from "./run-history-rail";
import { WorkbenchToolbar } from "./workbench-toolbar";
import { WorkflowCanvas } from "./workflow-canvas";

function orderedEvents(events: RunEvent[]): RunEvent[] {
  return [...events].sort((left, right) => left.sequence - right.sequence);
}

export function IssueDetailClient({ initialIssue }: { initialIssue: IssueDetail }) {
  const router = useRouter();
  const [issue, setIssue] = useState(initialIssue);
  const [actionState, setActionState] = useState<"retry" | "replay" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);

  const runs: Run[] = issue.runs.length > 0 ? issue.runs : issue.latest_run ? [issue.latest_run] : [];
  const activeRun = runs.find((r) => r.id === selectedRunId) ?? runs[0] ?? null;
  const activeEvents = activeRun ? orderedEvents(activeRun.events) : [];

  useEffect(() => {
    if (activeRun && selectedRunId !== activeRun.id) {
      setSelectedRunId(activeRun.id);
    }
  }, [activeRun?.id]);

  async function refreshIssue() {
    const next = await getIssueDetail(String(issue.id));
    if (next) {
      startTransition(() => {
        setIssue(next);
      });
    }
  }

  useEffect(() => {
    if (!activeRun?.id) return;

    const socket = new WebSocket(`${getWsBaseUrl()}/ws/runs/${activeRun.id}`);
    const heartbeat = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 15000);

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { kind?: string };
        if (payload.kind === "run_event") void refreshIssue();
      } catch {
        // Ignore non-JSON control messages.
      }
    };

    return () => {
      window.clearInterval(heartbeat);
      socket.close();
    };
  }, [activeRun?.id, issue.id]);

  async function handleRetry() {
    setActionError(null);
    setActionState("retry");
    try {
      const response = await retryIssue(issue.id);
      router.push(`/issues/${response.issue_id}`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Action failed.");
    } finally {
      setActionState(null);
    }
  }

  async function handleReplay() {
    setActionError(null);
    setActionState("replay");
    try {
      const response = await replayIssue(issue.id);
      router.push(`/issues/${response.issue_id}`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Action failed.");
    } finally {
      setActionState(null);
    }
  }

  const onNodeSelect = useCallback((id: string) => setSelectedNode(id), []);
  const onSelectRun = useCallback((id: number) => {
    setSelectedRunId(id);
    setSelectedNode(null);
  }, []);

  return (
    <div className="wb">
      <WorkbenchToolbar
        issue={issue}
        run={activeRun}
        actionState={actionState}
        actionError={actionError}
        onRetry={() => void handleRetry()}
        onReplay={() => void handleReplay()}
      />

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <RunHistoryRail
          runs={runs}
          selectedRunId={selectedRunId}
          onSelectRun={onSelectRun}
        />

        <div className="wb-main">
          <WorkflowCanvas
            events={activeEvents}
            currentAgent={activeRun?.current_agent ?? null}
            runStatus={activeRun?.status ?? "idle"}
            selectedNode={selectedNode}
            onNodeSelect={onNodeSelect}
          />
          <RunConsole events={activeEvents} />
        </div>

        <NodeInspector nodeId={selectedNode} events={activeEvents} />
      </div>
    </div>
  );
}

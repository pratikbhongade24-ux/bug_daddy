"use client";

import { useCallback, useState } from "react";
import { IssueDetail, Run, RunEvent } from "@/lib/types";
import { WorkflowCanvas } from "./workflow-canvas";
import { NodeInspector } from "./node-inspector";
import { RunConsole } from "./run-console";
import { WorkbenchToolbar } from "./workbench-toolbar";
import { RunHistoryRail } from "./run-history-rail";

function orderedEvents(events: RunEvent[]): RunEvent[] {
  return [...events].sort((a, b) => a.sequence - b.sequence);
}

export function RunWorkbench({
  issue,
  runs,
  activeRun,
  actionState,
  actionError,
  onRetry,
  onReplay,
  onSelectRun,
}: {
  issue: IssueDetail;
  runs: Run[];
  activeRun: Run | null;
  actionState: "retry" | "replay" | null;
  actionError: string | null;
  onRetry: () => void;
  onReplay: () => void;
  onSelectRun: (id: number) => void;
}) {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const events = activeRun ? orderedEvents(activeRun.events) : [];
  const onNodeSelect = useCallback((id: string) => setSelectedNode(id), []);

  return (
    <div className="wb">
      <WorkbenchToolbar
        issue={issue}
        run={activeRun}
        actionState={actionState}
        actionError={actionError}
        onRetry={onRetry}
        onReplay={onReplay}
      />

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <RunHistoryRail
          runs={runs}
          selectedRunId={activeRun?.id ?? null}
          onSelectRun={onSelectRun}
        />

        <div className="wb-main">
          <WorkflowCanvas
            events={events}
            currentAgent={activeRun?.current_agent ?? null}
            runStatus={activeRun?.status ?? "idle"}
            selectedNode={selectedNode}
            onNodeSelect={onNodeSelect}
          />
          <RunConsole events={events} />
        </div>

        <NodeInspector nodeId={selectedNode} events={events} />
      </div>
    </div>
  );
}
"use client";

import { useCallback, useMemo } from "react";
import ReactFlow, { Background, Controls } from "reactflow";
import type { NodeMouseHandler } from "reactflow";
import "reactflow/dist/style.css";

import { RunEvent } from "@/lib/types";
import { AgentNode } from "./agent-node";
import type { AgentNodeData } from "./agent-node";

const AGENT_DEFS = [
  { id: "trigger_router", label: "Trigger Router", subtitle: "Normalize & route signals", x: 0 },
  { id: "incident_daddy", label: "Incident Daddy", subtitle: "Triage, Slack, Jira", x: 320 },
  { id: "sme_agent", label: "SME Agent", subtitle: "SOPs & historical guidance", x: 640 },
  { id: "bug_daddy", label: "Bug Daddy", subtitle: "Plan, gather, fix, critique", x: 960 },
  { id: "reviewer_daddy", label: "Reviewer Daddy", subtitle: "Final review & PR path", x: 1280 },
];

const nodeTypes = { agentNode: AgentNode };

function summarizeNode(nodeId: string, events: RunEvent[]) {
  const nodeEvents = events.filter((e) => e.node_name === nodeId);
  const toolCount = nodeEvents.filter((e) => e.event_type === "tool_call").length;
  const tokenTotal = nodeEvents.reduce((sum, e) => {
    const usage = e.metadata_json?.token_usage as { total_tokens?: number } | undefined;
    return sum + (typeof usage?.total_tokens === "number" ? usage.total_tokens : 0);
  }, 0);
  return { eventCount: nodeEvents.length, toolCount, tokenTotal };
}

export function WorkflowCanvas({
  events,
  currentAgent,
  runStatus,
  selectedNode,
  onNodeSelect,
}: {
  events: RunEvent[];
  currentAgent: string | null;
  runStatus: string;
  selectedNode: string | null;
  onNodeSelect: (id: string) => void;
}) {
  const nodes = useMemo(() => {
    const activeIndex = AGENT_DEFS.findIndex((a) => a.id === currentAgent);
    const isFinished = runStatus === "resolved" || runStatus === "success";
    const isFailed = runStatus === "failed";

    return AGENT_DEFS.map((def, i) => {
      const summary = summarizeNode(def.id, events);
      let status: AgentNodeData["status"] = "idle";

      if (isFinished) {
        status = summary.eventCount > 0 ? "completed" : "idle";
      } else if (isFailed) {
        if (currentAgent === def.id) status = "failed";
        else if (summary.eventCount > 0) status = "completed";
      } else {
        if (currentAgent === def.id) status = "active";
        else if (activeIndex >= 0 && i < activeIndex) status = "completed";
        else if (summary.eventCount > 0) status = "completed";
      }

      return {
        id: def.id,
        type: "agentNode" as const,
        position: { x: def.x, y: 0 },
        data: {
          label: def.label,
          subtitle: def.subtitle,
          status,
          eventCount: summary.eventCount,
          toolCount: summary.toolCount,
          tokenTotal: summary.tokenTotal,
          isSelected: selectedNode === def.id,
        } satisfies AgentNodeData,
      };
    });
  }, [events, currentAgent, runStatus, selectedNode]);

  const edges = useMemo(
    () =>
      AGENT_DEFS.slice(0, -1).map((def, i) => ({
        id: `e-${def.id}-${AGENT_DEFS[i + 1].id}`,
        source: def.id,
        target: AGENT_DEFS[i + 1].id,
        animated: currentAgent !== null,
        style: { stroke: "rgba(255,255,255,0.12)", strokeWidth: 2 },
      })),
    [currentAgent],
  );

  const onNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => onNodeSelect(node.id),
    [onNodeSelect],
  );

  return (
    <div className="wb-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.35 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag
        zoomOnScroll
        minZoom={0.3}
        maxZoom={1.6}
      >
        <Background color="rgba(255,255,255,0.03)" gap={24} size={1} />
        <Controls className="wb-canvas__controls" showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

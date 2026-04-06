import { memo } from "react";
import { Handle, Position } from "reactflow";
import type { NodeProps } from "reactflow";

export interface AgentNodeData {
  label: string;
  subtitle: string;
  status: "idle" | "active" | "completed" | "failed";
  eventCount: number;
  toolCount: number;
  tokenTotal: number;
  isSelected: boolean;
}

const STATUS_LABEL: Record<AgentNodeData["status"], string> = {
  idle: "Idle",
  active: "Running",
  completed: "Done",
  failed: "Failed",
};

function AgentNodeInner({ data }: NodeProps<AgentNodeData>) {
  return (
    <div
      className={`wb-agent wb-agent--${data.status}${data.isSelected ? " wb-agent--selected" : ""}`}
    >
      <Handle type="target" position={Position.Left} className="wb-agent__handle" />

      <div className="wb-agent__head">
        <span className={`wb-agent__dot wb-agent__dot--${data.status}`} />
        <span className="wb-agent__status">{STATUS_LABEL[data.status]}</span>
      </div>

      <div className="wb-agent__name">{data.label}</div>
      <div className="wb-agent__sub">{data.subtitle}</div>

      {data.eventCount > 0 && (
        <div className="wb-agent__stats">
          <span>{data.eventCount} events</span>
          <span>{data.toolCount} tools</span>
          <span>{data.tokenTotal.toLocaleString()} tok</span>
        </div>
      )}

      <Handle type="source" position={Position.Right} className="wb-agent__handle" />
    </div>
  );
}

export const AgentNode = memo(AgentNodeInner);

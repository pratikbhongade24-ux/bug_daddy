"use client";

import { useEffect, useMemo, useRef } from "react";

import { RunEvent } from "@/lib/types";

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function renderMetadata(event: RunEvent): string[] {
  const metadata = event.metadata_json;
  const lines: string[] = [];

  if (typeof metadata.log_line === "string" && metadata.log_line.length > 0) {
    lines.push(metadata.log_line);
  }

  if (typeof metadata.thought_summary === "string" && metadata.thought_summary.length > 0) {
    lines.push(`thought=${metadata.thought_summary}`);
  }

  if (typeof metadata.tool_name === "string") {
    lines.push(`tool=${metadata.tool_name}`);
  }

  if (metadata.arguments && typeof metadata.arguments === "object") {
    lines.push(`args=${JSON.stringify(metadata.arguments)}`);
  }

  if (metadata.result_preview && typeof metadata.result_preview === "string") {
    lines.push(`result=${metadata.result_preview}`);
  }

  if (metadata.from && metadata.to && typeof metadata.from === "string" && typeof metadata.to === "string") {
    lines.push(`handoff=${metadata.from}->${metadata.to}`);
  }

  if (metadata.token_usage && typeof metadata.token_usage === "object") {
    const tokenUsage = metadata.token_usage as { input_tokens?: number; output_tokens?: number; total_tokens?: number };
    lines.push(
      `tokens=in:${tokenUsage.input_tokens ?? 0} out:${tokenUsage.output_tokens ?? 0} total:${tokenUsage.total_tokens ?? 0}`,
    );
  }

  if (typeof metadata.latency_ms === "number") {
    lines.push(`latency=${metadata.latency_ms}ms`);
  }

  if (typeof metadata.mode === "string") {
    lines.push(`mode=${metadata.mode}`);
  }

  return lines;
}

function buildTerminalLines(events: RunEvent[]) {
  return events.flatMap((event) => {
    const prefix = `${formatTime(event.created_at)}  ${event.node_name.padEnd(16)}  ${event.event_type.padEnd(14)}  `;
    const baseLine = `${prefix}${event.title}`;
    const detailLine = `${" ".repeat(prefix.length)}${event.detail}`;
    const metadataLines = renderMetadata(event).map((line) => `${" ".repeat(prefix.length)}${line}`);
    return [baseLine, detailLine, ...metadataLines];
  });
}

export function RunTerminal({ events }: { events: RunEvent[] }) {
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const lines = useMemo(() => buildTerminalLines(events), [events]);

  useEffect(() => {
    if (!terminalRef.current) {
      return;
    }
    terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  }, [lines]);

  return (
    <div className="run-terminal">
      <div className="run-terminal__header">
        <div>
          <span className="section-card__eyebrow">Session terminal</span>
          <h3>Logs, tool calls, handoffs, and token accounting</h3>
        </div>
        <span>{lines.length} lines</span>
      </div>
      <div className="run-terminal__body" ref={terminalRef}>
        {lines.length ? (
          lines.map((line, index) => (
            <div className="run-terminal__line" key={`${index}-${line}`}>
              {line}
            </div>
          ))
        ) : (
          <div className="run-terminal__line">No events have been emitted for this run yet.</div>
        )}
      </div>
    </div>
  );
}

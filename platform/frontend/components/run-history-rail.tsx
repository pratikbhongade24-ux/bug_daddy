import { Run } from "@/lib/types";

function relativeTime(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  if (diff < 60_000) return "Just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

export function RunHistoryRail({
  runs,
  selectedRunId,
  onSelectRun,
}: {
  runs: Run[];
  selectedRunId: number | null;
  onSelectRun: (id: number) => void;
}) {
  return (
    <div className="wb-rail">
      <div className="wb-rail__head">
        <h3>Run History</h3>
      </div>
      <div className="wb-rail__list">
        {runs.length === 0 && <div className="wb-rail__empty">No runs yet.</div>}
        {runs.map((run) => (
          <div
            key={run.id}
            className={`wb-rail__item${run.id === selectedRunId ? " wb-rail__item--active" : ""}`}
            onClick={() => onSelectRun(run.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") onSelectRun(run.id);
            }}
          >
            <div className="wb-rail__item-title">Run #{run.run_key}</div>
            <div className="wb-rail__item-meta">
              <span className={`wb-rail__item-dot wb-rail__item-dot--${run.status}`} />
              <span>{run.status}</span>
              <span>·</span>
              <span>{formatDuration(run.duration_seconds)}</span>
            </div>
            <div className="wb-rail__item-meta">
              <span>{relativeTime(run.started_at)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

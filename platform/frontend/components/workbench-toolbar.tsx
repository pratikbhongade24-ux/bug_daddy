import Link from "next/link";
import { IssueDetail, Run } from "@/lib/types";

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function statusClass(status: string): string {
  if (status === "running") return "wb-toolbar__status--running";
  if (status === "resolved" || status === "success") return "wb-toolbar__status--resolved";
  if (status === "failed") return "wb-toolbar__status--failed";
  return "wb-toolbar__status--idle";
}

export function WorkbenchToolbar({
  issue,
  run,
  actionState,
  actionError,
  onRetry,
  onReplay,
}: {
  issue: IssueDetail;
  run: Run | null;
  actionState: "retry" | "replay" | null;
  actionError: string | null;
  onRetry: () => void;
  onReplay: () => void;
}) {
  const status = run?.status ?? "idle";

  return (
    <div className="wb-toolbar">
      <div className="wb-toolbar__left">
        <Link href="/" className="wb-toolbar__back">
          ← Back
        </Link>
        <div className="wb-toolbar__info">
          <div className="wb-toolbar__title">{issue.title}</div>
          <div className="wb-toolbar__id">
            {issue.external_id} · {issue.service_name}
          </div>
        </div>
      </div>

      <div className="wb-toolbar__center">
        <div className={`wb-toolbar__status ${statusClass(status)}`}>
          {status === "running" && <span className="wb-toolbar__pulse" />}
          {status}
        </div>
        {run && (
          <span className="wb-toolbar__timer">
            {run.duration_seconds ? formatDuration(run.duration_seconds) : "Live"}
          </span>
        )}
        {actionError && <span className="wb-toolbar__error">{actionError}</span>}
      </div>

      <div className="wb-toolbar__right">
        <button
          className="wb-toolbar__btn wb-toolbar__btn--primary"
          disabled={actionState !== null}
          onClick={onRetry}
          type="button"
        >
          {actionState === "retry" ? "Retrying..." : "Retry"}
        </button>
        <button
          className="wb-toolbar__btn"
          disabled={actionState !== null}
          onClick={onReplay}
          type="button"
        >
          {actionState === "replay" ? "Replaying..." : "Replay"}
        </button>
      </div>
    </div>
  );
}

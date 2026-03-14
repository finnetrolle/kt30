import type { TaskEvent, TaskLifecycleStatus, TaskStageUsage } from "@/entities/task/model";

interface TaskProgressPanelProps {
  taskId: string | null;
  stage: string;
  events: TaskEvent[];
  totalTokens: number;
  requestCount: number;
  elapsedSeconds: number;
  stageUsage: TaskStageUsage[];
  jobStatus: TaskLifecycleStatus | null;
  isStreaming: boolean;
  error: string | null;
  onCancel: () => Promise<void> | void;
  isCanceling: boolean;
}

function formatElapsedTime(seconds: number) {
  if (seconds < 60) {
    return `${seconds} sec`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes} min ${remainder} sec`;
}

export function TaskProgressPanel({
  taskId,
  stage,
  events,
  totalTokens,
  requestCount,
  elapsedSeconds,
  stageUsage,
  jobStatus,
  isStreaming,
  error,
  onCancel,
  isCanceling
}: TaskProgressPanelProps) {
  if (!taskId) {
    return (
      <div className="panel subtle-panel">
        <h2>Progress stream</h2>
        <p>The next uploaded task will stream worker updates here.</p>
      </div>
    );
  }

  return (
    <div className="panel progress-panel">
      <div className="section-heading">
        <div>
          <h2>Task progress</h2>
          <p>Task ID: {taskId}</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={() => void onCancel()}
          disabled={!isStreaming || isCanceling}
        >
          {isCanceling ? "Canceling..." : "Cancel task"}
        </button>
      </div>

      <div className="progress-summary">
        <div>
          <span className="summary-label">Stage</span>
          <strong>{stage}</strong>
        </div>
        <div>
          <span className="summary-label">Tokens</span>
          <strong>{totalTokens}</strong>
        </div>
        <div>
          <span className="summary-label">Requests</span>
          <strong>{requestCount}</strong>
        </div>
        <div>
          <span className="summary-label">Elapsed</span>
          <strong>{formatElapsedTime(elapsedSeconds)}</strong>
        </div>
        <div>
          <span className="summary-label">Status</span>
          <strong>{jobStatus ?? (isStreaming ? "streaming" : "idle")}</strong>
        </div>
      </div>

      {error ? <p className="error-banner">{error}</p> : null}

      {stageUsage.length > 0 ? (
        <div className="stage-usage-grid">
          {stageUsage.map((entry) => (
            <div key={entry.stage_id} className="task-card">
              <div className="task-card-header">
                <strong>Stage {entry.stage_id}</strong>
                <span className="soft-badge">{entry.usage.total_tokens} tok.</span>
              </div>
              <p>{entry.message}</p>
              <p className="muted-copy">
                Requests: {entry.request_count} | Prompt: {entry.usage.prompt_tokens} | Completion:{" "}
                {entry.usage.completion_tokens}
              </p>
            </div>
          ))}
        </div>
      ) : null}

      <div className="event-log">
        {events.length === 0 ? (
          <p className="muted-copy">Waiting for the worker to emit the first event.</p>
        ) : (
          events.map((event) => (
            <div key={`${event.type}-${event.timestamp}`} className="event-item">
              <span className={`event-badge event-${event.type}`}>{event.type}</span>
              <div>
                <strong>{event.message}</strong>
                <p>{new Date(event.timestamp * 1000).toLocaleTimeString("ru-RU")}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

import type { TaskEvent } from "@/entities/task/model";

interface TaskProgressPanelProps {
  taskId: string | null;
  stage: string;
  events: TaskEvent[];
  totalTokens: number;
  isStreaming: boolean;
  error: string | null;
  onCancel: () => Promise<void> | void;
  isCanceling: boolean;
}

export function TaskProgressPanel({
  taskId,
  stage,
  events,
  totalTokens,
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
          <span className="summary-label">Status</span>
          <strong>{isStreaming ? "Streaming" : "Idle"}</strong>
        </div>
      </div>

      {error ? <p className="error-banner">{error}</p> : null}

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

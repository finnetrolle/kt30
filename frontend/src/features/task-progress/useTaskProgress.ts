import { useEffect, useEffectEvent, useState } from "react";

import type { TaskEvent, TaskProgressSnapshot, TaskStageUsage, TokenUsageBucket } from "@/entities/task/model";
import { createTaskEventSource, getTaskProgressSnapshot } from "@/shared/api/client";
import { isDocumentVisible } from "@/shared/lib/browser";
import { translateText } from "@/shared/lib/locale";

interface UseTaskProgressOptions {
  taskId: string | null;
  enabled?: boolean;
  streamingEnabled?: boolean;
  pollIntervalMs?: number;
  compactSnapshot?: boolean;
  onComplete?: (event: TaskEvent) => void;
}

interface TaskProgressState {
  stage: string;
  events: TaskEvent[];
  isStreaming: boolean;
  totalTokens: number;
  requestCount: number;
  elapsedSeconds: number;
  stageUsage: TaskStageUsage[];
  error: string | null;
}

const INITIAL_STATE: TaskProgressState = {
  stage: "Ожидание",
  events: [],
  isStreaming: false,
  totalTokens: 0,
  requestCount: 0,
  elapsedSeconds: 0,
  stageUsage: [],
  error: null
};

const RECONNECTING_MESSAGE = "Соединение прервалось. Ждем переподключения к потоку событий...";
const STREAM_STOPPED_MESSAGE =
  "Поток событий недоступен, поэтому показываем сохраненный журнал и обновляем его опросом.";
const WORKER_UNAVAILABLE_MESSAGE =
  "Воркер недоступен: задача стоит в очереди, но журнал и статус продолжают обновляться.";
const MAX_VISIBLE_EVENTS = 60;
const MAX_STREAM_ERRORS = 6;
const SNAPSHOT_POLL_INTERVAL_MS = 3000;

function normalizeUsageBucket(usage: unknown): TokenUsageBucket {
  if (!usage || typeof usage !== "object") {
    return { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
  }

  const bucket = usage as Partial<TokenUsageBucket>;

  return {
    prompt_tokens: Number(bucket.prompt_tokens ?? 0),
    completion_tokens: Number(bucket.completion_tokens ?? 0),
    total_tokens: Number(bucket.total_tokens ?? 0)
  };
}

function upsertStageUsage(stageUsage: TaskStageUsage[], entry: TaskStageUsage) {
  const next = stageUsage.filter((stage) => stage.stage_id !== entry.stage_id);
  next.push(entry);
  next.sort((left, right) => left.stage_id - right.stage_id);
  return next;
}

function appendVisibleEvent(events: TaskEvent[], event: TaskEvent, maxVisibleEvents: number) {
  const next = [...events, event];
  return next.length > maxVisibleEvents ? next.slice(next.length - maxVisibleEvents) : next;
}

function normalizeEvent(event: TaskEvent): TaskEvent {
  return {
    ...event,
    data: event.data ?? {}
  };
}

function sortStageUsage(stageUsage: TaskStageUsage[]) {
  const next = [...stageUsage];
  next.sort((left, right) => left.stage_id - right.stage_id);
  return next;
}

function mergeEvents(current: TaskEvent[], nextEvents: TaskEvent[], maxVisibleEvents: number) {
  const merged = new Map<string, TaskEvent>();

  for (const event of [...current, ...nextEvents]) {
    const normalized = normalizeEvent(event);
    const key = `${normalized.type}-${normalized.timestamp}-${normalized.message}`;
    merged.set(key, normalized);
  }

  return Array.from(merged.values())
    .sort((left, right) => left.timestamp - right.timestamp)
    .slice(-maxVisibleEvents);
}

function snapshotWarning(snapshot: TaskProgressSnapshot) {
  if (snapshot.status === "queued" && !snapshot.worker_available) {
    return WORKER_UNAVAILABLE_MESSAGE;
  }

  return null;
}

function applySnapshot(
  current: TaskProgressState,
  snapshot: TaskProgressSnapshot,
  maxVisibleEvents: number,
  compactSnapshot: boolean
): TaskProgressState {
  const stage = snapshot.current_stage ? translateText(snapshot.current_stage) : current.stage;
  const warning = snapshotWarning(snapshot);
  const nextError = warning ?? (current.error === WORKER_UNAVAILABLE_MESSAGE ? null : current.error);

  return {
    ...current,
    stage,
    events: mergeEvents(current.events, snapshot.events, maxVisibleEvents),
    totalTokens: Number(snapshot.overall_usage.total_tokens ?? current.totalTokens),
    requestCount: Number(snapshot.request_count ?? current.requestCount),
    stageUsage: compactSnapshot ? [] : sortStageUsage(snapshot.stage_usage),
    error: nextError
  };
}

export function useTaskProgress({
  taskId,
  enabled = true,
  streamingEnabled = true,
  pollIntervalMs = SNAPSHOT_POLL_INTERVAL_MS,
  compactSnapshot = false,
  onComplete
}: UseTaskProgressOptions) {
  const [state, setState] = useState<TaskProgressState>(INITIAL_STATE);
  const onCompleteEvent = useEffectEvent((event: TaskEvent) => {
    onComplete?.(event);
  });

  useEffect(() => {
    if (!taskId) {
      setState(INITIAL_STATE);
      return;
    }

    const activeTaskId = taskId;

    if (!enabled) {
      setState((current) => ({
        ...current,
        isStreaming: false
      }));
      return;
    }

    setState({
      stage: streamingEnabled ? "Подключаемся к потоку воркера..." : "Загружаем сохраненный журнал...",
      events: [],
      isStreaming: Boolean(streamingEnabled),
      totalTokens: 0,
      requestCount: 0,
      elapsedSeconds: 0,
      stageUsage: [],
      error: null
    });

    let isDisposed = false;
    let eventSource: EventSource | null = null;
    let consecutiveStreamErrors = 0;
    let streamClosed = false;
    let snapshotPollId: number | null = null;
    const maxVisibleEvents = compactSnapshot ? 15 : MAX_VISIBLE_EVENTS;

    async function refreshSnapshot() {
      try {
        const snapshot = await getTaskProgressSnapshot(activeTaskId, { compact: compactSnapshot });
        if (isDisposed) {
          return;
        }
        setState((current) => applySnapshot(current, snapshot, maxVisibleEvents, compactSnapshot));
      } catch {
        if (isDisposed) {
          return;
        }
        setState((current) => ({
          ...current,
          error: current.events.length > 0 ? current.error : STREAM_STOPPED_MESSAGE
        }));
      }
    }

    function ensurePolling() {
      if (snapshotPollId !== null) {
        return;
      }
      snapshotPollId = window.setInterval(() => {
        if (!isDocumentVisible()) {
          return;
        }
        void refreshSnapshot();
      }, pollIntervalMs);
    }

    void refreshSnapshot();

    if (!streamingEnabled) {
      ensurePolling();
      return () => {
        isDisposed = true;
        if (snapshotPollId !== null) {
          window.clearInterval(snapshotPollId);
        }
      };
    }

    eventSource = createTaskEventSource(activeTaskId);

    function parseEvent(rawEvent: MessageEvent<string>): TaskEvent {
      return JSON.parse(rawEvent.data) as TaskEvent;
    }

    function noteActivity() {
      consecutiveStreamErrors = 0;
    }

    eventSource.addEventListener("stage", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      noteActivity();
      setState((current) => ({
        ...current,
        events: appendVisibleEvent(current.events, event, maxVisibleEvents),
        error:
          current.error === RECONNECTING_MESSAGE || current.error === STREAM_STOPPED_MESSAGE ? null : current.error,
        stage: translateText(event.message),
        totalTokens: Number(event.data.overall_usage?.total_tokens ?? current.totalTokens),
        stageUsage:
          !compactSnapshot && typeof event.data.stage_id === "number"
            ? upsertStageUsage(current.stageUsage, {
                stage_id: event.data.stage_id,
                message: translateText(event.message),
                usage: normalizeUsageBucket(event.data.usage),
                request_count: Number(event.data.request_count ?? 0)
              })
            : current.stageUsage
      }));
    });

    eventSource.addEventListener("info", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      noteActivity();
      setState((current) => ({
        ...current,
        events: appendVisibleEvent(current.events, event, maxVisibleEvents),
        error:
          current.error === RECONNECTING_MESSAGE || current.error === STREAM_STOPPED_MESSAGE ? null : current.error
      }));
    });

    eventSource.addEventListener("agent", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      noteActivity();
      setState((current) => ({
        ...current,
        events: appendVisibleEvent(current.events, event, maxVisibleEvents),
        error:
          current.error === RECONNECTING_MESSAGE || current.error === STREAM_STOPPED_MESSAGE ? null : current.error
      }));
    });

    eventSource.addEventListener("usage", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      noteActivity();
      setState((current) => ({
        ...current,
        events: appendVisibleEvent(current.events, event, maxVisibleEvents),
        error:
          current.error === RECONNECTING_MESSAGE || current.error === STREAM_STOPPED_MESSAGE ? null : current.error,
        totalTokens: Number(event.data.overall_usage?.total_tokens ?? current.totalTokens),
        requestCount: Number(event.data.request_count ?? current.requestCount),
        stageUsage:
          !compactSnapshot && typeof event.data.stage_id === "number"
            ? upsertStageUsage(current.stageUsage, {
                stage_id: event.data.stage_id,
                message:
                  typeof event.data.stage_message === "string" && event.data.stage_message
                    ? translateText(event.data.stage_message)
                    : current.stage,
                usage: normalizeUsageBucket(event.data.stage_usage),
                request_count: Number(event.data.stage_request_count ?? 0)
              })
            : current.stageUsage
      }));
    });

    eventSource.addEventListener("complete", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      noteActivity();
      streamClosed = true;
      setState((current) => ({
        ...current,
        events: appendVisibleEvent(current.events, event, maxVisibleEvents),
        error:
          current.error === RECONNECTING_MESSAGE || current.error === STREAM_STOPPED_MESSAGE ? null : current.error,
        stage: translateText(event.message),
        isStreaming: false,
        totalTokens: Number(event.data.usage_summary?.totals.total_tokens ?? current.totalTokens),
        requestCount: Number(event.data.usage_summary?.request_count ?? current.requestCount),
        stageUsage: compactSnapshot ? current.stageUsage : event.data.usage_summary?.stages ?? current.stageUsage
      }));
      onCompleteEvent(event);
      eventSource?.close();
    });

    eventSource.addEventListener("error", (rawEvent) => {
      if (!(rawEvent instanceof MessageEvent)) {
        return;
      }

      const event = parseEvent(rawEvent);
      noteActivity();
      streamClosed = true;
      setState((current) => ({
        ...current,
        events: appendVisibleEvent(current.events, event, maxVisibleEvents),
        stage: "Анализ завершился с ошибкой",
        isStreaming: false,
        totalTokens: Number(event.data.usage_summary?.totals.total_tokens ?? current.totalTokens),
        requestCount: Number(event.data.usage_summary?.request_count ?? current.requestCount),
        stageUsage: compactSnapshot ? current.stageUsage : event.data.usage_summary?.stages ?? current.stageUsage,
        error: translateText(event.message)
      }));
      eventSource?.close();
    });

    eventSource.onerror = () => {
      if (streamClosed) {
        return;
      }

      consecutiveStreamErrors += 1;

      if (consecutiveStreamErrors >= MAX_STREAM_ERRORS) {
        streamClosed = true;
        eventSource?.close();
        ensurePolling();
        void refreshSnapshot();
        setState((current) => ({
          ...current,
          isStreaming: false,
          error: STREAM_STOPPED_MESSAGE
        }));
        return;
      }

      setState((current) => ({
        ...current,
        error: current.error ?? RECONNECTING_MESSAGE
      }));
    };

    return () => {
      isDisposed = true;
      eventSource?.close();
      if (snapshotPollId !== null) {
        window.clearInterval(snapshotPollId);
      }
    };
  }, [taskId, enabled, streamingEnabled, pollIntervalMs, compactSnapshot, onCompleteEvent]);

  useEffect(() => {
    if (!taskId || !state.isStreaming) {
      return;
    }

    const timerId = window.setInterval(() => {
      if (!isDocumentVisible()) {
        return;
      }
      setState((current) => ({
        ...current,
        elapsedSeconds: current.elapsedSeconds + 2
      }));
    }, 2000);

    return () => {
      window.clearInterval(timerId);
    };
  }, [taskId, state.isStreaming]);

  return state;
}

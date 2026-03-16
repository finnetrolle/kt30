import { useEffect, useEffectEvent, useState } from "react";

import type { TaskEvent, TaskStageUsage, TokenUsageBucket } from "@/entities/task/model";
import { createTaskEventSource } from "@/shared/api/client";
import { translateText } from "@/shared/lib/locale";

interface UseTaskProgressOptions {
  taskId: string | null;
  enabled?: boolean;
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
  "Живой поток временно остановлен для защиты браузера. Статус задачи продолжает обновляться опросом.";
const MAX_VISIBLE_EVENTS = 60;
const MAX_STREAM_ERRORS = 6;

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

function appendVisibleEvent(events: TaskEvent[], event: TaskEvent) {
  const next = [...events, event];
  return next.length > MAX_VISIBLE_EVENTS ? next.slice(next.length - MAX_VISIBLE_EVENTS) : next;
}

export function useTaskProgress({ taskId, enabled = true, onComplete }: UseTaskProgressOptions) {
  const [state, setState] = useState<TaskProgressState>(INITIAL_STATE);
  const onCompleteEvent = useEffectEvent((event: TaskEvent) => {
    onComplete?.(event);
  });

  useEffect(() => {
    if (!taskId) {
      setState(INITIAL_STATE);
      return;
    }

    if (!enabled) {
      setState((current) => ({
        ...current,
        isStreaming: false
      }));
      return;
    }

    setState({
      stage: "Подключаемся к потоку воркера...",
      events: [],
      isStreaming: true,
      totalTokens: 0,
      requestCount: 0,
      elapsedSeconds: 0,
      stageUsage: [],
      error: null
    });

    const eventSource = createTaskEventSource(taskId);
    let consecutiveStreamErrors = 0;
    let streamClosed = false;

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
        events: appendVisibleEvent(current.events, event),
        error: current.error === RECONNECTING_MESSAGE ? null : current.error,
        stage: translateText(event.message),
        totalTokens: Number(event.data.overall_usage?.total_tokens ?? current.totalTokens),
        stageUsage:
          typeof event.data.stage_id === "number"
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
        events: appendVisibleEvent(current.events, event),
        error: current.error === RECONNECTING_MESSAGE ? null : current.error
      }));
    });

    eventSource.addEventListener("agent", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      noteActivity();
      setState((current) => ({
        ...current,
        events: appendVisibleEvent(current.events, event),
        error: current.error === RECONNECTING_MESSAGE ? null : current.error
      }));
    });

    eventSource.addEventListener("usage", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      noteActivity();
      setState((current) => ({
        ...current,
        error: current.error === RECONNECTING_MESSAGE ? null : current.error,
        totalTokens: Number(event.data.overall_usage?.total_tokens ?? current.totalTokens),
        requestCount: Number(event.data.request_count ?? current.requestCount),
        stageUsage:
          typeof event.data.stage_id === "number"
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
        events: appendVisibleEvent(current.events, event),
        error: current.error === RECONNECTING_MESSAGE ? null : current.error,
        stage: translateText(event.message),
        isStreaming: false,
        totalTokens: Number(event.data.usage_summary?.totals.total_tokens ?? current.totalTokens),
        requestCount: Number(event.data.usage_summary?.request_count ?? current.requestCount),
        stageUsage: event.data.usage_summary?.stages ?? current.stageUsage
      }));
      onCompleteEvent(event);
      eventSource.close();
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
        events: appendVisibleEvent(current.events, event),
        stage: "Анализ завершился с ошибкой",
        isStreaming: false,
        totalTokens: Number(event.data.usage_summary?.totals.total_tokens ?? current.totalTokens),
        requestCount: Number(event.data.usage_summary?.request_count ?? current.requestCount),
        stageUsage: event.data.usage_summary?.stages ?? current.stageUsage,
        error: translateText(event.message)
      }));
      eventSource.close();
    });

    eventSource.onerror = () => {
      if (streamClosed) {
        return;
      }

      consecutiveStreamErrors += 1;

      if (consecutiveStreamErrors >= MAX_STREAM_ERRORS) {
        streamClosed = true;
        eventSource.close();
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
      eventSource.close();
    };
  }, [taskId, enabled, onCompleteEvent]);

  useEffect(() => {
    if (!taskId || !state.isStreaming) {
      return;
    }

    const timerId = window.setInterval(() => {
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

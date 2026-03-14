import { useEffect, useEffectEvent, useState } from "react";

import type { TaskEvent, TaskStageUsage, TokenUsageBucket } from "@/entities/task/model";
import { createTaskEventSource } from "@/shared/api/client";

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
  stage: "Idle",
  events: [],
  isStreaming: false,
  totalTokens: 0,
  requestCount: 0,
  elapsedSeconds: 0,
  stageUsage: [],
  error: null
};

const RECONNECTING_MESSAGE = "Connection hiccup detected. Waiting for SSE to reconnect...";

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
      stage: "Connecting to worker stream...",
      events: [],
      isStreaming: true,
      totalTokens: 0,
      requestCount: 0,
      elapsedSeconds: 0,
      stageUsage: [],
      error: null
    });

    const eventSource = createTaskEventSource(taskId);

    function appendEvent(event: TaskEvent) {
      setState((current) => ({
        ...current,
        events: [...current.events, event]
      }));
    }

    function parseEvent(rawEvent: MessageEvent<string>): TaskEvent {
      return JSON.parse(rawEvent.data) as TaskEvent;
    }

    function markActivity() {
      setState((current) => ({
        ...current,
        error: current.error === RECONNECTING_MESSAGE ? null : current.error
      }));
    }

    eventSource.addEventListener("stage", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      appendEvent(event);
      markActivity();
      setState((current) => ({
        ...current,
        stage: event.message,
        totalTokens: Number(event.data.overall_usage?.total_tokens ?? current.totalTokens),
        stageUsage:
          typeof event.data.stage_id === "number"
            ? upsertStageUsage(current.stageUsage, {
                stage_id: event.data.stage_id,
                message: event.message,
                usage: normalizeUsageBucket(event.data.usage),
                request_count: Number(event.data.request_count ?? 0)
              })
            : current.stageUsage
      }));
    });

    eventSource.addEventListener("info", (rawEvent) => {
      appendEvent(parseEvent(rawEvent as MessageEvent<string>));
      markActivity();
    });

    eventSource.addEventListener("agent", (rawEvent) => {
      appendEvent(parseEvent(rawEvent as MessageEvent<string>));
      markActivity();
    });

    eventSource.addEventListener("usage", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      markActivity();
      setState((current) => ({
        ...current,
        totalTokens: Number(event.data.overall_usage?.total_tokens ?? current.totalTokens),
        requestCount: Number(event.data.request_count ?? current.requestCount),
        stageUsage:
          typeof event.data.stage_id === "number"
            ? upsertStageUsage(current.stageUsage, {
                stage_id: event.data.stage_id,
                message:
                  typeof event.data.stage_message === "string" && event.data.stage_message
                    ? event.data.stage_message
                    : current.stage,
                usage: normalizeUsageBucket(event.data.stage_usage),
                request_count: Number(event.data.stage_request_count ?? 0)
              })
            : current.stageUsage
      }));
    });

    eventSource.addEventListener("complete", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      appendEvent(event);
      markActivity();
      setState((current) => ({
        ...current,
        stage: event.message,
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
      appendEvent(event);
      setState((current) => ({
        ...current,
        stage: "Analysis failed",
        isStreaming: false,
        totalTokens: Number(event.data.usage_summary?.totals.total_tokens ?? current.totalTokens),
        requestCount: Number(event.data.usage_summary?.request_count ?? current.requestCount),
        stageUsage: event.data.usage_summary?.stages ?? current.stageUsage,
        error: event.message
      }));
      eventSource.close();
    });

    eventSource.onerror = () => {
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
        elapsedSeconds: current.elapsedSeconds + 1
      }));
    }, 1000);

    return () => {
      window.clearInterval(timerId);
    };
  }, [taskId, state.isStreaming]);

  return state;
}

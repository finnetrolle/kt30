import { useEffect, useEffectEvent, useState } from "react";

import type { TaskEvent } from "@/entities/task/model";
import { createTaskEventSource } from "@/shared/api/client";

interface UseTaskProgressOptions {
  taskId: string | null;
  onComplete?: (event: TaskEvent) => void;
}

interface TaskProgressState {
  stage: string;
  events: TaskEvent[];
  isStreaming: boolean;
  totalTokens: number;
  error: string | null;
}

const INITIAL_STATE: TaskProgressState = {
  stage: "Idle",
  events: [],
  isStreaming: false,
  totalTokens: 0,
  error: null
};

export function useTaskProgress({ taskId, onComplete }: UseTaskProgressOptions) {
  const [state, setState] = useState<TaskProgressState>(INITIAL_STATE);
  const onCompleteEvent = useEffectEvent((event: TaskEvent) => {
    onComplete?.(event);
  });

  useEffect(() => {
    if (!taskId) {
      setState(INITIAL_STATE);
      return;
    }

    setState({
      stage: "Connecting to worker stream...",
      events: [],
      isStreaming: true,
      totalTokens: 0,
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

    eventSource.addEventListener("stage", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      appendEvent(event);
      setState((current) => ({
        ...current,
        stage: event.message,
        totalTokens: Number(event.data.overall_usage?.total_tokens ?? current.totalTokens)
      }));
    });

    eventSource.addEventListener("info", (rawEvent) => {
      appendEvent(parseEvent(rawEvent as MessageEvent<string>));
    });

    eventSource.addEventListener("agent", (rawEvent) => {
      appendEvent(parseEvent(rawEvent as MessageEvent<string>));
    });

    eventSource.addEventListener("usage", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      setState((current) => ({
        ...current,
        totalTokens: Number(event.data.overall_usage?.total_tokens ?? current.totalTokens)
      }));
    });

    eventSource.addEventListener("complete", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      appendEvent(event);
      setState((current) => ({
        ...current,
        stage: event.message,
        isStreaming: false,
        totalTokens: Number(event.data.usage_summary?.totals.total_tokens ?? current.totalTokens)
      }));
      onCompleteEvent(event);
      eventSource.close();
    });

    eventSource.addEventListener("error", () => {
      setState((current) => ({
        ...current,
        isStreaming: false,
        error: "The progress stream was interrupted."
      }));
      eventSource.close();
    });

    eventSource.addEventListener("error_event", (rawEvent) => {
      const event = parseEvent(rawEvent as MessageEvent<string>);
      appendEvent(event);
      setState((current) => ({
        ...current,
        stage: "Analysis failed",
        isStreaming: false,
        error: event.message
      }));
      eventSource.close();
    });

    return () => {
      eventSource.close();
    };
  }, [taskId, onCompleteEvent]);

  return state;
}

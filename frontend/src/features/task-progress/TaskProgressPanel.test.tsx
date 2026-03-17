import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TaskProgressPanel } from "@/features/task-progress/TaskProgressPanel";

describe("TaskProgressPanel", () => {
  it("renders the richer standalone task summary with stage usage", () => {
    render(
      <TaskProgressPanel
        taskId="task-123"
        stage="Analyzing dependencies"
        events={[
          {
            type: "stage",
            message: "Analyzing dependencies",
            timestamp: 1710000000,
            data: {
              stage_id: 2
            }
          }
        ]}
        totalTokens={3210}
        requestCount={7}
        elapsedSeconds={125}
        stageUsage={[
          {
            stage_id: 2,
            message: "Analyzing dependencies",
            usage: {
              prompt_tokens: 1200,
              completion_tokens: 450,
              total_tokens: 1650
            },
            request_count: 3
          }
        ]}
        jobStatus="running"
        isStreaming
        error={null}
        onCancel={vi.fn()}
        isCanceling={false}
      />
    );

    expect(screen.getByText("Ход выполнения")).toBeInTheDocument();
    expect(screen.getByText(/задача: task-123/i)).toBeInTheDocument();
    expect(screen.getByText(/3\s?210/)).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("2 мин 5 с")).toBeInTheDocument();
    expect(screen.getByText(/1\s?650 ток\./)).toBeInTheDocument();
    expect(screen.getByText(/запросы: 3/i)).toBeInTheDocument();
    expect(screen.getAllByText("Анализируем зависимости")).toHaveLength(3);
  });

  it("shows detailed event metadata for llm activity", () => {
    render(
      <TaskProgressPanel
        taskId="task-456"
        stage="Запуск мульти-агентного анализа"
        events={[
          {
            type: "agent",
            message: "📤 planner: запрос отправлен в gpt-test",
            timestamp: 1710000100,
            data: {
              agent: "planner",
              model: "gpt-test",
              worker_id: "worker-1",
              attempt: 2,
              elapsed_seconds: 4.2,
              request_id: "req-1",
              prompt_preview: "Построй каркас WBS по компактному анализу проекта",
              usage: {
                prompt_tokens: 120,
                completion_tokens: 48,
                total_tokens: 168
              }
            }
          }
        ]}
        totalTokens={168}
        requestCount={1}
        elapsedSeconds={8}
        stageUsage={[]}
        jobStatus="running"
        isStreaming={false}
        error={null}
        onCancel={vi.fn()}
        isCanceling={false}
      />
    );

    expect(screen.getByText(/агент: планировщик/i)).toBeInTheDocument();
    expect(screen.getByText(/модель: gpt-test/i)).toBeInTheDocument();
    expect(screen.getByText(/воркер: worker-1/i)).toBeInTheDocument();
    expect(screen.getByText(/токены: 168 \(prompt 120, completion 48\)/i)).toBeInTheDocument();
    expect(screen.getByText(/prompt preview/i)).toBeInTheDocument();
    expect(screen.getByText(/request id: req-1/i)).toBeInTheDocument();
  });
});

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
});

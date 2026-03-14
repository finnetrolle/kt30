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

    expect(screen.getByText("Task progress")).toBeInTheDocument();
    expect(screen.getByText(/task id: task-123/i)).toBeInTheDocument();
    expect(screen.getByText("3210")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("2 min 5 sec")).toBeInTheDocument();
    expect(screen.getByText("1650 tok.")).toBeInTheDocument();
    expect(screen.getByText(/requests: 3/i)).toBeInTheDocument();
    expect(screen.getAllByText("Analyzing dependencies")).toHaveLength(3);
  });
});

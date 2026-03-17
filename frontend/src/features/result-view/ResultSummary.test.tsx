import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResultSummary } from "@/features/result-view/ResultSummary";
import type { ResultPayload } from "@/entities/result/model";

const payload: ResultPayload = {
  result_id: "result-42",
  filename: "spec.docx",
  timestamp: "2026-03-14T12:00:00Z",
  usage: {
    llm_profile: "gpt-5.4",
    agent_system: "multi-agent",
    iterations: 2,
    elapsed_seconds: 98
  },
  metadata: {},
  token_usage: {
    totals: {
      total_tokens: 900,
      prompt_tokens: 600,
      completion_tokens: 300
    },
    request_count: 4,
    stages: [
      {
        message: "Draft WBS",
        request_count: 2,
        usage: {
          total_tokens: 450,
          prompt_tokens: 320,
          completion_tokens: 130
        }
      }
    ]
  },
  calculated_duration: {
    total_days: 12,
    total_weeks: 3
  },
  links: {
    self: "/api/results/result-42",
    legacy_html: "/results/result-42",
    excel_export: "/api/results/result-42/export.xlsx",
    legacy_excel_export: "/export/excel/result-42"
  },
  execution_trace: {
    available: true,
    llm_call_count: 2,
    error_count: 0,
    progress_event_count: 6,
    stages: [
      {
        stage_id: 2,
        message: "Draft WBS",
        request_count: 2,
        usage: {
          total_tokens: 450,
          prompt_tokens: 320,
          completion_tokens: 130
        },
        llm_calls: [
          {
            index: 1,
            agent: "Планировщик WBS",
            description: "Детализация пакета работ «Inventory» в задачи",
            status: "success",
            attempt: 1,
            model: "gpt-5.4",
            elapsed_seconds: 12,
            usage: {
              total_tokens: 210,
              prompt_tokens: 140,
              completion_tokens: 70
            }
          }
        ]
      }
    ],
    uncategorized_calls: [],
    recent_events: [
      {
        type: "info",
        message: "Документ загружен",
        timestamp: 1710000000
      }
    ]
  },
  result: {
    project_info: {
      project_name: "Standalone frontend migration",
      description: "Move the current UI to React/Vite.",
      complexity_level: "medium"
    },
    wbs: {
      phases: [
        {
          id: "P1",
          name: "Discovery",
          duration: "1 week",
          work_packages: [
            {
              id: "WP1",
              name: "Inventory",
              tasks: [
                {
                  id: "T1",
                  name: "Map API endpoints",
                  estimated_hours: 8
                }
              ]
            }
          ]
        }
      ]
    },
    dependencies_matrix: [
      {
        task_id: "T1",
        depends_on: [],
        parallel_with: []
      }
    ],
    risks: [
      {
        id: "R1",
        description: "Auth mismatch between legacy and new UI",
        mitigation: "Keep same-origin rollout first"
      }
    ],
    assumptions: ["Backend remains the source of business logic."],
    recommendations: [
      {
        category: "Migration",
        priority: "high",
        recommendation: "Cover the standalone flow with tests."
      }
    ]
  }
};

describe("ResultSummary", () => {
  it("renders the migrated result view with exports and structured sections", () => {
    render(<ResultSummary payload={payload} />);

    expect(screen.getByText("Standalone frontend migration")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /скачать excel/i })).toHaveAttribute(
      "href",
      "/api/results/result-42/export.xlsx"
    );
    expect(screen.getByRole("button", { name: /скачать pdf/i })).toBeInTheDocument();
    expect(screen.getByText("Использование токенов")).toBeInTheDocument();
    expect(screen.getByText("Журнал запуска")).toBeInTheDocument();
    expect(screen.getByText("Формируем черновик ИСР")).toBeInTheDocument();
    expect(screen.getByText(/детализация пакета работ «inventory» в задачи/i)).toBeInTheDocument();
    expect(screen.getByText("Допущения")).toBeInTheDocument();
    expect(screen.getByText("Риски")).toBeInTheDocument();
    expect(screen.getByText("Рекомендации")).toBeInTheDocument();
    expect(screen.getByText(/map api endpoints/i)).toBeInTheDocument();
  });
});

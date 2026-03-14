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
    expect(screen.getByRole("link", { name: /export excel/i })).toHaveAttribute(
      "href",
      "/api/results/result-42/export.xlsx"
    );
    expect(screen.getByText("Token usage")).toBeInTheDocument();
    expect(screen.getByText("Draft WBS")).toBeInTheDocument();
    expect(screen.getByText("Assumptions")).toBeInTheDocument();
    expect(screen.getByText("Risks")).toBeInTheDocument();
    expect(screen.getByText("Recommendations")).toBeInTheDocument();
    expect(screen.getByText(/map api endpoints/i)).toBeInTheDocument();
  });
});

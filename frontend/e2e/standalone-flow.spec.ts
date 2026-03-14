import { expect, test, type Page, type Route } from "@playwright/test";

interface MockState {
  authenticated: boolean;
  csrfToken: string;
  taskId: string;
  resultId: string;
  taskStatusReads: number;
  cancelRequested: boolean;
}

interface MockScenario {
  initiallyAuthenticated?: boolean;
  acceptedPassword?: string;
  taskId?: string;
  resultId?: string;
  taskStatusMode?: "happy_path" | "cancelled" | "missing";
  missingResult?: boolean;
}

function buildSessionPayload(state: MockState) {
  return {
    auth_enabled: true,
    authenticated: state.authenticated,
    csrf_token: state.csrfToken,
    session_ttl_seconds: 3600,
    frontend_base_path: "/app",
    frontend_build_available: true
  };
}

function buildResultPayload(state: MockState) {
  return {
    result_id: state.resultId,
    filename: "specification.pdf",
    timestamp: "2026-03-14T14:00:00Z",
    usage: {
      llm_profile: "gpt-5.4",
      agent_system: "multi-agent",
      iterations: 2,
      elapsed_seconds: 42
    },
    metadata: {},
    token_usage: {
      totals: {
        total_tokens: 150,
        prompt_tokens: 120,
        completion_tokens: 30
      },
      request_count: 1,
      stages: [
        {
          message: "Parsing specification",
          request_count: 1,
          usage: {
            total_tokens: 150,
            prompt_tokens: 120,
            completion_tokens: 30
          }
        }
      ]
    },
    calculated_duration: {
      total_days: 10,
      total_weeks: 2
    },
    links: {
      self: `/api/results/${state.resultId}`,
      legacy_html: `/results/${state.resultId}`,
      excel_export: `/api/results/${state.resultId}/export.xlsx`,
      legacy_excel_export: `/export/excel/${state.resultId}`,
      frontend_html: `/app/results/${state.resultId}`
    },
    result: {
      project_info: {
        project_name: "Standalone frontend E2E",
        description: "Browser-level verification of the new migration path.",
        complexity_level: "medium"
      },
      wbs: {
        phases: [
          {
            id: "P1",
            name: "Frontend migration",
            duration: "2 weeks",
            work_packages: [
              {
                id: "WP1",
                name: "Browser flow",
                estimated_hours: 16,
                tasks: [
                  {
                    id: "T1",
                    name: "Verify login-upload-progress-results",
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
      assumptions: ["Mocked backend contract stays compatible with the standalone app."],
      risks: [
        {
          id: "R1",
          description: "Standalone API contract drifts away from Flask behavior",
          mitigation: "Keep browser-level mocks aligned with backend tests"
        }
      ],
      recommendations: [
        {
          category: "QA",
          priority: "high",
          recommendation: "Keep extending e2e coverage before switching traffic."
        }
      ]
    }
  };
}

function buildProgressStream(state: MockState) {
  const events = [
    {
      event: "stage",
      payload: {
        type: "stage",
        message: "Parsing specification",
        timestamp: 1710428400,
        data: {
          stage_id: 1,
          usage: {
            prompt_tokens: 0,
            completion_tokens: 0,
            total_tokens: 0
          },
          request_count: 0,
          overall_usage: {
            prompt_tokens: 0,
            completion_tokens: 0,
            total_tokens: 0
          }
        }
      }
    },
    {
      event: "usage",
      payload: {
        type: "usage",
        message: "Tokens: planner",
        timestamp: 1710428401,
        data: {
          agent: "planner",
          stage_id: 1,
          stage_message: "Parsing specification",
          usage: {
            prompt_tokens: 120,
            completion_tokens: 30,
            total_tokens: 150
          },
          stage_usage: {
            prompt_tokens: 120,
            completion_tokens: 30,
            total_tokens: 150
          },
          stage_request_count: 1,
          overall_usage: {
            prompt_tokens: 120,
            completion_tokens: 30,
            total_tokens: 150
          },
          request_count: 1
        }
      }
    },
    {
      event: "complete",
      payload: {
        type: "complete",
        message: "Analysis complete",
        timestamp: 1710428402,
        data: {
          result_id: state.resultId,
          redirect_url: `/app/results/${state.resultId}`,
          usage_summary: {
            totals: {
              prompt_tokens: 120,
              completion_tokens: 30,
              total_tokens: 150
            },
            request_count: 1,
            stages: [
              {
                stage_id: 1,
                message: "Parsing specification",
                usage: {
                  prompt_tokens: 120,
                  completion_tokens: 30,
                  total_tokens: 150
                },
                request_count: 1
              }
            ]
          }
        }
      }
    }
  ];

  return `${events
    .map(({ event, payload }) => `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`)
    .join("")}: keepalive\n\n`;
}

function buildKeepaliveStream() {
  return ": keepalive\n\n";
}

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload)
  });
}

async function installStandaloneApiMock(page: Page, scenario: MockScenario = {}) {
  const state: MockState = {
    authenticated: scenario.initiallyAuthenticated ?? false,
    csrfToken: "csrf-e2e-token",
    taskId: scenario.taskId ?? "task-e2e-1",
    resultId: scenario.resultId ?? "result-e2e-1",
    taskStatusReads: 0,
    cancelRequested: false
  };
  const acceptedPassword = scenario.acceptedPassword ?? "secret-password";
  const taskStatusMode = scenario.taskStatusMode ?? "happy_path";
  const missingResult = scenario.missingResult ?? false;

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/auth/session" && method === "GET") {
      await fulfillJson(route, buildSessionPayload(state));
      return;
    }

    if (path === "/api/auth/csrf" && method === "GET") {
      await fulfillJson(route, { csrf_token: state.csrfToken });
      return;
    }

    if (path === "/api/auth/login" && method === "POST") {
      const payload = request.postDataJSON() as { password?: string } | null;
      if (payload?.password === acceptedPassword) {
        state.authenticated = true;
        await fulfillJson(route, {
          success: true,
          ...buildSessionPayload(state)
        });
        return;
      }

      await fulfillJson(
        route,
        {
          error: "Неверный пароль",
          status: 401
        },
        401
      );
      return;
    }

    if (path === "/api/auth/logout" && method === "POST") {
      state.authenticated = false;
      await fulfillJson(route, {
        success: true,
        ...buildSessionPayload(state)
      });
      return;
    }

    if (path === "/api/uploads" && method === "POST") {
      await fulfillJson(route, {
        success: true,
        task_id: state.taskId
      });
      return;
    }

    if (path === `/api/tasks/${state.taskId}` && method === "GET") {
      if (taskStatusMode === "missing") {
        await fulfillJson(
          route,
          {
            error: "Task not found",
            status: 404
          },
          404
        );
        return;
      }

      if (taskStatusMode === "cancelled") {
        await fulfillJson(route, {
          task_id: state.taskId,
          status: state.cancelRequested ? "canceled" : "running",
          error: state.cancelRequested ? "Task was canceled by user." : null,
          result_id: null,
          worker_id: "worker-e2e",
          cancel_requested: state.cancelRequested ? 1 : 0,
          payload: {
            filename: "specification.pdf"
          }
        });
        return;
      }

      state.taskStatusReads += 1;
      const isCompleted = state.taskStatusReads > 1;

      await fulfillJson(route, {
        task_id: state.taskId,
        status: isCompleted ? "succeeded" : "running",
        error: null,
        result_id: isCompleted ? state.resultId : null,
        worker_id: "worker-e2e",
        cancel_requested: 0,
        payload: {
          filename: "specification.pdf"
        }
      });
      return;
    }

    if (path === `/api/tasks/${state.taskId}/cancel` && method === "POST") {
      state.cancelRequested = true;
      await fulfillJson(route, {
        success: true,
        status: "cancel_requested"
      });
      return;
    }

    if (path === `/api/tasks/${state.taskId}/events` && method === "GET") {
      if (taskStatusMode === "missing") {
        await fulfillJson(
          route,
          {
            error: "Task not found",
            status: 404
          },
          404
        );
        return;
      }

      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive"
        },
        body: taskStatusMode === "cancelled" ? buildKeepaliveStream() : buildProgressStream(state)
      });
      return;
    }

    if (path === `/api/results/${state.resultId}` && method === "GET") {
      if (missingResult) {
        await fulfillJson(
          route,
          {
            error: "Result not found",
            status: 404
          },
          404
        );
        return;
      }

      await fulfillJson(route, buildResultPayload(state));
      return;
    }

    await fulfillJson(
      route,
      {
        error: `Unhandled mock route: ${method} ${path}`,
        status: 500
      },
      500
    );
  });
}

test.describe("standalone frontend flow", () => {
  test("shows a backend auth error when login fails", async ({ page }) => {
    await installStandaloneApiMock(page);

    await page.goto("/app/");
    await expect(page).toHaveURL(/\/app\/login$/);

    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/app\/login$/);
    await expect(page.getByText("Неверный пароль")).toBeVisible();
  });

  test("redirects a direct result visit to login when the session is not authenticated", async ({ page }) => {
    await installStandaloneApiMock(page, {
      initiallyAuthenticated: false,
      resultId: "guarded-result"
    });

    await page.goto("/app/results/guarded-result");

    await expect(page).toHaveURL(/\/app\/login$/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("completes login -> upload -> progress -> results under /app", async ({ page }) => {
    await installStandaloneApiMock(page);

    await page.goto("/app/");
    await expect(page).toHaveURL(/\/app\/login$/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

    await page.getByLabel("Password").fill("secret-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/app\/$/);
    await expect(page.getByRole("heading", { name: "Upload and monitor" })).toBeVisible();

    await page.getByLabel(/choose a word or pdf file/i).setInputFiles({
      name: "specification.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 mocked spec")
    });
    await page.getByRole("button", { name: "Run analysis" }).click();

    await expect(page).toHaveURL(/taskId=task-e2e-1/);
    await expect(page.getByText(/task id: task-e2e-1/i)).toBeVisible();

    await expect(page).toHaveURL(/\/app\/results\/result-e2e-1$/);
    await expect(page.getByRole("heading", { name: "Analysis result" })).toBeVisible();
    await expect(page.getByText("Standalone frontend E2E")).toBeVisible();
    await expect(page.getByText("Browser flow")).toBeVisible();
    await expect(page.getByRole("link", { name: "Export Excel" })).toHaveAttribute(
      "href",
      "/api/results/result-e2e-1/export.xlsx"
    );
  });

  test("lets the user cancel a running task and reflects the durable canceled state", async ({ page }) => {
    await installStandaloneApiMock(page, {
      initiallyAuthenticated: true,
      taskId: "task-cancel-1",
      taskStatusMode: "cancelled"
    });

    await page.goto("/app/");
    await expect(page.getByRole("heading", { name: "Upload and monitor" })).toBeVisible();

    await page.getByLabel(/choose a word or pdf file/i).setInputFiles({
      name: "specification.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 mocked spec")
    });
    await page.getByRole("button", { name: "Run analysis" }).click();

    await expect(page).toHaveURL(/taskId=task-cancel-1/);
    await page.getByRole("button", { name: "Cancel task" }).click();

    await expect(page.getByText("Task was canceled by user.")).toBeVisible();
    await expect(page.getByText(/^canceled$/)).toBeVisible();
  });

  test("surfaces missing task recovery errors from a resumed URL", async ({ page }) => {
    await installStandaloneApiMock(page, {
      initiallyAuthenticated: true,
      taskId: "missing-task",
      taskStatusMode: "missing"
    });

    await page.goto("/app/?taskId=missing-task");

    await expect(page.getByRole("heading", { name: "Upload and monitor" })).toBeVisible();
    await expect(page.getByText("Task not found")).toBeVisible();
  });

  test("shows an unavailable state when the backend result is missing", async ({ page }) => {
    await installStandaloneApiMock(page, {
      initiallyAuthenticated: true,
      resultId: "missing-result",
      missingResult: true
    });

    await page.goto("/app/results/missing-result");

    await expect(page.getByRole("heading", { name: "Result unavailable" })).toBeVisible();
    await expect(page.getByText("Could not load result")).toBeVisible();
    await expect(page.getByText("Result not found")).toBeVisible();
  });
});

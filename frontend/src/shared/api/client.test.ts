import { afterEach, describe, expect, it, vi } from "vitest";

function jsonResponse(payload: unknown, init: { status?: number } = {}) {
  const status = init.status ?? 200;

  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({
      "content-type": "application/json"
    }),
    json: async () => payload
  } as Response;
}

describe("shared api client", () => {
  afterEach(() => {
    vi.resetModules();
  });

  it("reuses the CSRF token for API login requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          csrf_token: "csrf-1"
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          auth_enabled: true,
          authenticated: true,
          csrf_token: "csrf-2",
          session_ttl_seconds: 3600,
          frontend_base_path: "/app",
          frontend_build_available: true
        })
      );

    vi.stubGlobal("fetch", fetchMock);

    const { login } = await import("@/shared/api/client");
    const result = await login("swordfish");

    expect(result.authenticated).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/auth/csrf");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/auth/login");

    const requestInit = fetchMock.mock.calls[1]?.[1];
    expect(new Headers(requestInit?.headers).get("X-CSRF-Token")).toBe("csrf-1");
    expect(JSON.parse(String(requestInit?.body))).toEqual({ password: "swordfish" });
  });

  it("parses durable task status payloads from the standalone backend API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        task_id: "task-42",
        status: "running",
        cancel_requested: 0,
        result_id: null,
        worker_id: "worker-a",
        payload: {
          filename: "spec.docx"
        }
      })
    );

    vi.stubGlobal("fetch", fetchMock);

    const { getTask } = await import("@/shared/api/client");
    const task = await getTask("task-42");

    expect(task.task_id).toBe("task-42");
    expect(task.status).toBe("running");
    expect(task.worker_id).toBe("worker-a");
    expect(task.payload).toEqual({ filename: "spec.docx" });
  });

  it("parses the active task dashboard payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        scope: "active",
        generated_at: "2026-03-16T12:00:00Z",
        counts: {
          total: 1,
          queued: 0,
          running: 1,
          cancel_requested: 0
        },
        items: [
          {
            task_id: "task-77",
            status: "running",
            filename: "roadmap.docx",
            cancel_requested: 0,
            current_stage: "Парсинг документа...",
            request_count: 2,
            total_tokens: 340,
            created_at: 1710000000,
            updated_at: 1710000030,
            started_at: 1710000010,
            finished_at: null,
            worker_id: "worker-a"
          }
        ],
        recent_results: [
          {
            task_id: "task-88",
            status: "succeeded",
            filename: "result.docx",
            cancel_requested: 0,
            request_count: 4,
            total_tokens: 780,
            created_at: 1710000000,
            updated_at: 1710000300,
            started_at: 1710000010,
            finished_at: 1710000300,
            result_id: "result-88"
          }
        ]
      })
    );

    vi.stubGlobal("fetch", fetchMock);

    const { getActiveTasks } = await import("@/shared/api/client");
    const taskList = await getActiveTasks();

    expect(taskList.counts.running).toBe(1);
    expect(taskList.items[0]?.task_id).toBe("task-77");
    expect(taskList.items[0]?.cancel_requested).toBe(false);
    expect(taskList.items[0]?.total_tokens).toBe(340);
    expect(taskList.recent_results[0]?.result_id).toBe("result-88");
  });

  it("parses the results history payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        scope: "history",
        generated_at: "2026-03-16T12:00:00Z",
        items: [
          {
            result_id: "result-101",
            stored_at: 1710000300,
            timestamp: "2026-03-16T11:59:00Z",
            filename: "history.docx",
            project_name: "History project",
            description: "Saved result entry",
            complexity_level: "medium",
            calculated_duration: {
              total_days: 6,
              total_weeks: 2
            },
            token_usage: {
              totals: {
                total_tokens: 480
              },
              request_count: 3
            },
            links: {
              self: "/api/results/result-101",
              legacy_html: "/results/result-101",
              excel_export: "/api/results/result-101/export.xlsx",
              legacy_excel_export: "/export/excel/result-101",
              frontend_html: "/app/results/result-101"
            }
          }
        ]
      })
    );

    vi.stubGlobal("fetch", fetchMock);

    const { getResultsHistory } = await import("@/shared/api/client");
    const history = await getResultsHistory();

    expect(history.scope).toBe("history");
    expect(history.items[0]?.result_id).toBe("result-101");
    expect(history.items[0]?.links.excel_export).toBe("/api/results/result-101/export.xlsx");
  });

  it("surfaces backend API errors with the original status and message", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          csrf_token: "csrf-1"
        })
      )
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: "Неверный пароль",
            status: 401
          },
          { status: 401 }
        )
      );

    vi.stubGlobal("fetch", fetchMock);

    const { login } = await import("@/shared/api/client");

    await expect(login("wrong-password")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: "Неверный пароль"
    });
  });
});

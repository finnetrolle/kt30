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

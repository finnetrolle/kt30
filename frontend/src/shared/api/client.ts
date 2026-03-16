import { z } from "zod";

import type { ResultHistoryList, ResultPayload } from "@/entities/result/model";
import type { ActiveTaskList, TaskStatus } from "@/entities/task/model";

const sessionSchema = z.object({
  auth_enabled: z.boolean(),
  authenticated: z.boolean(),
  csrf_token: z.string(),
  session_ttl_seconds: z.number(),
  frontend_base_path: z.string().optional(),
  frontend_build_available: z.boolean().optional()
});

const uploadSchema = z.object({
  success: z.boolean(),
  task_id: z.string()
});

const cancelSchema = z.object({
  success: z.boolean(),
  status: z.string()
});

const taskStatusSchema = z.object({
  task_id: z.string(),
  status: z.string(),
  error: z.string().nullable().optional(),
  result_id: z.string().nullable().optional(),
  worker_id: z.string().nullable().optional(),
  cancel_requested: z.union([z.boolean(), z.number()]).nullable().optional(),
  filename: z.string().nullable().optional(),
  file_size: z.number().nullable().optional(),
  current_stage: z.string().nullable().optional(),
  current_stage_id: z.number().nullable().optional(),
  request_count: z.number().optional(),
  total_tokens: z.number().optional(),
  created_at: z.number().optional(),
  updated_at: z.number().optional(),
  started_at: z.number().nullable().optional(),
  finished_at: z.number().nullable().optional(),
  payload: z.record(z.unknown()).optional()
});

const activeTaskSchema = z.object({
  task_id: z.string(),
  status: z.string(),
  error: z.string().nullable().optional(),
  result_id: z.string().nullable().optional(),
  worker_id: z.string().nullable().optional(),
  cancel_requested: z.union([z.boolean(), z.number()]).nullable().optional().transform((value) => Boolean(value)),
  filename: z.string().nullable().optional(),
  file_size: z.number().nullable().optional(),
  request_id: z.string().nullable().optional(),
  current_stage: z.string().nullable().optional(),
  current_stage_id: z.number().nullable().optional(),
  request_count: z.number().default(0),
  total_tokens: z.number().default(0),
  created_at: z.number(),
  updated_at: z.number(),
  started_at: z.number().nullable().optional(),
  finished_at: z.number().nullable().optional(),
  artifacts_dir: z.string().nullable().optional()
});

const activeTaskListSchema = z.object({
  scope: z.string(),
  generated_at: z.string(),
  counts: z.object({
    total: z.number(),
    queued: z.number(),
    running: z.number(),
    cancel_requested: z.number()
  }),
  items: z.array(activeTaskSchema),
  recent_results: z.array(activeTaskSchema).default([])
});

const resultHistoryEntrySchema = z.object({
  result_id: z.string(),
  stored_at: z.number().nullable().optional(),
  timestamp: z.string(),
  filename: z.string(),
  project_name: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  complexity_level: z.string().nullable().optional(),
  calculated_duration: z.object({
    total_days: z.number(),
    total_weeks: z.number(),
    phase_durations: z.record(z.number()).optional()
  }),
  token_usage: z.object({
    totals: z
      .object({
        total_tokens: z.number().optional(),
        prompt_tokens: z.number().optional(),
        completion_tokens: z.number().optional()
      })
      .optional(),
    request_count: z.number().optional()
  }),
  links: z.object({
    self: z.string(),
    legacy_html: z.string(),
    excel_export: z.string(),
    legacy_excel_export: z.string(),
    frontend_html: z.string().optional()
  })
});

const resultHistoryListSchema = z.object({
  scope: z.string(),
  generated_at: z.string(),
  items: z.array(resultHistoryEntrySchema)
});

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

let csrfToken: string | null = null;

function apiPath(path: string) {
  return `${API_BASE_URL}${path}`;
}

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  const method = (init.method ?? "GET").toUpperCase();
  const hasBody = init.body !== undefined && init.body !== null;

  if (hasBody && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (csrfToken && !["GET", "HEAD"].includes(method)) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(apiPath(path), {
    ...init,
    headers,
    credentials: "include"
  });

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    const message =
      typeof payload === "object" && payload && "error" in payload
        ? String(payload.error)
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, payload);
  }

  if (payload && typeof payload === "object" && "csrf_token" in payload && typeof payload.csrf_token === "string") {
    csrfToken = payload.csrf_token;
  }

  return payload as T;
}

export async function getSession() {
  const payload = await apiFetch("/api/auth/session");
  return sessionSchema.parse(payload);
}

export async function ensureCsrfToken() {
  if (csrfToken) {
    return csrfToken;
  }

  const payload = await apiFetch<{ csrf_token: string }>("/api/auth/csrf");
  csrfToken = payload.csrf_token;
  return csrfToken;
}

export async function login(password: string) {
  await ensureCsrfToken();
  const payload = await apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ password })
  });
  return sessionSchema.extend({ success: z.literal(true) }).parse(payload);
}

export async function logout() {
  await ensureCsrfToken();
  const payload = await apiFetch("/api/auth/logout", { method: "POST" });
  return sessionSchema.extend({ success: z.literal(true) }).parse(payload);
}

export async function uploadFile(file: File) {
  await ensureCsrfToken();
  const formData = new FormData();
  formData.append("file", file);
  const payload = await apiFetch("/api/uploads", {
    method: "POST",
    body: formData
  });
  return uploadSchema.parse(payload);
}

export async function cancelTask(taskId: string) {
  await ensureCsrfToken();
  const payload = await apiFetch(`/api/tasks/${taskId}/cancel`, {
    method: "POST"
  });
  return cancelSchema.parse(payload);
}

export async function getTask(taskId: string) {
  const payload = await apiFetch(`/api/tasks/${taskId}`);
  return taskStatusSchema.parse(payload) as TaskStatus;
}

export async function getActiveTasks() {
  const payload = await apiFetch("/api/tasks");
  return activeTaskListSchema.parse(payload) as ActiveTaskList;
}

export async function getResult(resultId: string) {
  return apiFetch<ResultPayload>(`/api/results/${resultId}`);
}

export async function getResultsHistory() {
  const payload = await apiFetch("/api/results");
  return resultHistoryListSchema.parse(payload) as ResultHistoryList;
}

export function createTaskEventSource(taskId: string) {
  return new EventSource(apiPath(`/api/tasks/${taskId}/events`), {
    withCredentials: true
  });
}

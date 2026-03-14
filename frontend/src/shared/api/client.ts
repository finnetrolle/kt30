import { z } from "zod";

import type { ResultPayload } from "@/entities/result/model";
import type { TaskStatus } from "@/entities/task/model";

const sessionSchema = z.object({
  auth_enabled: z.boolean(),
  authenticated: z.boolean(),
  csrf_token: z.string(),
  session_ttl_seconds: z.number()
});

const uploadSchema = z.object({
  success: z.boolean(),
  task_id: z.string()
});

const cancelSchema = z.object({
  success: z.boolean(),
  status: z.string()
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
  return apiFetch<TaskStatus>(`/api/tasks/${taskId}`);
}

export async function getResult(resultId: string) {
  return apiFetch<ResultPayload>(`/api/results/${resultId}`);
}

export function createTaskEventSource(taskId: string) {
  return new EventSource(apiPath(`/api/tasks/${taskId}/events`), {
    withCredentials: true
  });
}

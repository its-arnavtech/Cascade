import type { JsonRecord } from "./types";

const DEFAULT_TIMEOUT_MS = 12_000;

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "/api";
export const refreshIntervalMs = Number(import.meta.env.VITE_REFRESH_INTERVAL_MS || 10_000);
export const dangerousActionsEnabled = import.meta.env.VITE_ENABLE_DANGEROUS_ACTIONS === "true";

export async function apiGet<T>(path: string, params?: JsonRecord): Promise<T> {
  return request<T>(path, { method: "GET", params });
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body });
}

async function request<T>(path: string, options: { method: "GET" | "POST"; params?: JsonRecord; body?: unknown }): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  const url = new URL(`${apiBaseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`, window.location.origin);
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  try {
    const response = await fetch(url, {
      method: options.method,
      headers: options.body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
    const text = await response.text();
    const body = parseBody(text);
    if (!response.ok) {
      throw new ApiError(errorMessage(body, response.status), response.status, body);
    }
    return body as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("Request timed out", 408, null);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function parseBody(text: string): unknown {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

function errorMessage(body: unknown, status: number): string {
  if (typeof body === "object" && body !== null) {
    const detail = (body as { detail?: unknown; message?: unknown }).detail ?? (body as { message?: unknown }).message;
    if (typeof detail === "string") return detail;
    if (detail !== undefined) return JSON.stringify(detail);
  }
  return `Request failed with HTTP ${status}`;
}

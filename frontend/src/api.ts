import type { Message, ChatResponse } from "./types";

const API_BASE = import.meta.env.PROD
  ? "https://halos-ai.onrender.com/api"
  : import.meta.env.VITE_API_URL || "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function wakeUpBackend(): Promise<boolean> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 35000);
  try {
    const resp = await fetch(`${API_BASE}/health`, {
      method: "GET",
      signal: controller.signal,
    });
    return resp.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

export async function sendMessage(
  message: string,
  history: Message[],
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const resp = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => "Unknown error");
    throw new ApiError(
      `Request failed (${resp.status}): ${text}`,
      resp.status,
    );
  }

  return resp.json() as Promise<ChatResponse>;
}

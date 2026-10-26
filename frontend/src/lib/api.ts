import { parseSSE } from "./sse";
import type { ApiErrorDetail, EvalReport, Meta, PipelineEvent, ProbeResult, SchemaInfo, SqlResult } from "./types";

export class ApiError extends Error {
  constructor(public detail: ApiErrorDetail, public status: number) {
    super(detail.message);
  }
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const d = body?.detail;
    if (d && typeof d === "object" && "message" in d) return new ApiError(d as ApiErrorDetail, res.status);
    if (Array.isArray(d)) return new ApiError({ stage: "input", code: "invalid", message: d.map((x) => x.msg).join("; ") }, res.status);
  } catch { /* fall through */ }
  return new ApiError({ stage: "network", code: "http_" + res.status, message: `Request failed (${res.status}).` }, res.status);
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { "content-type": "application/json" }, ...init });
  } catch {
    throw new ApiError({ stage: "network", code: "unreachable", message: "Can't reach the API. Is the backend running on port 8000?" }, 0);
  }
  if (!res.ok) throw await toError(res);
  return res.json() as Promise<T>;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const getMeta = () => json<Meta>("/api/meta");
export const getSchema = () => json<SchemaInfo>("/api/schema");
export const executeSql = (sql: string) => json<SqlResult>("/api/sql/execute", post({ sql }));
export const runEval = (recording: "reference" | "naive") => json<EvalReport>("/api/evals/run", post({ recording }));
export const probe = (layer: "guard" | "transaction" | "privileges" | "timeout") => json<ProbeResult>("/api/security/probe", post({ layer }));

/** POST + read the SSE stream, calling onEvent for every event as it arrives. */
export async function askStream(question: string, onEvent: (e: PipelineEvent) => void, signal?: AbortSignal): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/ask/stream", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question }), signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    throw new ApiError({ stage: "network", code: "unreachable", message: "Can't reach the API. Is the backend running on port 8000?" }, 0);
  }
  if (!res.ok || !res.body) throw await toError(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseSSE<PipelineEvent>(buffer);
      buffer = rest;
      events.forEach(onEvent);
    }
  } catch (e) {
    if ((e as Error).name !== "AbortError") throw e;
  }
}

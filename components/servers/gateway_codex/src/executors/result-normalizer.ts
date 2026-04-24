import type { ExecutorResult } from "../types.js";

export function okText(payload: string, durationMs: number): ExecutorResult {
  return {
    status: "ok",
    resultKind: "text",
    payload,
    durationMs
  };
}

export function errorText(message: string, durationMs: number, exitCode?: number): ExecutorResult {
  return {
    status: "error",
    resultKind: "text",
    payload: message,
    durationMs,
    exitCode,
    errorMessage: message
  };
}

export function canceledText(message: string, durationMs: number): ExecutorResult {
  return {
    status: "canceled",
    resultKind: "text",
    payload: message,
    durationMs
  };
}

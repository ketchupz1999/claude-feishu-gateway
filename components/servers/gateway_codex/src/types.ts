export type RouteKind = "control" | "chat" | "unknown_command";

export type ResultKind = "text" | "card" | "multi_part";

export type TaskStatus = "running" | "cancel_requested";

export type ExecutorStatus = "ok" | "canceled" | "timeout" | "error";

export type CodexModelId =
  | "gpt-5.4"
  | "gpt-5.4-mini"
  | "gpt-5.3-codex"
  | "gpt-5.2-codex"
  | "gpt-5.2"
  | "gpt-5.1-codex-max"
  | "gpt-5.1-codex-mini";

export const CODEX_MODELS: Record<CodexModelId, string> = {
  "gpt-5.4":           "Latest frontier agentic coding model.",
  "gpt-5.4-mini":      "Smaller frontier agentic coding model.",
  "gpt-5.3-codex":     "Frontier Codex-optimized agentic coding model.",
  "gpt-5.2-codex":     "Frontier agentic coding model.",
  "gpt-5.2":           "Optimized for professional work and long-running agents.",
  "gpt-5.1-codex-max": "Codex-optimized model for deep and fast reasoning.",
  "gpt-5.1-codex-mini":"Optimized for codex. Cheaper, faster, but less capable."
};

export const FALLBACK_CODEX_MODEL: CodexModelId = "gpt-5.3-codex";

export type ControlCommandName =
  | "/model"
  | "/new"
  | "/clear"
  | "/sessions"
  | "/switch"
  | "/top"
  | "/pin"
  | "/unpin"
  | "/stop";

export type RoutedRequest =
  | { kind: "control"; commandName: ControlCommandName; args: string[]; rawText: string }
  | { kind: "unknown_command"; commandName: string; args: string[]; rawText: string }
  | { kind: "chat"; text: string; rawText: string };

export type ExecutorResult = {
  status: ExecutorStatus;
  resultKind: ResultKind;
  payload: string | string[] | { card: Record<string, unknown> };
  providerSessionId?: string;
  durationMs: number;
  exitCode?: number;
  errorMessage?: string;
};

export type ActiveTask = {
  requestId: string;
  taskType: "chat";
  gatewaySessionId?: string;
  startedAt: number;
  cancelMode: "codex_interrupt";
  status: TaskStatus;
  childPid?: number;
};

export type Logger = {
  info: (message: string, meta?: Record<string, unknown>) => void;
  error: (message: string, meta?: Record<string, unknown>) => void;
  warn: (message: string, meta?: Record<string, unknown>) => void;
};

export type MessageContext = {
  messageId: string;
  chatId: string;
  openId: string;
  text: string;
};

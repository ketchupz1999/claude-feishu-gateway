import {
  Codex,
  type ApprovalMode,
  type SandboxMode,
  type Thread,
  type ThreadEvent,
  type ThreadItem,
  type ThreadOptions
} from "@openai/codex-sdk";

import type { GatewayConfig } from "../config.js";
import type { ExecutorResult, Logger } from "../types.js";
import type { AgentChatExecutor, AgentRunInput } from "./agent-executor.js";

function summarizeItem(item: ThreadItem): string | null {
  switch (item.type) {
    case "command_execution":
      return `执行命令: ${item.command}`;
    case "web_search":
      return `搜索: ${item.query}`;
    case "mcp_tool_call":
      return `工具调用: ${item.server}/${item.tool}`;
    case "todo_list":
      return `更新任务列表`;
    default:
      return null;
  }
}

function resolveSandboxMode(value: string | undefined): SandboxMode {
  const v = (value ?? "").trim();
  if (v === "read-only" || v === "workspace-write" || v === "danger-full-access") {
    return v;
  }
  // Single-user server: skip sandbox to avoid .codex directory conflicts.
  return "danger-full-access";
}

function resolveApprovalPolicy(value: string | undefined): ApprovalMode {
  const v = (value ?? "").trim();
  if (v === "never" || v === "on-request" || v === "on-failure" || v === "untrusted") {
    return v;
  }
  // Keep non-interactive behavior by default; sandboxMode provides the primary safety boundary.
  return "never";
}

export class CodexChatExecutor implements AgentChatExecutor {
  private codex: Codex | null = null;
  private currentAbortController: AbortController | null = null;

  constructor(
    private readonly config: GatewayConfig,
    private readonly logger: Logger
  ) {
    const sandboxMode = resolveSandboxMode(process.env.CODEX_SANDBOX_MODE);
    const approvalPolicy = resolveApprovalPolicy(process.env.CODEX_APPROVAL_POLICY);
    if (sandboxMode === "danger-full-access") {
      this.logger.warn("CODEX_SANDBOX_MODE is set to danger-full-access", {
        approvalPolicy
      });
    }
  }

  async run(input: AgentRunInput): Promise<ExecutorResult> {
    const startedAt = Date.now();
    const abortController = new AbortController();
    this.currentAbortController = abortController;

    try {
      const threadOptions = this.makeThreadOptions(input.model);
      const thread = input.providerSessionId
        ? this.getCodex().resumeThread(input.providerSessionId, threadOptions)
        : this.getCodex().startThread(threadOptions);

      const { events } = await thread.runStreamed(input.text, {
        signal: abortController.signal
      });

      let finalResponse = "";
      let threadId: string | undefined = input.providerSessionId;
      // NOTE: Codex SDK 无原生 maxTurns 参数，如需限制轮数需手动计数 + abort
      for await (const event of events) {
        await this.handleEvent(event, input, thread, (nextResponse, nextThreadId) => {
          finalResponse = nextResponse;
          threadId = nextThreadId;
        });
      }

      return {
        status: abortController.signal.aborted ? "canceled" : "ok",
        resultKind: "text",
        payload: finalResponse || "(无输出)",
        providerSessionId: threadId,
        durationMs: Date.now() - startedAt
      };
    } catch (err) {
      this.logger.error("codex executor failed", {
        message: err instanceof Error ? err.message : String(err),
        gatewaySessionId: input.gatewaySessionId
      });
      return {
        status: abortController.signal.aborted ? "canceled" : "error",
        resultKind: "text",
        payload: err instanceof Error ? err.message : String(err),
        durationMs: Date.now() - startedAt
      };
    } finally {
      this.currentAbortController = null;
    }
  }

  async interrupt(): Promise<boolean> {
    if (!this.currentAbortController) {
      return false;
    }
    this.currentAbortController.abort();
    return true;
  }

  private async handleEvent(
    event: ThreadEvent,
    input: AgentRunInput,
    thread: Thread,
    updateState: (finalResponse: string, threadId?: string) => void
  ): Promise<void> {
    if (event.type === "thread.started") {
      updateState("", event.thread_id);
      return;
    }
    if (event.type === "item.completed") {
      if (event.item.type === "agent_message") {
        const item = event.item as Extract<ThreadItem, { type: "agent_message" }>;
        updateState(item.text, thread.id ?? undefined);
        await this.safeNotify(() => input.onText(item.text), "onText");
        return;
      }
      const summary = summarizeItem(event.item);
      if (summary) {
        await this.safeNotify(() => input.onStatus(summary), "onStatus");
      }
      return;
    }
    if (event.type === "item.updated") {
      const summary = summarizeItem(event.item);
      if (summary) {
        await this.safeNotify(() => input.onStatus(summary), "onStatus");
      }
      return;
    }
    if (event.type === "turn.failed" || event.type === "error") {
      this.logger.error("codex turn failed", {
        message: event.type === "error" ? event.message : event.error.message,
        gatewaySessionId: input.gatewaySessionId
      });
      updateState(event.type === "error" ? event.message : event.error.message, thread.id ?? undefined);
    }
  }

  private getCodex(): Codex {
    if (this.codex) {
      return this.codex;
    }
    // Let the SDK/CLI inherit the ambient Codex auth/config so it can reuse:
    // - ChatGPT/API-key login cached by Codex CLI
    // - custom provider config from ~/.codex/config.toml
    // - provider env keys loaded by the CLI from its own environment/config
    this.codex = this.config.codexApiKey
      ? new Codex({ apiKey: this.config.codexApiKey })
      : new Codex();
    return this.codex;
  }

  private makeThreadOptions(model?: string): ThreadOptions {
    return {
      ...(model ? { model } : {}),
      workingDirectory: this.config.workspace,
      skipGitRepoCheck: false,
      approvalPolicy: resolveApprovalPolicy(process.env.CODEX_APPROVAL_POLICY),
      sandboxMode: resolveSandboxMode(process.env.CODEX_SANDBOX_MODE),
      modelReasoningEffort: this.config.codexReasoningEffort
    };
  }

  private async safeNotify(fn: () => Promise<void>, kind: "onText" | "onStatus"): Promise<void> {
    try {
      await fn();
    } catch (err) {
      this.logger.warn("codex notification handler failed", {
        kind,
        message: err instanceof Error ? err.message : String(err)
      });
    }
  }
}

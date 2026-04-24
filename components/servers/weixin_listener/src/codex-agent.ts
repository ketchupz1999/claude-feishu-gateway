import {
  Codex,
  type ApprovalMode,
  type SandboxMode,
  type ThreadEvent,
  type ThreadItem,
  type ThreadOptions
} from "@openai/codex-sdk";
import type { Agent, ChatRequest, ChatResponse } from "weixin-agent-sdk";

function resolveSandboxMode(value: string | undefined): SandboxMode {
  const v = (value ?? "").trim();
  if (v === "read-only" || v === "workspace-write" || v === "danger-full-access") {
    return v;
  }
  return "danger-full-access";
}

function resolveApprovalPolicy(value: string | undefined): ApprovalMode {
  const v = (value ?? "").trim();
  if (v === "never" || v === "on-request" || v === "on-failure" || v === "untrusted") {
    return v;
  }
  return "never";
}

function summarizeItem(item: ThreadItem): string | null {
  switch (item.type) {
    case "command_execution":
      return `执行命令: ${item.command}`;
    case "web_search":
      return `搜索: ${item.query}`;
    case "mcp_tool_call":
      return `工具调用: ${item.server}/${item.tool}`;
    case "todo_list":
      return "更新任务列表";
    default:
      return null;
  }
}

export type CodexWeixinAgentOptions = {
  workingDirectory: string;
  onStatus?: (status: string) => void;
};

export class CodexWeixinAgent implements Agent {
  private readonly codex: Codex;
  private readonly workingDirectory: string;
  private readonly onStatus?: (status: string) => void;
  private readonly providerSessionByConversation = new Map<string, string>();
  private readonly inFlightByConversation = new Map<string, Promise<ChatResponse>>();

  constructor(opts: CodexWeixinAgentOptions) {
    this.workingDirectory = opts.workingDirectory;
    this.onStatus = opts.onStatus;
    const apiKey = process.env.CODEX_API_KEY ?? process.env.OPENAI_API_KEY;
    this.codex = apiKey ? new Codex({ apiKey }) : new Codex();
  }

  async chat(request: ChatRequest): Promise<ChatResponse> {
    const key = request.conversationId || "_default";
    const previous = this.inFlightByConversation.get(key);
    const next = (previous ?? Promise.resolve({ text: "" } as ChatResponse))
      .catch(() => ({ text: "" } as ChatResponse))
      .then(() => this.chatInner(request));
    this.inFlightByConversation.set(key, next);
    try {
      return await next;
    } finally {
      if (this.inFlightByConversation.get(key) === next) {
        this.inFlightByConversation.delete(key);
      }
    }
  }

  private async chatInner(request: ChatRequest): Promise<ChatResponse> {
    const prompt = this.buildPrompt(request);
    const providerSessionId = this.providerSessionByConversation.get(request.conversationId);
    const threadOptions = this.makeThreadOptions();
    const thread = providerSessionId
      ? this.codex.resumeThread(providerSessionId, threadOptions)
      : this.codex.startThread(threadOptions);

    const { events } = await thread.runStreamed(prompt);

    let finalText = "";
    let nextProviderSessionId = providerSessionId;
    for await (const event of events) {
      this.handleEvent(event, (text, nextSession) => {
        finalText = text;
        nextProviderSessionId = nextSession;
      });
    }

    if (nextProviderSessionId) {
      this.providerSessionByConversation.set(request.conversationId, nextProviderSessionId);
    }

    return { text: finalText || "(无输出)" };
  }

  private handleEvent(
    event: ThreadEvent,
    updateState: (text: string, providerSessionId?: string) => void
  ): void {
    if (event.type === "thread.started") {
      updateState("", event.thread_id);
      return;
    }

    if (event.type === "item.completed") {
      if (event.item.type === "agent_message") {
        updateState(event.item.text);
        return;
      }
      const summary = summarizeItem(event.item);
      if (summary) {
        this.onStatus?.(summary);
      }
      return;
    }

    if (event.type === "item.updated") {
      const summary = summarizeItem(event.item);
      if (summary) {
        this.onStatus?.(summary);
      }
      return;
    }

    if (event.type === "error") {
      throw new Error(event.message);
    }

    if (event.type === "turn.failed") {
      throw new Error(event.error.message);
    }
  }

  private makeThreadOptions(): ThreadOptions {
    return {
      workingDirectory: this.workingDirectory,
      skipGitRepoCheck: false,
      approvalPolicy: resolveApprovalPolicy(process.env.CODEX_APPROVAL_POLICY),
      sandboxMode: resolveSandboxMode(process.env.CODEX_SANDBOX_MODE),
      modelReasoningEffort: (process.env.CODEX_REASONING_EFFORT as "low" | "medium" | "high") || "high"
    };
  }

  private buildPrompt(request: ChatRequest): string {
    const parts: string[] = [];
    if (request.text?.trim()) {
      parts.push(request.text.trim());
    }
    if (request.media) {
      const name = request.media.fileName ? `, file=${request.media.fileName}` : "";
      parts.push(
        `\n[附件]\n- type=${request.media.type}\n- mime=${request.media.mimeType}${name}\n- path=${request.media.filePath}\n`
      );
    }
    if (parts.length === 0) {
      return "(空消息)";
    }
    return parts.join("\n");
  }
}

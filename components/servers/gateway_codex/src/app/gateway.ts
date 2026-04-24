import type { GatewayConfig } from "../config.js";
import type {
  CodexModelId,
  Logger,
  MessageContext
} from "../types.js";
import { CODEX_MODELS, FALLBACK_CODEX_MODEL } from "../types.js";
import { readCodexDefaultModel } from "../config.js";
import { routeMessage } from "./router.js";
import { CodexNativeStore } from "../sessions/codex-native-store.js";
import { GeminiNativeStore } from "../sessions/gemini-native-store.js";
import type { SessionStore } from "../sessions/session-store.js";
import { ReplyAdapter } from "../lark/reply-adapter.js";
import { TaskLock } from "./task-lock.js";
import { StopController } from "./stop-controller.js";
import { CodexChatExecutor } from "../executors/codex-chat-executor.js";
import {
  formatGeminiAuthType,
  GEMINI_DEFAULT_MODEL,
  GeminiChatExecutor
} from "../executors/gemini-chat-executor.js";
import type { AgentChatExecutor } from "../executors/agent-executor.js";

function formatProgress(status: string): string {
  if (status.startsWith("执行命令: ")) {
    const command = status.slice("执行命令: ".length);
    return `## 进度\n执行命令：\n\`\`\`bash\n${command}\n\`\`\``;
  }
  return `## 进度\n- ${status}`;
}

export class GatewayApp {
  private readonly seenMessages = new Map<string, number>();
  private readonly nativeStore: SessionStore;
  private readonly taskLock: TaskLock;
  private readonly stopController: StopController;
  private readonly chatExecutor: AgentChatExecutor;
  private readonly maxSeenMessages = 500;
  private codexModel: CodexModelId = readCodexDefaultModel() ?? FALLBACK_CODEX_MODEL;

  constructor(
    private readonly config: GatewayConfig,
    private readonly logger: Logger,
    private readonly reply?: ReplyAdapter
  ) {
    if (config.gatewayMode === "gemini") {
      this.nativeStore = new GeminiNativeStore(config.workspace, config.dataDir);
      this.chatExecutor = new GeminiChatExecutor(config, logger);
    } else {
      this.nativeStore = new CodexNativeStore(config.workspace, config.dataDir);
      this.chatExecutor = new CodexChatExecutor(config, logger);
    }
    this.taskLock = new TaskLock();
    this.stopController = new StopController(this.taskLock);
  }

  start(): void {
    this.logger.info("gateway skeleton started", {
      workspace: this.config.workspace,
      feishuAppId: this.config.feishuAppId,
      feishuAllowedOpenId: this.config.feishuAllowedOpenId
    });
  }

  inspectRoute(text: string) {
    return routeMessage(text);
  }

  async handleMessage(message: MessageContext): Promise<void> {
    if (this.isDuplicateMessage(message.messageId)) {
      this.logger.warn("ignored duplicate message", {
        messageId: message.messageId
      });
      return;
    }

    if (process.env.FEISHU_DEBUG_ECHO === "1" && this.reply) {
      await this.reply.replyText(message.messageId, `echo: ${message.text}`, message.chatId);
      return;
    }

    const routed = routeMessage(message.text);
    this.logger.info("received message", {
      routeKind: routed.kind,
      text: message.text.slice(0, 80)
    });

    if (!this.reply) {
      return;
    }

    if (routed.kind === "control") {
      await this.handleControl(message, routed.commandName, routed.args);
      return;
    }

    if (routed.kind === "unknown_command") {
      await this.reply.replyRich(
        message.messageId,
        message.chatId,
        `开源版暂不支持该命令: ${routed.commandName}\n可用控制命令: /model /new /clear /sessions /switch /top /pin /unpin /stop`,
      );
      return;
    }

    const activeTask = this.taskLock.getActiveTask();
    if (activeTask) {
      const busyMessage =
        activeTask.status === "cancel_requested"
          ? "正在取消上一个任务，请稍后再试"
          : "有任务正在执行中，请稍后再试\n发送 /stop 可中断当前任务";
      await this.reply.replyText(message.messageId, busyMessage, message.chatId);
      return;
    }

    await this.handleChat(message, routed.text);
  }

  private async handleControl(
    message: MessageContext,
    commandName: string,
    args: string[]
  ): Promise<void> {
    if (!this.reply) {
      return;
    }
    switch (commandName) {
      case "/new": {
        this.nativeStore.setCurrentThreadId(null);
        await this.chatExecutor.resetSession?.();
        await this.reply.replyText(message.messageId, "会话已新建，下次聊天将开启新对话", message.chatId);
        return;
      }
      case "/model": {
        const target = args[0]?.trim().toLowerCase();
        if (this.config.gatewayMode === "gemini") {
          if (target) {
            await this.reply.replyText(
              message.messageId,
              "Gemini 模式暂不支持 /model 切换，请在 Google CLI 配置里调整默认模型",
              message.chatId
            );
            return;
          }
          await this.reply.replyRich(
            message.messageId,
            message.chatId,
            [
              "## 当前模式: gemini",
              "",
              "Gemini 模式复用本机 Google CLI 登录态。",
              "当前开源版暂不提供飞书侧模型切换，请在本机 Gemini CLI 配置默认模型。"
            ].join("\n")
          );
          return;
        }
        if (target) {
          const codexModelIds = Object.keys(CODEX_MODELS) as CodexModelId[];
          const exactMatch = codexModelIds.find(id => id === target);
          if (exactMatch) {
            this.codexModel = exactMatch;
            await this.reply.replyRich(
              message.messageId,
              message.chatId,
              `模型已切换到 **${this.codexModel}**\n${CODEX_MODELS[this.codexModel]}`
            );
            return;
          }
          const prefixMatches = codexModelIds.filter(id => id.startsWith(target));
          if (prefixMatches.length === 1) {
            this.codexModel = prefixMatches[0]!;
            await this.reply.replyRich(
              message.messageId,
              message.chatId,
              `模型已切换到 **${this.codexModel}**\n${CODEX_MODELS[this.codexModel]}`
            );
            return;
          }
          if (prefixMatches.length > 1) {
            await this.reply.replyText(
              message.messageId,
              `多个模型匹配 "${target}":\n${prefixMatches.map(id => `  ${id}`).join("\n")}\n请输入更完整的模型名`,
              message.chatId
            );
            return;
          }
          if (target.startsWith("claude")) {
            await this.reply.replyText(
              message.messageId,
              "Codex 模式不支持 Claude 模型，请切换到 Claude 模式后使用",
              message.chatId
            );
            return;
          }
          await this.reply.replyText(
            message.messageId,
            `未知模型: ${target}\n发送 /model 查看可用模型列表`,
            message.chatId
          );
          return;
        }
        // No argument: show model list
        const modelLines = (Object.entries(CODEX_MODELS) as [CodexModelId, string][]).map(
          ([id, desc]) => {
            const current = id === this.codexModel ? " (current)" : "";
            return `  \`/model ${id}\`${current}\n  ${desc}`;
          }
        );
        await this.reply.replyRich(
          message.messageId,
          message.chatId,
          [
            `## 当前模型: ${this.codexModel}`,
            "",
            "## 可用模型",
            ...modelLines
          ].join("\n")
        );
        return;
      }
      case "/clear": {
        this.nativeStore.setCurrentThreadId(null);
        await this.chatExecutor.resetSession?.();
        await this.reply.replyText(message.messageId, "当前会话上下文已清除", message.chatId);
        return;
      }
      case "/sessions": {
        const threads = this.nativeStore.listThreads(20);
        const currentId = this.nativeStore.getCurrentThreadId();
        await this.reply.replyRich(
          message.messageId,
          message.chatId,
          this.nativeStore.formatThreadList(threads, currentId)
        );
        return;
      }
      case "/switch": {
        const target = args[0];
        if (!target) {
          await this.reply.replyText(message.messageId, "用法: /switch <序号|thread_id>", message.chatId);
          return;
        }
        const threads = this.nativeStore.listThreads(50);
        const resolved = this.nativeStore.resolveTarget(target, threads);
        if (!resolved) {
          await this.reply.replyText(message.messageId, `未找到会话: ${target}`, message.chatId);
          return;
        }
        this.nativeStore.setCurrentThreadId(resolved);
        const thread = threads.find(t => t.id === resolved);
        const preview = thread ? (thread.firstUserMessage || thread.title).slice(0, 60) : resolved;
        await this.reply.replyText(message.messageId, `已切换到: ${preview}\n${resolved}`, message.chatId);
        return;
      }
      case "/pin": {
        if (this.config.gatewayMode === "gemini") {
          await this.reply.replyText(message.messageId, "Gemini 暂不支持置顶", message.chatId);
          return;
        }
        const target = args[0];
        if (!target) {
          await this.reply.replyText(message.messageId, "用法: /pin <序号|thread_id>", message.chatId);
          return;
        }
        const threads = this.nativeStore.listThreads(50);
        const resolved = this.nativeStore.resolveTarget(target, threads);
        if (!resolved) {
          await this.reply.replyText(message.messageId, `未找到会话: ${target}`, message.chatId);
          return;
        }
        this.nativeStore.pinThread(resolved, true);
        await this.reply.replyText(message.messageId, `已置顶: ${resolved}`, message.chatId);
        return;
      }
      case "/unpin": {
        if (this.config.gatewayMode === "gemini") {
          await this.reply.replyText(message.messageId, "Gemini 暂不支持置顶", message.chatId);
          return;
        }
        const target = args[0];
        if (!target) {
          await this.reply.replyText(message.messageId, "用法: /unpin <序号|thread_id>", message.chatId);
          return;
        }
        // Resolve against pinned list to match /top display order
        const threads = this.nativeStore.listThreads(50).filter(t => t.pinned);
        const resolved = this.nativeStore.resolveTarget(target, threads);
        if (!resolved) {
          await this.reply.replyText(message.messageId, `未找到会话: ${target}`, message.chatId);
          return;
        }
        this.nativeStore.pinThread(resolved, false);
        await this.reply.replyText(message.messageId, `已取消置顶: ${resolved}`, message.chatId);
        return;
      }
      case "/top": {
        const threads = this.nativeStore.listThreads(50);
        const currentId = this.nativeStore.getCurrentThreadId();
        const formatted = this.nativeStore.formatPinnedList(threads, currentId);
        await this.reply.replyRich(message.messageId, message.chatId, formatted);
        return;
      }
      case "/stop": {
        const cancel = this.stopController.requestCancel();
        if (!cancel.requested) {
          await this.reply.replyText(message.messageId, "当前没有正在执行的任务", message.chatId);
          return;
        }
        await this.chatExecutor.interrupt();
        this.nativeStore.setCurrentThreadId(null);
        await this.chatExecutor.resetSession?.();
        await this.reply.replyText(message.messageId, "已中断当前聊天任务，会话上下文已清除", message.chatId);
        return;
      }
      default:
        await this.reply.replyText(message.messageId, `控制命令暂未实现: ${commandName}`, message.chatId);
    }
  }

  private async handleChat(message: MessageContext, text: string): Promise<void> {
    if (!this.reply) {
      return;
    }
    const requestId = `req_${Date.now()}`;
    // Use Codex thread ID directly — null means start a new thread
    const currentThreadId = this.nativeStore.getCurrentThreadId();
    const locked = this.taskLock.acquire({
      requestId,
      taskType: "chat",
      startedAt: Date.now(),
      gatewaySessionId: currentThreadId ?? undefined,
      cancelMode: "codex_interrupt",
      status: "running"
    });
    if (!locked) {
      await this.reply.replyText(message.messageId, "有任务正在执行中，请稍后再试\n发送 /stop 可中断当前任务", message.chatId);
      return;
    }
    await this.reply.replyText(
      message.messageId,
      this.formatRunningLabel(currentThreadId),
      message.chatId
    );
    try {
      const result = await this.chatExecutor.run({
        text,
        gatewaySessionId: currentThreadId ?? `new_${Date.now()}`,
        providerSessionId: currentThreadId ?? undefined,
        model: this.config.gatewayMode === "codex" ? this.codexModel : undefined,
        onText: async (chunk) => {
          if (this.stopController.shouldDiscardLateResult(requestId)) {
            return;
          }
          await this.reply!.sendRich(message.chatId, chunk);
        },
        onStatus: async (status) => {
          if (this.stopController.shouldDiscardLateResult(requestId)) {
            return;
          }
          await this.reply!.sendRich(message.chatId, formatProgress(status));
        }
      });
      const discardLateResult = this.stopController.shouldDiscardLateResult(requestId);
      if (!discardLateResult) {
        // Save the thread ID returned by Codex for future resume
        if (result.status === "ok" && result.providerSessionId) {
          this.nativeStore.setCurrentThreadId(result.providerSessionId);
        }
        if (result.status === "ok") {
          const durationSec = Math.round((result.durationMs ?? 0) / 1000);
          const footer = durationSec > 0 ? `${this.formatCompletedFooter(durationSec)}` : "";
          const doneMsg = footer ? `${footer}\n任务已完成` : "任务已完成";
          await this.reply.sendText(message.chatId, doneMsg);
        } else {
          await this.reply.sendRich(message.chatId, String(result.payload));
        }
      }
    } finally {
      this.taskLock.release(requestId);
    }
  }

  private isDuplicateMessage(messageId: string): boolean {
    if (this.seenMessages.has(messageId)) {
      return true;
    }
    this.seenMessages.set(messageId, Date.now());
    while (this.seenMessages.size > this.maxSeenMessages) {
      const firstKey = this.seenMessages.keys().next().value as string | undefined;
      if (!firstKey) {
        break;
      }
      this.seenMessages.delete(firstKey);
    }
    return false;
  }

  private formatRunningLabel(currentThreadId?: string | null): string {
    if (this.config.gatewayMode === "gemini") {
      return `正在执行... [gemini ${GEMINI_DEFAULT_MODEL} | ${formatGeminiAuthType()} | session ${formatShortSessionId(currentThreadId)}]`;
    }
    return `正在执行... [codex ${this.codexModel}]`;
  }

  private formatCompletedFooter(durationSec: number): string {
    if (this.config.gatewayMode === "gemini") {
      return `[gemini ${GEMINI_DEFAULT_MODEL} | ${formatGeminiAuthType()} | ${durationSec}s]`;
    }
    return `[codex ${this.codexModel} | ${durationSec}s]`;
  }
}

function formatShortSessionId(sessionId?: string | null): string {
  if (!sessionId) {
    return "new";
  }
  return sessionId.length > 8 ? sessionId.slice(0, 8) : sessionId;
}

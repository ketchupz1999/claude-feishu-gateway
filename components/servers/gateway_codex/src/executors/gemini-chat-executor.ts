import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import {
  AuthType,
  clearOauthClientCache,
  makeFakeConfig,
  GeminiEventType
} from "@google/gemini-cli-core";
import type { Config, GeminiClient } from "@google/gemini-cli-core";
import type { GatewayConfig } from "../config.js";
import type { ExecutorResult, Logger } from "../types.js";
import type { AgentChatExecutor, AgentRunInput } from "./agent-executor.js";
import { resolveGeminiChatsDir } from "../sessions/gemini-native-store.js";
import type { GeminiConversationRecord } from "../sessions/gemini-native-store.js";

const GEMINI_LOGIN_REQUIRED_MESSAGE =
  "Gemini 未登录：Gateway 需要复用本机 Gemini CLI 登录态，但当前进程无法获取有效凭证。\n" +
  "请先在服务器终端运行 `gemini` 完成登录，或配置 `GEMINI_API_KEY` 后重启 Gateway。";

export const GEMINI_DEFAULT_MODEL = "gemini-3-flash-preview";

function normalizeGeminiError(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  const lowerMessage = message.toLowerCase();
  const isAuthError =
    lowerMessage.includes("authentication") ||
    lowerMessage.includes("authorization") ||
    lowerMessage.includes("credential") ||
    lowerMessage.includes("api key") ||
    lowerMessage.includes("login");

  if (!isAuthError) {
    return message;
  }

  return `${GEMINI_LOGIN_REQUIRED_MESSAGE}\n原始错误：${message}`;
}

export function resolveGeminiAuthType(): AuthType {
  if (process.env.GOOGLE_GENAI_USE_GCA === "true") {
    return AuthType.LOGIN_WITH_GOOGLE;
  }
  if (process.env.GOOGLE_GENAI_USE_VERTEXAI === "true") {
    return AuthType.USE_VERTEX_AI;
  }
  if (process.env.GEMINI_API_KEY) {
    return AuthType.USE_GEMINI;
  }
  if (
    process.env.CLOUD_SHELL === "true" ||
    process.env.GEMINI_CLI_USE_COMPUTE_ADC === "true"
  ) {
    return AuthType.COMPUTE_ADC;
  }
  return AuthType.LOGIN_WITH_GOOGLE;
}

export function formatGeminiAuthType(authType = resolveGeminiAuthType()): string {
  switch (authType) {
    case AuthType.USE_GEMINI:
      return "api-key";
    case AuthType.USE_VERTEX_AI:
      return "vertex";
    case AuthType.COMPUTE_ADC:
      return "adc";
    case AuthType.GATEWAY:
      return "gateway";
    case AuthType.LOGIN_WITH_GOOGLE:
    default:
      return "oauth";
  }
}

function readGeminiRecord(filePath: string): GeminiConversationRecord | null {
  try {
    const record = JSON.parse(fs.readFileSync(filePath, "utf8")) as GeminiConversationRecord;
    return typeof record.sessionId === "string" && record.sessionId ? record : null;
  } catch {
    return null;
  }
}

export function findGeminiSessionFile(
  chatsDir: string,
  providerSessionId: string
): { filePath: string; record: GeminiConversationRecord } | null {
  if (!fs.existsSync(chatsDir)) {
    return null;
  }
  const files = fs.readdirSync(chatsDir)
    .filter(file => file.startsWith("session-") && file.endsWith(".json"));

  for (const file of files) {
    const filePath = path.join(chatsDir, file);
    const record = readGeminiRecord(filePath);
    if (record?.sessionId === providerSessionId) {
      return { filePath, record };
    }
  }

  // Backward compatibility for older pointers that stored the file-name suffix.
  for (const file of files) {
    if (file !== `session-${providerSessionId}.json` && !file.includes(`-${providerSessionId}.json`)) {
      continue;
    }
    const filePath = path.join(chatsDir, file);
    const record = readGeminiRecord(filePath);
    if (record) {
      return { filePath, record };
    }
  }

  const shortId = providerSessionId.length >= 8
    ? providerSessionId.slice(0, 8)
    : providerSessionId;
  for (const file of files) {
    if (!file.includes(`-${shortId}.json`)) {
      continue;
    }
    const filePath = path.join(chatsDir, file);
    const record = readGeminiRecord(filePath);
    if (record) {
      return { filePath, record };
    }
  }
  return null;
}

function getRecordingSessionId(client: GeminiClient): string | null {
  const rec = client.getChatRecordingService();
  const sessionId = rec?.getConversation()?.sessionId;
  return typeof sessionId === "string" && sessionId ? sessionId : null;
}

function getRecordingFileSessionId(client: GeminiClient): string | null {
  const rec = client.getChatRecordingService();
  const filePath = rec?.getConversationFilePath();
  if (!filePath) {
    return null;
  }
  return readGeminiRecord(filePath)?.sessionId ?? null;
}

export class GeminiChatExecutor implements AgentChatExecutor {
  private configInstance: Config | null = null;
  private client: GeminiClient | null = null;
  private currentAbortController: AbortController | null = null;
  private initialized = false;

  constructor(
    private readonly gatewayConfig: GatewayConfig,
    private readonly logger: Logger
  ) {}

  private async ensureInitialized() {
    if (this.initialized) return;

    this.logger.info("Initializing Gemini SDK...");
    try {
      this.configInstance = makeFakeConfig({
        model: GEMINI_DEFAULT_MODEL,
        sessionId: randomUUID(),
        cwd: this.gatewayConfig.workspace,
        targetDir: this.gatewayConfig.workspace,
        noBrowser: true,
        interactive: false,
      });

      await this.configInstance.initialize();

      await this.configInstance.refreshAuth(resolveGeminiAuthType());

      this.client = this.configInstance.geminiClient;
      await this.client.initialize();

      this.initialized = true;
      this.logger.info("Gemini SDK initialized successfully.");
    } catch (err) {
      this.logger.error("Failed to initialize Gemini SDK", {
        error: err instanceof Error ? err.message : String(err)
      });
      clearOauthClientCache();
      throw new Error(normalizeGeminiError(err));
    }
  }

  async run(input: AgentRunInput): Promise<ExecutorResult> {
    const startedAt = Date.now();
    const abortController = new AbortController();
    this.currentAbortController = abortController;

    try {
      await this.ensureInitialized();

      if (input.providerSessionId) {
        const currentSessionId = getRecordingSessionId(this.client!);
        if (currentSessionId !== input.providerSessionId) {
          this.logger.info(`Resuming Gemini session: ${input.providerSessionId}`);
          const chatsDir = resolveGeminiChatsDir(this.gatewayConfig.workspace);
          const sessionFile = findGeminiSessionFile(chatsDir, input.providerSessionId);
          if (sessionFile) {
            await this.client!.resumeChat([], {
              conversation: sessionFile.record as any,
              filePath: sessionFile.filePath
            });
            this.logger.info(`Successfully resumed Gemini session: ${sessionFile.record.sessionId}`);
          } else {
            this.logger.warn(`Could not find session file for: ${input.providerSessionId}, starting new chat.`);
          }
        }
      }

      const events = this.client!.sendMessageStream(
        input.text,
        abortController.signal,
        `gw_${Date.now()}`
      );

      let fullResponse = "";
      let lastProviderSessionId = input.providerSessionId;

      for await (const event of events) {
        switch (event.type) {
          case GeminiEventType.Content:
            fullResponse += event.value;
            await input.onText(event.value);
            break;
          case GeminiEventType.Thought:
            await input.onStatus(`思考中: ${event.value.subject} - ${event.value.description}`);
            break;
          case GeminiEventType.ToolCallRequest:
            await input.onStatus(`调用工具: ${event.value.name}`);
            break;
          case GeminiEventType.ToolCallResponse:
            // Optional: show tool result summary
            break;
          case GeminiEventType.Finished:
            lastProviderSessionId =
              getRecordingSessionId(this.client!) ??
              getRecordingFileSessionId(this.client!) ??
              lastProviderSessionId;
            break;
          case GeminiEventType.Error:
            throw event.value.error;
        }
      }

      return {
        status: "ok",
        resultKind: "text",
        payload: fullResponse,
        providerSessionId: lastProviderSessionId,
        durationMs: Date.now() - startedAt
      };

    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return {
          status: "canceled",
          resultKind: "text",
          payload: "已中断",
          durationMs: Date.now() - startedAt
        };
      }

      this.logger.error("Gemini run failed", {
        error: err instanceof Error ? err.message : String(err)
      });

      return {
        status: "error",
        resultKind: "text",
        payload: err instanceof Error ? err.message : String(err),
        durationMs: Date.now() - startedAt
      };
    } finally {
      this.currentAbortController = null;
    }
  }

  async interrupt(): Promise<boolean> {
    if (this.currentAbortController) {
      this.currentAbortController.abort();
      return true;
    }
    return false;
  }

  resetSession(): void {
    this.currentAbortController?.abort();
    this.currentAbortController = null;
    this.client = null;
    this.configInstance = null;
    this.initialized = false;
  }
}

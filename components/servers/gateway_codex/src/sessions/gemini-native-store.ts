import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import type { SessionStore, ThreadMeta } from "./session-store.js";

// Matching the structure from @google/gemini-cli-core/dist/src/services/chatRecordingService.js
export interface GeminiConversationRecord {
  sessionId: string;
  projectHash: string;
  startTime: string;
  lastUpdated: string;
  messages: Array<{
    type: string;
    content: string | unknown[];
    displayContent?: unknown;
    timestamp: string;
    model?: string;
  }>;
  summary?: string;
}

function resolveGeminiHomeDir(): string {
  return process.env.GEMINI_CLI_HOME || os.homedir();
}

export function resolveGeminiChatsDir(workspace: string): string {
  return path.join(resolveGeminiHomeDir(), ".gemini", "tmp", path.basename(workspace), "chats");
}

function oneLine(text: string): string {
  return text.replace(/[\r\n]+/g, " ").replace(/\s+/g, " ").trim();
}

function truncate(text: string, maxLen: number): string {
  const clean = oneLine(text);
  if (clean.length <= maxLen) {
    return clean;
  }
  return clean.slice(0, maxLen) + "…";
}

function formatTimestamp(epochMs: number): string {
  if (!Number.isFinite(epochMs) || epochMs <= 0) {
    return "unknown-time";
  }
  const date = new Date(epochMs);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function contentToText(content: string | unknown[]): string {
  if (typeof content === "string") {
    return content;
  }
  const parts: string[] = [];
  for (const part of content) {
    if (typeof part === "string") {
      parts.push(part);
      continue;
    }
    if (!part || typeof part !== "object") {
      continue;
    }
    const maybeText = (part as { text?: unknown }).text;
    if (typeof maybeText === "string") {
      parts.push(maybeText);
    }
  }
  return parts.join("\n");
}

function pickUserPreview(record: GeminiConversationRecord): string {
  const userMessages = record.messages
    .filter(message => message.type === "user")
    .map(message => contentToText(message.content))
    .map(oneLine)
    .filter(Boolean);
  return userMessages.at(-1) || record.summary || record.sessionId;
}

function pickModel(record: GeminiConversationRecord): string {
  const model = [...record.messages]
    .reverse()
    .find(message => message.type === "gemini" && typeof message.model === "string")
    ?.model;
  return model || "unknown-model";
}

export class GeminiNativeStore implements SessionStore {
  private readonly sessionPointerFile: string;
  private readonly chatsDir: string;

  constructor(
    private readonly workspace: string,
    private readonly dataDir: string
  ) {
    // Current active session ID pointer
    this.sessionPointerFile = path.join(dataDir, ".gateway_gemini_session");

    // Directory where @google/gemini-cli-core stores session JSONs
    this.chatsDir = resolveGeminiChatsDir(workspace);
  }

  listThreads(limit = 20): ThreadMeta[] {
    if (!fs.existsSync(this.chatsDir)) {
      return [];
    }

    const files = fs.readdirSync(this.chatsDir)
      .filter(f => f.startsWith("session-") && f.endsWith(".json"))
      .map(f => {
        const fullPath = path.join(this.chatsDir, f);
        const stats = fs.statSync(fullPath);
        return { name: f, fullPath, mtime: stats.mtimeMs };
      })
      .sort((a, b) => b.mtime - a.mtime)
      .slice(0, limit);

    const threads: ThreadMeta[] = [];
    for (const file of files) {
      try {
        const content = fs.readFileSync(file.fullPath, "utf8");
        const record = JSON.parse(content) as GeminiConversationRecord;
        const preview = pickUserPreview(record);
        const updatedAt = Date.parse(record.lastUpdated);

        threads.push({
          id: record.sessionId,
          title: preview || record.sessionId,
          model: pickModel(record),
          updatedAt: Number.isFinite(updatedAt) ? updatedAt : file.mtime,
          pinned: false,
          firstUserMessage: preview
        });
      } catch (e) {
        // Skip malformed files
      }
    }
    return threads;
  }

  getThread(threadId: string): ThreadMeta | null {
    const threads = this.listThreads(100);
    return threads.find(t => t.id === threadId) || null;
  }

  getCurrentThreadId(): string | null {
    if (!fs.existsSync(this.sessionPointerFile)) {
      return null;
    }
    const value = fs.readFileSync(this.sessionPointerFile, "utf8").trim();
    return value || null;
  }

  setCurrentThreadId(threadId: string | null): void {
    fs.mkdirSync(path.dirname(this.sessionPointerFile), { recursive: true });
    fs.writeFileSync(this.sessionPointerFile, threadId ?? "", "utf8");
  }

  pinThread(threadId: string, pinned: boolean): void {
    // TODO: implement pin state for gemini sessions if needed
  }

  formatThreadList(threads: ThreadMeta[], currentThreadId: string | null): string {
    if (threads.length === 0) {
      return "暂无历史会话";
    }
    const lines = ["## Gemini 历史会话"];
    for (let i = 0; i < threads.length; i++) {
      const t = threads[i]!;
      const marker = t.id === currentThreadId ? " ◀ 当前" : "";
      const preview = truncate(t.firstUserMessage || t.title || "(空会话)", 48);
      lines.push(`**${i + 1}. ${preview}${marker}**`);
      lines.push(`模型：${t.model || "unknown-model"} · 时间：${formatTimestamp(t.updatedAt)} · 来源：Gemini CLI`);
      lines.push("");
    }
    lines.push("切换：`/switch 1`");
    return lines.join("\n");
  }

  formatPinnedList(threads: ThreadMeta[], currentThreadId: string | null): string {
    return "Gemini 暂不支持置顶";
  }

  resolveTarget(target: string, threads: ThreadMeta[]): string | null {
    const normalized = target.trim();
    if (!normalized) return null;
    if (/^\d+$/.test(normalized)) {
      const index = Number.parseInt(normalized, 10) - 1;
      return threads[index]?.id ?? null;
    }
    return threads.find(t => t.id === normalized)?.id ?? null;
  }
}

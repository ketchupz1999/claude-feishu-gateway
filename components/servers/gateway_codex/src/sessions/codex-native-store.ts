/**
 * Codex Native Session Store
 *
 * Reads threads directly from Codex local state instead of maintaining a
 * separate gateway session registry. Current Codex CLI entries live in
 * ~/.codex/state_5.sqlite, while SDK-created sessions can live in
 * ~/.codex/sessions/.../*.jsonl before they appear in the SQLite index.
 *
 * This means `/sessions` shows the same threads as `codex` CLI,
 * and `resumeThread(id)` can resume any of them.
 *
 * Pin state is stored in a lightweight JSON file since we don't modify Codex's schema.
 */
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import type { SessionStore, ThreadMeta } from "./session-store.js";

export type CodexThread = ThreadMeta & {
  source: string;
  cwd: string;
  createdAt: number;   // unix epoch seconds
  archived: boolean;
};

type PinState = Record<string, boolean>;

function readPinState(pinFile: string): PinState {
  if (!fs.existsSync(pinFile)) {
    return {};
  }
  try {
    return JSON.parse(fs.readFileSync(pinFile, "utf8")) as PinState;
  } catch {
    return {};
  }
}

function savePinState(pinFile: string, state: PinState): void {
  fs.mkdirSync(path.dirname(pinFile), { recursive: true });
  fs.writeFileSync(pinFile, JSON.stringify(state, null, 2), "utf8");
}

function resolveScriptPath(workspace: string): string {
  return path.join(workspace, "components", "scripts", "codex_session.py");
}

function runSessionScript(
  scriptPath: string,
  args: string[]
): Record<string, unknown>[] | Record<string, unknown> | null {
  try {
    const result = execFileSync("python3", [scriptPath, ...args], {
      encoding: "utf8",
      timeout: 5000
    });
    if (!result.trim()) {
      return [];
    }
    return JSON.parse(result) as Record<string, unknown>[] | Record<string, unknown> | null;
  } catch {
    return [];
  }
}

function formatTimestamp(epoch: number): string {
  return new Date(epoch * 1000).toISOString().replace("T", " ").slice(0, 16);
}

function oneLine(text: string): string {
  return text.replace(/[\r\n]+/g, " ").trim();
}

function truncate(text: string, maxLen: number): string {
  const clean = oneLine(text);
  if (clean.length <= maxLen) {
    return clean;
  }
  return clean.slice(0, maxLen) + "…";
}

function formatThreadSource(source: string): string {
  if (source === "codex_sdk_ts") {
    return "Codex SDK";
  }
  if (source === "codex-tui") {
    return "Codex CLI";
  }
  return source || "Codex";
}

export class CodexNativeStore implements SessionStore {
  private readonly scriptPath: string;
  private readonly sessionFile: string;
  private readonly pinFile: string;

  constructor(
    private readonly workspace: string,
    private readonly dataDir: string
  ) {
    this.scriptPath = resolveScriptPath(workspace);
    this.sessionFile = path.join(dataDir, ".gateway_session");
    this.pinFile = path.join(dataDir, ".gateway_pins.json");
  }

  private rowToThread(row: Record<string, unknown>, pins: PinState): CodexThread {
    const id = String(row.id ?? "");
    return {
      id,
      title: String(row.title ?? ""),
      model: String(row.model ?? ""),
      source: String(row.source ?? ""),
      cwd: String(row.cwd ?? ""),
      firstUserMessage: String(row.first_user_message ?? ""),
      createdAt: Number(row.created_at ?? 0),
      updatedAt: Number(row.updated_at ?? 0),
      archived: row.archived === 1,
      pinned: Boolean(pins[id])
    };
  }

  /** List threads for this workspace (excludes subagents and archived) */
  listThreads(limit = 20): CodexThread[] {
    const result = runSessionScript(this.scriptPath, [
      "list", "--cwd", this.workspace, "--limit", String(limit)
    ]);
    if (!Array.isArray(result)) {
      return [];
    }
    const pins = readPinState(this.pinFile);
    return result.map(row => this.rowToThread(row as Record<string, unknown>, pins));
  }

  /** Get a single thread by ID */
  getThread(threadId: string): CodexThread | null {
    const result = runSessionScript(this.scriptPath, ["get", threadId]);
    if (!result || Array.isArray(result)) {
      return null;
    }
    const pins = readPinState(this.pinFile);
    return this.rowToThread(result, pins);
  }

  /** Get current thread ID (from gateway session file) */
  getCurrentThreadId(): string | null {
    if (!fs.existsSync(this.sessionFile)) {
      return null;
    }
    const value = fs.readFileSync(this.sessionFile, "utf8").trim();
    return value || null;
  }

  /** Set current thread ID */
  setCurrentThreadId(threadId: string | null): void {
    fs.mkdirSync(path.dirname(this.sessionFile), { recursive: true });
    fs.writeFileSync(this.sessionFile, threadId ?? "", "utf8");
  }

  /** Pin/unpin a thread */
  pinThread(threadId: string, pinned: boolean): void {
    const state = readPinState(this.pinFile);
    if (pinned) {
      state[threadId] = true;
    } else {
      delete state[threadId];
    }
    savePinState(this.pinFile, state);
  }

  /** Format thread list for display */
  formatThreadList(threads: ThreadMeta[], currentThreadId: string | null): string {
    if (threads.length === 0) {
      return "暂无历史会话";
    }
    const lines = ["## 历史会话"];
    for (let i = 0; i < threads.length; i++) {
      const t = threads[i]! as CodexThread;
      const marker = t.id === currentThreadId ? " ◀ 当前" : "";
      const pin = t.pinned ? "[置顶] " : "";
      const preview = truncate(t.firstUserMessage || t.title || "(空会话)", 48);
      const time = formatTimestamp(t.updatedAt);
      const model = t.model || "unknown-model";
      const source = formatThreadSource(t.source);
      lines.push(`**${i + 1}. ${pin}${preview}${marker}**`);
      lines.push(`模型：${model} · 时间：${time} · 来源：${source}`);
      lines.push("");
    }
    lines.push("切换：`/switch 1`");
    lines.push("置顶：`/pin 1`");
    return lines.join("\n");
  }

  /** Format pinned thread list */
  formatPinnedList(threads: ThreadMeta[], currentThreadId: string | null): string {
    const pinned = threads.filter(t => t.pinned);
    if (pinned.length === 0) {
      return "暂无置顶会话";
    }
    const lines = ["## 置顶会话"];
    for (let i = 0; i < pinned.length; i++) {
      const t = pinned[i]! as CodexThread;
      const marker = t.id === currentThreadId ? " ◀ 当前" : "";
      const preview = truncate(t.firstUserMessage || t.title || "(空会话)", 48);
      lines.push(`**${i + 1}. ${preview}${marker}**`);
      lines.push(`模型：${t.model || "unknown-model"} · 时间：${formatTimestamp(t.updatedAt)} · 来源：${formatThreadSource(t.source)}`);
      lines.push("");
    }
    lines.push("切换：`/switch 1`");
    lines.push("取消置顶：`/unpin 1`");
    return lines.join("\n");
  }

  /** Resolve a target (1-based index or thread ID) to thread ID */
  resolveTarget(target: string, threads: ThreadMeta[]): string | null {
    const normalized = target.trim();
    if (!normalized) {
      return null;
    }
    if (/^\d+$/.test(normalized)) {
      const index = Number.parseInt(normalized, 10) - 1;
      return threads[index]?.id ?? null;
    }
    // Direct thread ID
    return threads.find(t => t.id === normalized)?.id ?? null;
  }
}

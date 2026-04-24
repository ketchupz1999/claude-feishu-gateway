import path from "node:path";
import process from "node:process";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";
import type { CodexModelId } from "./types.js";
import { CODEX_MODELS } from "./types.js";

export type GatewayConfig = {
  workspace: string;
  dataDir: string;
  logDir: string;
  pidFile: string;
  sessionFile: string;
  currentDate: string;
  feishuSecretsFile: string;
  feishuAppId?: string;
  feishuAppSecret?: string;
  feishuAllowedOpenId?: string;
  codexApiKey?: string;
  codexReasoningEffort: "low" | "medium" | "high";
  gatewayMode: "codex" | "gemini";
  listenerChannels?: Record<string, ListenerChannelConfig>;
};

export type ListenerChannelConfig = {
  enabled: boolean;
  command?: string[] | string;
  env?: Record<string, string>;
};

function moduleDirname(): string {
  return path.dirname(fileURLToPath(import.meta.url));
}

function isWorkspaceRoot(dir: string): boolean {
  return (
    (fs.existsSync(path.join(dir, "CLAUDE.md")) ||
      fs.existsSync(path.join(dir, ".claude", "CLAUDE.md"))) &&
    fs.existsSync(path.join(dir, "components")) &&
    fs.existsSync(path.join(dir, "Makefile"))
  );
}

function resolveWorkspace(): string {
  const here = moduleDirname();
  const candidates = [
    // tsx dev: .../components/servers/gateway_codex/src
    path.resolve(here, "..", "..", "..", ".."),
    // compiled start: .../components/servers/gateway_codex/dist/src
    path.resolve(here, "..", "..", "..", "..", ".."),
    // make targets often `cd components/servers/gateway_codex`
    path.resolve(process.cwd(), "..", "..", ".."),
    path.resolve(process.cwd(), "..", "..", "..", "..")
  ];
  for (const dir of candidates) {
    if (isWorkspaceRoot(dir)) {
      return dir;
    }
  }
  return candidates[0]!;
}

function utcDate(): string {
  return new Date().toISOString().slice(0, 10);
}

function deepMerge(base: Record<string, unknown>, override: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const old = result[key];
    if (
      old &&
      value &&
      typeof old === "object" &&
      !Array.isArray(old) &&
      typeof value === "object" &&
      !Array.isArray(value)
    ) {
      result[key] = deepMerge(
        old as Record<string, unknown>,
        value as Record<string, unknown>
      );
      continue;
    }
    result[key] = value;
  }
  return result;
}

function loadYamlAsObject(filePath: string): Record<string, unknown> {
  if (!fs.existsSync(filePath)) {
    return {};
  }
  try {
    const parsed = parseYaml(fs.readFileSync(filePath, "utf8")) as unknown;
    if (parsed == null) {
      return {};
    }
    if (typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("top-level YAML document must be a mapping object");
    }
    return parsed as Record<string, unknown>;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(`failed to parse config file ${filePath}: ${message}`);
  }
}

function normalizeListenerChannels(raw: unknown): Record<string, ListenerChannelConfig> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return {};
  }
  const channels: Record<string, ListenerChannelConfig> = {};
  for (const [name, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      continue;
    }
    const obj = value as Record<string, unknown>;
    const enabled = Boolean(obj.enabled);
    const commandRaw = obj.command;
    let command: string[] | string | undefined;
    if (Array.isArray(commandRaw)) {
      command = commandRaw.map((part) => String(part));
    } else if (typeof commandRaw === "string") {
      command = commandRaw;
    }

    let env: Record<string, string> | undefined;
    if (obj.env && typeof obj.env === "object" && !Array.isArray(obj.env)) {
      env = {};
      for (const [k, v] of Object.entries(obj.env as Record<string, unknown>)) {
        env[String(k)] = String(v);
      }
    }

    channels[name] = { enabled, command, env };
  }
  return channels;
}

function normalizeReasoningEffort(value: string): "low" | "medium" | "high" {
  const v = value.trim().toLowerCase();
  if (v === "low" || v === "medium" || v === "high") return v;
  return "high";
}

export function loadConfig(): GatewayConfig {
  const workspace = process.env.AGENTS_WORKSPACE ?? resolveWorkspace();
  const dataDir = path.join(workspace, "data");
  const runtimeConfigExample = path.join(workspace, "components", "config.example.yaml");
  const runtimeConfigFile = path.join(workspace, "components", "config.yaml");
  const runtimeConfig = deepMerge(
    loadYamlAsObject(runtimeConfigExample),
    loadYamlAsObject(runtimeConfigFile)
  );
  const listenerChannels = normalizeListenerChannels(runtimeConfig.listener_channels);
  const feishuSecretsFile = path.join(workspace, ".claude", "secrets", "feishu_app.json");
  let feishu: Record<string, string> = {};
  if (fs.existsSync(feishuSecretsFile)) {
    try {
      feishu = JSON.parse(fs.readFileSync(feishuSecretsFile, "utf8")) as Record<string, string>;
    } catch {
      feishu = {};
    }
  }
  return {
    workspace,
    dataDir,
    // Reuse the legacy gateway runtime contract so Makefile/watchdog/status remain compatible.
    logDir: path.join(dataDir, "logs"),
    pidFile: path.join(dataDir, "gateway.pid"),
    sessionFile: path.join(dataDir, ".gateway_session"),
    currentDate: utcDate(),
    feishuSecretsFile,
    feishuAppId: process.env.FEISHU_APP_ID ?? feishu.app_id,
    feishuAppSecret: process.env.FEISHU_APP_SECRET ?? feishu.app_secret,
    feishuAllowedOpenId: process.env.FEISHU_ALLOWED_OPEN_ID ?? feishu.allowed_open_id,
    codexApiKey: process.env.OPENAI_API_KEY ?? process.env.CODEX_API_KEY,
    codexReasoningEffort: normalizeReasoningEffort(
      String(runtimeConfig.codex_reasoning_effort ?? "")
    ),
    gatewayMode: (process.env.GATEWAY_MODE ?? runtimeConfig.gateway_mode ?? "codex") as "codex" | "gemini",
    listenerChannels
  };
}

/**
 * Read the default model from ~/.codex/config.toml.
 * Returns null if not found or not a known model.
 */
export function readCodexDefaultModel(): CodexModelId | null {
  const home = process.env.HOME ?? "/home/claude";
  const configPath = path.join(home, ".codex", "config.toml");
  if (!fs.existsSync(configPath)) {
    return null;
  }
  try {
    const content = fs.readFileSync(configPath, "utf8");
    // Simple TOML parse: find top-level `model = "..."` (before any [section])
    for (const line of content.split("\n")) {
      if (line.startsWith("[")) {
        break; // reached a section header, stop
      }
      const match = line.match(/^\s*model\s*=\s*"([^"]+)"/);
      if (match) {
        const value = match[1] as string;
        if (value in CODEX_MODELS) {
          return value as CodexModelId;
        }
        return null;
      }
    }
  } catch {
    // ignore
  }
  return null;
}

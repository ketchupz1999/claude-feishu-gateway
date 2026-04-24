import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { clearOauthClientCache } from "@google/gemini-cli-core";

import {
  findGeminiSessionFile,
  GeminiChatExecutor
} from "../src/executors/gemini-chat-executor.js";

const noopLogger = {
  info: () => {},
  warn: () => {},
  error: () => {}
};

function makeConfig(dir: string) {
  return {
    workspace: dir,
    dataDir: path.join(dir, "data"),
    logDir: path.join(dir, "logs"),
    pidFile: path.join(dir, "gateway.pid"),
    sessionFile: path.join(dir, ".gateway_session"),
    currentDate: "2026-03-20",
    feishuSecretsFile: path.join(dir, "feishu_app.json"),
    feishuAppId: "cli_test",
    feishuAppSecret: "secret",
    feishuAllowedOpenId: "ou_test",
    codexApiKey: undefined,
    codexReasoningEffort: "high" as const,
    gatewayMode: "gemini" as const
  };
}

function saveEnv(keys: string[]): Record<string, string | undefined> {
  return Object.fromEntries(keys.map((key) => [key, process.env[key]]));
}

function restoreEnv(values: Record<string, string | undefined>): void {
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
}

test("GeminiChatExecutor returns a login-required error when CLI credentials are missing", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-gemini-auth-"));
  const envKeys = [
    "GEMINI_CLI_HOME",
    "GEMINI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_GENAI_USE_GCA",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "CLOUD_SHELL",
    "GEMINI_CLI_USE_COMPUTE_ADC"
  ];
  const previousEnv = saveEnv(envKeys);
  clearOauthClientCache();

  try {
    process.env.GEMINI_CLI_HOME = path.join(dir, "gemini-home");
    delete process.env.GEMINI_API_KEY;
    delete process.env.GOOGLE_APPLICATION_CREDENTIALS;
    delete process.env.GOOGLE_GENAI_USE_GCA;
    delete process.env.GOOGLE_GENAI_USE_VERTEXAI;
    delete process.env.CLOUD_SHELL;
    delete process.env.GEMINI_CLI_USE_COMPUTE_ADC;

    const executor = new GeminiChatExecutor(makeConfig(dir), noopLogger);
    const result = await executor.run({
      text: "hi",
      gatewaySessionId: "new_test",
      onText: async () => {},
      onStatus: async () => {}
    });

    assert.equal(result.status, "error");
    assert.match(String(result.payload), /Gemini 未登录/);
  } finally {
    clearOauthClientCache();
    restoreEnv(previousEnv);
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("findGeminiSessionFile resolves native sessionId before legacy filename ids", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-gemini-session-file-"));
  try {
    const chatsDir = path.join(dir, "chats");
    fs.mkdirSync(chatsDir, { recursive: true });
    const filePath = path.join(chatsDir, "session-2026-04-24T03-49-bb47f0d1.json");
    fs.writeFileSync(
      filePath,
      JSON.stringify({
        sessionId: "bb47f0d1-f770-4049-8bd8-7ca7055f8790",
        projectHash: "claude-feishu-gateway",
        startTime: "2026-04-24T03:49:26.550Z",
        lastUpdated: "2026-04-24T03:49:48.127Z",
        messages: []
      }),
      "utf8"
    );

    const byNativeId = findGeminiSessionFile(chatsDir, "bb47f0d1-f770-4049-8bd8-7ca7055f8790");
    assert.equal(byNativeId?.filePath, filePath);
    assert.equal(byNativeId?.record.sessionId, "bb47f0d1-f770-4049-8bd8-7ca7055f8790");

    const byLegacyFilenameId = findGeminiSessionFile(chatsDir, "2026-04-24T03-49-bb47f0d1");
    assert.equal(byLegacyFilenameId?.filePath, filePath);
    assert.equal(byLegacyFilenameId?.record.sessionId, "bb47f0d1-f770-4049-8bd8-7ca7055f8790");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

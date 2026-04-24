import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { GeminiNativeStore } from "../src/sessions/gemini-native-store.js";

function restoreEnv(key: string, value: string | undefined): void {
  if (value === undefined) {
    delete process.env[key];
  } else {
    process.env[key] = value;
  }
}

test("GeminiNativeStore extracts user text and model from native Gemini sessions", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-gemini-store-"));
  const previousHome = process.env.GEMINI_CLI_HOME;

  try {
    const workspace = path.join(dir, "claude-feishu-gateway");
    const geminiHome = path.join(dir, "gemini-home");
    process.env.GEMINI_CLI_HOME = geminiHome;

    const chatsDir = path.join(geminiHome, ".gemini", "tmp", path.basename(workspace), "chats");
    fs.mkdirSync(chatsDir, { recursive: true });
    fs.writeFileSync(
      path.join(chatsDir, "session-2026-04-24T03-49-bb47f0d1.json"),
      JSON.stringify({
        kind: "main",
        sessionId: "bb47f0d1-f770-4049-8bd8-7ca7055f8790",
        projectHash: "claude-feishu-gateway",
        startTime: "2026-04-24T03:49:26.550Z",
        lastUpdated: "2026-04-24T03:49:48.127Z",
        messages: [
          {
            type: "user",
            timestamp: "2026-04-24T03:49:26.550Z",
            content: [{ text: "hi" }]
          },
          {
            type: "gemini",
            timestamp: "2026-04-24T03:49:34.344Z",
            content: "Hello",
            model: "gemini-3-flash-preview"
          },
          {
            type: "user",
            timestamp: "2026-04-24T03:49:38.781Z",
            content: [{ text: "请读取 README.md，概括这个项目现在支持哪些 Gateway 模式。" }]
          }
        ]
      }),
      "utf8"
    );

    const store = new GeminiNativeStore(workspace, path.join(dir, "data"));
    const threads = store.listThreads();
    assert.equal(threads.length, 1);
    assert.equal(threads[0]?.title, "请读取 README.md，概括这个项目现在支持哪些 Gateway 模式。");
    assert.equal(threads[0]?.model, "gemini-3-flash-preview");

    const formatted = store.formatThreadList(threads, "bb47f0d1-f770-4049-8bd8-7ca7055f8790");
    assert.match(formatted, /请读取 README\.md/);
    assert.match(formatted, /模型：gemini-3-flash-preview/);
    assert.match(formatted, /来源：Gemini CLI/);
    assert.match(formatted, /当前/);
    assert.doesNotMatch(formatted, /Complex content/);
    assert.doesNotMatch(formatted, /bb47f0d1-f770-4049-8bd8-7ca7055f8790/);
  } finally {
    restoreEnv("GEMINI_CLI_HOME", previousHome);
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

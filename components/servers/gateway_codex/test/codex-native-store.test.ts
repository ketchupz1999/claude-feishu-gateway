import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { CodexNativeStore } from "../src/sessions/codex-native-store.js";

test("CodexNativeStore points to a repo-owned session script", () => {
  const workspace = path.resolve(process.cwd(), "..", "..", "..");
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-codex-store-"));
  const store = new CodexNativeStore(workspace, dataDir) as any;

  assert.equal(
    fs.existsSync(store.scriptPath),
    true,
    `missing session script: ${store.scriptPath}`
  );
});

test("CodexNativeStore degrades gracefully when Codex database is absent", () => {
  const workspace = path.resolve(process.cwd(), "..", "..", "..");
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-codex-store-home-"));
  const fakeHome = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-codex-home-"));
  const previousHome = process.env.HOME;
  process.env.HOME = fakeHome;

  try {
    const store = new CodexNativeStore(workspace, dataDir);
    assert.deepEqual(store.listThreads(5), []);
    assert.equal(store.getThread("missing-thread"), null);
  } finally {
    if (previousHome === undefined) {
      delete process.env.HOME;
    } else {
      process.env.HOME = previousHome;
    }
  }
});

test("CodexNativeStore lists SDK JSONL sessions when SQLite has no thread", () => {
  const workspace = path.resolve(process.cwd(), "..", "..", "..");
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-codex-store-jsonl-"));
  const fakeHome = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-codex-home-jsonl-"));
  const sessionDir = path.join(fakeHome, ".codex", "sessions", "2026", "04", "24");
  const threadId = "019dbd7c-62f1-7f83-b1dc-59e83257bbaf";
  fs.mkdirSync(sessionDir, { recursive: true });
  fs.writeFileSync(
    path.join(sessionDir, `rollout-2026-04-24T11-15-38-${threadId}.jsonl`),
    [
      JSON.stringify({
        timestamp: "2026-04-24T03:15:39.996Z",
        type: "session_meta",
        payload: {
          id: threadId,
          cwd: workspace,
          originator: "codex_sdk_ts",
          source: "exec"
        }
      }),
      JSON.stringify({
        timestamp: "2026-04-24T03:15:40.000Z",
        type: "response_item",
        payload: {
          type: "message",
          role: "user",
          content: [{ type: "input_text", text: "<environment_context>\n</environment_context>" }]
        }
      }),
      JSON.stringify({
        timestamp: "2026-04-24T03:15:41.000Z",
        type: "turn_context",
        payload: { cwd: workspace, model: "gpt-5.3-codex" }
      }),
      JSON.stringify({
        timestamp: "2026-04-24T03:15:42.000Z",
        type: "response_item",
        payload: {
          type: "message",
          role: "user",
          content: [{ type: "input_text", text: "hello from sdk" }]
        }
      })
    ].join("\n"),
    "utf8"
  );
  const previousHome = process.env.HOME;
  process.env.HOME = fakeHome;

  try {
    const store = new CodexNativeStore(workspace, dataDir);
    const threads = store.listThreads(5);
    assert.equal(threads.length, 1);
    assert.equal(threads[0]?.id, threadId);
    assert.equal(threads[0]?.firstUserMessage, "hello from sdk");
    assert.equal(threads[0]?.model, "gpt-5.3-codex");
    assert.equal(store.getThread(threadId)?.id, threadId);
  } finally {
    if (previousHome === undefined) {
      delete process.env.HOME;
    } else {
      process.env.HOME = previousHome;
    }
  }
});

test("CodexNativeStore formats sessions without exposing full thread ids", () => {
  const workspace = path.resolve(process.cwd(), "..", "..", "..");
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-codex-format-"));
  const store = new CodexNativeStore(workspace, dataDir);
  const threads = [
    {
      id: "019dbd7c-62f1-7f83-b1dc-59e83257bbaf",
      title: "hello from sdk",
      model: "gpt-5.3-codex",
      source: "codex_sdk_ts",
      cwd: workspace,
      firstUserMessage: "hello from sdk",
      createdAt: 1777000539,
      updatedAt: 1777000604,
      archived: false,
      pinned: false
    }
  ];
  const output = store.formatThreadList(threads, null);

  assert.match(output, /\*\*1\. hello from sdk\*\*/);
  assert.match(output, /模型：gpt-5\.3-codex · 时间：2026-04-24 03:16 · 来源：Codex SDK/);
  assert.match(output, /切换：`\/switch 1`/);
  assert.doesNotMatch(output, /019dbd7c-62f1-7f83-b1dc-59e83257bbaf/);
});

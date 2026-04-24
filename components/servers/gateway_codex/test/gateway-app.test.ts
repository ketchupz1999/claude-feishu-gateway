import test from "node:test";
import assert from "node:assert/strict";
import os from "node:os";
import fs from "node:fs";
import path from "node:path";

import { GatewayApp } from "../src/app/gateway.js";

function makeConfig(gatewayMode: "codex" | "gemini" = "codex") {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-codex-app-"));
  return {
    workspace: process.cwd(),
    dataDir: dir,
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
    gatewayMode
  };
}

const noopLogger = {
  info: () => {},
  warn: () => {},
  error: () => {}
};

test("GatewayApp ignores duplicate Feishu message ids", async () => {
  const previous = process.env.FEISHU_DEBUG_ECHO;
  process.env.FEISHU_DEBUG_ECHO = "1";

  const replies: Array<{ messageId: string; text: string; chatId?: string }> = [];
  const app = new GatewayApp(makeConfig(), noopLogger, {
    replyText: async (messageId: string, text: string, chatId?: string) => {
      replies.push({ messageId, text, chatId });
    },
    sendText: async () => {}
  } as any);

  try {
    await app.handleMessage({
      messageId: "om_dup",
      chatId: "oc_1",
      openId: "ou_test",
      text: "你好"
    });
    await app.handleMessage({
      messageId: "om_dup",
      chatId: "oc_1",
      openId: "ou_test",
      text: "你好"
    });

    assert.equal(replies.length, 1);
    assert.deepEqual(replies[0], {
      messageId: "om_dup",
      text: "echo: 你好",
      chatId: "oc_1"
    });
  } finally {
    if (previous === undefined) {
      delete process.env.FEISHU_DEBUG_ECHO;
    } else {
      process.env.FEISHU_DEBUG_ECHO = previous;
    }
  }
});

test("GatewayApp /stop clears current chat provider session", async () => {
  const replies: Array<{ messageId: string; text: string; chatId?: string }> = [];
  const app = new GatewayApp(makeConfig(), noopLogger, {
    replyText: async (messageId: string, text: string, chatId?: string) => {
      replies.push({ messageId, text, chatId });
    },
    sendText: async () => {},
    replyRich: async () => {},
    sendRich: async () => {}
  } as any);

  const nativeStore = (app as any).nativeStore;
  nativeStore.setCurrentThreadId("thread_1");

  (app as any).taskLock.acquire({
    requestId: "req_chat",
    taskType: "chat",
    startedAt: Date.now(),
    gatewaySessionId: "thread_1",
    cancelMode: "codex_interrupt",
    status: "running"
  });
  let interrupted = false;
  (app as any).chatExecutor = {
    interrupt: async () => {
      interrupted = true;
      return true;
    }
  };

  await app.handleMessage({
    messageId: "om_stop",
    chatId: "oc_1",
    openId: "ou_test",
    text: "/stop"
  });

  assert.equal(interrupted, true);
  assert.deepEqual(replies[0], {
    messageId: "om_stop",
    text: "已中断当前聊天任务，会话上下文已清除",
    chatId: "oc_1"
  });
  assert.equal(nativeStore.getCurrentThreadId(), null);
});

test("GatewayApp /new clears pointer and resets Gemini executor session", async () => {
  const replies: Array<{ messageId: string; text: string; chatId?: string }> = [];
  const app = new GatewayApp(makeConfig("gemini"), noopLogger, {
    replyText: async (messageId: string, text: string, chatId?: string) => {
      replies.push({ messageId, text, chatId });
    },
    sendText: async () => {},
    replyRich: async () => {},
    sendRich: async () => {}
  } as any);

  const nativeStore = (app as any).nativeStore;
  nativeStore.setCurrentThreadId("gemini-session-old");

  let resetCount = 0;
  (app as any).chatExecutor = {
    interrupt: async () => false,
    resetSession: () => {
      resetCount += 1;
    }
  };

  await app.handleMessage({
    messageId: "om_new",
    chatId: "oc_1",
    openId: "ou_test",
    text: "/new"
  });

  assert.equal(resetCount, 1);
  assert.equal(nativeStore.getCurrentThreadId(), null);
  assert.deepEqual(replies[0], {
    messageId: "om_new",
    text: "会话已新建，下次聊天将开启新对话",
    chatId: "oc_1"
  });
});

test("GatewayApp reports cancel-in-progress while previous task is stopping", async () => {
  const replies: Array<{ messageId: string; text: string; chatId?: string }> = [];
  const app = new GatewayApp(makeConfig(), noopLogger, {
    replyText: async (messageId: string, text: string, chatId?: string) => {
      replies.push({ messageId, text, chatId });
    },
    sendText: async () => {},
    replyRich: async () => {},
    sendRich: async () => {}
  } as any);

  (app as any).taskLock.acquire({
    requestId: "req_chat_busy",
    taskType: "chat",
    startedAt: Date.now(),
    cancelMode: "codex_interrupt",
    status: "running"
  });
  (app as any).stopController.requestCancel();

  await app.handleMessage({
    messageId: "om_next",
    chatId: "oc_1",
    openId: "ou_test",
    text: "继续"
  });

  assert.deepEqual(replies[0], {
    messageId: "om_next",
    text: "正在取消上一个任务，请稍后再试",
    chatId: "oc_1"
  });
});

test("GatewayApp returns unsupported for removed private slash commands", async () => {
  const richReplies: string[] = [];
  const app = new GatewayApp(makeConfig(), noopLogger, {
    replyText: async () => {},
    sendText: async () => {},
    replyRich: async (_messageId: string, _chatId: string, text: string) => {
      richReplies.push(text);
    },
    sendRich: async () => {}
  } as any);

  await app.handleMessage({
    messageId: "om_private",
    chatId: "oc_1",
    openId: "ou_test",
    text: "/pulse"
  });

  assert.match(richReplies[0] ?? "", /开源版暂不支持该命令: \/pulse/);
});

test("GatewayApp does not restore provider session after /stop cancels chat", async () => {
  const replies: Array<{ messageId: string; text: string; chatId?: string }> = [];
  const sent: string[] = [];
  let resolveRun: ((value: any) => void) | undefined;

  const app = new GatewayApp(makeConfig(), noopLogger, {
    replyText: async (messageId: string, text: string, chatId?: string) => {
      replies.push({ messageId, text, chatId });
    },
    sendText: async (_chatId: string, text: string) => {
      sent.push(text);
    },
    replyRich: async (_messageId: string, _chatId: string, text: string) => {
      sent.push(text);
    },
    sendRich: async (_chatId: string, text: string) => {
      sent.push(text);
    }
  } as any);

  const nativeStore = (app as any).nativeStore;
  nativeStore.setCurrentThreadId("thread_old");

  let interrupted = false;
  (app as any).chatExecutor = {
    run: async () =>
      await new Promise((resolve) => {
        resolveRun = resolve;
      }),
    interrupt: async () => {
      interrupted = true;
      return true;
    }
  };

  const chatPromise = app.handleMessage({
    messageId: "om_chat",
    chatId: "oc_1",
    openId: "ou_test",
    text: "继续"
  });

  await new Promise((resolve) => setTimeout(resolve, 0));

  await app.handleMessage({
    messageId: "om_stop2",
    chatId: "oc_1",
    openId: "ou_test",
    text: "/stop"
  });

  resolveRun?.({
    status: "canceled",
    resultKind: "text",
    payload: "已取消",
    providerSessionId: "provider_new",
    durationMs: 10
  });
  await chatPromise;

  assert.equal(interrupted, true);
  // After /stop, current thread should be cleared (null)
  assert.equal(nativeStore.getCurrentThreadId(), null);
  assert.equal(replies[0]?.text.startsWith("正在执行... [codex "), true);
  assert.equal(replies[1]?.text, "已中断当前聊天任务，会话上下文已清除");
  assert.deepEqual(sent, []);
});

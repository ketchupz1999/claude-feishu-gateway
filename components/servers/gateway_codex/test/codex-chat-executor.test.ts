import test from "node:test";
import assert from "node:assert/strict";

import { CodexChatExecutor } from "../src/executors/codex-chat-executor.js";

type LoggedWarning = {
  message: string;
  meta?: Record<string, unknown>;
};

const baseConfig = {
  workspace: process.cwd(),
  dataDir: `${process.cwd()}/data`,
  logDir: `${process.cwd()}/data/logs`,
  pidFile: `${process.cwd()}/data/gateway.pid`,
  sessionFile: `${process.cwd()}/data/.gateway_session`,
  currentDate: "2026-03-20",
  feishuSecretsFile: `${process.cwd()}/.claude/secrets/feishu_app.json`,
  feishuAppId: undefined,
  feishuAppSecret: undefined,
  feishuAllowedOpenId: undefined,
  codexApiKey: undefined,
  codexReasoningEffort: "high" as const,
  gatewayMode: "codex" as const
};

test("CodexChatExecutor allows CLI auth/config fallback without API key", () => {
  const warnings: LoggedWarning[] = [];
  const previousSandbox = process.env.CODEX_SANDBOX_MODE;
  const previousApproval = process.env.CODEX_APPROVAL_POLICY;
  delete process.env.CODEX_SANDBOX_MODE;
  delete process.env.CODEX_APPROVAL_POLICY;

  try {
    const executor = new CodexChatExecutor(baseConfig, {
      info: () => {},
      error: () => {},
      warn: (message, meta) => warnings.push({ message, meta })
    });

    assert.ok(executor);
    assert.equal(warnings.length, 1);
    assert.match(warnings[0]!.message, /danger-full-access/);
    assert.equal(warnings[0]!.meta?.approvalPolicy, "never");
  } finally {
    if (previousSandbox === undefined) {
      delete process.env.CODEX_SANDBOX_MODE;
    } else {
      process.env.CODEX_SANDBOX_MODE = previousSandbox;
    }
    if (previousApproval === undefined) {
      delete process.env.CODEX_APPROVAL_POLICY;
    } else {
      process.env.CODEX_APPROVAL_POLICY = previousApproval;
    }
  }
});

test("CodexChatExecutor warns when dangerous sandbox mode is enabled", () => {
  const warnings: LoggedWarning[] = [];
  const previousSandbox = process.env.CODEX_SANDBOX_MODE;
  const previousApproval = process.env.CODEX_APPROVAL_POLICY;
  process.env.CODEX_SANDBOX_MODE = "danger-full-access";
  process.env.CODEX_APPROVAL_POLICY = "never";

  try {
    const executor = new CodexChatExecutor(
      {
        ...baseConfig,
        codexApiKey: "test-key",
        codexReasoningEffort: "high" as const
      },
      {
        info: () => {},
        error: () => {},
        warn: (message, meta) => warnings.push({ message, meta })
      }
    );

    assert.ok(executor);
    assert.equal(warnings.length, 1);
    assert.match(warnings[0]!.message, /danger-full-access/);
    assert.equal(warnings[0]!.meta?.approvalPolicy, "never");
  } finally {
    if (previousSandbox === undefined) {
      delete process.env.CODEX_SANDBOX_MODE;
    } else {
      process.env.CODEX_SANDBOX_MODE = previousSandbox;
    }
    if (previousApproval === undefined) {
      delete process.env.CODEX_APPROVAL_POLICY;
    } else {
      process.env.CODEX_APPROVAL_POLICY = previousApproval;
    }
  }
});

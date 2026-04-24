import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { loadConfig } from "../src/config.js";

function withEnv(
  key: string,
  value: string | undefined,
  fn: () => void
): void {
  const previous = process.env[key];
  if (value === undefined) {
    delete process.env[key];
  } else {
    process.env[key] = value;
  }
  try {
    fn();
  } finally {
    if (previous === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = previous;
    }
  }
}

test("loadConfig reads gateway mode and listener channels from YAML", () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-codex-config-"));
  fs.mkdirSync(path.join(workspace, "components"), { recursive: true });
  fs.writeFileSync(
    path.join(workspace, "components", "config.example.yaml"),
    [
      "gateway_mode: gemini",
      "codex_reasoning_effort: medium",
      "listener_channels:",
      "  weixin:",
      "    enabled: true",
      "    command:",
      "      - make",
      "      - -C",
      "      - components/servers/weixin_listener",
      "      - start-gateway",
      "    env:",
      "      OPENCLAW_STATE_DIR: ./data/weixin_state",
    ].join("\n"),
    "utf8"
  );

  withEnv("AGENTS_WORKSPACE", workspace, () => {
    const config = loadConfig();
    assert.equal(config.gatewayMode, "gemini");
    assert.equal(config.codexReasoningEffort, "medium");
    assert.equal(config.listenerChannels?.weixin?.enabled, true);
    assert.deepEqual(config.listenerChannels?.weixin?.command, [
      "make",
      "-C",
      "components/servers/weixin_listener",
      "start-gateway",
    ]);
  });
});

test("loadConfig fails fast on invalid YAML", () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "gateway-codex-config-invalid-"));
  fs.mkdirSync(path.join(workspace, "components"), { recursive: true });
  fs.writeFileSync(
    path.join(workspace, "components", "config.example.yaml"),
    "gateway_mode: [codex\n",
    "utf8"
  );

  withEnv("AGENTS_WORKSPACE", workspace, () => {
    assert.throws(
      () => loadConfig(),
      /failed to parse config file/
    );
  });
});

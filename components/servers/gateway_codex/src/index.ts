import process from "node:process";
import fs from "node:fs";
import path from "node:path";
import { spawn, type ChildProcess } from "node:child_process";

import { loadConfig } from "./config.js";
import { GatewayApp } from "./app/gateway.js";
import { createLogger } from "./logger.js";
import { assertSingleProcess, removePidFile, writePidFile } from "./pid.js";
import { createLarkRuntime } from "./lark/client.js";

type ListenerProc = {
  name: string;
  proc: ChildProcess;
  logFile: string;
  stream: fs.WriteStream;
};

function startExtraListeners(
  config: ReturnType<typeof loadConfig>,
  logger: ReturnType<typeof createLogger>
): ListenerProc[] {
  const children: ListenerProc[] = [];
  const listeners = config.listenerChannels;
  if (!listeners || Object.keys(listeners).length === 0) {
    return children;
  }

  for (const [name, cfg] of Object.entries(listeners)) {
    if (!cfg?.enabled) {
      continue;
    }
    if (!cfg.command || (Array.isArray(cfg.command) && cfg.command.length === 0)) {
      logger.warn("listener enabled but command is empty", { channel: name });
      continue;
    }

    fs.mkdirSync(config.logDir, { recursive: true });
    const logFile = path.join(config.logDir, `${config.currentDate}-listener-${name}.log`);
    const stream = fs.createWriteStream(logFile, { flags: "a" });
    const env = { ...process.env, ...(cfg.env ?? {}) };

    let proc: ChildProcess;
    let commandPreview = "";
    if (Array.isArray(cfg.command)) {
      const [bin, ...args] = cfg.command;
      commandPreview = cfg.command.join(" ");
      proc = spawn(bin!, args, {
        cwd: config.workspace,
        env,
        stdio: ["ignore", "pipe", "pipe"]
      });
    } else {
      commandPreview = cfg.command;
      proc = spawn(cfg.command, {
        cwd: config.workspace,
        env,
        shell: true,
        stdio: ["ignore", "pipe", "pipe"]
      });
    }

    // 收集 stderr 最后几行，退出时打出来方便排查
    let stderrTail = "";
    proc.stderr?.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stderrTail = (stderrTail + text).slice(-2000); // 保留最后 2KB
    });

    proc.stdout?.pipe(stream, { end: false });
    proc.stderr?.pipe(stream, { end: false });
    stream.on("error", (err) => {
      logger.warn("extra listener log stream error", { channel: name, error: String(err) });
    });
    proc.on("exit", (code, signal) => {
      const lastErr = stderrTail.trim();
      logger.warn("extra listener exited", {
        channel: name,
        code: code ?? null,
        signal: signal ?? null,
        logFile,
        ...(lastErr ? { stderr: lastErr } : {})
      });
      stream.end();
    });
    children.push({ name, proc, logFile, stream });
    logger.info("extra listener started", {
      channel: name,
      pid: proc.pid ?? null,
      command: commandPreview,
      logFile
    });
  }
  return children;
}

function stopExtraListeners(
  listeners: ListenerProc[],
  logger: ReturnType<typeof createLogger>
): void {
  for (const item of listeners) {
    try {
      if (item.proc.pid && item.proc.exitCode === null) {
        item.proc.kill("SIGTERM");
      }
    } catch (err) {
      logger.warn("failed to stop extra listener", {
        channel: item.name,
        message: err instanceof Error ? err.message : String(err)
      });
    } finally {
      item.stream.end();
    }
  }
}

async function main(): Promise<void> {
  const config = loadConfig();
  const logger = createLogger(config);

  assertSingleProcess(config.pidFile);
  writePidFile(config.pidFile);

  let larkRuntime: ReturnType<typeof createLarkRuntime> | null = null;
  let wsHealthTimer: ReturnType<typeof setInterval> | null = null;
  let wsUnhealthySince: number | null = null;
  let listenerChildren: ListenerProc[] = [];
  let cleaned = false;
  const cleanup = (exitCode: number, reason: string) => {
    if (cleaned) {
      return;
    }
    cleaned = true;
    if (wsHealthTimer) {
      clearInterval(wsHealthTimer);
      wsHealthTimer = null;
    }
    try {
      larkRuntime?.stop();
    } catch (err) {
      logger.warn("gateway ws shutdown failed", {
        message: err instanceof Error ? err.message : String(err)
      });
    }
    stopExtraListeners(listenerChildren, logger);
    listenerChildren = [];
    logger.info("gateway skeleton stopped", { reason, exitCode });
    removePidFile(config.pidFile);
    process.exit(exitCode);
  };

  // Register signal handlers before any potentially blocking awaits.
  process.on("SIGINT", () => cleanup(0, "SIGINT"));
  process.on("SIGTERM", () => cleanup(0, "SIGTERM"));

  try {
    larkRuntime = createLarkRuntime(config, logger);
    const app = new GatewayApp(config, logger, larkRuntime.reply);
    app.start();
    listenerChildren = startExtraListeners(config, logger);
    logger.info("extra listeners configured", {
      enabled: listenerChildren.map((x) => x.name)
    });
    await larkRuntime.start(async (message) => {
      await app.handleMessage(message);
    });
    wsHealthTimer = setInterval(() => {
      const health = larkRuntime!.getHealth();
      const now = Date.now();
      if (health.readyState === 1) {
        wsUnhealthySince = null;
        return;
      }
      if (wsUnhealthySince === null) {
        wsUnhealthySince = now;
        logger.warn("gateway ws became unhealthy", {
          readyState: health.readyState,
          reconnectInfo: health.reconnectInfo
        });
        return;
      }
      if (now - wsUnhealthySince >= 120_000) {
        logger.error("gateway ws unhealthy for too long", {
          readyState: health.readyState,
          reconnectInfo: health.reconnectInfo,
          unhealthyForMs: now - wsUnhealthySince
        });
        cleanup(1, "ws_unhealthy");
      }
    }, 15_000);
  } catch (err) {
    logger.error("gateway skeleton crashed", {
      message: err instanceof Error ? err.message : String(err)
    });
    cleanup(1, "fatal");
  }
}

void main();

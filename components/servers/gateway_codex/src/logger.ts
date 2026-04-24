import fs from "node:fs";
import path from "node:path";

import type { GatewayConfig } from "./config.js";
import type { Logger } from "./types.js";

function serializeMeta(meta?: Record<string, unknown>): string {
  if (!meta || Object.keys(meta).length === 0) {
    return "";
  }
  return ` ${JSON.stringify(meta)}`;
}

export function createLogger(config: GatewayConfig): Logger {
  fs.mkdirSync(config.logDir, { recursive: true });
  const logfile = path.join(config.logDir, `${config.currentDate}-gateway.log`);

  function write(level: string, message: string, meta?: Record<string, unknown>): void {
    const line = `[${new Date().toISOString()}] [gateway-codex] [${level}] ${message}${serializeMeta(meta)}`;
    console.log(line);
    fs.appendFileSync(logfile, `${line}\n`, "utf8");
  }

  return {
    info: (message, meta) => write("info", message, meta),
    warn: (message, meta) => write("warn", message, meta),
    error: (message, meta) => write("error", message, meta)
  };
}

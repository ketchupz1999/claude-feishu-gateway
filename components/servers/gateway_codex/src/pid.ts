import fs from "node:fs";
import process from "node:process";

export function writePidFile(pidFile: string): void {
  fs.mkdirSync(new URL(`file://${pidFile}`).pathname.replace(/\/[^/]+$/, ""), { recursive: true });
  fs.writeFileSync(pidFile, String(process.pid), "utf8");
}

export function removePidFile(pidFile: string): void {
  if (fs.existsSync(pidFile)) {
    fs.unlinkSync(pidFile);
  }
}

export function assertSingleProcess(pidFile: string): void {
  if (!fs.existsSync(pidFile)) {
    return;
  }
  const oldPid = Number(fs.readFileSync(pidFile, "utf8").trim());
  if (!Number.isFinite(oldPid) || oldPid <= 0) {
    return;
  }
  try {
    process.kill(oldPid, 0);
    throw new Error(`gateway already running (PID=${oldPid})`);
  } catch (error) {
    const err = error as NodeJS.ErrnoException;
    if (err.code !== "ESRCH") {
      throw error;
    }
  }
}

import type { ControlCommandName } from "../types.js";

export const CONTROL_COMMANDS = new Set<ControlCommandName>([
  "/model",
  "/new",
  "/clear",
  "/sessions",
  "/switch",
  "/top",
  "/pin",
  "/unpin",
  "/stop"
]);

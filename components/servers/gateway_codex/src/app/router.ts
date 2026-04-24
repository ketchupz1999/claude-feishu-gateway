import { CONTROL_COMMANDS } from "../commands/command-table.js";
import type { RoutedRequest } from "../types.js";

function splitCommand(text: string): { command: string; args: string[] } {
  const parts = text.trim().split(/\s+/).filter(Boolean);
  return {
    command: parts[0] ?? "",
    args: parts.slice(1)
  };
}

export function routeMessage(rawText: string): RoutedRequest {
  const text = rawText.trim();
  if (!text) {
    return { kind: "chat", text: "", rawText };
  }

  const { command, args } = splitCommand(text);
  if (!command.startsWith("/")) {
    return { kind: "chat", text, rawText };
  }

  if (CONTROL_COMMANDS.has(command as never)) {
    return { kind: "control", commandName: command as never, args, rawText };
  }

  return { kind: "unknown_command", commandName: command, args, rawText };
}

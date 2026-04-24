import process from "node:process";

import { Codex } from "@openai/codex-sdk";

const workingDirectory = process.argv[2] ?? process.cwd();
const prompt = process.argv[3] ?? "Reply with exactly OK and nothing else.";

async function main(): Promise<void> {
  const startedAt = Date.now();
  const codex = process.env.OPENAI_API_KEY || process.env.CODEX_API_KEY
    ? new Codex({ apiKey: process.env.OPENAI_API_KEY ?? process.env.CODEX_API_KEY })
    : new Codex();

  const thread = codex.startThread({
    workingDirectory,
    skipGitRepoCheck: false,
    sandboxMode: "read-only",
    approvalPolicy: "never",
    // Avoid `minimal` here because some Codex configs enable tools such as web_search.
    modelReasoningEffort: "medium"
  });

  const turn = await thread.run(prompt);
  console.log(
    JSON.stringify(
      {
        ok: true,
        workingDirectory,
        prompt,
        threadId: thread.id,
        finalResponse: turn.finalResponse,
        usage: turn.usage,
        durationMs: Date.now() - startedAt
      },
      null,
      2
    )
  );
}

void main().catch((err) => {
  console.error(
    JSON.stringify(
      {
        ok: false,
        message: err instanceof Error ? err.message : String(err)
      },
      null,
      2
    )
  );
  process.exit(1);
});

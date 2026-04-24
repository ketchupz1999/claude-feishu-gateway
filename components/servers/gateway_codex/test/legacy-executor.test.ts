import test from "node:test";
import assert from "node:assert/strict";
import { LegacyExecutor } from "../src/executors/legacy-executor.js";

test("LegacyExecutor cancels gracefully when no child exists", () => {
  const executor = new LegacyExecutor();
  assert.equal(executor.cancel(), false);
  assert.equal(executor.getChildPid(), undefined);
});

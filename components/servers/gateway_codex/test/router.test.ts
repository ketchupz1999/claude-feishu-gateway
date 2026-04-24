import test from "node:test";
import assert from "node:assert/strict";

import { routeMessage } from "../src/app/router.js";

test("Router classifies control command", () => {
  const route = routeMessage("/new topic");
  assert.equal(route.kind, "control");
  if (route.kind === "control") {
    assert.equal(route.commandName, "/new");
    assert.deepEqual(route.args, ["topic"]);
  }
});

test("Router leaves removed legacy command as unsupported slash", () => {
  const route = routeMessage("/pulse");
  assert.equal(route.kind, "unknown_command");
});

test("Router leaves removed private shortcut as unsupported slash", () => {
  const route = routeMessage("/brief-evening");
  assert.equal(route.kind, "unknown_command");
});

test("Router classifies unknown slash command explicitly", () => {
  const route = routeMessage("/unknown cmd");
  assert.equal(route.kind, "unknown_command");
  if (route.kind === "unknown_command") {
    assert.equal(route.commandName, "/unknown");
    assert.deepEqual(route.args, ["cmd"]);
  }
});

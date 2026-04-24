import test from "node:test";
import assert from "node:assert/strict";

import { parseFeishuMessage, type ParseWarning } from "../src/lark/event-parser.js";

test("parseFeishuMessage warns and returns null for invalid json payload", () => {
  const warnings: ParseWarning[] = [];
  const parsed = parseFeishuMessage(
    {
      event: {
        message: {
          message_id: "msg_1",
          chat_id: "chat_1",
          message_type: "text",
          content: "{bad-json"
        },
        sender: {
          sender_id: {
            open_id: "ou_xxx"
          }
        }
      }
    },
    (warning) => warnings.push(warning)
  );

  assert.equal(parsed, null);
  assert.deepEqual(warnings, [
    {
      reason: "invalid_json",
      messageId: "msg_1",
      messageType: "text"
    }
  ]);
});

test("parseFeishuMessage supports Node SDK top-level payload shape", () => {
  const parsed = parseFeishuMessage({
    event_id: "evt_1",
    sender: {
      sender_id: {
        open_id: "ou_top"
      },
      sender_type: "user"
    },
    message: {
      message_id: "msg_top",
      chat_id: "chat_top",
      create_time: "1742460000000",
      chat_type: "p2p",
      message_type: "text",
      content: JSON.stringify({ text: "你好 @_user_1" }),
      mentions: [{ key: "@_user_1" }]
    }
  });

  assert.deepEqual(parsed, {
    messageId: "msg_top",
    chatId: "chat_top",
    openId: "ou_top",
    text: "你好",
    raw: {
      event_id: "evt_1",
      sender: {
        sender_id: {
          open_id: "ou_top"
        },
        sender_type: "user"
      },
      message: {
        message_id: "msg_top",
        chat_id: "chat_top",
        create_time: "1742460000000",
        chat_type: "p2p",
        message_type: "text",
        content: JSON.stringify({ text: "你好 @_user_1" }),
        mentions: [{ key: "@_user_1" }]
      }
    },
    messageType: "text"
  });
});

test("parseFeishuMessage warns on malformed payload", () => {
  const warnings: ParseWarning[] = [];
  const parsed = parseFeishuMessage({ foo: "bar" }, (warning) => warnings.push(warning));

  assert.equal(parsed, null);
  assert.deepEqual(warnings, [
    {
      reason: "malformed_payload",
      detail: "missing event/message/sender",
      messageId: undefined,
      messageType: undefined
    }
  ]);
});

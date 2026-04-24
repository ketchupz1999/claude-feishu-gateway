export type ParsedMessage = {
  messageId: string;
  chatId: string;
  openId: string;
  text: string;
  raw: unknown;
  messageType: string;
};

export type ParseWarning = {
  reason: "invalid_json" | "unsupported_message_type" | "malformed_payload";
  messageId?: string;
  messageType?: string;
  detail?: string;
};

type EventShape = {
  message?: {
    message_id?: string;
    chat_id?: string;
    message_type?: string;
    content?: string;
    mentions?: Array<{ key?: string }>;
  };
  sender?: {
    sender_id?: {
      open_id?: string;
    };
  };
};

function stripMentions(text: string, mentions?: Array<{ key?: string }>): string {
  let next = text;
  for (const mention of mentions ?? []) {
    if (mention.key) {
      next = next.replaceAll(mention.key, "");
    }
  }
  return next.trim();
}

export function parseFeishuMessage(
  data: any,
  onWarning?: (warning: ParseWarning) => void
): ParsedMessage | null {
  // Node SDK `im.message.receive_v1` handlers receive a top-level payload (`data.message`, `data.sender`).
  // Some webhook-style payloads may still wrap this under `data.event`, so support both.
  const event = (data?.event ?? data) as EventShape | undefined;
  const message = event?.message;
  const sender = event?.sender;
  if (!event || !message || !sender) {
    onWarning?.({
      reason: "malformed_payload",
      detail: "missing event/message/sender",
      messageId: typeof data?.message?.message_id === "string" ? data.message.message_id : undefined,
      messageType: typeof data?.message?.message_type === "string" ? data.message.message_type : undefined
    });
    return null;
  }

  let text = "";
  let content: any = {};
  if (message.content) {
    try {
      content = JSON.parse(message.content);
    } catch {
      onWarning?.({
        reason: "invalid_json",
        messageId: typeof message.message_id === "string" ? message.message_id : undefined,
        messageType: typeof message.message_type === "string" ? message.message_type : undefined
      });
      return null;
    }
  }
  if (message.message_type === "text") {
    text = String(content.text ?? "").trim();
  } else if (message.message_type === "post" && Array.isArray(content.content)) {
    const parts: string[] = [];
    for (const line of content.content) {
      if (!Array.isArray(line)) {
        continue;
      }
      for (const node of line) {
        if (node?.tag === "text" && node.text) {
          parts.push(String(node.text));
        }
      }
    }
    text = parts.join(" ").trim();
  } else {
    onWarning?.({
      reason: "unsupported_message_type",
      messageId: typeof message.message_id === "string" ? message.message_id : undefined,
      messageType: typeof message.message_type === "string" ? message.message_type : undefined
    });
    return null;
  }

  return {
    messageId: String(message.message_id),
    chatId: String(message.chat_id),
    openId: String(sender.sender_id?.open_id ?? ""),
    text: stripMentions(text, message.mentions),
    raw: data,
    messageType: String(message.message_type ?? "")
  };
}

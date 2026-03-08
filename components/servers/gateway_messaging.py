"""
消息解析 + 回复 + 卡片渲染模块

被 feishu_gateway.py 导入使用。
"""

import json
import re

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetMessageRequest,
    P2ImMessageReceiveV1,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

MAX_REPLY_LEN = 4000
CARD_THRESHOLD = 200

_MD_PATTERN = re.compile(r"(^#{1,3}\s|^\-{3,}$|^\*{3,}$|\*\*.*\*\*|\[.*\]\(.*\)|^- |^>\s)", re.MULTILINE)

# 模块级引用，由 feishu_gateway.py 启动时注入
_api_client = None
_log_fn = print


def init(api_client, log_fn):
    """初始化模块依赖（api_client 和 log 函数）"""
    global _api_client, _log_fn
    _api_client = api_client
    _log_fn = log_fn


def log(msg: str):
    _log_fn(msg)


# ===== 消息解析 =====

def extract_text(data: P2ImMessageReceiveV1) -> str:
    """从消息事件中提取纯文本，支持 text 和 post 类型，去除 @bot"""
    msg = data.event.message
    content = json.loads(msg.content)

    if msg.message_type == "text":
        text = content.get("text", "").strip()
    elif msg.message_type == "post":
        parts = []
        post_body = None
        for lang in ("zh_cn", "en_us", "ja_jp"):
            val = content.get(lang)
            if isinstance(val, dict):
                post_body = val.get("content")
                if post_body:
                    break
        if not post_body and isinstance(content.get("content"), list):
            post_body = content["content"]
        for line in (post_body or []):
            if not isinstance(line, list):
                continue
            for node in line:
                if not isinstance(node, dict):
                    continue
                tag = node.get("tag")
                if tag == "text":
                    parts.append(node.get("text", ""))
                elif tag == "a":
                    href = node.get("href", "")
                    link_text = node.get("text", "")
                    if link_text and link_text != href:
                        parts.append(f"{link_text} {href}")
                    else:
                        parts.append(href or link_text)
        text = " ".join(parts).strip()
    else:
        return ""

    # 群聊中 @bot 会产生 mentions，文本中有 @_user_N 占位符，去掉
    if msg.mentions:
        for mention in msg.mentions:
            text = text.replace(mention.key, "").strip()
    return text


def _fetch_message_content(message_id: str) -> dict:
    """通过 API 拉取消息完整内容，返回 content dict。失败返回 {}"""
    try:
        req = GetMessageRequest.builder().message_id(message_id).build()
        resp = _api_client.im.v1.message.get(req)
        if not resp.success():
            log(f"GetMessage 失败: code={resp.code}, msg={resp.msg}")
            return {}
        items = resp.data.items
        if not items:
            return {}
        item = items[0]
        raw = item.body.content if item.body else ""
        return json.loads(raw) if raw else {}
    except Exception as e:
        log(f"_fetch_message_content 异常: {e}")
        return {}


def _parse_msg_list(msg_list: list) -> tuple[list[str], int]:
    """从 msg_list 提取 ['Name: text', ...] 行列表和消息条数"""
    lines = []
    for m in msg_list:
        from_user = m.get("from_user") or m.get("sender") or {}
        name = from_user.get("name") or from_user.get("name_py") or "未知"
        msg_type = m.get("msg_type", "")
        body = m.get("body", {})

        if msg_type == "text":
            text = body.get("text", "").strip() if isinstance(body, dict) else str(body).strip()
            if not text and isinstance(body, str):
                try:
                    text = json.loads(body).get("text", "")
                except Exception:
                    pass
            if text:
                lines.append(f"{name}: {text}")
        elif msg_type == "post":
            parts = []
            post_content = body.get("content", []) if isinstance(body, dict) else []
            for line in post_content:
                if not isinstance(line, list):
                    continue
                for node in line:
                    if isinstance(node, dict):
                        if node.get("tag") == "text":
                            parts.append(node.get("text", ""))
                        elif node.get("tag") == "a":
                            parts.append(node.get("href", "") or node.get("text", ""))
            text = " ".join(parts).strip()
            if text:
                lines.append(f"{name}: {text}")
    return lines, len(msg_list)


def extract_merge_forward(data: P2ImMessageReceiveV1) -> tuple[str, int]:
    """解析合并转发消息，返回 (对话文本, 消息条数)。解析失败返回 ('', 0)"""
    msg = data.event.message
    try:
        content: dict = {}
        raw_content = msg.content if isinstance(msg.content, str) else ""
        if raw_content.strip():
            try:
                content = json.loads(raw_content)
            except json.JSONDecodeError:
                pass

        if not content or not content.get("msg_list"):
            content = _fetch_message_content(msg.message_id)

        if not content:
            log("merge_forward: 内容为空，API 也未返回数据")
            return "", 0

        chat_name = content.get("chat_name", "群聊")
        msg_list = content.get("msg_list", [])
        if not msg_list:
            log(f"merge_forward: msg_list 为空，content keys={list(content.keys())}")
            return "", 0

        lines, count = _parse_msg_list(msg_list)
        if not lines:
            return "", 0

        result = f"[群聊会话记录: {chat_name}]\n" + "\n".join(lines)
        return result, count
    except Exception as e:
        log(f"解析合并转发失败: {e}")
        return "", 0


# ===== 回复/发送 =====

def reply_text(message_id: str, text: str) -> bool:
    """回复到原消息"""
    req = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            ReplyMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        )
        .build()
    )
    resp = _api_client.im.v1.message.reply(req)
    if not resp.success():
        log(f"reply 失败: code={resp.code}, msg={resp.msg}")
        return False
    return True


def send_text(chat_id: str, text: str) -> bool:
    """直接发到聊天"""
    req = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        )
        .build()
    )
    resp = _api_client.im.v1.message.create(req)
    if not resp.success():
        log(f"send 失败: code={resp.code}, msg={resp.msg}")
        return False
    return True


def split_text(text: str, limit: int = MAX_REPLY_LEN) -> list[str]:
    """按段落边界拆分长文本"""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


def reply_card(message_id: str, card: dict) -> bool:
    """用卡片格式回复消息"""
    req = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            ReplyMessageRequestBody.builder()
            .msg_type("interactive")
            .content(json.dumps(card, ensure_ascii=False))
            .build()
        )
        .build()
    )
    resp = _api_client.im.v1.message.reply(req)
    if not resp.success():
        log(f"reply_card 失败: code={resp.code}, msg={resp.msg}")
        return False
    return True


def send_card(chat_id: str, card: dict) -> bool:
    """用卡片格式发送消息到聊天"""
    req = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("interactive")
            .content(json.dumps(card, ensure_ascii=False))
            .build()
        )
        .build()
    )
    resp = _api_client.im.v1.message.create(req)
    if not resp.success():
        log(f"send_card 失败: code={resp.code}, msg={resp.msg}")
        return False
    return True


def safe_reply(message_id: str, chat_id: str, text: str):
    """回复消息。长文本+markdown 自动升级为卡片，否则纯文本拆分发送"""
    if _should_use_card(text):
        card = _md_to_card(text)
        if not reply_card(message_id, card):
            log("reply_card 失败, fallback 到 send_card")
            if not send_card(chat_id, card):
                log("send_card 也失败, 降级为纯文本")
                for chunk in split_text(text):
                    send_text(chat_id, chunk)
        return
    chunks = split_text(text)
    for chunk in chunks:
        if not reply_text(message_id, chunk):
            log("reply 失败, fallback 到 send")
            send_text(chat_id, chunk)


# ===== 卡片渲染 =====

def _has_md_structure(text: str) -> bool:
    return bool(_MD_PATTERN.search(text))


def _should_use_card(text: str) -> bool:
    return len(text) > CARD_THRESHOLD or "\n" in text.strip()


def _split_md(content: str, max_len: int = 3800) -> list[str]:
    """将长 markdown 按段落边界拆分"""
    if len(content) <= max_len:
        return [content]
    chunks: list[str] = []
    paragraphs = content.split("\n\n")
    current = ""
    for para in paragraphs:
        candidate = (current + "\n\n" + para) if current else para
        if len(candidate) > max_len:
            if current:
                chunks.append(current)
            if len(para) > max_len:
                while para:
                    chunks.append(para[:max_len])
                    para = para[max_len:]
                current = ""
            else:
                current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _parse_table_row(line: str) -> list[str]:
    """解析表格行 '| a | b | c |' 为 ['a', 'b', 'c']"""
    cells = line.split("|")
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [c.strip() for c in cells]


def _table_to_list(header_cells: list[str], data_rows: list[list[str]]) -> list[str]:
    """将表格转为 markdown 列表行"""
    result = []
    for row in data_rows:
        parts = []
        for i, cell in enumerate(row):
            key = header_cells[i] if i < len(header_cells) else ""
            if key and cell:
                parts.append(f"**{key}**: {cell}")
            elif cell:
                parts.append(cell)
        if parts:
            result.append("- " + " | ".join(parts))
    return result


def _md_to_card(text: str) -> dict:
    """将 markdown 文本转为飞书消息卡片 v2 JSON"""
    elements: list[dict] = []
    current_lines: list[str] = []
    table_count = 0
    table_sep_re = re.compile(r"^\|[\s:]*-+[\s:]*(\|[\s:]*-+[\s:]*)*\|?\s*$")
    table_row_re = re.compile(r"^\|.+\|")

    def flush() -> None:
        block = "\n".join(current_lines).strip()
        current_lines.clear()
        if not block:
            return
        for chunk in _split_md(block):
            elements.append({"tag": "markdown", "content": chunk})

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped in ("---", "***", "___"):
            flush()
            if elements and elements[-1].get("tag") != "hr":
                elements.append({"tag": "hr"})
            i += 1
            continue

        if table_sep_re.match(stripped):
            header_line = current_lines.pop() if current_lines else ""
            header_cells = _parse_table_row(header_line) if header_line else []

            data_rows = []
            i += 1
            while i < len(lines) and table_row_re.match(lines[i].strip()):
                data_rows.append(_parse_table_row(lines[i].strip()))
                i += 1

            table_count += 1
            if table_count <= 3:
                current_lines.append(header_line)
                current_lines.append(stripped)
                for row in data_rows:
                    current_lines.append("| " + " | ".join(row) + " |")
            else:
                list_lines = _table_to_list(header_cells, data_rows)
                current_lines.extend(list_lines)
            continue

        current_lines.append(line)
        i += 1

    flush()

    title = text.strip().split("\n")[0].lstrip("# ").strip()[:30] or "回复"

    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "indigo",
        },
        "body": {"elements": elements},
    }

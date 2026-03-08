#!/usr/bin/env python3
"""
飞书 Webhook 推送脚本
用法:
    python3 feishu_webhook.py test
    python3 feishu_webhook.py alert <news_item.json>
    python3 feishu_webhook.py batch <items.json>
    python3 feishu_webhook.py brief <brief.md>
    python3 feishu_webhook.py text <file_or_content> [--title TITLE]
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "")
DEDUP_FILE = os.path.join(os.path.dirname(__file__), ".last_sends")
DEDUP_WINDOW = 120  # 秒：同内容在此窗口内不重复发送


def _card_hash(card: dict) -> str:
    """对卡片 JSON 取 sha256 前 16 位作为指纹（排除发送时间等动态字段）"""
    import copy
    stable = copy.deepcopy(card)
    # 移除 note 元素中的动态时间戳，避免同一内容因发送时间不同而绕过去重
    for elem in stable.get("elements", []):
        if elem.get("tag") == "note":
            for sub in elem.get("elements", []):
                content = sub.get("content", "")
                if any(k in content for k in ("发送时间:", "生成时间:", "执行时间:", "验证时间:")):
                    sub["content"] = ""
    raw = json.dumps(stable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_duplicate(card_hash: str) -> bool:
    """检查此卡片是否在去重窗口内已发送过"""
    now = time.time()
    records: dict[str, float] = {}
    if os.path.exists(DEDUP_FILE):
        try:
            with open(DEDUP_FILE) as f:
                records = json.load(f)
        except (json.JSONDecodeError, OSError):
            records = {}
    # 清理过期记录
    records = {h: ts for h, ts in records.items() if now - ts < DEDUP_WINDOW}
    if card_hash in records:
        return True
    # 记录本次发送
    records[card_hash] = now
    try:
        with open(DEDUP_FILE, "w") as f:
            json.dump(records, f)
    except OSError:
        pass
    return False


def _upgrade_card_v2(card: dict) -> dict:
    """将 v1 卡片自动升级为 v2 结构，支持 markdown 标题/引用/行内代码渲染。"""
    if card.get("schema") == "2.0":
        return card
    v2 = {"schema": "2.0"}
    if "header" in card:
        v2["header"] = card["header"]
    if "config" in card:
        v2["config"] = card["config"]
    elements = _convert_elements_v2(card.get("elements", []))
    v2["body"] = {"elements": elements}
    return v2


def _convert_elements_v2(elements: list[dict]) -> list[dict]:
    """将 v1 元素转为 v2 兼容格式（note → notation markdown）"""
    result = []
    for el in elements:
        if el.get("tag") == "note":
            texts = []
            for child in el.get("elements", []):
                if child.get("tag") in ("plain_text", "lark_md"):
                    texts.append(child.get("content", ""))
            if texts:
                result.append({
                    "tag": "markdown",
                    "content": " ".join(texts),
                    "text_size": "notation",
                })
        else:
            result.append(el)
    return result


def send_card(webhook_url: str, card: dict) -> None:
    if not webhook_url:
        print("ERROR: FEISHU_WEBHOOK_URL 未设置", file=sys.stderr)
        sys.exit(1)
    card = _upgrade_card_v2(card)
    ch = _card_hash(card)
    if _is_duplicate(ch):
        print(f"DEDUP: 相同内容 {ch} 在 {DEDUP_WINDOW}s 内已发送，跳过")
        return
    payload = {"msg_type": "interactive", "card": card}
    resp = requests.post(webhook_url, json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"ERROR: 飞书返回 {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)
    body = resp.json()
    if body.get("code", 0) != 0:
        print(f"ERROR: 飞书业务错误: {body}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: 消息已发送 (status={resp.status_code})")


def build_test_card() -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return {
        "header": {
            "title": {"tag": "plain_text", "content": "✅ 通道测试"},
            "template": "green",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": f"推送通道正常工作。\n\n测试时间: {now}",
            }
        ],
    }


def build_alert_card(item: dict) -> dict | None:
    """构建告警卡片。item 需包含 title 字段。"""
    if not item.get("title"):
        print("WARN: 告警数据缺少 title，跳过发送", file=sys.stderr)
        return None

    level = item.get("level", "medium")
    template = "red" if level == "high" else "orange"
    level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "⚪")

    content = f"{level_emoji} **{item.get('title', '')}**\n\n"
    if item.get("detail"):
        content += f"{item['detail']}\n\n"
    if item.get("source"):
        content += f"来源: {item['source']}\n"

    return {
        "header": {
            "title": {"tag": "plain_text", "content": "🚨 告警"},
            "template": template,
        },
        "elements": [
            {"tag": "markdown", "content": content},
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"⏰ {item.get('timestamp', datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))}",
                    }
                ],
            },
        ],
    }


def build_batch_card(items: list) -> dict:
    lines = []
    for i, item in enumerate(items, 1):
        title = item.get("title", "No Title")
        detail = item.get("detail", "")
        lines.append(f"**{i}. {title}**")
        if detail:
            lines.append(f"   {detail}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"📋 批量更新 ({len(items)}条)",
            },
            "template": "orange",
        },
        "elements": [
            {"tag": "markdown", "content": "\n\n".join(lines)},
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": f"汇总时间: {now}"}],
            },
        ],
    }


def build_brief_card(content: str, filepath: str) -> dict:
    basename = os.path.basename(filepath).lower()
    if "morning" in basename:
        period = "早"
    elif "evening" in basename:
        period = "晚"
    else:
        period = "日"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    elements = _md_to_elements(content)
    elements.append({"tag": "hr"})
    elements.append(
        {
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": f"生成时间: {date_str} | 来源: {os.path.basename(filepath)}"}],
        }
    )

    return {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"📊 {period}报 ({date_str})",
            },
            "template": "blue",
        },
        "elements": elements,
    }


def build_text_card(content: str, title: str = "", filepath: str = "") -> dict:
    """通用文本/Markdown 推送卡片，自动拆分长内容为多个 markdown 元素"""
    if not title:
        first_line = content.strip().split("\n")[0].lstrip("# ").strip()
        title = first_line[:50] if first_line else "消息"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    note_text = f"发送时间: {now}"
    if filepath:
        note_text += f" | 来源: {os.path.basename(filepath)}"
    elements = _md_to_elements(content)
    elements.append({"tag": "hr"})
    elements.append(
        {
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": note_text}],
        }
    )

    return {
        "header": {
            "title": {"tag": "plain_text", "content": f"📨 {title}"},
            "template": "indigo",
        },
        "elements": elements,
    }


def _table_to_list(header_cells: list[str], data_rows: list[list[str]]) -> list[str]:
    """将表格转为 markdown 列表行。"""
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
            result.append("- " + " · ".join(parts))
    return result


def _parse_table_row(line: str) -> list[str]:
    """解析表格行 '| a | b | c |' 为 ['a', 'b', 'c']"""
    cells = line.split("|")
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [c.strip() for c in cells]


def _md_to_elements(content: str) -> list[dict]:
    """将 Markdown 转为飞书卡片 v2 elements。

    规则：
    - `# / ## / ###` 标题 → 保留原始 markdown（v2 支持标题渲染）
    - `---` 分割线（独立行） → {"tag": "hr"}
    - 表格：前 3 个保留原样渲染，第 4 个起转为列表格式（飞书 v2 限制）
    - 其余段落 → {"tag": "markdown"} 块（超长自动拆分）
    """
    import re

    elements: list[dict] = []
    current_lines: list[str] = []
    table_count = 0

    table_sep_re = re.compile(r"^\|[\s:]*-+[\s:]*(\|[\s:]*-+[\s:]*)*\|?\s*$")
    table_row_re = re.compile(r"^\|.+\|")

    def flush() -> None:
        text = "\n".join(current_lines).strip()
        current_lines.clear()
        if not text:
            return
        for chunk in _split_markdown(text):
            elements.append({"tag": "markdown", "content": chunk})

    lines = content.split("\n")
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
    return elements


def _split_markdown(content: str, max_len: int = 3800) -> list[str]:
    """将长 markdown 按段落边界拆分，每个 chunk 不超过 max_len 字符。"""
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


def load_json_file(filepath: str) -> dict | list:
    if not os.path.exists(filepath):
        print(f"ERROR: 文件不存在: {filepath}", file=sys.stderr)
        sys.exit(1)
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text_file(filepath: str) -> str:
    if not os.path.exists(filepath):
        print(f"ERROR: 文件不存在: {filepath}", file=sys.stderr)
        sys.exit(1)
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def main():
    if len(sys.argv) < 2:
        print(
            "用法: feishu_webhook.py <test|alert|batch|brief|text> [file|content] [--title TITLE]",
            file=sys.stderr,
        )
        sys.exit(1)

    cmd = sys.argv[1]
    webhook_url = WEBHOOK_URL
    pushed_flag = None

    if cmd == "test":
        card = build_test_card()
    elif cmd == "alert":
        if len(sys.argv) < 3:
            print("ERROR: alert 需要指定 JSON 文件路径", file=sys.stderr)
            sys.exit(1)
        item = load_json_file(sys.argv[2])
        card = build_alert_card(item)
    elif cmd == "batch":
        if len(sys.argv) < 3:
            print("ERROR: batch 需要指定 JSON 文件路径", file=sys.stderr)
            sys.exit(1)
        data = load_json_file(sys.argv[2])
        items = data if isinstance(data, list) else [data]
        card = build_batch_card(items)
    elif cmd == "brief":
        if len(sys.argv) < 3:
            print("ERROR: brief 需要指定 Markdown 文件路径", file=sys.stderr)
            sys.exit(1)
        content = load_text_file(sys.argv[2])
        card = build_brief_card(content, sys.argv[2])
    elif cmd == "text":
        if len(sys.argv) < 3:
            print("ERROR: text 需要指定文件路径或文本内容", file=sys.stderr)
            sys.exit(1)
        title = ""
        args = sys.argv[2:]
        if "--title" in args:
            idx = args.index("--title")
            if idx + 1 < len(args):
                title = args[idx + 1]
                args = args[:idx] + args[idx + 2:]
        source = args[0] if args else ""
        if os.path.exists(source):
            pushed_flag = source + ".pushed"
            if os.path.exists(pushed_flag):
                print(f"SKIP: 已推送过 {os.path.basename(source)}，跳过重复发送", file=sys.stderr)
                sys.exit(0)
            content = load_text_file(source)
            card = build_text_card(content, title, filepath=source)
        else:
            content = source
            card = build_text_card(content, title)
    else:
        print(
            f"ERROR: 未知命令 '{cmd}'，可选: test, alert, batch, brief, text", file=sys.stderr
        )
        sys.exit(1)

    if card is None:
        print("SKIP: 数据无效，未发送", file=sys.stderr)
        sys.exit(0)
    send_card(webhook_url, card)

    if pushed_flag:
        try:
            open(pushed_flag, "w").close()
        except OSError:
            pass


if __name__ == "__main__":
    main()

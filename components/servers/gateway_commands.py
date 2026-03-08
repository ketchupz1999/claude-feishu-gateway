"""
命令处理模块 — 所有 /command 的具体实现

每个 cmd_xxx 函数签名统一: (message_id, chat_id, text, ctx) -> None
ctx 是 CommandContext，提供对 gateway 全局状态的访问。
"""

import os


class CommandContext:
    """命令处理函数的依赖注入容器"""

    def __init__(self, *, workspace, session_mgr, models, log_fn, safe_reply_fn,
                 split_text_fn, send_text_fn, interrupt_fn):
        self.workspace = workspace
        self.session_mgr = session_mgr
        self.models = models
        self.current_model: str = "sonnet"
        self.log = log_fn
        self.safe_reply = safe_reply_fn
        self.split_text = split_text_fn
        self.send_text = send_text_fn
        self.interrupt_fn = interrupt_fn

        # 转发状态
        self.forwarding_mode: bool = False
        self.forwarding_buffer: list[str] = []
        self.pending_context: str | None = None


# ===== 转发相关 =====

def cmd_start_forward(message_id, chat_id, text, ctx: CommandContext):
    ctx.forwarding_mode = True
    ctx.forwarding_buffer = []
    ctx.safe_reply(message_id, chat_id, "收集模式开启，请逐条转发消息\n完成后发送 /结束转发")


def cmd_cancel_forward(message_id, chat_id, text, ctx: CommandContext):
    ctx.forwarding_mode = False
    ctx.forwarding_buffer = []
    ctx.safe_reply(message_id, chat_id, "已取消收集，模式已退出")


def cmd_end_forward(message_id, chat_id, text, ctx: CommandContext):
    ctx.forwarding_mode = False
    if not ctx.forwarding_buffer:
        ctx.safe_reply(message_id, chat_id, "没有收集到任何消息，已退出收集模式")
    else:
        n = len(ctx.forwarding_buffer)
        lines = [f"以下是从群聊中逐条转发的 {n} 条消息：", ""]
        for i, msg_text in enumerate(ctx.forwarding_buffer, 1):
            lines.append(f"[{i}] {msg_text}")
        ctx.pending_context = "\n".join(lines)
        ctx.forwarding_buffer = []
        ctx.safe_reply(message_id, chat_id, f"已收集 {n} 条消息，请提问")


# ===== 模型/会话控制 =====

def cmd_model(message_id, chat_id, text, ctx: CommandContext):
    parts = text.strip().split()
    if len(parts) >= 2 and parts[1] in ctx.models:
        ctx.current_model = parts[1]
        ctx.safe_reply(message_id, chat_id, f"已切换到 {ctx.current_model} ({ctx.models[ctx.current_model]})")
    else:
        lines = [f"当前模型: {ctx.current_model} ({ctx.models[ctx.current_model]})", "可用模型:"]
        for k, v in ctx.models.items():
            marker = " <-" if k == ctx.current_model else ""
            lines.append(f"  /model {k}  ->  {v}{marker}")
        ctx.safe_reply(message_id, chat_id, "\n".join(lines))


def cmd_stop(message_id, chat_id, text, ctx: CommandContext):
    if ctx.interrupt_fn():
        ctx.session_mgr.clear_session()
        ctx.safe_reply(message_id, chat_id, "已中断当前任务，会话已清除")
    else:
        ctx.safe_reply(message_id, chat_id, "当前没有正在执行的任务")


def cmd_clear(message_id, chat_id, text, ctx: CommandContext):
    ctx.session_mgr.clear_session()
    ctx.safe_reply(message_id, chat_id, "会话已清除，下条消息将新开对话")


def cmd_new(message_id, chat_id, text, ctx: CommandContext):
    parts = text.strip().split(None, 1)
    topic = parts[1].strip() if len(parts) > 1 else ""
    ctx.session_mgr.pending_topic = topic if topic else None
    ctx.session_mgr.clear_session()
    msg = "会话已清除，下条消息将新开对话"
    if topic:
        msg += f"\n主题: {topic}"
    ctx.safe_reply(message_id, chat_id, msg)


def cmd_sessions(message_id, chat_id, text, ctx: CommandContext):
    parts = text.strip().split(maxsplit=1)
    keyword = parts[1] if len(parts) > 1 else None
    sessions = ctx.session_mgr.get_session_list(50)
    if keyword:
        kw = keyword.lower()
        sessions = [s for s in sessions if kw in (s.get("topic") or "").lower() or kw in (s.get("first_msg") or "").lower()]
    ctx.safe_reply(message_id, chat_id, ctx.session_mgr.format_session_list(sessions, keyword=keyword))


def cmd_switch(message_id, chat_id, text, ctx: CommandContext):
    parts = text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        ctx.safe_reply(message_id, chat_id, "用法: /switch <序号>（序号见 /sessions）")
        return
    idx = int(parts[1]) - 1
    sessions = ctx.session_mgr.get_session_list(50)
    if idx < 0 or idx >= len(sessions):
        ctx.safe_reply(message_id, chat_id, f"序号超出范围，当前共 {len(sessions)} 个会话")
        return
    target = sessions[idx]
    ctx.session_mgr.save_session(target["session_id"])
    ctx.session_mgr.pending_topic = None
    preview_msgs = ctx.session_mgr.read_last_messages(target["session_id"], n=2)
    display = target["topic"] or target["first_msg"] or "(无摘要)"
    lines = [f"已切换到: {display}", f"[{target['mtime_str']}]", ""]
    if preview_msgs:
        lines.append("-- 最近消息 --")
        for m in preview_msgs:
            role_label = "你" if m["role"] == "user" else "AI"
            snippet = m["content"][:120].replace("\n", " ")
            lines.append(f"{role_label}: {snippet}")
    else:
        lines.append("(暂无可预览消息)")
    ctx.safe_reply(message_id, chat_id, "\n".join(lines))


# ===== 命令路由表 =====

# 精确匹配命令
EXACT_COMMANDS = {
    "/开始转发": cmd_start_forward,
    "/结束转发": cmd_end_forward,
    "/取消转发": cmd_cancel_forward,
    "/stop": cmd_stop,
    "/clear": cmd_clear,
    "/sessions": cmd_sessions,
}

# 前缀匹配命令（需要参数）
PREFIX_COMMANDS = [
    ("/model", cmd_model),
    ("/new", cmd_new),
    ("/switch", cmd_switch),
]


def dispatch(message_id: str, chat_id: str, text: str, ctx: CommandContext) -> bool:
    """尝试匹配并执行命令。返回 True 表示已处理，False 表示不是命令。"""
    stripped = text.strip()
    cmd_word = stripped.split()[0] if stripped else ""

    # 精确匹配
    if stripped in EXACT_COMMANDS:
        EXACT_COMMANDS[stripped](message_id, chat_id, text, ctx)
        return True

    # 前缀匹配
    for prefix, handler in PREFIX_COMMANDS:
        if cmd_word == prefix or stripped.startswith(prefix + " "):
            handler(message_id, chat_id, text, ctx)
            return True

    return False

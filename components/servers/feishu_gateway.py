#!/usr/bin/env python3
"""
飞书双向消息网关 — 手机飞书 at bot → Claude Code 执行 → 结果回复

职责：消息路由 + Claude SDK 执行引擎 + 进程管理
命令处理 → gateway_commands.py
消息解析/回复 → gateway_messaging.py
会话管理 → gateway_sessions.py

用法:
    python3 components/servers/feishu_gateway.py          # 前台运行
    nohup python3 components/servers/feishu_gateway.py &  # 后台运行

配置: .claude/secrets/feishu_app.json
"""

import asyncio
import json
import os
import signal
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

import gateway_messaging as messaging
import lark_oapi as lark
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)
from gateway_commands import CommandContext
from gateway_commands import dispatch as dispatch_command

# 同目录模块
from gateway_sessions import SessionManager

# ===== Monkey-patch: 第三方 API 兼容 =====
# 部分第三方 API（如 StepFun）返回的 thinking block 缺少 signature 字段，
# SDK 默认用 block["signature"] 会 KeyError。patch 为 block.get("signature") 容错。
def _patch_sdk_message_parser():
    try:
        import claude_agent_sdk._internal.message_parser as _mp
        _original_parse = _mp.parse_message

        def _patched_parse(data):
            # 预处理: 给 assistant 消息的 thinking block 补上缺失的 signature
            if (isinstance(data, dict)
                    and data.get("type") == "assistant"
                    and "message" in data):
                for block in data.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "thinking":
                        block.setdefault("signature", None)
            return _original_parse(data)

        _mp.parse_message = _patched_parse
    except Exception:
        pass  # SDK 内部结构变化时静默跳过

_patch_sdk_message_parser()
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)

# ===== 路径 =====
WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECRETS_FILE = os.path.join(WORKSPACE, ".claude", "secrets", "feishu_app.json")
LOGDIR = os.path.join(WORKSPACE, "data", "logs")
PIDFILE = os.path.join(WORKSPACE, "data", "gateway.pid")

EXEC_TIMEOUT = 600  # 10 分钟
HEARTBEAT_INTERVAL = 60  # 工具心跳最小间隔(秒)

# ===== 系统提示 =====
SYSTEM_HINT = """你是飞书消息网关背后的助手。注意以下工具使用原则：
- 用户要求"搜索"、"查一下"、"最新消息"时，优先用 WebSearch，不要调用 Skill
- Skill 只在用户明确使用 /slash 命令时调用（如 /pulse, /triage）
- 保持回复简洁，适合手机阅读
- 用户可能通过语音转文字输入，内容可能有同音错别字、漏字或断句不清，请根据上下文推断真实意图，不要纠正错别字
"""

# 模型配置
# 如果设置了 ANTHROPIC_MODEL 环境变量（第三方 API），所有别名指向同一个模型
_OVERRIDE_MODEL = os.environ.get("ANTHROPIC_MODEL")
if _OVERRIDE_MODEL:
    MODELS = {
        "sonnet": _OVERRIDE_MODEL,
        "haiku": _OVERRIDE_MODEL,
        "opus": _OVERRIDE_MODEL,
    }
else:
    MODELS = {
        "sonnet": "claude-sonnet-4-6",
        "haiku": "claude-haiku-4-5-20251001",
        "opus": "claude-opus-4-6",
    }

# 快捷指令映射（自定义：添加你自己的 skill 映射）
SHORTCUTS = {
    # "/pulse": "/your-skill-name",
}

# ===== 全局状态 =====
executor_lock = threading.Lock()
seen_messages: OrderedDict = OrderedDict()
MAX_SEEN = 500

api_client: lark.Client = None
config: dict = {}
session_mgr: SessionManager = None
cmd_ctx: CommandContext = None

# 中断控制
_current_client: ClaudeSDKClient | None = None
_current_loop: asyncio.AbstractEventLoop | None = None


# ===== 日志 =====
def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    line = f"[{ts}] [gateway] {msg}"
    print(line, flush=True)
    os.makedirs(LOGDIR, exist_ok=True)
    logfile = os.path.join(LOGDIR, f"{datetime.now(timezone.utc):%Y-%m-%d}-gateway.log")
    with open(logfile, "a") as f:
        f.write(line + "\n")


# ===== 紧急通知 =====
def emergency_notify(text: str):
    try:
        cfg = config if config else load_config()
        client = api_client or (lark.Client.builder().app_id(cfg["app_id"]).app_secret(cfg["app_secret"]).build())
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("open_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(cfg["allowed_open_id"])
                .msg_type("text")
                .content(json.dumps({"text": f"[Gateway 紧急] {text}"}))
                .build()
            )
            .build()
        )
        client.im.v1.message.create(req)
    except Exception as e:
        print(f"紧急通知发送失败: {e}", file=sys.stderr)


# ===== 配置加载 =====
def load_config() -> dict:
    if not os.path.exists(SECRETS_FILE):
        print(f"ERROR: 配置文件不存在: {SECRETS_FILE}", file=sys.stderr)
        print('格式: {"app_id":"cli_xxx","app_secret":"xxx","allowed_open_id":"ou_xxx"}')
        sys.exit(1)
    with open(SECRETS_FILE) as f:
        cfg = json.load(f)
    for key in ("app_id", "app_secret", "allowed_open_id"):
        if not cfg.get(key) or cfg[key].endswith("_xxx"):
            print(f"ERROR: 请填写 {SECRETS_FILE} 中的 {key}", file=sys.stderr)
            sys.exit(1)
    return cfg


# ===== 消息去重 =====
def is_duplicate(message_id: str) -> bool:
    if message_id in seen_messages:
        return True
    seen_messages[message_id] = time.time()
    while len(seen_messages) > MAX_SEEN:
        seen_messages.popitem(last=False)
    return False


# ===== 执行引擎 =====
def resolve_prompt(text: str) -> str:
    cmd = text.split()[0] if text else ""
    if cmd in SHORTCUTS:
        return SHORTCUTS[cmd]
    return text


def wrap_skill_prompt(prompt: str) -> str:
    """新 SDK 用 stream-json stdin 传 prompt，CLI 会把 / 开头视为内置斜杠命令。
    包一层自然语言让它作为普通用户消息传给 LLM，由 LLM 调用 Skill tool 执行。"""
    if prompt.startswith("/"):
        return f"请执行 {prompt}"
    return prompt


def classify_tier(prompt: str) -> str:
    return "skill" if prompt.startswith("/") else "chat"


def format_tool_summary(metadata: dict) -> str:
    parts = []
    tool_counts = metadata.get("tool_counts", {})
    if tool_counts:
        tool_parts = []
        for name, count in tool_counts.items():
            tool_parts.append(f"{name} x{count}" if count > 1 else name)
        parts.append(", ".join(tool_parts))
    duration = metadata.get("duration_ms", 0)
    if duration:
        parts.append(f"{duration / 1000:.0f}s")
    cost = metadata.get("cost_usd")
    if cost is not None:
        parts.append(f"${cost:.3f}")
    if not parts:
        return ""
    model_label = MODELS[cmd_ctx.current_model]
    return f"\n---\n[{model_label} | {' | '.join(parts)}]"


def _summarize_input(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Bash":
        return tool_input.get("command", "")[:120]
    if tool_name in ("Read", "Write", "Edit"):
        return tool_input.get("file_path", "")
    if tool_name == "Glob":
        return tool_input.get("pattern", "")
    if tool_name == "Grep":
        return f'{tool_input.get("pattern", "")} in {tool_input.get("path", ".")}'
    if tool_name in ("WebFetch", "WebSearch"):
        return tool_input.get("url", "") or tool_input.get("query", "")
    if tool_name == "Skill":
        return tool_input.get("skill", "")
    if tool_name == "Task":
        return tool_input.get("description", "")[:80]
    for v in tool_input.values():
        if isinstance(v, str) and v:
            return v[:80]
    return ""


async def execute_claude_async(
    prompt: str, resume_session: str | None = None, on_progress=None
) -> tuple[bool, str, dict]:
    """异步调用 claude-agent-sdk，返回 (success, output, metadata)"""
    global _current_client
    tier = classify_tier(prompt)
    log(f"执行: prompt='{prompt[:100]}', tier={tier}, resume={resume_session or 'None'}")

    text_parts: list[str] = []
    tool_counts: dict[str, int] = {}
    metadata: dict = {}
    msg_index = 0
    skill_active = False
    last_heartbeat = time.time()
    streamed_any_text = False

    sp: dict = {"type": "preset", "preset": "claude_code"}
    if tier == "chat":
        sp["append"] = SYSTEM_HINT

    options = ClaudeAgentOptions(
        cwd=WORKSPACE,
        model=MODELS[cmd_ctx.current_model],
        permission_mode="bypassPermissions",
        max_turns=80,
        system_prompt=sp,
        resume=resume_session,
        setting_sources=["user", "project", "local"],
    )
    client = ClaudeSDKClient(options)

    try:
        log(f"SDK connect 开始 (model={options.model}, resume={resume_session})")
        await client.connect()
        log("SDK connect 成功")
        _current_client = client
        await client.query(wrap_skill_prompt(prompt))
        log("SDK query 发送成功")

        async for msg in client.receive_response():
            if msg is None:
                continue
            if isinstance(msg, ResultMessage):
                metadata = {
                    "session_id": msg.session_id,
                    "num_turns": msg.num_turns,
                    "duration_ms": msg.duration_ms,
                    "cost_usd": msg.total_cost_usd,
                    "is_error": msg.is_error,
                    "tool_counts": tool_counts,
                    "streamed": streamed_any_text,
                }
                if msg.is_error:
                    return False, msg.result or "未知错误", metadata
            else:
                msg_index += 1
                msg_text: list[str] = []
                skill_names: list[str] = []
                has_tools = False
                for block in getattr(msg, "content", []):
                    if isinstance(block, TextBlock):
                        msg_text.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        has_tools = True
                        tool_counts[block.name] = tool_counts.get(block.name, 0) + 1
                        summary = _summarize_input(block.name, block.input)
                        log(f"  ▶ {block.name}: {summary}")
                        if on_progress and time.time() - last_heartbeat >= HEARTBEAT_INTERVAL:
                            on_progress("status", f"▶ {block.name}: {summary}")
                            last_heartbeat = time.time()
                        if block.name == "Skill":
                            skill_names.append(block.input.get("skill", "unknown"))
                joined = " ".join(msg_text).strip()
                first50 = joined[:50].replace("\n", "\\n") if joined else "(empty)"
                if skill_names:
                    action = "SKILL_INVOKE"
                    text_parts.append(f"[执行 skill: {', '.join(skill_names)}]")
                    skill_active = True
                elif skill_active:
                    action = "SKILL_CONTENT_SKIP" if joined else "SKILL_EMPTY_SKIP"
                    if joined:
                        skill_active = False
                else:
                    action = "KEEP"
                    text_parts.extend(msg_text)
                    if on_progress and joined:
                        on_progress("text", joined)
                        streamed_any_text = True
                log(f'  msg#{msg_index} [{action}] tools={has_tools} text={len(joined)}c "{first50}"')

        output = "\n".join(text_parts).strip()
        if not output:
            output = "(执行完成，无输出)"

        log(
            f"执行完成: session={metadata.get('session_id', '?')}, "
            f"turns={metadata.get('num_turns', '?')}, "
            f"duration={metadata.get('duration_ms', '?')}ms, "
            f"cost=${metadata.get('cost_usd') or 0:.4f}, "
            f"tools={tool_counts}"
        )
        return True, output, metadata

    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        return False, f"执行超时 (>{EXEC_TIMEOUT}s)", {"tool_counts": tool_counts}
    except Exception as e:
        import traceback
        log(f"SDK 异常: {e}\n{traceback.format_exc()}")
        return False, f"执行异常: {e}", {"tool_counts": tool_counts}
    finally:
        _current_client = None
        try:
            await client.disconnect()
        except Exception:
            pass


def _run_in_new_loop(coro):
    """在新线程的新 event loop 中执行协程"""
    global _current_loop
    result = [None]
    exc = [None]

    def _target():
        global _current_loop
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _current_loop = loop
            result[0] = loop.run_until_complete(
                asyncio.wait_for(coro, timeout=EXEC_TIMEOUT)
            )
        except asyncio.CancelledError:
            exc[0] = InterruptedError("用户中断")
        except Exception as e:
            exc[0] = e
        finally:
            _current_loop = None
            loop.close()

    t = threading.Thread(target=_target)
    t.start()
    t.join(timeout=EXEC_TIMEOUT + 10)
    if exc[0]:
        raise exc[0]
    return result[0]


def interrupt_current_task() -> bool:
    """中断当前执行：通过 SDK client.interrupt() 发送中断信号"""
    client = _current_client
    loop = _current_loop
    if client and loop:
        async def _do_interrupt():
            try:
                await client.interrupt()
                log("SDK interrupt 信号已发送")
            except Exception as e:
                log(f"SDK interrupt 失败: {e}")
        loop.call_soon_threadsafe(asyncio.ensure_future, _do_interrupt())
        return True
    return False


def execute_claude(prompt: str, resume_session: str | None = None, on_progress=None) -> tuple[bool, str, dict]:
    """同步包装: 在独立线程的新 event loop 中执行 async SDK 调用"""
    saved = {k: v for k, v in os.environ.items() if k.startswith("CLAUDE")}
    for k in saved:
        del os.environ[k]
    try:
        return _run_in_new_loop(execute_claude_async(prompt, resume_session, on_progress))
    except InterruptedError:
        log("任务被用户中断")
        return False, "已中断", {"tool_counts": {}, "streamed": False}
    finally:
        os.environ.update(saved)


# ===== 消息处理（thin dispatcher） =====
def handle_message(data: P2ImMessageReceiveV1) -> None:
    """飞书消息事件回调 — 路由到命令处理或 Claude 执行"""
    msg = data.event.message
    sender = data.event.sender

    sender_id = sender.sender_id.open_id
    message_id = msg.message_id
    chat_id = msg.chat_id

    log(f"事件: chat_type={getattr(msg, 'chat_type', 'unknown')}, sender={sender_id}, msg_id={message_id}")

    # 鉴权
    if sender_id != config["allowed_open_id"]:
        log(f"忽略非授权用户: {sender_id}")
        return

    # 去重
    if is_duplicate(message_id):
        log(f"忽略重复消息: {message_id}")
        return

    # 过滤过期消息
    MAX_MSG_AGE = 120
    try:
        create_ts = int(msg.create_time) / 1000
        age = time.time() - create_ts
        if age > MAX_MSG_AGE:
            log(f"忽略过期消息: age={age:.0f}s > {MAX_MSG_AGE}s, msg_id={message_id}")
            return
    except (ValueError, TypeError, AttributeError):
        pass

    # 合并转发消息
    if msg.message_type == "merge_forward":
        ctx, count = messaging.extract_merge_forward(data)
        if ctx:
            cmd_ctx.pending_context = ctx
            messaging.safe_reply(message_id, chat_id, f"已收到 {count} 条对话记录，请提问")
        else:
            raw = json.loads(msg.content) if msg.content else {}
            log(f"merge_forward 解析失败，原始内容: {json.dumps(raw, ensure_ascii=False)[:300]}")
            messaging.safe_reply(message_id, chat_id, "解析对话记录失败，请重试或直接粘贴文字")
        return

    # 只处理文本和富文本
    if msg.message_type not in ("text", "post"):
        messaging.safe_reply(message_id, chat_id, "暂只支持文本消息")
        return

    text = messaging.extract_text(data)
    if not text:
        return

    log(f"收到消息: {text[:100]}")

    # 逐条收集模式中：非命令消息直接入 buffer
    if cmd_ctx.forwarding_mode and text.strip() not in ("/结束转发", "/取消转发"):
        cmd_ctx.forwarding_buffer.append(text.strip())
        messaging.safe_reply(message_id, chat_id, f"ok {len(cmd_ctx.forwarding_buffer)}")
        return

    # 命令路由
    if dispatch_command(message_id, chat_id, text, cmd_ctx):
        return

    # 拼接转发上下文
    if cmd_ctx.pending_context:
        text = f"{cmd_ctx.pending_context}\n\n---\n{text}"
        cmd_ctx.pending_context = None
        log("已附加逐条转发上下文")

    # 解析指令
    prompt = resolve_prompt(text)
    tier = classify_tier(prompt)
    resume_session = session_mgr.last_session_id if tier == "chat" else None

    # 并发控制
    if not executor_lock.acquire(blocking=False):
        messaging.safe_reply(message_id, chat_id, "有任务正在执行中，请稍后再试\n发送 /stop 可中断当前任务")
        return

    messaging.reply_text(message_id, "正在执行...")

    # 在后台线程执行，不阻塞事件循环（让 /stop 等命令能被即时处理）
    def _execute_in_background():
        try:
            def progress_cb(msg_type, text):
                try:
                    if msg_type == "text":
                        if messaging._should_use_card(text):
                            card = messaging._md_to_card(text)
                            if not messaging.send_card(chat_id, card):
                                for chunk in messaging.split_text(text):
                                    messaging.send_text(chat_id, chunk)
                        else:
                            for chunk in messaging.split_text(text):
                                messaging.send_text(chat_id, chunk)
                    elif msg_type == "status":
                        messaging.send_text(chat_id, f"[进度] {text}")
                except Exception as e:
                    log(f"流式推送失败: {e}")

            success, output, metadata = execute_claude(prompt, resume_session, on_progress=progress_cb)

            # resume 失败时降级为新会话重试
            if not success and resume_session:
                log(f"resume 失败，降级为新会话重试: {output[:100]}")
                session_mgr.clear_session()
                messaging.send_text(chat_id, "[会话续接失败，新开对话重试...]")
                success, output, metadata = execute_claude(prompt, on_progress=progress_cb)

            # 保存 session
            if success and tier == "chat":
                new_sid = metadata.get("session_id")
                if new_sid:
                    session_mgr.save_session(new_sid)
                    log(f"会话已保存: {new_sid}")
                    session_mgr.register_session(
                        new_sid,
                        topic=session_mgr.pending_topic,
                        first_msg=prompt[:60] if not resume_session else None,
                    )
                    if session_mgr.pending_topic:
                        session_mgr.pending_topic = None

            summary = format_tool_summary(metadata)
            streamed = metadata.get("streamed", False)

            if success:
                log(f"执行成功, 输出 {len(output)} 字符, streamed={streamed}")
                footer = summary.replace("\n---\n", "").strip() if summary else ""
                done_msg = f"{footer}\n任务已完成" if footer else "任务已完成"
                if streamed:
                    messaging.send_text(chat_id, done_msg)
                else:
                    messaging.safe_reply(message_id, chat_id, output + summary)
                    messaging.send_text(chat_id, "任务已完成")
            else:
                log(f"执行失败: {output[:200]}")
                messaging.safe_reply(message_id, chat_id, f"[错误] {output}{summary}")
        except Exception as e:
            log(f"后台执行异常: {e}")
            messaging.send_text(chat_id, f"[错误] {e}")
        finally:
            executor_lock.release()

    threading.Thread(target=_execute_in_background, daemon=True).start()


# ===== 进程管理 =====
def write_pid():
    os.makedirs(os.path.dirname(PIDFILE), exist_ok=True)
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))


def cleanup(*_):
    log("收到终止信号，退出")
    if os.path.exists(PIDFILE):
        os.remove(PIDFILE)
    sys.exit(0)


# ===== 入口 =====
def main():
    global config, api_client, session_mgr, cmd_ctx

    # 检查是否已有实例
    if os.path.exists(PIDFILE):
        with open(PIDFILE) as f:
            old_pid = f.read().strip()
        try:
            os.kill(int(old_pid), 0)
            print(
                f"ERROR: gateway 已在运行 (PID={old_pid}), " f"先 kill {old_pid} 或删除 {PIDFILE}",
                file=sys.stderr,
            )
            sys.exit(1)
        except (OSError, ValueError):
            pass

    # 加载配置
    config = load_config()

    # 初始化会话管理器
    session_mgr = SessionManager(WORKSPACE)
    session_mgr.load_registry()
    session_mgr.load_session()
    if session_mgr.last_session_id:
        log(f"恢复上次会话: {session_mgr.last_session_id}")
    else:
        log("无历史会话，将新开对话")

    # 创建 API Client
    api_client = (
        lark.Client.builder()
        .app_id(config["app_id"])
        .app_secret(config["app_secret"])
        .log_level(lark.LogLevel.INFO)
        .build()
    )

    # 初始化消息模块
    messaging.init(api_client, log)

    # 初始化命令上下文
    cmd_ctx = CommandContext(
        workspace=WORKSPACE,
        session_mgr=session_mgr,
        models=MODELS,
        log_fn=log,
        safe_reply_fn=messaging.safe_reply,
        split_text_fn=messaging.split_text,
        send_text_fn=messaging.send_text,
        interrupt_fn=interrupt_current_task,
    )

    # 事件分发器
    event_handler = (
        lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(handle_message).build()
    )

    # WebSocket 长连接
    ws_client = lark.ws.Client(
        app_id=config["app_id"],
        app_secret=config["app_secret"],
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
        auto_reconnect=True,
    )

    # 进程管理
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    write_pid()

    log(f"gateway 启动 (PID={os.getpid()})")
    log(f"workspace: {WORKSPACE}")
    log(f"engine: claude-agent-sdk, model: {cmd_ctx.current_model} ({MODELS[cmd_ctx.current_model]})")
    oid = config["allowed_open_id"]
    log(f"allowed_open_id: {oid[:8]}...{oid[-4:]}")
    log(f"快捷指令: {list(SHORTCUTS.keys())}")
    log("会话管理: /sessions 查看列表, /new [主题] 新建, /switch <n> 切换, /clear 清除, /stop 中断")

    # 防止嵌套检测
    os.environ.pop("CLAUDECODE", None)

    # 阻塞运行
    try:
        ws_client.start()
    except Exception as e:
        errmsg = f"Gateway 异常退出: {e}"
        log(errmsg)
        emergency_notify(errmsg)
        raise


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        try:
            emergency_notify(f"Gateway 启动失败: {e}")
        except Exception:
            pass

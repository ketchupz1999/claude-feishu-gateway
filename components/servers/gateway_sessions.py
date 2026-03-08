"""
会话管理模块 — session 持久化、多会话注册、会话列表

被 feishu_gateway.py 导入使用。
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

_TAG_RE = re.compile(r"<[^>]+>.*?</[^>]+>|<[^>]+/>", re.DOTALL)


def _clean_msg(text: str) -> str:
    """去除 XML/系统标签，返回干净的纯文本"""
    text = _TAG_RE.sub("", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


class SessionManager:
    """管理 gateway 的会话状态（当前 session、多会话注册表）"""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.session_file = os.path.join(workspace, "data", ".gateway_session")
        self.registry_file = os.path.join(workspace, "data", ".gateway_session_registry.json")

        _claude_projects = Path.home() / ".claude" / "projects"
        _project_key = str(workspace).replace("/", "-")
        self.project_dir = _claude_projects / _project_key

        self.last_session_id: str | None = None
        self.session_registry: dict = {}
        self.pending_topic: str | None = None

    # -- 当前 session --

    def load_session(self) -> str | None:
        """从文件加载上次的 session_id（网关重启后恢复）"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file) as f:
                    sid = f.read().strip()
                self.last_session_id = sid if sid else None
                return self.last_session_id
        except Exception:
            pass
        return None

    def save_session(self, session_id: str | None):
        """持久化 session_id 到文件"""
        self.last_session_id = session_id
        try:
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            with open(self.session_file, "w") as f:
                f.write(session_id or "")
        except Exception:
            pass

    def clear_session(self):
        """清除会话，下次新开对话"""
        self.save_session(None)

    # -- 多会话注册表 --

    def load_registry(self):
        try:
            if os.path.exists(self.registry_file):
                with open(self.registry_file) as f:
                    self.session_registry = json.load(f)
        except Exception:
            self.session_registry = {}

    def save_registry(self):
        try:
            os.makedirs(os.path.dirname(self.registry_file), exist_ok=True)
            with open(self.registry_file, "w") as f:
                json.dump(self.session_registry, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def register_session(self, session_id: str, topic: str | None = None, first_msg: str | None = None):
        """注册或更新会话 topic / first_msg"""
        if session_id not in self.session_registry:
            self.session_registry[session_id] = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "topic": topic or "",
                "first_msg": first_msg or "",
            }
        else:
            if topic:
                self.session_registry[session_id]["topic"] = topic
            if first_msg and not self.session_registry[session_id].get("first_msg"):
                self.session_registry[session_id]["first_msg"] = first_msg
        self.save_registry()

    # -- 会话列表 --

    def _read_first_user_msg(self, jsonl_path: Path) -> str:
        """从 JSONL 会话文件中提取第一条有效用户消息（最多 60 字符）"""
        try:
            with open(jsonl_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if entry.get("type") != "user":
                        continue
                    c = entry.get("message", {}).get("content", "")
                    raw = ""
                    if isinstance(c, str):
                        raw = c
                    elif isinstance(c, list):
                        for item in c:
                            if isinstance(item, dict) and item.get("type") == "text":
                                raw = item.get("text", "")
                                break
                    cleaned = _clean_msg(raw)
                    if cleaned:
                        return cleaned[:60]
        except Exception:
            pass
        return ""

    def read_last_messages(self, session_id: str, n: int = 2) -> list[dict]:
        """读取会话最后 n 条有效消息（user / assistant）"""
        f = self.project_dir / f"{session_id}.jsonl"
        if not f.exists():
            return []
        messages = []
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        role, content = None, ""
                        if entry.get("type") == "user":
                            role = "user"
                            c = entry.get("message", {}).get("content", "")
                            content = c if isinstance(c, str) else ""
                        elif entry.get("type") == "assistant":
                            role = "assistant"
                            c = entry.get("message", {}).get("content", [])
                            if isinstance(c, list):
                                content = "".join(
                                    x.get("text", "") for x in c
                                    if isinstance(x, dict) and x.get("type") == "text"
                                )
                        if role and content.strip():
                            messages.append({"role": role, "content": content.strip()})
                    except Exception:
                        pass
        except Exception:
            pass
        return messages[-n:]

    def get_session_list(self, limit: int = 8) -> list[dict]:
        """从项目目录读取最近的会话列表"""
        sessions = []
        if not self.project_dir.exists():
            return sessions
        for f in self.project_dir.glob("*.jsonl"):
            if f.name.startswith("agent-"):
                continue
            session_id = f.stem
            try:
                stat = f.stat()
                reg = self.session_registry.get(session_id, {})
                topic = reg.get("topic", "")
                first_msg = reg.get("first_msg", "") or self._read_first_user_msg(f)
                sessions.append({
                    "session_id": session_id,
                    "topic": topic,
                    "first_msg": first_msg,
                    "mtime": stat.st_mtime,
                    "mtime_str": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%m-%d %H:%MZ"),
                })
            except Exception:
                pass
        sessions.sort(key=lambda x: x["mtime"], reverse=True)
        return sessions[:limit]

    def format_session_list(self, sessions: list[dict], keyword: str | None = None) -> str:
        if not sessions:
            if keyword:
                return f"未找到包含「{keyword}」的会话\n\n用法: /sessions [关键词]"
            return "暂无历史会话\n\n新建: /new [主题]"
        header = f"搜索「{keyword}」({len(sessions)} 条):" if keyword else f"最近会话 ({len(sessions)} 条):"
        lines = [header, ""]
        for i, s in enumerate(sessions, 1):
            is_current = s["session_id"] == self.last_session_id
            marker = " <-" if is_current else ""
            display = s["topic"] or s["first_msg"] or "(无摘要)"
            if len(display) > 38:
                display = display[:36] + "..."
            lines.append(f"{i}. [{s['mtime_str']}] {display}{marker}")
        lines += ["", "切换: /switch <序号>  搜索: /sessions <关键词>"]
        return "\n".join(lines)

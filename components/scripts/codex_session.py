#!/usr/bin/env python3
"""
Codex CLI session query tool.

Reads thread data from Codex local state:
- ~/.codex/state_5.sqlite (Codex CLI's thread index)
- ~/.codex/sessions/**/*.jsonl (Codex SDK session rollouts)
All output is JSON to stdout.

Usage:
    python3 codex_session.py list [--cwd PATH] [--limit N]
    python3 codex_session.py get <thread_id>
"""
import argparse
import datetime as dt
import glob
import json
import os
import sqlite3
import sys

CODEX_HOME = os.path.join(os.path.expanduser("~"), ".codex")
DB_PATH = os.path.join(CODEX_HOME, "state_5.sqlite")
SESSIONS_GLOB = os.path.join(CODEX_HOME, "sessions", "**", "*.jsonl")

COLUMNS = [
    "id", "title", "model", "source", "cwd",
    "first_user_message", "created_at", "updated_at", "archived",
]


def get_connection():
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def is_subagent(source: str) -> bool:
    if not source.startswith("{"):
        return False
    try:
        return "subagent" in json.loads(source)
    except (json.JSONDecodeError, TypeError):
        return False


def row_to_dict(row) -> dict:
    return dict(zip(COLUMNS, row))


def parse_timestamp(value: str | None) -> int:
    if not value:
        return 0
    try:
        normalized = value.replace("Z", "+00:00")
        return int(dt.datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return 0


def should_skip_user_message(text: str) -> bool:
    stripped = text.strip()
    return not stripped or stripped.startswith("<environment_context>")


def iter_jsonl_session_files():
    files = glob.glob(SESSIONS_GLOB, recursive=True)
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    yield from files


def parse_jsonl_session(file_path: str, cwd_filter: str | None = None) -> dict | None:
    meta: dict = {}
    first_user_message = ""
    model = ""
    created_at = 0
    updated_at = 0

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                updated_at = max(updated_at, parse_timestamp(event.get("timestamp")))
                payload = event.get("payload") or {}

                if event.get("type") == "session_meta":
                    meta = payload
                    created_at = parse_timestamp(event.get("timestamp"))
                    model = str(payload.get("model") or model)
                    if cwd_filter and str(meta.get("cwd") or "") != cwd_filter:
                        return None
                    continue

                if event.get("type") == "turn_context":
                    model = str(payload.get("model") or model)
                    continue

                if event.get("type") != "response_item" or payload.get("role") != "user":
                    continue
                content = payload.get("content") or []
                if not content:
                    continue
                text = str((content[0] or {}).get("text") or "")
                if should_skip_user_message(text):
                    continue
                if not first_user_message:
                    first_user_message = text.strip()
    except OSError:
        return None

    thread_id = str(meta.get("id") or "")
    cwd = str(meta.get("cwd") or "")
    if not thread_id or not cwd:
        return None
    if not updated_at:
        updated_at = int(os.path.getmtime(file_path))
    if not created_at:
        created_at = updated_at
    source = str(meta.get("originator") or meta.get("source") or "codex_session_jsonl")
    return {
        "id": thread_id,
        "title": first_user_message or thread_id,
        "model": model,
        "source": source,
        "cwd": cwd,
        "first_user_message": first_user_message,
        "created_at": created_at,
        "updated_at": updated_at,
        "archived": 0,
    }


def list_sqlite_threads(cwd: str | None, limit: int) -> list[dict]:
    conn = get_connection()
    if conn is None:
        return []
    cur = conn.cursor()
    fetch_limit = limit * 3
    params = []
    where_clauses = ["archived = 0"]
    if cwd:
        where_clauses.append("cwd = ?")
        params.append(cwd)
    where = " AND ".join(where_clauses)
    cur.execute(
        f"SELECT {', '.join(COLUMNS)} FROM threads"
        f" WHERE {where}"
        f" ORDER BY updated_at DESC"
        f" LIMIT ?",
        params + [fetch_limit],
    )
    rows = cur.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def list_jsonl_threads(cwd: str | None, limit: int) -> list[dict]:
    threads = []
    for file_path in iter_jsonl_session_files():
        thread = parse_jsonl_session(file_path, cwd)
        if not thread:
            continue
        if cwd and thread.get("cwd") != cwd:
            continue
        threads.append(thread)
        if len(threads) >= limit:
            break
    return threads


def cmd_list(args):
    limit = args.limit or 20
    by_id = {}
    for thread in list_sqlite_threads(args.cwd, limit):
        by_id[thread["id"]] = thread
    for thread in list_jsonl_threads(args.cwd, limit):
        existing = by_id.get(thread["id"])
        if not existing or int(thread.get("updated_at") or 0) >= int(existing.get("updated_at") or 0):
            by_id[thread["id"]] = thread

    threads = []
    for thread in sorted(by_id.values(), key=lambda x: int(x.get("updated_at") or 0), reverse=True):
        if is_subagent(str(thread.get("source") or "")):
            continue
        threads.append(thread)
        if len(threads) >= limit:
            break

    print(json.dumps(threads, ensure_ascii=False))


def get_sqlite_thread(thread_id: str) -> dict | None:
    conn = get_connection()
    if conn is None:
        return None
    cur = conn.cursor()
    cur.execute(
        f"SELECT {', '.join(COLUMNS)} FROM threads WHERE id = ? LIMIT 1",
        (thread_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row_to_dict(row) if row else None


def get_jsonl_thread(thread_id: str) -> dict | None:
    for file_path in iter_jsonl_session_files():
        thread = parse_jsonl_session(file_path)
        if thread and thread.get("id") == thread_id:
            return thread
    return None


def cmd_get(args):
    thread = get_sqlite_thread(args.thread_id) or get_jsonl_thread(args.thread_id)
    print(json.dumps(thread, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Codex CLI session query tool")
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="List threads")
    p_list.add_argument("--cwd", help="Filter by working directory")
    p_list.add_argument("--limit", type=int, default=20, help="Max results (default 20)")

    p_get = sub.add_parser("get", help="Get a single thread")
    p_get.add_argument("thread_id", help="Thread ID")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "get":
        cmd_get(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

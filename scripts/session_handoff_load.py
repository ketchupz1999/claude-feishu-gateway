#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from session_handoff_lib import (
    ACTIVE_STATE,
    dump_json,
    find_context_path,
    guess_scope,
    has_expire_when,
    has_recovery_source,
    is_stale,
    latest_path,
    load_json,
    meta_path,
    normalize_scope,
    now_local,
    parse_latest_sections,
    read_text,
    summarize_context_text,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Load a local session handoff summary.")
    p.add_argument("--scope")
    p.add_argument("--req-id")
    p.add_argument("--query")
    return p


def emit_candidates(candidates: list[dict]) -> None:
    print("scope unresolved; candidates:")
    for row in candidates[:5]:
        ident = row.get("scope") or row.get("req_id") or "N/A"
        parts = [ident, row.get("title"), row.get("status")]
        if row.get("why"):
            parts.append(f"why={row.get('why')}")
        if row.get("updated_at"):
            parts.append(f"updated_at={row.get('updated_at')}")
        print("- " + " | ".join(filter(None, parts)))


def main() -> None:
    args = parser().parse_args()
    if args.scope:
        scope = normalize_scope(args.scope)
        candidates = []
    else:
        scope, candidates = guess_scope(req_id=args.req_id, query=args.query)
        if not scope:
            emit_candidates(candidates)
            raise SystemExit(2)

    if not has_recovery_source(scope, req_id=args.req_id):
        print(f"error: no handoff or project context found for scope={scope}", file=sys.stderr)
        raise SystemExit(2)

    latest_file = latest_path(scope)
    latest_text = read_text(latest_file) if latest_file.exists() else None
    meta_file = meta_path(scope)
    meta = load_json(meta_file)

    req_id = args.req_id or meta.get("req_id")
    context_path = find_context_path(scope, req_id=req_id)
    context_text = read_text(context_path) if context_path and context_path.exists() else ""
    context_lines = summarize_context_text(context_text, max_lines=3)
    stale = is_stale(meta, latest_text or "") if latest_text else False
    expire_note = has_expire_when(latest_text or "")

    if meta_file.exists():
        meta["last_loaded_at"] = now_local().isoformat()
        dump_json(meta_file, meta)

    sections = parse_latest_sections(latest_text) if latest_text else {}

    print(f"scope={scope}")
    sources = []
    if ACTIVE_STATE.exists():
        sources.append(str(ACTIVE_STATE))
    if latest_text:
        sources.append(str(latest_file))
    if context_path:
        sources.append(str(context_path))
    print("sources=" + (" + ".join(sources) if sources else "none"))
    print(f"handoff_stale={'yes' if stale else 'no'}")
    print("")
    print("## 恢复简报")

    current_goal = sections.get("Current Goal")
    if isinstance(current_goal, str) and current_goal:
        print(f"- 当前你在做：{current_goal}")
    elif context_lines:
        print(f"- 当前你在做：{context_lines[0]}")

    done = sections.get("Done")
    if isinstance(done, list) and done:
        print(f"- 上次已完成：{'；'.join(done[:3])}")
    elif len(context_lines) > 1:
        print(f"- 上次已完成：{context_lines[1]}")

    decisions = sections.get("Decisions")
    if isinstance(decisions, list) and decisions:
        print(f"- 仍然生效的决策：{'；'.join(decisions[:3])}")

    risks = sections.get("Risks")
    if isinstance(risks, list) and risks:
        print(f"- 当前风险 / 待确认：{'；'.join(risks[:3])}")

    next_steps = sections.get("Next")
    if isinstance(next_steps, list) and next_steps:
        print(f"- 建议下一步：{'；'.join(next_steps[:3])}")
    elif len(context_lines) > 2:
        print(f"- 建议下一步：{context_lines[2]}")

    related = sections.get("Related Files")
    if isinstance(related, list) and related:
        print(f"- 先看文件：{'、'.join(related[:3])}")
    elif context_path:
        print(f"- 先看文件：`{context_path}`")

    if not latest_text:
        print("- 备注：当前没有短期 handoff，以上结果主要来自项目上下文；本轮结束时建议执行一次 `sh-save`")
    elif stale:
        print("- 备注：当前 handoff 已陈旧，恢复时应先确认是否仍适用")
    elif expire_note:
        print("- 备注：当前 handoff 定义了 `Expire When`，恢复前请人工确认是否已触发")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(1)

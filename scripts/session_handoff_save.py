#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from session_handoff_lib import (
    dump_json,
    handoff_semantics_from_latest,
    history_dir,
    latest_path,
    latest_snapshot_id,
    load_json,
    meta_path,
    normalize_scope,
    now_local,
    project_scope,
    read_text,
    render_history,
    render_latest,
    scope_dir,
    slugify,
    topic_scope,
    normalize_list,
    normalize_scalar,
    update_active_state,
    write_text,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Save a local session handoff snapshot.")
    p.add_argument("--scope")
    p.add_argument("--req-id")
    p.add_argument("--topic")
    p.add_argument("--current-goal")
    p.add_argument("--done", action="append", default=[])
    p.add_argument("--decision", action="append", default=[])
    p.add_argument("--risk", action="append", default=[])
    p.add_argument("--next-step", action="append", default=[])
    p.add_argument("--related-file", action="append", default=[])
    p.add_argument("--expire-when", action="append", default=[])
    p.add_argument("--status", default="active")
    p.add_argument("--set-current", choices=["auto", "yes", "no"], default="auto")
    p.add_argument("--source", default="sh-save")
    p.add_argument("--snapshot-slug", default="update")
    p.add_argument("--change-type", default="status_update")
    p.add_argument("--delta-summary", default="Handoff updated.")
    p.add_argument("--force-history", action="store_true")
    return p


def resolve_scope(args: argparse.Namespace) -> str:
    if args.scope:
        return normalize_scope(args.scope)
    if args.topic:
        return topic_scope(args.topic)
    if args.req_id:
        return project_scope(args.req_id)
    raise SystemExit("error: one of --scope, --topic, or --req-id is required")


def display_path(path: Path) -> Path:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        return Path(os.path.relpath(resolved, Path.cwd().resolve()))


def main() -> None:
    args = parser().parse_args()
    scope = resolve_scope(args)
    now = now_local()
    supersedes = latest_snapshot_id(scope)
    snapshot_id = f"{now.strftime('%Y-%m-%d-%H%M')}-{slugify(args.snapshot_slug)}"

    latest = render_latest(
        scope=scope,
        updated_at=now,
        status=args.status,
        source=args.source,
        supersedes=supersedes,
        current_goal=args.current_goal,
        done=args.done,
        decisions=args.decision,
        risks=args.risk,
        next_steps=args.next_step,
        related_files=args.related_file,
        expire_when=args.expire_when,
    )

    scope_dir(scope).mkdir(parents=True, exist_ok=True)
    old_latest_path = latest_path(scope)
    old_latest = read_text(old_latest_path) if old_latest_path.exists() else ""
    new_semantics = {
        "status": args.status,
        "source": args.source,
        "current_goal": normalize_scalar(args.current_goal),
        "done": normalize_list(args.done),
        "decisions": normalize_list(args.decision),
        "risks": normalize_list(args.risk),
        "next_steps": normalize_list(args.next_step),
        "related_files": normalize_list(args.related_file, strip_code=True, sort_items=True),
        "expire_when": normalize_list(args.expire_when),
    }
    old_semantics = handoff_semantics_from_latest(old_latest) if old_latest else {}
    changed = old_semantics != new_semantics

    write_text(old_latest_path, latest)

    meta = load_json(meta_path(scope))
    history_created = False
    if changed or args.force_history:
        history_created = True
        history_file = history_dir(scope) / f"{snapshot_id}.md"
        write_text(
            history_file,
            render_history(
                scope=scope,
                snapshot_id=snapshot_id,
                created_at=now,
                change_type=args.change_type,
                delta_summary=args.delta_summary,
                current_goal=args.current_goal,
                done=args.done,
                decisions=args.decision,
                risks=args.risk,
                next_steps=args.next_step,
            ),
        )

    meta.update(
        {
            "scope": scope,
            "req_id": args.req_id,
            "status": args.status,
            "latest_snapshot_id": snapshot_id if history_created else meta.get("latest_snapshot_id"),
            "history_count": int(meta.get("history_count", 0)) + (1 if history_created else 0),
            "last_loaded_at": meta.get("last_loaded_at"),
            "last_saved_at": now.isoformat(),
            "rollup_snapshot_id": meta.get("rollup_snapshot_id"),
        }
    )
    dump_json(meta_path(scope), meta)
    update_active_state(
        scope=scope,
        req_id=args.req_id,
        status=args.status,
        current_goal=args.current_goal,
        next_steps=args.next_step,
        set_current=args.set_current,
    )

    print(f"scope={scope}")
    print(f"latest={display_path(old_latest_path)}")
    print(f"changed={'yes' if changed else 'no'}")
    print(f"history_created={'yes' if history_created else 'no'}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(1)

#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import zlib
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT / "knowledge/projects"
HANDOFF_ROOT = ROOT / "memory/session-handoffs"
ACTIVE_STATE = HANDOFF_ROOT / "_active.json"
STALE_DAYS = 7


def now_local() -> datetime:
    return datetime.now().astimezone()


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-") or "update"


def short_hash(text: str) -> str:
    return f"{zlib.crc32(text.encode('utf-8')) & 0xFFFFFFFF:08x}"[:8]


def normalize_scope(text: str) -> str:
    return slugify(text)


def topic_scope(text: str) -> str:
    slug = slugify(text)
    if slug == "update" and text.strip().lower() != "update":
        slug = f"{slug}-{short_hash(text)}"
    return f"ad-hoc_{slug}"


def normalize_query(text: str) -> str:
    return slugify(text).replace("_", "-")


def project_scope(ref: str) -> str:
    query = normalize_query(ref)
    if PROJECT_ROOT.exists():
        for path in sorted(PROJECT_ROOT.iterdir()):
            if path.is_dir() and query in normalize_query(path.name):
                return path.name
    return slugify(ref)


def scope_dir(scope: str) -> Path:
    return HANDOFF_ROOT / scope


def latest_path(scope: str) -> Path:
    return scope_dir(scope) / "latest.md"


def meta_path(scope: str) -> Path:
    return scope_dir(scope) / "meta.json"


def history_dir(scope: str) -> Path:
    return scope_dir(scope) / "history"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(read_text(path))


def dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def latest_exists_for_scope(scope: str | None) -> bool:
    return bool(scope) and latest_path(scope).exists()


def is_active_item(item: dict | None) -> bool:
    return bool(item) and item.get("status") == "active" and latest_exists_for_scope(item.get("scope"))


def choose_current_scope(items: dict) -> str | None:
    active_items = [item for item in items.values() if is_active_item(item)]
    if not active_items:
        return None
    return max(active_items, key=lambda item: item.get("updated_at", "")).get("scope")


def sanitize_active_state(state: dict) -> dict:
    items = state.get("items", {})
    sanitized_items = {}
    for scope, item in items.items():
        if latest_exists_for_scope(scope):
            sanitized_items[scope] = item

    current_scope = state.get("current_scope")
    current_item = sanitized_items.get(current_scope) if isinstance(current_scope, str) else None
    if not is_active_item(current_item):
        current_scope = choose_current_scope(sanitized_items)

    return {
        "current_scope": current_scope,
        "items": sanitized_items,
        "updated_at": state.get("updated_at"),
    }


def load_active_state() -> dict:
    raw = load_json(ACTIVE_STATE) if ACTIVE_STATE.exists() else {"current_scope": None, "items": {}}
    state = sanitize_active_state(raw)
    if state != raw:
        save_active_state(state)
    return state


def save_active_state(data: dict) -> None:
    dump_json(ACTIVE_STATE, data)


def update_active_state(
    *,
    scope: str,
    req_id: str | None,
    status: str,
    current_goal: str | None,
    next_steps: list[str],
    set_current: str,
) -> None:
    state = load_active_state()
    items = state.setdefault("items", {})
    now = now_local().isoformat()
    items[scope] = {
        "scope": scope,
        "req_id": req_id,
        "status": status,
        "updated_at": now,
        "current_goal": current_goal,
        "next_steps": next_steps[:3],
    }

    current_scope = state.get("current_scope")
    current_item = items.get(current_scope) if isinstance(current_scope, str) else None
    should_set_current = False
    if status == "active":
        if set_current == "yes":
            should_set_current = True
        elif set_current == "auto":
            should_set_current = current_scope == scope or not is_active_item(current_item)
        if should_set_current:
            state["current_scope"] = scope
    elif current_scope == scope:
        state["current_scope"] = None

    if not is_active_item(items.get(state.get("current_scope"))):
        state["current_scope"] = choose_current_scope(items)
    state["updated_at"] = now
    save_active_state(state)


def build_handoff_candidate(scope: str, state: dict, *, fallback_status: str) -> dict:
    item = state.get("items", {}).get(scope, {})
    status = item.get("status") or fallback_status
    why = "matched handoff scope"
    if scope == state.get("current_scope"):
        status = f"{status} current"
        why = "current active handoff"
    elif item.get("status") == "active":
        why = "active handoff"
    return {
        "title": item.get("current_goal") or scope,
        "status": status,
        "ref": str(scope_dir(scope).relative_to(ROOT)),
        "req_id": item.get("req_id"),
        "scope": scope,
        "updated_at": item.get("updated_at"),
        "why": why,
    }


def sort_candidates(candidates: list[dict], state: dict) -> list[dict]:
    current_scope = state.get("current_scope")

    def key(row: dict) -> tuple:
        timestamp = 0
        if row.get("updated_at"):
            try:
                timestamp = int(datetime.fromisoformat(row["updated_at"]).timestamp())
            except ValueError:
                timestamp = 0
        return (
            0 if row.get("scope") == current_scope else 1,
            0 if "active" in row.get("status", "") else 1,
            -timestamp,
            row.get("title", ""),
        )

    return sorted(candidates, key=key)


def default_candidates(state: dict) -> list[dict]:
    candidates = []
    seen: set[str] = set()
    for item in state.get("items", {}).values():
        scope = item.get("scope")
        if not scope or scope in seen or not latest_path(scope).exists():
            continue
        seen.add(scope)
        candidates.append(build_handoff_candidate(scope, state, fallback_status="handoff-index"))

    if HANDOFF_ROOT.exists():
        for path in sorted(HANDOFF_ROOT.iterdir()):
            if not path.is_dir() or path.name in seen or not latest_path(path.name).exists():
                continue
            seen.add(path.name)
            candidates.append(build_handoff_candidate(path.name, state, fallback_status="handoff-only"))

    return sort_candidates(candidates, state)


def guess_scope(req_id: str | None = None, query: str | None = None) -> tuple[str | None, list[dict]]:
    if req_id:
        return project_scope(req_id), []

    state = load_active_state()
    if not query:
        current_scope = state.get("current_scope")
        if isinstance(current_scope, str) and is_active_item(state.get("items", {}).get(current_scope)):
            return current_scope, [build_handoff_candidate(current_scope, state, fallback_status="current")]
        return None, default_candidates(state)

    q = normalize_query(query)
    matches: list[dict] = []
    for candidate in default_candidates(state):
        haystack = " ".join(
            filter(
                None,
                [
                    candidate.get("scope"),
                    candidate.get("title"),
                    candidate.get("status"),
                    candidate.get("req_id"),
                    candidate.get("ref"),
                ],
            )
        )
        if q in normalize_query(haystack):
            matches.append(candidate)

    if PROJECT_ROOT.exists():
        for path in sorted(PROJECT_ROOT.iterdir()):
            if not path.is_dir() or q not in normalize_query(path.name):
                continue
            matches.append(
                {
                    "title": path.name,
                    "status": "project-context",
                    "ref": str(path.relative_to(ROOT)),
                    "req_id": None,
                    "scope": path.name,
                    "updated_at": None,
                    "why": "matched project context",
                }
            )

    unique = {}
    for item in matches:
        scope = item.get("scope")
        if scope and scope not in unique:
            unique[scope] = item
    candidates = sort_candidates(list(unique.values()), state)
    if len(candidates) == 1:
        return candidates[0].get("scope"), candidates
    return None, candidates


def latest_snapshot_id(scope: str) -> str | None:
    meta = load_json(meta_path(scope))
    value = meta.get("latest_snapshot_id")
    return value if isinstance(value, str) and value else None


def render_latest(
    *,
    scope: str,
    updated_at: datetime,
    status: str,
    source: str,
    supersedes: str | None,
    current_goal: str | None,
    done: list[str],
    decisions: list[str],
    risks: list[str],
    next_steps: list[str],
    related_files: list[str],
    expire_when: list[str],
) -> str:
    lines = [
        "# Session Handoff",
        "",
        f"> scope: {scope}",
        f"> updated_at: {updated_at.strftime('%Y-%m-%d %H:%M %z')}",
        f"> status: {status}",
        f"> source: {source}",
        f"> supersedes: {supersedes or 'none'}",
        "",
    ]
    if current_goal:
        lines.extend(["## Current Goal", current_goal.strip(), ""])
    if done:
        lines.extend(["## Done", *[f"- {item}" for item in done], ""])
    if decisions:
        lines.extend(["## Decisions", *[f"- {item}" for item in decisions], ""])
    if risks:
        lines.extend(["## Risks", *[f"- {item}" for item in risks], ""])
    if next_steps:
        lines.extend(["## Next", *[f"- {item}" for item in next_steps], ""])
    if related_files:
        lines.extend(["## Related Files", *[f"- `{item}`" for item in related_files], ""])
    if expire_when:
        lines.extend(["## Expire When", *[f"- {item}" for item in expire_when], ""])
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def render_history(
    *,
    scope: str,
    snapshot_id: str,
    created_at: datetime,
    change_type: str,
    delta_summary: str,
    current_goal: str | None,
    done: list[str],
    decisions: list[str],
    risks: list[str],
    next_steps: list[str],
) -> str:
    lines = [
        "# Handoff Snapshot",
        "",
        f"> snapshot_id: {snapshot_id}",
        f"> scope: {scope}",
        f"> created_at: {created_at.strftime('%Y-%m-%d %H:%M %z')}",
        f"> change_type: {change_type}",
        "",
        "## Delta Summary",
        delta_summary.strip(),
        "",
    ]
    if current_goal:
        lines.extend(["## Current Goal", current_goal.strip(), ""])
    if done:
        lines.extend(["## Done", *[f"- {item}" for item in done], ""])
    if decisions:
        lines.extend(["## Decisions", *[f"- {item}" for item in decisions], ""])
    if risks:
        lines.extend(["## Risks", *[f"- {item}" for item in risks], ""])
    if next_steps:
        lines.extend(["## Next", *[f"- {item}" for item in next_steps], ""])
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def parse_latest_sections(text: str) -> dict[str, list[str] | str]:
    sections: dict[str, list[str] | str] = {}
    current = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
            continue
        if current is None or not line:
            continue
        if line.startswith("- "):
            cast = sections[current]
            assert isinstance(cast, list)
            cast.append(line[2:].strip())
        else:
            cast = sections[current]
            if isinstance(cast, list) and not cast:
                sections[current] = line.strip()
    return sections


def normalize_scalar(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip()


def normalize_list(values: list[str] | str | None, *, strip_code: bool = False, sort_items: bool = False) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]

    normalized = []
    for value in values:
        item = value.strip()
        if strip_code and item.startswith("`") and item.endswith("`"):
            item = item[1:-1].strip()
        normalized.append(item)
    if sort_items:
        normalized.sort()
    return normalized


def handoff_semantics_from_latest(text: str) -> dict:
    sections = parse_latest_sections(text)
    status_match = re.search(r"^> status: (.+)$", text, re.MULTILINE)
    source_match = re.search(r"^> source: (.+)$", text, re.MULTILINE)
    return {
        "status": status_match.group(1).strip() if status_match else "active",
        "source": source_match.group(1).strip() if source_match else "sh-save",
        "current_goal": normalize_scalar(sections.get("Current Goal")) if isinstance(sections.get("Current Goal"), str) else None,
        "done": normalize_list(sections.get("Done")) if isinstance(sections.get("Done"), list) else [],
        "decisions": normalize_list(sections.get("Decisions")) if isinstance(sections.get("Decisions"), list) else [],
        "risks": normalize_list(sections.get("Risks")) if isinstance(sections.get("Risks"), list) else [],
        "next_steps": normalize_list(sections.get("Next")) if isinstance(sections.get("Next"), list) else [],
        "related_files": normalize_list(sections.get("Related Files"), strip_code=True, sort_items=True)
        if isinstance(sections.get("Related Files"), list)
        else [],
        "expire_when": normalize_list(sections.get("Expire When")) if isinstance(sections.get("Expire When"), list) else [],
    }


def has_expire_when(latest_text: str) -> bool:
    sections = parse_latest_sections(latest_text)
    expire = sections.get("Expire When")
    return isinstance(expire, list) and bool(expire)


def is_stale(meta: dict, latest_text: str) -> bool:
    ts = meta.get("last_saved_at")
    if isinstance(ts, str):
        try:
            if datetime.fromisoformat(ts) < now_local() - timedelta(days=STALE_DAYS):
                return True
        except ValueError:
            pass
    status_match = re.search(r"^> status: (.+)$", latest_text, re.MULTILINE)
    return bool(status_match and status_match.group(1).strip() != "active")


def find_context_path(scope: str, req_id: str | None = None) -> Path | None:
    candidates = []
    if req_id:
        q = normalize_query(req_id)
        candidates.extend(path for path in PROJECT_ROOT.glob("*") if path.is_dir() and q in normalize_query(path.name))

    direct_scope = scope[7:] if scope.startswith("ad-hoc_") else scope
    direct = PROJECT_ROOT / direct_scope
    if direct.is_dir():
        candidates.insert(0, direct)

    for project in candidates:
        for name in ("CONTEXT.md", "README.md"):
            path = project / name
            if path.exists():
                return path
    return None


def has_recovery_source(scope: str, req_id: str | None = None) -> bool:
    return latest_path(scope).exists() or find_context_path(scope, req_id=req_id) is not None


def summarize_context_text(text: str, max_lines: int = 3) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(">"):
            continue
        if line.startswith("- ") or line.startswith("* "):
            lines.append(line[2:].strip())
        elif len(line) <= 100:
            lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines

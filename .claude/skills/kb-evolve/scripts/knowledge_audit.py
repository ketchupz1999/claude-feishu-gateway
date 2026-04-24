#!/usr/bin/env python3
"""
知识库健康审计脚本 — 采集 memory/todo/agent-memory/daemon-logs/code-todos 指标
输出 JSON 供 kb-evolve skill 消费
"""

import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[4]  # .claude/skills/kb-evolve/scripts/ → root
MEMORY_DIR = WORKSPACE / "memory"
TODO_DIR = WORKSPACE / "todo"
AGENT_MEMORY_DIR = WORKSPACE / ".claude" / "agent-memory"
LOG_DIR = WORKSPACE / "data" / "logs"
SKILLS_DIR = WORKSPACE / ".claude" / "skills"
COMPONENTS_DIR = WORKSPACE / "components"


def check_memory_long():
    """memory/long/* 每个文件的 age、size、lines"""
    long_dir = MEMORY_DIR / "long"
    if not long_dir.exists():
        return []
    now = time.time()
    results = []
    for f in sorted(long_dir.iterdir()):
        if not f.is_file():
            continue
        stat = f.stat()
        results.append({
            "file": f.name,
            "age_days": int((now - stat.st_mtime) / 86400),
            "size": stat.st_size,
            "lines": len(f.read_text(errors="ignore").splitlines()),
        })
    return results


def check_memory_scratch():
    """memory/scratch/* 文件列表 + 超 7 天标记"""
    scratch_dir = MEMORY_DIR / "scratch"
    if not scratch_dir.exists():
        return {"total": 0, "stale_7d": []}
    now = time.time()
    seven_days = 7 * 86400
    files = [f for f in scratch_dir.iterdir() if f.is_file()]
    stale = []
    for f in files:
        age = now - f.stat().st_mtime
        if age > seven_days:
            stale.append({
                "file": f.name,
                "age_days": int(age / 86400),
            })
    return {
        "total": len(files),
        "stale_7d": sorted(stale, key=lambda x: -x["age_days"]),
    }


def check_agent_memory():
    """各 agent 的 MEMORY.md 行数、最后修改天数"""
    if not AGENT_MEMORY_DIR.exists():
        return []
    now = time.time()
    results = []
    for agent_dir in sorted(AGENT_MEMORY_DIR.iterdir()):
        if not agent_dir.is_dir():
            continue
        mem_file = agent_dir / "MEMORY.md"
        if not mem_file.exists():
            results.append({
                "agent": agent_dir.name,
                "lines": 0,
                "last_modified_days": -1,
                "has_memory": False,
            })
            continue
        stat = mem_file.stat()
        results.append({
            "agent": agent_dir.name,
            "lines": len(mem_file.read_text(errors="ignore").splitlines()),
            "last_modified_days": int((now - stat.st_mtime) / 86400),
            "has_memory": True,
        })
    return results


def check_todo(filename):
    """检查 todo 文件: done/open 数量 + 超 2 周未动项估算"""
    path = TODO_DIR / filename
    if not path.exists():
        return {"error": "not found"}
    text = path.read_text(errors="ignore")
    lines = text.splitlines()
    done_count = sum(1 for l in lines if "- [x]" in l.lower())
    open_count = sum(1 for l in lines if "- [ ]" in l)

    now = datetime.now(timezone.utc)
    stale_2w = 0
    date_pattern = re.compile(r"20\d{2}[-/]\d{2}[-/]\d{2}")
    for line in lines:
        if "- [ ]" not in line:
            continue
        dates = date_pattern.findall(line)
        if dates:
            try:
                latest = max(datetime.strptime(d.replace("/", "-"), "%Y-%m-%d").replace(tzinfo=timezone.utc) for d in dates)
                if (now - latest).days > 14:
                    stale_2w += 1
            except ValueError:
                pass

    return {
        "done_count": done_count,
        "open_count": open_count,
        "stale_2w": stale_2w,
    }


def check_error_patterns(days=7):
    """最近 N 天 daemon 日志中的 ERROR/FAIL 模式聚合"""
    if not LOG_DIR.exists():
        return []
    now = datetime.now(timezone.utc)
    pattern_counter = Counter()
    last_seen = {}

    for d in range(days):
        date = now - timedelta(days=d)
        date_str = date.strftime("%Y-%m-%d")
        log_file = LOG_DIR / f"{date_str}-daemon.log"
        if not log_file.exists():
            continue
        for line in log_file.read_text(errors="ignore").splitlines():
            if "FAIL" in line or "ERROR" in line:
                cleaned = re.sub(r"\[.*?\]", "", line).strip()
                normalized = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", cleaned)
                normalized = re.sub(r"\d+\.\d+", "N", normalized)
                pattern_counter[normalized] += 1
                last_seen[normalized] = date_str

    results = []
    for pattern, count in pattern_counter.most_common(20):
        results.append({
            "pattern": pattern[:200],
            "count": count,
            "last_seen": last_seen.get(pattern, "unknown"),
        })
    return results


def check_code_todos():
    """扫描 .claude/skills/ 和 components/ 中的 TODO/FIXME/HACK 注释"""
    results = []
    dirs_to_scan = [SKILLS_DIR, COMPONENTS_DIR]

    for scan_dir in dirs_to_scan:
        if not scan_dir.exists():
            continue
        try:
            proc = subprocess.run(
                ["grep", "-rn", r"#\s*TODO\|#\s*FIXME\|#\s*HACK\|//\s*TODO\|//\s*FIXME\|//\s*HACK",
                 "--include=*.py", "--include=*.sh",
                 "--exclude-dir=kb-evolve",
                 str(scan_dir)],
                capture_output=True, text=True, timeout=10,
            )
            for line in proc.stdout.splitlines()[:50]:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    filepath = parts[0]
                    try:
                        rel = str(Path(filepath).relative_to(WORKSPACE))
                    except ValueError:
                        rel = filepath
                    results.append({
                        "file": rel,
                        "line": int(parts[1]) if parts[1].isdigit() else 0,
                        "text": parts[2].strip()[:150],
                    })
        except (subprocess.TimeoutExpired, Exception):
            pass

    return results[:50]


def check_previous_reports():
    """读取之前的 kb-evolve 报告"""
    scratch_dir = MEMORY_DIR / "scratch"
    if not scratch_dir.exists():
        return []
    reports = []
    for f in sorted(scratch_dir.glob("*kb-evolve*.md")):
        reports.append({
            "file": f.name,
            "date": f.name[:8] if len(f.name) >= 8 else "unknown",
            "size_bytes": f.stat().st_size,
        })
    return reports


def main():
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "memory_long": check_memory_long(),
        "memory_scratch": check_memory_scratch(),
        "agent_memory": check_agent_memory(),
        "todo_inbox": check_todo("inbox.md"),
        "todo_backlog": check_todo("backlog.md"),
        "error_patterns": check_error_patterns(),
        "code_todos": check_code_todos(),
        "previous_reports": check_previous_reports(),
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

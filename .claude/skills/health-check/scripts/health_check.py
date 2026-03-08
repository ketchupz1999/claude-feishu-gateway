#!/usr/bin/env python3
"""
系统健康检查脚本 — 自动收集系统状态指标
输出 JSON 格式的健康报告，供 health-check skill 消费
"""

import json
import os
import sys
import glob
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter

WORKSPACE = Path(__file__).resolve().parents[4]  # .claude/skills/health-check/scripts/ → workspace root
DATA_DIR = WORKSPACE / "data"
SKILLS_DIR = WORKSPACE / ".claude" / "skills"
MEMORY_DIR = WORKSPACE / "memory"
TODO_DIR = WORKSPACE / "todo"
LOG_DIR = DATA_DIR / "logs"


def check_skills():
    """检查 skills 目录完整性"""
    results = []
    if not SKILLS_DIR.exists():
        return results
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith('.'):
            continue
        if skill_dir.name == 'common' or skill_dir.name.endswith('-workspace'):
            continue
        skill_md = skill_dir / "SKILL.md"
        has_scripts = (skill_dir / "scripts").is_dir()
        has_refs = (skill_dir / "references").is_dir()
        has_evals = (skill_dir / "evals").is_dir()
        results.append({
            "name": skill_dir.name,
            "has_skill_md": skill_md.exists(),
            "has_scripts": has_scripts,
            "has_references": has_refs,
            "has_evals": has_evals,
            "lines": len(skill_md.read_text().splitlines()) if skill_md.exists() else 0,
        })
    return results


def check_memory():
    """检查 memory 健康度"""
    scratch_dir = MEMORY_DIR / "scratch"
    long_dir = MEMORY_DIR / "long"
    now = time.time()
    seven_days_ago = now - 7 * 86400

    stale_scratch = []
    if scratch_dir.exists():
        for f in scratch_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < seven_days_ago:
                age_days = int((now - f.stat().st_mtime) / 86400)
                stale_scratch.append({"file": f.name, "age_days": age_days})

    long_files = []
    if long_dir.exists():
        for f in long_dir.iterdir():
            if f.is_file():
                age_days = int((now - f.stat().st_mtime) / 86400)
                long_files.append({
                    "file": f.name,
                    "age_days": age_days,
                    "size_bytes": f.stat().st_size,
                })

    scratch_count = len(list(scratch_dir.iterdir())) if scratch_dir.exists() else 0

    return {
        "scratch_count": scratch_count,
        "stale_scratch": stale_scratch,
        "long_files": long_files,
    }


def check_logs(days=3):
    """分析最近 N 天的 daemon 日志"""
    if not LOG_DIR.exists():
        return {"error": "log dir not found"}

    now = datetime.now(timezone.utc)
    stats = Counter()
    errors = []

    for d in range(days):
        date = now - timedelta(days=d)
        date_str = date.strftime("%Y-%m-%d")
        log_file = LOG_DIR / f"{date_str}-daemon.log"
        if not log_file.exists():
            continue

        for line in log_file.read_text(errors='ignore').splitlines():
            if "SUCCESS" in line or "✓" in line or "DONE" in line:
                stats["success"] += 1
            elif "FAIL" in line or "ERROR" in line or "error" in line.lower():
                stats["fail"] += 1
                if len(errors) < 10:
                    errors.append(line.strip()[:200])
            elif "TIMEOUT" in line:
                stats["timeout"] += 1

    total = stats["success"] + stats["fail"] + stats["timeout"]
    return {
        "days_checked": days,
        "total_tasks": total,
        "success": stats["success"],
        "fail": stats["fail"],
        "timeout": stats["timeout"],
        "success_rate": f"{stats['success']/total*100:.1f}%" if total > 0 else "N/A",
        "recent_errors": errors,
    }


def check_todo():
    """检查 todo 状态"""
    results = {}
    for name in ("inbox.md", "backlog.md"):
        path = TODO_DIR / name
        if not path.exists():
            results[name] = {"error": "file not found"}
            continue

        text = path.read_text()
        lines = text.splitlines()
        done = sum(1 for l in lines if "- [x]" in l)
        open_items = sum(1 for l in lines if "- [ ]" in l)
        results[name] = {
            "total_lines": len(lines),
            "done": done,
            "open": open_items,
        }
    return results


def check_data_freshness():
    """检查关键数据目录的新鲜度"""
    results = {}
    now = time.time()

    if not DATA_DIR.exists():
        return results

    for dirpath in sorted(DATA_DIR.iterdir()):
        if not dirpath.is_dir() or dirpath.name.startswith('.'):
            continue

        files = [f for f in dirpath.iterdir() if f.is_file()]
        if not files:
            results[dirpath.name] = {"exists": True, "file_count": 0}
            continue

        newest = max(f.stat().st_mtime for f in files)
        results[dirpath.name] = {
            "exists": True,
            "file_count": len(files),
            "newest_age_hours": round((now - newest) / 3600, 1),
        }
    return results


def check_previous_reports():
    """读取之前的自检报告，提取趋势数据"""
    scratch_dir = MEMORY_DIR / "scratch"
    if not scratch_dir.exists():
        return []

    reports = []
    for f in sorted(scratch_dir.glob("*health-check*.md")):
        reports.append({
            "file": f.name,
            "date": f.name[:8] if len(f.name) >= 8 else "unknown",
            "size_bytes": f.stat().st_size,
        })
    return reports


def main():
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace": str(WORKSPACE),
        "skills": check_skills(),
        "memory": check_memory(),
        "logs": check_logs(),
        "todo": check_todo(),
        "data_freshness": check_data_freshness(),
        "previous_reports": check_previous_reports(),
    }

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

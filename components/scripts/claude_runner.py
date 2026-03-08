#!/usr/bin/env python3
"""
Claude CLI 调用封装 — 错误分类 + 选择性重试 + 熔断机制 + Token 追踪

退出码：
  0 = 成功
  1 = 重试后仍失败（网络/瞬时错误）
  2 = 额度耗尽，已触发熔断
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")

os.environ.pop("CLAUDECODE", None)
CIRCUIT_BREAKER_FILE = os.path.join(WORKSPACE, "data", ".circuit_breaker")
TASK_STATS_FILE = os.path.join(WORKSPACE, "data", "logs", "task_stats.jsonl")

QUOTA_PATTERNS = [
    re.compile(r"credit.*balance", re.IGNORECASE),
    re.compile(r"credit.*low", re.IGNORECASE),
    re.compile(r"insufficient.*credit", re.IGNORECASE),
    re.compile(r"quota.*exceeded", re.IGNORECASE),
    re.compile(r"billing", re.IGNORECASE),
    re.compile(r"payment.*required", re.IGNORECASE),
    re.compile(r"plan.*limit", re.IGNORECASE),
]

RETRYABLE_PATTERNS = [
    re.compile(r"api_error", re.IGNORECASE),
    re.compile(r"internal.server.error", re.IGNORECASE),
    re.compile(r"overloaded", re.IGNORECASE),
    re.compile(r"529", re.IGNORECASE),
    re.compile(r"connection.*(?:reset|refused|timeout)", re.IGNORECASE),
    re.compile(r"ETIMEDOUT|ECONNRESET|ECONNREFUSED", re.IGNORECASE),
]

MAX_RETRIES = 3
INITIAL_WAIT = 15


def log(msg: str, logfile: str | None = None):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if logfile:
        with open(logfile, "a") as f:
            f.write(line + "\n")


def classify_error(stderr: str, stdout: str) -> str:
    combined = stderr + "\n" + stdout
    for pat in QUOTA_PATTERNS:
        if pat.search(combined):
            return "quota"
    for pat in RETRYABLE_PATTERNS:
        if pat.search(combined):
            return "retryable"
    return "unknown"


def trigger_circuit_breaker(desc: str, logfile: str | None):
    os.makedirs(os.path.dirname(CIRCUIT_BREAKER_FILE), exist_ok=True)
    with open(CIRCUIT_BREAKER_FILE, "w") as f:
        f.write(str(int(time.time())))
    log(f"CIRCUIT BREAK: {desc} — 额度耗尽，写入熔断文件", logfile)


def _write_task_stat(desc: str, model: str, status: str, duration_sec: float,
                     tokens_in: int = 0, tokens_out: int = 0):
    try:
        os.makedirs(os.path.dirname(TASK_STATS_FILE), exist_ok=True)
        record = {
            "task": desc, "model": model,
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "duration_sec": round(duration_sec, 1), "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(TASK_STATS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _parse_token_usage(stdout: str) -> tuple[int, int]:
    tokens_in = tokens_out = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            usage = obj.get("usage", {})
            if usage:
                tokens_in += usage.get("input_tokens", 0)
                tokens_out += usage.get("output_tokens", 0)
            result = obj.get("result", {})
            if isinstance(result, dict):
                r_usage = result.get("usage", {})
                if r_usage:
                    tokens_in += r_usage.get("input_tokens", 0)
                    tokens_out += r_usage.get("output_tokens", 0)
        except (json.JSONDecodeError, AttributeError):
            continue
    return tokens_in, tokens_out


def run_claude(desc: str, prompt: str, model: str, logfile: str | None) -> int:
    wait_sec = INITIAL_WAIT
    start_time = time.time()

    for attempt in range(1, MAX_RETRIES + 1):
        log(f"START: {desc} (model={model}, attempt={attempt}/{MAX_RETRIES})", logfile)
        attempt_start = time.time()

        try:
            result = subprocess.run(
                [CLAUDE_BIN, "--dangerously-skip-permissions", "--model", model,
                 "--output-format", "json", "-p", prompt],
                cwd=WORKSPACE,
                capture_output=True, text=True, timeout=600,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - attempt_start
            log(f"TIMEOUT: {desc} (>600s)", logfile)
            _write_task_stat(desc, model, "timeout", duration)
            return 1

        duration = time.time() - attempt_start

        if result.returncode == 0:
            tokens_in, tokens_out = _parse_token_usage(result.stdout)
            if logfile and result.stdout:
                with open(logfile, "a") as f:
                    f.write(result.stdout)
            log(f"DONE: {desc} (tokens: {tokens_in}in/{tokens_out}out, {duration:.0f}s)", logfile)
            _write_task_stat(desc, model, "ok", duration, tokens_in, tokens_out)
            return 0

        stderr = result.stderr or ""
        stdout = result.stdout or ""

        if logfile:
            with open(logfile, "a") as f:
                if stdout:
                    f.write(stdout)
                if stderr:
                    f.write(f"\n--- STDERR ---\n{stderr}\n")

        error_type = classify_error(stderr, stdout)

        if error_type == "quota":
            log(f"QUOTA EXHAUSTED: {desc}", logfile)
            _write_task_stat(desc, model, "quota", duration)
            trigger_circuit_breaker(desc, logfile)
            return 2

        if error_type == "retryable" and attempt < MAX_RETRIES:
            log(f"RETRY: {desc} (attempt {attempt}/{MAX_RETRIES}, wait {wait_sec}s)", logfile)
            time.sleep(wait_sec)
            wait_sec *= 2
            continue

        if error_type == "retryable":
            log(f"FAIL: {desc} (all {MAX_RETRIES} retries exhausted)", logfile)
        else:
            log(f"FAIL: {desc} (unknown error, exit={result.returncode})", logfile)
        total_duration = time.time() - start_time
        _write_task_stat(desc, model, "error", total_duration)
        return 1

    total_duration = time.time() - start_time
    _write_task_stat(desc, model, "error", total_duration)
    return 1


def main():
    parser = argparse.ArgumentParser(description="Claude CLI runner with retry and circuit breaker")
    parser.add_argument("--desc", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--logfile", default=None)
    args = parser.parse_args()
    sys.exit(run_claude(args.desc, args.prompt, args.model, args.logfile))


if __name__ == "__main__":
    main()

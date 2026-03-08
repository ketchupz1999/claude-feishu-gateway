#!/usr/bin/env python3
"""
定时调度 daemon — 定期触发 Claude Code skill

用法:
    python3 components/daemon/daemon.py              # 前台运行
    nohup python3 components/daemon/daemon.py &      # 后台运行
    python3 components/daemon/daemon.py --once check # 单次执行（调试用）

调度规则在 SCHEDULE 中定义，格式类似 cron。
运行在用户 shell 环境中，Claude CLI auth 天然可用。
"""
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIPELINE = os.path.join(WORKSPACE, "components", "scripts", "pipeline.sh")
LOGDIR = os.path.join(WORKSPACE, "data", "logs")
PIDFILE = os.path.join(WORKSPACE, "data", "daemon.pid")
CIRCUIT_BREAKER_FILE = os.path.join(WORKSPACE, "data", ".circuit_breaker")
CIRCUIT_BREAKER_DURATION = 3600  # 熔断 1 小时后自动恢复
MAX_CONSECUTIVE_FAIL = 3  # 同一 mode 连续失败 N 次后冷却
COOLDOWN_SECONDS = 600  # 冷却 10 分钟

# ===== 调度规则 =====
# (名称, pipeline参数, 小时列表, 分钟列表, 星期几列表)
# 星期: 0=周日, 1-5=周一至周五, 6=周六, None=每天
#
# 注意: 所有小时均为 **UTC**
#
# 自定义：按需添加你自己的调度规则
SCHEDULE = [
    # 系统自检: 每周日 19:00 UTC
    ("系统自检", "evolve", [19], [0], [0]),
    # 知识进化: 每周四 19:00 UTC
    ("知识进化", "knowledge", [19], [0], [4]),
    # 示例: 每天 00:00 UTC 执行某个 skill
    # ("每日任务", "daily-task", [0], [0], None),
]


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    line = f"[{ts}] [daemon] {msg}"
    print(line, flush=True)
    os.makedirs(LOGDIR, exist_ok=True)
    logfile = os.path.join(LOGDIR, f"{datetime.now(timezone.utc):%Y-%m-%d}-daemon.log")
    with open(logfile, "a") as f:
        f.write(line + "\n")


def should_run(hours: list, minutes: list, weekdays: list | None, now: datetime) -> bool:
    if weekdays is not None and now.weekday() not in [
        (d - 1) % 7 for d in weekdays
    ]:
        return False
    return now.hour in hours and now.minute in minutes


def is_circuit_open() -> bool:
    """检查是否处于熔断状态（额度耗尽）"""
    if not os.path.exists(CIRCUIT_BREAKER_FILE):
        return False
    try:
        with open(CIRCUIT_BREAKER_FILE) as f:
            ts = float(f.read().strip())
        elapsed = time.time() - ts
        if elapsed > CIRCUIT_BREAKER_DURATION:
            os.remove(CIRCUIT_BREAKER_FILE)
            log("熔断器自动恢复（已过 1 小时）")
            return False
        return True
    except (ValueError, OSError):
        return False


# 连续失败跟踪: {mode: {"count": int, "cooldown_until": float}}
_failure_tracker: dict[str, dict] = {}


def is_cooled_down(mode: str) -> bool:
    """检查某个 mode 是否在冷却期"""
    info = _failure_tracker.get(mode)
    if not info:
        return False
    until = info.get("cooldown_until", 0)
    if until and time.time() < until:
        return True
    if until and time.time() >= until:
        _failure_tracker.pop(mode, None)
        log(f"冷却结束: {mode}，恢复调度")
    return False


def run_pipeline(mode: str) -> int:
    """运行 pipeline，返回退出码。0=成功, 1=失败, 2=熔断"""
    if is_circuit_open():
        log(f"SKIP: pipeline.sh {mode} — 熔断中（额度耗尽）")
        return 2

    if is_cooled_down(mode):
        remaining = int(_failure_tracker[mode]["cooldown_until"] - time.time())
        log(f"SKIP: pipeline.sh {mode} — 冷却中（剩余 {remaining}s）")
        return 1

    log(f"START: pipeline.sh {mode}")
    try:
        result = subprocess.run(
            [PIPELINE, mode],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if result.returncode == 0:
            log(f"DONE: pipeline.sh {mode}")
            _failure_tracker.pop(mode, None)
            return 0

        info = _failure_tracker.setdefault(mode, {"count": 0})
        info["count"] += 1

        if result.returncode == 2:
            log(f"CIRCUIT BREAK: pipeline.sh {mode} — 额度耗尽")
            return 2

        stderr = result.stderr.strip()[-200:] if result.stderr else ""
        log(f"FAIL: pipeline.sh {mode} (exit={result.returncode}) {stderr}")

        if info["count"] >= MAX_CONSECUTIVE_FAIL:
            info["cooldown_until"] = time.time() + COOLDOWN_SECONDS
            log(f"COOLDOWN: {mode} 连续失败 {info['count']} 次，冷却 {COOLDOWN_SECONDS // 60}min")

        return result.returncode
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT: pipeline.sh {mode} (>900s)")
        return 1
    except Exception as e:
        log(f"ERROR: pipeline.sh {mode}: {e}")
        return 1


def write_pid():
    os.makedirs(os.path.dirname(PIDFILE), exist_ok=True)
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))


def cleanup(*_):
    log("收到终止信号，退出")
    if os.path.exists(PIDFILE):
        os.remove(PIDFILE)
    sys.exit(0)


def main():
    # --once 模式：单次执行后退出
    if len(sys.argv) >= 3 and sys.argv[1] == "--once":
        run_pipeline(sys.argv[2])
        return

    # 检查是否已有实例在运行
    if os.path.exists(PIDFILE):
        with open(PIDFILE) as f:
            old_pid = f.read().strip()
        try:
            os.kill(int(old_pid), 0)
            print(f"ERROR: daemon 已在运行 (PID={old_pid})，先 kill {old_pid} 或删除 {PIDFILE}", file=sys.stderr)
            sys.exit(1)
        except (OSError, ValueError):
            pass

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    write_pid()

    log(f"daemon 启动 (PID={os.getpid()})")
    log(f"调度规则: {len(SCHEDULE)} 条")
    for name, mode, hours, minutes, weekdays in SCHEDULE:
        wd = "每天" if weekdays is None else f"星期{weekdays}"
        log(f"  - {name}: {mode} @ {hours}h {minutes}min {wd}")

    executed = set()

    while True:
        now = datetime.now(timezone.utc)
        current_key = now.strftime("%Y%m%d%H%M")

        for name, mode, hours, minutes, weekdays in SCHEDULE:
            task_key = f"{current_key}:{name}"
            if task_key in executed:
                continue
            if should_run(hours, minutes, weekdays, now):
                executed.add(task_key)
                log(f"触发: {name}")
                run_pipeline(mode)

        # 清理过期记录（保留最近 2 小时）
        cutoff = now.strftime("%Y%m%d") + f"{max(0, now.hour - 2):02d}"
        executed = {k for k in executed if k[:12] >= cutoff}

        # 每 30 秒检查一次
        time.sleep(30)


if __name__ == "__main__":
    main()

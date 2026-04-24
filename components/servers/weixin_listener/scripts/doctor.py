#!/usr/bin/env python3
"""Weixin listener config doctor."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    yaml = None


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    output = (proc.stdout or proc.stderr).strip()
    return proc.returncode, output


def check_node_version(workspace: Path) -> None:
    code, output = run(
        [
            "node",
            "-e",
            "const major=parseInt(process.versions.node.split('.')[0],10);"
            "if(Number.isNaN(major)||major<22){process.exit(1)};"
            "console.log(process.versions.node)"
        ],
        workspace,
    )
    if code == 0:
        print(f"OK: Node version {output} satisfies >=22")
    else:
        print("WARN: Node >=22 is required for weixin listener")


def check_vendor_metadata(listener_dir: Path) -> None:
    license_file = listener_dir / "vendor" / "weixin-agent-sdk" / "LICENSE"
    source_file = listener_dir / "vendor" / "weixin-agent-sdk" / "SOURCE.md"
    if license_file.exists():
        print("OK: vendored SDK license file exists")
    else:
        print("WARN: vendored SDK license file is missing")
    if source_file.exists():
        print("OK: vendored SDK source note exists")
    else:
        print("WARN: vendored SDK source note is missing")


def check_git_isolation(workspace: Path, state_dir: str) -> None:
    tracked_targets = [
        "components/config.yaml",
        "data/weixin_state",
        "data/weixin_state/openclaw-weixin",
        "accounts.json",
    ]
    code, tracked = run(["git", "ls-files", *tracked_targets], workspace)
    if code == 0 and not tracked:
        print("OK: config/state files are not tracked by git")
    else:
        print(f"WARN: git tracks unexpected config/state paths: {tracked or '(unknown)'}")

    if state_dir:
        rel = os.path.relpath(state_dir, workspace)
        code, ignored = run(["git", "status", "--ignored", "--short", "--", rel], workspace)
        if code == 0 and ignored:
            print(f"OK: git ignore covers {rel}")
        else:
            print(f"WARN: git ignore status is unclear for {rel}")


def main() -> int:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
    listener_dir = workspace / "components" / "servers" / "weixin_listener"
    cfg_path = workspace / "components" / "config.yaml"
    check_node_version(workspace)
    check_vendor_metadata(listener_dir)
    if not cfg_path.exists():
        print(f"WARN: {cfg_path} not found")
        check_git_isolation(workspace, "")
        return 0

    if yaml is None:
        print("WARN: PyYAML is not installed; skipping config content checks")
        print("HINT: run `make init` to install Python dependencies")
        check_git_isolation(workspace, "")
        return 0

    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    notify = ((cfg.get("notify_channels") or {}).get("weixin") or {})
    listener = ((cfg.get("listener_channels") or {}).get("weixin") or {})

    if notify.get("enabled"):
        print("WARN: notify_channels.weixin.enabled=true (may cause cross-channel notifications)")
    else:
        print("OK: notify_channels.weixin.enabled=false")

    cmd = listener.get("command") or []
    expected = ["make", "-C", "components/servers/weixin_listener", "start-gateway"]
    if cmd == expected:
        print("OK: listener command uses local Makefile entrypoint")
    else:
        print(f"WARN: listener command is {cmd!r}, recommended: {expected!r}")

    state_dir = ((listener.get("env") or {}).get("OPENCLAW_STATE_DIR") or "").strip()
    if not state_dir:
        print("WARN: listener env OPENCLAW_STATE_DIR is empty (migration may be harder)")
    else:
        print(f"OK: OPENCLAW_STATE_DIR={state_dir}")
    check_git_isolation(workspace, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

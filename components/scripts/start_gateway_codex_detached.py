#!/usr/bin/env python3
"""Detach and launch the Codex gateway with a stable stdout log file."""

import os
import subprocess
import sys
import time

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATEWAY_DIR = os.path.join(WORKSPACE, "components", "servers", "gateway_codex")
_today = time.strftime("%Y-%m-%d")
STDOUT_LOG = os.path.join(WORKSPACE, "data", "logs", f"gateway-codex-stdout-{_today}.log")


def main() -> int:
    node_bin = os.environ.get("NODE_BIN", "node")
    os.makedirs(os.path.dirname(STDOUT_LOG), exist_ok=True)
    with open(STDOUT_LOG, "ab") as log:
        child = subprocess.Popen(
            [node_bin, "dist/src/index.js"],
            cwd=GATEWAY_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    print(child.pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())

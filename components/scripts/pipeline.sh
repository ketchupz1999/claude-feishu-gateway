#!/bin/bash
# 调度执行器 — daemon 触发的具体任务
set -euo pipefail

unset CLAUDECODE 2>/dev/null || true

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"

# 加载模型策略配置
source "$WORKSPACE/config/models.sh"
LOGDIR="$WORKSPACE/data/logs"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
PERIOD="${1:-knowledge}"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOGFILE="$LOGDIR/$DATE-$PERIOD-$TIMESTAMP.log"

mkdir -p "$LOGDIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOGFILE"
}

run_claude() {
    local desc="$1"
    local prompt="$2"
    local model="${3:-sonnet}"
    python3 "$WORKSPACE/components/scripts/claude_runner.py" \
        --desc "$desc" --prompt "$prompt" --model "$model" --logfile "$LOGFILE"
}

case "$PERIOD" in
    evolve)
        log "=== 知识进化 (兼容 evolve, model=$CHEAP_MODEL) ==="
        run_claude "知识进化" "/kb-evolve" "$CHEAP_MODEL"
        log "=== 知识进化完成 ==="
        ;;
    knowledge)
        log "=== 知识进化 (model=$CHEAP_MODEL) ==="
        run_claude "知识进化" "/kb-evolve" "$CHEAP_MODEL"
        log "=== 知识进化完成 ==="
        ;;
    # 在这里添加自定义任务:
    # your-task)
    #     log "=== 自定义任务 ==="
    #     run_claude "任务描述" "/your-skill-name" "$LIGHT_MODEL"
    #     log "=== 自定义任务完成 ==="
    #     ;;
    *)
        echo "用法: $0 <knowledge|evolve|your-task>" >&2
        exit 1
        ;;
esac

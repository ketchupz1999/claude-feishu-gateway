#!/bin/bash
# 启动前配置检查
set -e

WORKSPACE="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS_FILE="$WORKSPACE/.claude/secrets/feishu_app.json"
OK=true

echo "=== Claude Feishu Gateway 配置检查 ==="
echo ""

# 1. Python
if command -v python3 &>/dev/null; then
    VER=$(python3 --version 2>&1)
    echo "✅ Python3     $VER"
else
    echo "❌ Python3     未安装"
    OK=false
fi

# 2. Claude Code CLI
if command -v claude &>/dev/null; then
    CVER=$(claude --version 2>&1 | head -1)
    echo "✅ Claude CLI  $CVER"
else
    CLAUDE_BIN="${CLAUDE_BIN:-}"
    if [ -n "$CLAUDE_BIN" ] && [ -x "$CLAUDE_BIN" ]; then
        CVER=$($CLAUDE_BIN --version 2>&1 | head -1)
        echo "✅ Claude CLI  $CVER (via CLAUDE_BIN)"
    else
        echo "❌ Claude CLI  未找到 (安装: https://docs.anthropic.com/en/docs/claude-code/overview)"
        OK=false
    fi
fi

# 3. 飞书配置文件
if [ -f "$SECRETS_FILE" ]; then
    # 检查三个必填字段
    MISSING=""
    for KEY in app_id app_secret allowed_open_id; do
        VAL=$(python3 -c "import json; d=json.load(open('$SECRETS_FILE')); v=d.get('$KEY',''); print('EMPTY' if not v or v.endswith('_xxx') else 'OK')" 2>/dev/null)
        if [ "$VAL" != "OK" ]; then
            MISSING="$MISSING $KEY"
        fi
    done
    if [ -z "$MISSING" ]; then
        echo "✅ 飞书配置    $SECRETS_FILE"
    else
        echo "❌ 飞书配置    缺少字段:$MISSING"
        OK=false
    fi
else
    echo "❌ 飞书配置    文件不存在: $SECRETS_FILE"
    echo "   创建方法: cp .claude/secrets/feishu_app.example.json $SECRETS_FILE"
    OK=false
fi

# 4. Python 依赖
DEPS_OK=true
for PKG in lark_oapi claude_agent_sdk websocket requests schedule; do
    python3 -c "import $PKG" 2>/dev/null || { DEPS_OK=false; break; }
done
if $DEPS_OK; then
    echo "✅ Python 依赖 已安装"
else
    echo "❌ Python 依赖 缺少包，运行: pip3 install -r requirements.txt"
    OK=false
fi

# 5. 第三方 API（可选，从环境变量或 config/env.conf 读取）
ENV_CONF="$WORKSPACE/config/env.conf"
if [ -z "$ANTHROPIC_BASE_URL" ] && [ -f "$ENV_CONF" ]; then
    # 从配置文件加载（与 Makefile 一致）
    eval "$(grep -v '^\s*#' "$ENV_CONF" | grep -v '^\s*$' | sed 's/^/export /')"
fi

if [ -n "$ANTHROPIC_BASE_URL" ]; then
    if [ -f "$ENV_CONF" ]; then
        echo "✅ 第三方 API  $ANTHROPIC_BASE_URL (from config/env.conf)"
    else
        echo "✅ 第三方 API  $ANTHROPIC_BASE_URL (from env)"
    fi
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        echo "⚠️  API Key    ANTHROPIC_API_KEY 未设置"
        OK=false
    else
        echo "✅ API Key     已设置"
    fi
    if [ -n "$ANTHROPIC_MODEL" ]; then
        echo "✅ 模型        $ANTHROPIC_MODEL"
    else
        echo "⚠️  模型        ANTHROPIC_MODEL 未设置（第三方 API 通常需要指定）"
    fi
else
    echo "ℹ️  第三方 API  未配置（使用 Claude Code 订阅）"
fi

# 6. 数据目录
mkdir -p "$WORKSPACE/data/logs" 2>/dev/null
echo "✅ 数据目录    $WORKSPACE/data/"

echo ""
if $OK; then
    echo "🟢 所有检查通过，可以启动: make gateway"
else
    echo "🔴 有未通过的检查项，请修复后重试"
    exit 1
fi

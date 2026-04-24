#!/bin/bash
# 启动前配置检查
set -e

WORKSPACE="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS_FILE="$WORKSPACE/.claude/secrets/feishu_app.json"
PYTHON_BIN="${PYTHON:-python3}"
GATEWAY_MODE="${GATEWAY_MODE:-codex}"
OK=true

echo "=== Claude Feishu Gateway 配置检查 ==="
echo "Gateway 模式: $GATEWAY_MODE"
echo ""

# 1. Python
if command -v "$PYTHON_BIN" &>/dev/null; then
    VER=$("$PYTHON_BIN" --version 2>&1)
    echo "✅ Python3     $VER"
else
    echo "❌ Python3     未安装: $PYTHON_BIN"
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
        if [ "$GATEWAY_MODE" = "claude" ]; then
            echo "❌ Claude CLI  未找到 (安装: https://docs.anthropic.com/en/docs/claude-code/overview)"
            OK=false
        else
            echo "⚠️  Claude CLI  未找到；当前 gateway_mode=${GATEWAY_MODE}，不影响 Node Gateway"
        fi
    fi
fi

# 3. 飞书配置文件
if [ -f "$SECRETS_FILE" ]; then
    # 检查三个必填字段
    MISSING=""
    for KEY in app_id app_secret allowed_open_id; do
        VAL=$("$PYTHON_BIN" -c "import json; d=json.load(open('$SECRETS_FILE')); v=d.get('$KEY',''); print('EMPTY' if not v or v.endswith('_xxx') else 'OK')" 2>/dev/null)
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
    "$PYTHON_BIN" -c "import $PKG" 2>/dev/null || { DEPS_OK=false; break; }
done
if $DEPS_OK; then
    echo "✅ Python 依赖 已安装"
else
    if [ "$GATEWAY_MODE" = "claude" ]; then
        echo "❌ Python 依赖 缺少包，运行: make init"
        OK=false
    else
        echo "⚠️  Python 依赖 缺少 Claude/Python Gateway 依赖；当前 gateway_mode=${GATEWAY_MODE}，不影响 Node Gateway"
    fi
fi

# 5. Node Gateway 依赖
if [ "$GATEWAY_MODE" = "codex" ] || [ "$GATEWAY_MODE" = "gemini" ]; then
    if command -v node &>/dev/null; then
        NODE_VERSION=$(node --version 2>&1)
        NODE_MAJOR=$(node -e 'process.stdout.write(String(parseInt(process.versions.node.split(".")[0], 10)))' 2>/dev/null || echo 0)
        if [ "$NODE_MAJOR" -ge 20 ] 2>/dev/null; then
            echo "✅ Node.js     $NODE_VERSION"
        else
            echo "❌ Node.js     需要 >=20，当前 $NODE_VERSION"
            OK=false
        fi
    else
        echo "❌ Node.js     未找到；$GATEWAY_MODE Gateway 需要 Node.js >=20"
        OK=false
    fi

    if [ -d "$WORKSPACE/components/servers/gateway_codex/node_modules" ]; then
        echo "✅ Node 依赖   gateway_codex 已安装"
    else
        echo "❌ Node 依赖   gateway_codex 未安装，运行: make gateway-codex-install"
        OK=false
    fi
fi

# 6. 当前 Agent 登录态提示
if [ "$GATEWAY_MODE" = "codex" ]; then
    if [ -n "$CODEX_API_KEY" ] || [ -n "$OPENAI_API_KEY" ] || command -v codex &>/dev/null; then
        echo "✅ Codex       已发现 Codex CLI 或 API key"
    else
        echo "⚠️  Codex       未发现 codex CLI / CODEX_API_KEY / OPENAI_API_KEY；请确认本机 Codex 登录态可用"
    fi
fi

if [ "$GATEWAY_MODE" = "gemini" ]; then
    if [ -n "$GEMINI_API_KEY" ] || command -v gemini &>/dev/null; then
        echo "✅ Gemini      已发现 gemini CLI 或 GEMINI_API_KEY"
    else
        echo "⚠️  Gemini      未发现 gemini CLI / GEMINI_API_KEY；Gateway 可启动，但聊天会返回“Gemini 未登录”"
    fi
fi

# 7. 第三方 API（可选，从环境变量或 config/env.conf 读取）
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
        if [ "$GATEWAY_MODE" = "claude" ]; then
            OK=false
        fi
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

# 8. 数据目录
mkdir -p "$WORKSPACE/data/logs" 2>/dev/null
echo "✅ 数据目录    $WORKSPACE/data/"

echo ""
if $OK; then
    echo "🟢 所有检查通过，可以启动: make gateway"
else
    echo "🔴 有未通过的检查项，请修复后重试"
    exit 1
fi

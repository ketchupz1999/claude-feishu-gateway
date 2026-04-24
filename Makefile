# Claude Feishu Gateway 服务管理
# 自动检测 OS：macOS 直接用 python3 跑当前目录；Linux 适配生产环境
UNAME := $(shell uname)
WHOAMI := $(shell whoami)
GATEWAY_CONFIG_FILE := $(CURDIR)/components/config.yaml
GATEWAY_CONFIG_EXAMPLE := $(CURDIR)/components/config.example.yaml
READ_GATEWAY_MODE = mode="$$(sed -n 's/^gateway_mode:[[:space:]]*//p' $(GATEWAY_CONFIG_FILE) 2>/dev/null | head -1 | tr -d '[:space:]')"; \
	[ -n "$$mode" ] || mode="$$(sed -n 's/^gateway_mode:[[:space:]]*//p' $(GATEWAY_CONFIG_EXAMPLE) 2>/dev/null | head -1 | tr -d '[:space:]')"; \
	[ -n "$$mode" ] || mode="claude"; \
	if [ "$$mode" != "claude" ] && [ "$$mode" != "codex" ] && [ "$$mode" != "gemini" ]; then \
		echo "ERROR: unsupported gateway_mode=$$mode (expected claude|codex|gemini)"; \
		exit 1; \
	fi;

ifeq ($(UNAME),Darwin)
  # macOS 本地开发
  RUN_WORKSPACE := $(CURDIR)
  PYTHON        := python3
  NODE          := node
else
  # Linux 生产环境 — 修改 RUN_USER 和路径以匹配你的部署
  RUN_USER      := $(USER)
  RUN_WORKSPACE := $(CURDIR)
  PYTHON        := python3
  NODE          := node
endif

BOOTSTRAP_PYTHON := python3
VENV_DIR := $(RUN_WORKSPACE)/.venv
VENV_PYTHON := $(VENV_DIR)/bin/python
ifneq (,$(wildcard $(VENV_PYTHON)))
  PYTHON := $(VENV_PYTHON)
endif

# 自动加载 config/env.conf（第三方 API 配置）
# 格式：KEY=VALUE，跳过注释和空行，自动 export
ENV_FILE := $(RUN_WORKSPACE)/config/env.conf
ifneq (,$(wildcard $(ENV_FILE)))
  RUN = cd $(RUN_WORKSPACE) && export $$(grep -v '^\#' $(ENV_FILE) | grep -v '^$$' | xargs) && $(1)
else
  RUN = cd $(RUN_WORKSPACE) && $(1)
endif

DAEMON_PID := $(RUN_WORKSPACE)/data/daemon.pid
DAEMON_LOG = $(RUN_WORKSPACE)/data/logs/$$(date +%Y-%m-%d)-daemon.log
GATEWAY_PID := $(RUN_WORKSPACE)/data/gateway.pid
GATEWAY_LOG = $(RUN_WORKSPACE)/data/logs/$$(date +%Y-%m-%d)-gateway.log
GATEWAY_NODE_PID := $(GATEWAY_PID)
GATEWAY_NODE_LOG = $(GATEWAY_LOG)
GATEWAY_PY_MATCH := components/servers/feishu_gateway.py
GATEWAY_NODE_MATCH := dist/src/index.js
WEIXIN_LISTENER_DIR := components/servers/weixin_listener

# ===== 初始化 =====

.PHONY: init
init: ## [setup] 安装依赖 + 创建目录
	@$(call RUN,$(BOOTSTRAP_PYTHON) -m venv .venv)
	@$(call RUN,$(VENV_PYTHON) -m pip install -r requirements.txt)
	@$(call RUN,mkdir -p data/logs memory/{scratch,long} todo knowledge/{areas,projects,resources,archive})
	@echo "✓ 依赖已安装到 .venv，目录已创建"

.PHONY: check
check: ## [setup] 启动前配置检查
	@$(call RUN,$(READ_GATEWAY_MODE) GATEWAY_MODE="$$mode" PYTHON="$(PYTHON)" bash scripts/preflight.sh)

# ===== Daemon: 定时调度引擎 =====

.PHONY: daemon
daemon: ## [daemon] 启动（前台，Ctrl+C 停止）
	@$(call RUN,$(PYTHON) components/daemon/daemon.py)

.PHONY: daemon-bg
daemon-bg: ## [daemon] 启动（后台 nohup）
	@if [ -f $(DAEMON_PID) ] && kill -0 $$(cat $(DAEMON_PID)) 2>/dev/null; then \
		echo "ERROR: daemon 已在运行 (PID=$$(cat $(DAEMON_PID)))"; exit 1; \
	fi
	@$(call RUN,nohup $(PYTHON) components/daemon/daemon.py > /dev/null 2>&1 &)
	@sleep 2
	@if [ -f $(DAEMON_PID) ]; then \
		echo "✓ daemon 已启动 (PID=$$(cat $(DAEMON_PID)))"; \
	else \
		echo "ERROR: 启动失败，查看日志"; exit 1; \
	fi

.PHONY: daemon-stop
daemon-stop: ## [daemon] 停止
	@if [ -f $(DAEMON_PID) ]; then \
		kill $$(cat $(DAEMON_PID)) 2>/dev/null && echo "✓ daemon 已停止" || echo "WARN: 进程不存在"; \
		rm -f $(DAEMON_PID); \
	else \
		echo "WARN: 未找到 PID 文件，daemon 可能未运行"; \
	fi

.PHONY: daemon-restart
daemon-restart: daemon-stop daemon-bg ## [daemon] 重启

.PHONY: daemon-status
daemon-status: ## [daemon] 查看状态
	@if [ -f $(DAEMON_PID) ] && kill -0 $$(cat $(DAEMON_PID)) 2>/dev/null; then \
		echo "✓ daemon 运行中 (PID=$$(cat $(DAEMON_PID)))"; \
		echo "--- 最近日志 ---"; \
		tail -5 $(DAEMON_LOG) 2>/dev/null || echo "(无日志)"; \
	else \
		echo "✗ daemon 未运行"; \
	fi

.PHONY: daemon-logs
daemon-logs: ## [daemon] 实时查看日志
	@tail -f $(DAEMON_LOG)

# ===== Gateway: 飞书消息网关 =====

.PHONY: gateway
gateway: ## [gateway] 启动（前台）
	@$(call RUN,$(READ_GATEWAY_MODE) \
		if [ "$$mode" = "codex" ] || [ "$$mode" = "gemini" ]; then \
			cd components/servers/gateway_codex && npm run build && $(NODE) dist/src/index.js; \
		else \
			$(PYTHON) components/servers/feishu_gateway.py; \
		fi)

.PHONY: gateway-bg
gateway-bg: ## [gateway] 启动（后台 nohup）
	@if [ -f $(GATEWAY_PID) ] && kill -0 $$(cat $(GATEWAY_PID)) 2>/dev/null; then \
		echo "ERROR: gateway 已在运行 (PID=$$(cat $(GATEWAY_PID)))"; exit 1; \
	fi
	@$(call RUN,$(READ_GATEWAY_MODE) \
		mkdir -p data/logs; \
		if [ "$$mode" = "codex" ] || [ "$$mode" = "gemini" ]; then \
			cd components/servers/gateway_codex && npm run build >/dev/null 2>&1 && cd ../../.. && $(PYTHON) components/scripts/start_gateway_codex_detached.py >/dev/null; \
		else \
			nohup $(PYTHON) components/servers/feishu_gateway.py > /dev/null 2>&1 & \
		fi)
	@sleep 3
	@if [ -f $(GATEWAY_PID) ] && kill -0 $$(cat $(GATEWAY_PID)) 2>/dev/null; then \
		echo "✓ gateway 已启动 (PID=$$(cat $(GATEWAY_PID)))"; \
	else \
		echo "ERROR: 启动失败，查看日志"; exit 1; \
	fi

.PHONY: gateway-stop
gateway-stop: ## [gateway] 停止
	@if [ -f $(GATEWAY_PID) ]; then \
		pid=$$(cat $(GATEWAY_PID)); \
		kill $$pid 2>/dev/null || { echo "WARN: 进程不存在"; rm -f $(GATEWAY_PID); exit 0; }; \
		for i in 1 2 3 4 5; do \
			kill -0 $$pid 2>/dev/null || break; \
			sleep 1; \
		done; \
		kill -0 $$pid 2>/dev/null && kill -9 $$pid 2>/dev/null; \
		rm -f $(GATEWAY_PID); \
		echo "✓ gateway 已停止"; \
	else \
		echo "WARN: 未找到 PID 文件，gateway 可能未运行"; \
	fi

.PHONY: gateway-restart
gateway-restart: gateway-stop gateway-bg ## [gateway] 重启

.PHONY: gateway-status
gateway-status: ## [gateway] 查看状态
	@$(READ_GATEWAY_MODE) \
	echo "configured gateway_mode=$$mode"; \
	if [ -f $(GATEWAY_PID) ] && kill -0 $$(cat $(GATEWAY_PID)) 2>/dev/null; then \
		pid=$$(cat $(GATEWAY_PID)); \
		cmd="$$(ps -p $$pid -o command= 2>/dev/null)"; \
		impl="unknown"; \
		if echo "$$cmd" | grep -Fq "$(GATEWAY_PY_MATCH)"; then impl="claude"; fi; \
		if echo "$$cmd" | grep -Fq "$(GATEWAY_NODE_MATCH)"; then impl="node"; fi; \
		echo "✓ gateway 运行中 (impl=$$impl, PID=$$pid)"; \
		echo "--- 最近日志 ---"; \
		tail -5 $(GATEWAY_LOG) 2>/dev/null || echo "(无日志)"; \
	else \
		echo "✗ gateway 未运行"; \
	fi

.PHONY: gateway-logs
gateway-logs: ## [gateway] 实时查看日志
	@tail -f $(GATEWAY_LOG)

# ===== Gateway Codex / Gemini =====

.PHONY: gateway-codex-install
gateway-codex-install: ## [gateway-codex] 安装依赖
	@$(call RUN,cd components/servers/gateway_codex && npm install)

.PHONY: gateway-codex-build
gateway-codex-build: ## [gateway-codex] 构建 TypeScript
	@$(call RUN,cd components/servers/gateway_codex && npm run build)

.PHONY: gateway-codex-test
gateway-codex-test: ## [gateway-codex] 运行单测
	@$(call RUN,cd components/servers/gateway_codex && npm test)

.PHONY: gateway-codex
gateway-codex: ## [gateway-codex] 前台运行 Node Gateway
	@$(call RUN,cd components/servers/gateway_codex && npm run build && $(NODE) dist/src/index.js)

.PHONY: gateway-codex-bg
gateway-codex-bg: ## [gateway-codex] 后台运行 Node Gateway
	@if [ -f $(GATEWAY_NODE_PID) ] && kill -0 $$(cat $(GATEWAY_NODE_PID)) 2>/dev/null; then \
		echo "ERROR: gateway-codex 已在运行 (PID=$$(cat $(GATEWAY_NODE_PID)))"; exit 1; \
	fi
	@$(call RUN,mkdir -p data/logs && cd components/servers/gateway_codex && npm run build >/dev/null 2>&1 && cd ../../.. && $(PYTHON) components/scripts/start_gateway_codex_detached.py >/dev/null)
	@sleep 3
	@if [ -f $(GATEWAY_NODE_PID) ] && kill -0 $$(cat $(GATEWAY_NODE_PID)) 2>/dev/null; then \
		echo "✓ gateway-codex 已启动 (PID=$$(cat $(GATEWAY_NODE_PID)))"; \
	else \
		echo "ERROR: 启动失败，查看日志"; exit 1; \
	fi

.PHONY: gateway-codex-stop
gateway-codex-stop: ## [gateway-codex] 停止 Node Gateway
	@if [ -f $(GATEWAY_NODE_PID) ]; then \
		pid=$$(cat $(GATEWAY_NODE_PID)); \
		if ! kill -0 $$pid 2>/dev/null; then \
			echo "WARN: 进程不存在"; \
			rm -f $(GATEWAY_NODE_PID); \
		else \
			cmd="$$(ps -p $$pid -o command= 2>/dev/null)"; \
			if echo "$$cmd" | grep -Fq "$(GATEWAY_NODE_MATCH)"; then \
				$(MAKE) --no-print-directory gateway-stop; \
			else \
				echo "ERROR: 当前运行的不是 gateway-codex (PID=$$pid)"; \
				echo "$$cmd"; \
				exit 1; \
			fi; \
		fi; \
	else \
		echo "WARN: 未找到 PID 文件，gateway-codex 可能未运行"; \
	fi

.PHONY: gateway-codex-restart
gateway-codex-restart: gateway-codex-stop gateway-codex-bg ## [gateway-codex] 重启

.PHONY: gateway-codex-status
gateway-codex-status: ## [gateway-codex] 查看 Node Gateway 状态
	@if [ -f $(GATEWAY_NODE_PID) ] && kill -0 $$(cat $(GATEWAY_NODE_PID)) 2>/dev/null; then \
		pid=$$(cat $(GATEWAY_NODE_PID)); \
		cmd="$$(ps -p $$pid -o command= 2>/dev/null)"; \
		if echo "$$cmd" | grep -Fq "$(GATEWAY_NODE_MATCH)"; then \
			echo "✓ gateway-codex 运行中 (PID=$$pid)"; \
			echo "--- 最近日志 ---"; \
			tail -5 $(GATEWAY_NODE_LOG) 2>/dev/null || echo "(无日志)"; \
		else \
			echo "✗ gateway-codex 未运行 (当前 PID 不是 Node Gateway)"; \
		fi; \
	else \
		echo "✗ gateway-codex 未运行"; \
	fi

.PHONY: gateway-codex-logs
gateway-codex-logs: ## [gateway-codex] 实时查看日志
	@if [ -f $(GATEWAY_NODE_PID) ] && kill -0 $$(cat $(GATEWAY_NODE_PID)) 2>/dev/null; then \
		pid=$$(cat $(GATEWAY_NODE_PID)); \
		cmd="$$(ps -p $$pid -o command= 2>/dev/null)"; \
		if echo "$$cmd" | grep -Fq "$(GATEWAY_NODE_MATCH)"; then \
			tail -f $(GATEWAY_NODE_LOG); \
		else \
			echo "ERROR: 当前运行的不是 gateway-codex (PID=$$pid)"; \
			echo "$$cmd"; \
			exit 1; \
		fi; \
	else \
		echo "✗ gateway-codex 未运行"; \
	fi

.PHONY: gateway-codex-dev
gateway-codex-dev: ## [gateway-codex] 开发模式（tsx）
	@$(call RUN,cd components/servers/gateway_codex && npm run dev)

# ===== Weixin Listener =====

.PHONY: weixin-setup
weixin-setup: ## [weixin] 安装/检查依赖
	@$(call RUN,$(MAKE) -C $(WEIXIN_LISTENER_DIR) WORKSPACE=$(RUN_WORKSPACE) setup)

.PHONY: weixin-login
weixin-login: ## [weixin] 扫码登录
	@$(call RUN,$(MAKE) -C $(WEIXIN_LISTENER_DIR) WORKSPACE=$(RUN_WORKSPACE) login)

.PHONY: weixin-start
weixin-start: ## [weixin] 前台启动监听
	@$(call RUN,$(MAKE) -C $(WEIXIN_LISTENER_DIR) WORKSPACE=$(RUN_WORKSPACE) start)

.PHONY: weixin-status
weixin-status: ## [weixin] 查看监听状态
	@$(call RUN,$(MAKE) -C $(WEIXIN_LISTENER_DIR) WORKSPACE=$(RUN_WORKSPACE) status)

.PHONY: weixin-tail
weixin-tail: ## [weixin] 跟踪监听日志
	@$(call RUN,$(MAKE) -C $(WEIXIN_LISTENER_DIR) WORKSPACE=$(RUN_WORKSPACE) tail)

.PHONY: weixin-doctor
weixin-doctor: ## [weixin] 配置与隔离自检
	@$(call RUN,$(MAKE) -C $(WEIXIN_LISTENER_DIR) WORKSPACE=$(RUN_WORKSPACE) PYTHON="$(PYTHON)" doctor)

.PHONY: gateway-node-install gateway-node-build gateway-node-test gateway-node gateway-node-bg gateway-node-stop gateway-node-restart gateway-node-status gateway-node-logs gateway-node-dev
gateway-node-install: gateway-codex-install
gateway-node-build: gateway-codex-build
gateway-node-test: gateway-codex-test
gateway-node: gateway-codex
gateway-node-bg: gateway-codex-bg
gateway-node-stop: gateway-codex-stop
gateway-node-restart: gateway-codex-restart
gateway-node-status: gateway-codex-status
gateway-node-logs: gateway-codex-logs
gateway-node-dev: gateway-codex-dev

# ===== Daemon 手动触发 =====

.PHONY: evolve
evolve: ## [daemon] 手动: 知识进化
	@$(call RUN,$(PYTHON) components/daemon/daemon.py --once evolve)

# ===== 状态 =====

.PHONY: status
status: daemon-status gateway-status ## [ops] 查看所有服务状态

# ===== 维护 =====

.PHONY: clean-logs
clean-logs: ## [ops] 清理 7 天前的日志
	@find $(RUN_WORKSPACE)/data/logs -name "*.log" -mtime +7 -delete 2>/dev/null; true
	@echo "✓ 已清理 7 天前日志"

# ===== 帮助 =====

.PHONY: help
help: ## 显示帮助
	@echo "用法: make <target>"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help

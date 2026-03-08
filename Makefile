# Claude Feishu Gateway 服务管理
# 自动检测 OS：macOS 直接用 python3 跑当前目录；Linux 适配生产环境
UNAME := $(shell uname)
WHOAMI := $(shell whoami)

ifeq ($(UNAME),Darwin)
  # macOS 本地开发
  RUN_WORKSPACE := $(CURDIR)
  PYTHON        := python3
else
  # Linux 生产环境 — 修改 RUN_USER 和路径以匹配你的部署
  RUN_USER      := $(USER)
  RUN_WORKSPACE := $(CURDIR)
  PYTHON        := python3
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

# ===== 初始化 =====

.PHONY: init
init: ## [setup] 安装依赖 + 创建目录
	@$(call RUN,$(PYTHON) -m pip install -r requirements.txt)
	@$(call RUN,mkdir -p data/logs memory/{scratch,long} todo knowledge/{areas,projects,resources,archive})
	@echo "✓ 依赖已安装，目录已创建"

.PHONY: check
check: ## [setup] 启动前配置检查
	@bash scripts/preflight.sh

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
	@$(call RUN,$(PYTHON) components/servers/feishu_gateway.py)

.PHONY: gateway-bg
gateway-bg: ## [gateway] 启动（后台 nohup）
	@if [ -f $(GATEWAY_PID) ] && kill -0 $$(cat $(GATEWAY_PID)) 2>/dev/null; then \
		echo "ERROR: gateway 已在运行 (PID=$$(cat $(GATEWAY_PID)))"; exit 1; \
	fi
	@$(call RUN,nohup $(PYTHON) components/servers/feishu_gateway.py > /dev/null 2>&1 &)
	@sleep 8
	@if [ -f $(GATEWAY_PID) ]; then \
		echo "✓ gateway 已启动 (PID=$$(cat $(GATEWAY_PID)))"; \
	else \
		echo "ERROR: 启动失败，查看日志"; exit 1; \
	fi

.PHONY: gateway-stop
gateway-stop: ## [gateway] 停止
	@if [ -f $(GATEWAY_PID) ]; then \
		kill $$(cat $(GATEWAY_PID)) 2>/dev/null && echo "✓ gateway 已停止" || echo "WARN: 进程不存在"; \
		rm -f $(GATEWAY_PID); \
	else \
		echo "WARN: 未找到 PID 文件，gateway 可能未运行"; \
	fi

.PHONY: gateway-restart
gateway-restart: gateway-stop gateway-bg ## [gateway] 重启

.PHONY: gateway-status
gateway-status: ## [gateway] 查看状态
	@if [ -f $(GATEWAY_PID) ] && kill -0 $$(cat $(GATEWAY_PID)) 2>/dev/null; then \
		echo "✓ gateway 运行中 (PID=$$(cat $(GATEWAY_PID)))"; \
		echo "--- 最近日志 ---"; \
		tail -5 $(GATEWAY_LOG) 2>/dev/null || echo "(无日志)"; \
	else \
		echo "✗ gateway 未运行"; \
	fi

.PHONY: gateway-logs
gateway-logs: ## [gateway] 实时查看日志
	@tail -f $(GATEWAY_LOG)

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

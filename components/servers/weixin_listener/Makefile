# Weixin Listener lifecycle (self-contained)

WORKSPACE ?= $(abspath $(CURDIR)/../../..)
STATE_DIR ?= $(WORKSPACE)/data/weixin_state
LOG_DIR ?= $(WORKSPACE)/data/logs
DATE := $(shell date +%F)
LISTENER_LOG := $(LOG_DIR)/$(DATE)-listener-weixin.log

NODE ?= node
NPM ?= npm
PYTHON ?= python3

.PHONY: setup login start start-gateway status tail doctor check-node ensure-deps

check-node:
	@$(NODE) -e 'const major=parseInt(process.versions.node.split(".")[0],10); if(Number.isNaN(major)||major<22){console.error("ERROR: Node >=22 is required for weixin listener (current="+process.versions.node+")"); process.exit(1);}'

ensure-deps: check-node
	@if [ ! -d "$(CURDIR)/node_modules" ]; then \
		echo "node_modules missing, installing..."; \
		$(NPM) install; \
	fi

setup: check-node
	@mkdir -p "$(STATE_DIR)" "$(LOG_DIR)"
	@$(NPM) install
	@echo "✓ weixin_listener setup done"
	@echo "  workspace=$(WORKSPACE)"
	@echo "  state_dir=$(STATE_DIR)"

login: setup
	@echo "清理旧登录态..."
	@rm -rf "$(STATE_DIR)/openclaw-weixin/accounts" "$(STATE_DIR)/openclaw-weixin/accounts.json" 2>/dev/null || true
	@OPENCLAW_STATE_DIR="$(STATE_DIR)" AGENTS_WORKSPACE="$(WORKSPACE)" $(NPM) run login

start: setup
	@OPENCLAW_STATE_DIR="$(STATE_DIR)" AGENTS_WORKSPACE="$(WORKSPACE)" $(NPM) run start

start-gateway: ensure-deps
	@mkdir -p "$(STATE_DIR)" "$(LOG_DIR)"
	@OPENCLAW_STATE_DIR="$(STATE_DIR)" AGENTS_WORKSPACE="$(WORKSPACE)" $(NPM) run start

status:
	@echo "workspace: $(WORKSPACE)"
	@echo "state_dir: $(STATE_DIR)"
	@echo "log_file:  $(LISTENER_LOG)"
	@pids="$$(ps -ef | grep 'components/servers/weixin_listener/node_modules/.bin/tsx src/main.ts start' | grep -v grep | awk '{print $$2}')"; \
	if [ -n "$$pids" ]; then \
		echo "✓ listener running PID(s): $$pids"; \
	else \
		echo "✗ listener not running"; \
	fi

tail:
	@mkdir -p "$(LOG_DIR)"
	@touch "$(LISTENER_LOG)"
	@tail -f "$(LISTENER_LOG)"

doctor:
	@$(MAKE) --no-print-directory status
	@$(PYTHON) "$(CURDIR)/scripts/doctor.py" "$(WORKSPACE)"

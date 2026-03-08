#!/bin/bash
# ============================================================
# 模型策略配置 — 修改此文件即可统一切换所有场景的模型
# 用法: source config/models.sh
#
# 可用值: opus / sonnet / haiku
# 也支持完整 model ID，如 claude-sonnet-4-6
# ============================================================

# 重型任务（需要深度推理的场景）
HEAVY_MODEL="${HEAVY_MODEL:-opus}"

# 日常任务（通用分析、日常交互）
LIGHT_MODEL="${LIGHT_MODEL:-sonnet}"

# 低成本任务（系统自检、知识进化等）
CHEAP_MODEL="${CHEAP_MODEL:-haiku}"

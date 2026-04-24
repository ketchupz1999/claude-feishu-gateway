# 部署指南

## 前置：创建飞书 Bot

所有方案都需要先创建飞书自建应用 → **[飞书 Bot 创建指南](feishu-bot-setup.md)**（完整图文教程）

## 按环境选择部署文档

当前 `docs/setup/` 里的分步文档主要覆盖 Claude 模式。
如果你要启用 Codex / Gemini / 微信 listener，请先看仓库根目录 `README.md` 里的 `Gateway 模式` 一节，并参考 `components/config.example.yaml`。

## macOS

1. **方式一：通过第三方服务商**（如阶跃星辰 StepFun、DeepSeek）→ [mac-thirdparty.md](mac-thirdparty.md)
2. **方式二：通过 Claude Code 订阅** → [mac-claude.md](mac-claude.md)

> 没装过 Python / Claude Code？先看 **[macOS 环境准备](prerequisites-mac.md)**

## Windows

1. **方式一：通过第三方服务商**（如阶跃星辰 StepFun、DeepSeek）→ [windows-thirdparty.md](windows-thirdparty.md)
2. **方式二：通过 Claude Code 订阅** → windows-claude.md（待补充）

> 没装过 Git / Python / Claude Code？先看 **[Windows 环境准备](prerequisites-windows.md)**

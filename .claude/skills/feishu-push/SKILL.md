---
name: feishu-push
description: Send formatted messages to Feishu webhook for alerts, batched updates, and daily briefs.
disable-model-invocation: true
allowed-tools: Bash(python3 *)
---

# feishu-push

向飞书 Webhook 发送格式化消息。支持多种模式：测试、告警、批量、日报、通用文本。

## 用法

```
/feishu-push test                  # 发送测试消息，验证通道可用
/feishu-push alert <json_file>     # 发送单条告警（红色卡片）
/feishu-push batch <json_file>     # 发送批量更新（橙色卡片）
/feishu-push brief <md_file>       # 发送日报摘要（蓝色卡片）
/feishu-push text <file_or_text>   # 发送通用文本/Markdown（靛蓝色卡片）
```

## 实现步骤

根据用户输入的命令：

### `/feishu-push test`
运行：
```bash
python3 .claude/skills/feishu-push/scripts/feishu_webhook.py test
```

### `/feishu-push alert <json_file>`
1. 用 Read 工具读取 `<json_file>` 确认文件存在且格式正确
2. 运行：
```bash
python3 .claude/skills/feishu-push/scripts/feishu_webhook.py alert <json_file>
```

### `/feishu-push batch <json_file>`
1. 用 Read 工具读取 `<json_file>` 确认文件存在
2. 运行：
```bash
python3 .claude/skills/feishu-push/scripts/feishu_webhook.py batch <json_file>
```

### `/feishu-push brief <md_file>`
1. 用 Read 工具读取 `<md_file>` 确认文件存在
2. 运行：
```bash
python3 .claude/skills/feishu-push/scripts/feishu_webhook.py brief <md_file>
```

### `/feishu-push text <file_or_text>`
1. 如果是文件路径，用 Read 工具确认文件存在
2. 运行：
```bash
python3 .claude/skills/feishu-push/scripts/feishu_webhook.py text <file_or_text> [--title TITLE]
```

## 环境变量

- `FEISHU_WEBHOOK_URL` — 飞书自定义机器人 Webhook 地址（必须）

## 卡片模板

参见 `message-templates.md` 了解各种卡片样式。

## 错误处理

- 如果 `FEISHU_WEBHOOK_URL` 未设置，脚本会报错退出
- 如果飞书返回非 200，打印错误详情
- 如果文件不存在或格式错误，打印提示

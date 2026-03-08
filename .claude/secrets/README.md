# Secrets 目录

此目录存放敏感配置，**不应提交到 Git**（已在 .gitignore 中排除）。

## 必需文件

### `feishu_app.json`
飞书应用凭据，从飞书开放平台获取：
```json
{
  "app_id": "cli_xxxxxxxxxxxx",
  "app_secret": "your_app_secret_here"
}
```

## 可选文件

根据你扩展的 Skill 需要，可以在此目录添加其他 API 凭据。

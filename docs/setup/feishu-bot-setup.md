# 创建飞书自建应用（Bot）

> **🚧 WIP** — 文档内容已完成，截图待补充

完整图文教程，从零创建飞书 Bot 并配置好所有权限。约 10 分钟。

---

## 第一步：登录开发者控制台

打开 [飞书开放平台](https://open.feishu.cn/app)，用你的飞书账号登录。

> 推荐用**个人账号**登录。企业账号也可以，但发布审批可能需要管理员同意。个人账号创建的测试企业，发布即生效。

![登录飞书开放平台](assets/feishu-login.png)

---

## 第二步：创建自建应用

1. 点击「创建企业自建应用」
2. 填写应用名称（比如 `Claude Agent`），选个图标
3. 点击「确定」创建

![创建应用](assets/feishu-create-app.png)

创建完成后自动进入应用详情页。

---

## 第三步：添加机器人能力

左侧菜单「添加应用能力」→ 点击「机器人」旁边的「添加」。

![添加机器人能力](assets/feishu-add-bot.png)

---

## 第四步：获取 App ID 和 App Secret

左侧菜单「凭证与基础信息」，可以看到：

- **App ID**：`cli_xxxxxxxxx` 格式
- **App Secret**：点击「显示」并复制

![获取凭证](assets/feishu-credentials.png)

把这两个值填入配置文件：

```bash
# 创建配置文件
cp .claude/secrets/feishu_app.example.json .claude/secrets/feishu_app.json
```

编辑 `.claude/secrets/feishu_app.json`：

```json
{
  "app_id": "cli_你的app_id",
  "app_secret": "你的app_secret",
  "allowed_open_id": "ou_稍后获取"
}
```

---

## 第五步：开通权限

左侧菜单「权限管理」，需要开通以下权限。

### 批量添加

点击「权限管理」页面的「批量开通」，粘贴以下权限标识，一次性添加：

```
im:message
im:message:send_as_bot
im:message.receive_v1
im:chat
```

![批量开通权限](assets/feishu-permissions.png)

> 权限说明：
> - `im:message` — 读取消息
> - `im:message:send_as_bot` — 以机器人身份发送消息
> - `im:message.receive_v1` — 接收消息事件回调
> - `im:chat` — 获取会话信息

---

## 第六步：发布应用

左侧菜单「版本管理与发布」→ 点击「创建版本」→ 填写版本号和更新说明 → 「保存」→ 「申请发布」。

![发布应用](assets/feishu-publish.png)

> 个人测试企业通常**自动审批**，几秒钟就上线。企业账号可能需要管理员审批。

---

## 第七步：配置事件回调（长连接模式）

> **注意**：这一步需要先启动 Gateway，因为飞书会验证连接。

### 7.1 先启动 Gateway

```bash
make check      # 检查配置
make gateway    # 启动网关
```

确认 Gateway 启动成功，日志中出现 `WebSocket connected` 字样。

### 7.2 在开发者控制台配置

1. 左侧菜单「事件与回调」
2. 加密策略选择「不加密」（本地开发足够安全）
3. 事件请求方式选择 **长连接**（不是 HTTP Webhook）
4. 添加事件：搜索 `im.message.receive_v1`，勾选添加

![配置长连接](assets/feishu-callback.png)

> **为什么选长连接？** 不需要公网 IP、不需要域名、不需要 HTTPS 证书。Gateway 主动连飞书服务器，家里电脑就能用。

---

## 第八步：获取你的 Open ID

Open ID 是你在这个飞书应用中的用户标识（格式 `ou_xxxxxxxxx`），用于安全限制——只处理你的消息。

### 方法一：通过机器人对话获取（推荐）

1. 打开飞书，搜索你创建的机器人名称，发送一条消息
2. 回到开发者控制台 →「事件与回调」→ 查看事件日志
3. 在日志详情中找到 `open_id` 字段

![从事件日志获取 Open ID](assets/feishu-openid.png)

### 方法二：通过 API 调试器查询

打开 [飞书 API 调试器 — 获取用户信息](https://open.feishu.cn/api-explorer/cli_a6e2571d8f78d00e?apiName=batch_get_id&project=contact&resource=user&version=v3)，用手机号或邮箱查询。

---

### 填入配置

拿到 Open ID 后，更新配置文件：

```json
{
  "app_id": "cli_你的app_id",
  "app_secret": "你的app_secret",
  "allowed_open_id": "ou_你的open_id"
}
```

重启 Gateway：

```bash
# Ctrl+C 停掉当前 Gateway，然后重新启动
make gateway
```

---

## 完成

现在在飞书里给你的 Bot 发消息，应该能收到回复了。

如果遇到问题，检查：
1. 应用状态是否为「已上线」（版本管理与发布）
2. 权限是否全部开通（权限管理，状态应为「已开通」）
3. 事件回调是否配置了 `im.message.receive_v1`
4. Gateway 日志是否有报错

返回 → [部署指南首页](README.md)

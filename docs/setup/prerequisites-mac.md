# macOS 环境准备

从零开始，一步步来。全程大约 10 分钟。

---

## 0. 安装命令行工具（git、make 等）

Mac 默认没有 `git` 和 `make`，需要先装 Apple 的命令行开发工具。打开「终端」应用（Spotlight 搜索 `终端` 或 `Terminal`），输入：

```bash
xcode-select --install
```

弹出窗口点「安装」，等待完成（可能需要几分钟）。

> 如果提示「已经安装」，说明之前装过，直接跳过。

装完后验证：

```bash
git --version    # 应输出 git version 2.x.x
make --version   # 应输出 GNU Make 3.x 或更高
```

---

## 1. 安装 Python 3

### 检查是否已安装

打开「终端」应用（Spotlight 搜索 `终端` 或 `Terminal`），输入：

```bash
python3 --version
```

如果输出类似 `Python 3.10.x` 或更高版本，说明已安装，跳到[第 2 步](#2-安装-claude-code)。

如果提示 `command not found` 或版本低于 3.10，继续往下。

### 方法一：官网下载（推荐新手）

1. 打开 [python.org/downloads](https://www.python.org/downloads/)
2. 点击黄色按钮「Download Python 3.x.x」下载安装包
3. 双击 `.pkg` 文件，一路点「继续」→「安装」
4. 安装完成后，重新打开终端，验证：

```bash
python3 --version
```

### 方法二：用 Homebrew 安装

如果你已经有 Homebrew（不确定就用方法一）：

```bash
brew install python3
```

---

## 2. 安装 Claude Code

Claude Code 是 Anthropic 官方的命令行工具。Gateway 通过它来调用 AI 能力。

### 2.1 安装 Node.js（Claude Code 的依赖）

检查是否已有：

```bash
node --version
```

如果提示 `command not found`，需要先装 Node.js：

1. 打开 [nodejs.org](https://nodejs.org/)
2. 下载 **LTS** 版本（左边的按钮）
3. 双击安装包，一路「继续」
4. 重新打开终端，验证：

```bash
node --version   # 应输出 v18 或更高
```

### 2.2 安装 Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

等安装完成，验证：

```bash
claude --version
```

应输出类似 `2.x.x (Claude Code)`。

### 2.3 登录 Claude Code（仅 Claude 订阅用户）

如果你使用 Claude Code 订阅（不是第三方 API），需要登录：

```bash
claude
```

按提示完成浏览器授权登录。登录成功后，测试：

```bash
claude -p "说你好"
```

能收到回复就说明一切正常。

> **第三方 API 用户**不需要登录，跳过这步即可。配置第三方 API 后再测试。

---

## 3. 验证清单

全部装好后，逐一检查：

```bash
git --version        # ✅ git 2.x
make --version       # ✅ GNU Make 3.x+
python3 --version    # ✅ Python 3.10+
node --version       # ✅ Node.js 18+
claude --version     # ✅ Claude Code 2.x
```

五个都通过，就可以去看部署文档了：

- Claude 订阅用户 → [mac-claude.md](mac-claude.md)
- 第三方 API 用户 → [mac-thirdparty.md](mac-thirdparty.md)

---

## 常见问题

### `command not found: python3`

安装后需要**重新打开终端**，新安装的命令才能生效。

### `permission denied` 安装 npm 包

在命令前加 `sudo`：

```bash
sudo npm install -g @anthropic-ai/claude-code
```

输入你的 Mac 登录密码（输入时不会显示，正常现象）。

### Mac 提示「无法验证开发者」

系统偏好设置 → 隐私与安全性 → 点「仍要打开」。

### 公司电脑有网络限制

如果 `npm install` 很慢或失败，可能需要配置公司代理。问你的 IT 部门获取代理地址，然后：

```bash
npm config set proxy http://代理地址:端口
npm config set https-proxy http://代理地址:端口
```

# Windows 环境准备

> **WIP：赶工中**，内容可能不完整，欢迎反馈。

从零开始，一步步来。全程大约 15 分钟。

---

## 0. 打开 PowerShell

后续所有命令都在 PowerShell 中执行。

按 `Win + X`，选择「Windows PowerShell」或「终端」。

> 不要用 CMD（命令提示符），部分命令不兼容。

---

## 1. 安装 Git

### 检查是否已安装

```powershell
git --version
```

如果输出版本号，跳到[第 2 步](#2-安装-python-3)。

### 安装

1. 打开 [git-scm.com/download/win](https://git-scm.com/download/win)
2. 下载安装包，双击运行
3. 安装选项全部保持默认，一路「Next」→「Install」
4. **重新打开 PowerShell**，验证：

```powershell
git --version    # 应输出 git version 2.x.x
```

---

## 2. 安装 Python 3

### 检查是否已安装

```powershell
python3 --version
```

如果输出 `Python 3.10.x` 或更高，跳到[第 3 步](#3-安装-claude-code)。

### 安装

1. 打开 [python.org/downloads](https://www.python.org/downloads/)
2. 点击黄色按钮「Download Python 3.x.x」下载安装包
3. 双击运行，**勾选底部「Add python.exe to PATH」**（很重要！）
4. 点「Install Now」
5. **重新打开 PowerShell**，验证：

```powershell
python3 --version
```

> 如果 `python3` 不行，试试 `python --version`。Windows 有时用 `python` 而不是 `python3`。

---

## 3. 安装 Claude Code

Claude Code 是 Anthropic 官方的命令行工具。Gateway 通过它来调用 AI 能力。

### 3.1 安装 Node.js（Claude Code 的依赖）

检查是否已有：

```powershell
node --version
```

如果提示找不到命令，需要安装：

1. 打开 [nodejs.org](https://nodejs.org/)
2. 下载 **LTS** 版本（左边的按钮）
3. 双击安装，一路「Next」
4. **重新打开 PowerShell**，验证：

```powershell
node --version   # 应输出 v18 或更高
```

### 3.2 安装 Claude Code

```powershell
npm install -g @anthropic-ai/claude-code
```

等安装完成，验证：

```powershell
claude --version
```

应输出类似 `2.x.x (Claude Code)`。

### 3.3 登录 Claude Code（仅 Claude 订阅用户）

如果你使用 Claude Code 订阅（不是第三方 API），需要登录：

```powershell
claude
```

按提示完成浏览器授权登录。登录成功后，测试：

```powershell
claude -p "说你好"
```

能收到回复就说明一切正常。

> **第三方 API 用户**不需要登录，跳过这步即可。配置第三方 API 后再测试。

---

## 4. 安装 Make（可选但推荐）

项目用 `make` 来简化启动命令。Windows 默认没有 `make`，有两种方案：

### 方法一：用 Chocolatey 安装（推荐）

先装 [Chocolatey](https://chocolatey.org/install)（Windows 的包管理器），以**管理员身份**打开 PowerShell，运行：

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

然后安装 make：

```powershell
choco install make
```

重新打开 PowerShell，验证：

```powershell
make --version
```

### 方法二：不装 Make，手动运行命令

如果不想装 Make，也可以直接用 Python 命令启动（参考部署文档中的说明）。

---

## 5. 验证清单

全部装好后，逐一检查：

```powershell
git --version        # ✅ git 2.x
python3 --version    # ✅ Python 3.10+（或 python --version）
node --version       # ✅ Node.js 18+
claude --version     # ✅ Claude Code 2.x
make --version       # ✅ GNU Make（可选）
```

都通过了，就可以去看部署文档：

- Claude 订阅用户 → [windows-claude.md](windows-claude.md)
- 第三方 API 用户 → [windows-thirdparty.md](windows-thirdparty.md)

---

## 常见问题

### 安装后命令找不到

每次安装新工具后，需要**重新打开 PowerShell**，新命令才能生效。

### `python3` 找不到但 `python` 可以

Windows 上两个命令可能不同。如果 `python --version` 显示 3.10+，后续文档中所有 `python3` 替换为 `python`，`pip3` 替换为 `pip`。

### npm 安装报错 `EACCES` 或权限问题

以**管理员身份**打开 PowerShell 重试（右键 PowerShell → 以管理员身份运行）。

### 公司电脑有网络限制

如果下载很慢或失败，可能需要配置代理。问 IT 部门获取代理地址，然后：

```powershell
npm config set proxy http://代理地址:端口
npm config set https-proxy http://代理地址:端口
```

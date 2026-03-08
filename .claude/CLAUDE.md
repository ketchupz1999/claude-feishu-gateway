# CLAUDE.md — Claude Feishu Gateway 项目指令

## 项目概述
飞书 + Claude Code 的个人 Agent 系统。通过飞书消息驱动 Claude Code，实现知识库自进化、定时任务调度、移动端 Agent 交互。

## 设计哲学
- **简洁优先**：能一行解决的不写三行，能用现有工具的不造新轮子
- **根因导向**：遇到问题先追根因，不做表面修补
- **最小影响**：改动范围越小越好，避免连锁副作用

## 工作流程
所有非平凡任务遵循四步循环：**Plan → Execute → Verify → Learn**
- Plan：先读代码、理解现状，再动手
- Execute：最小改动实现目标
- Verify：改完必须验证（跑测试 / 检查日志 / 手动确认）
- Learn：值得记录的经验沉淀到 rules/ 或 skills/

## 委派策略
- 能委派给 subagent 就委派，保持主上下文干净
- 无依赖的任务并发执行
- 委派时提供充分上下文，避免 subagent 重复探索

## 自进化规则
收到用户任何纠正后，立即判断：
- 行为约束类（"不要这样做"）→ 写入 `rules/` 对应文件
- 能力流程类（"某件事的完整方法"）→ 提炼为 skill 或更新现有 skill
- 全局总纲类 → 更新 CLAUDE.md

## 目录约定

### 热上下文（高频访问、有时效性）
- `todo/inbox.md` — 当前活跃 TODO（本周任务、随手记）
- `todo/backlog.md` — 长期规划和待排期项
- `todo/discuss.md` — 待讨论/待观察的想法，确认后移入 inbox 或 backlog
- `memory/scratch/` — 临时记忆（对话摘要、事件记录），定期清理沉淀到 long/
- `memory/long/` — 长期记忆（领域经验、认知积累），持续更新

### 冷知识（PARA 体系，做事导向）
- `knowledge/areas/` — 领域概览，含指向 projects 的指针
- `knowledge/projects/<name>/` — 以事件驱动的项目文件夹
- `knowledge/resources/` — 参考资料、方法论
- `knowledge/archive/` — 归档

### Agent 记忆（按领域隔离）
- `.claude/agent-memory/<agent-name>/` — 每个 Agent 的独立记忆空间
  - 每个 agent 拥有自己的 `MEMORY.md` + 可选的细分文件（如 `patterns.md`）
  - 新建 agent 记忆前先询问用户确认，说明为什么需要独立记忆空间
  - 与 `memory/long/` 的分工：agent-memory 是**领域专属**的操作记忆，long/ 是**跨领域通用**经验

### Agent 反馈规范

人类对 agent 行为的反馈，**不直接修改 agent 的记忆或内部规则**，而是通过外部反馈通道传递，让 agent 自主消化和调整。

- **反馈位置**：`.claude/agent-memory/<agent-name>/feedback.md`
  - 每个 agent 有且仅有一个反馈文件，路径固定、可预测
  - 格式：以 `## 反馈 (YYYY-MM-DD)` 为标题，按日期倒序排列（最新在前）
  - 内容：描述观察到的问题 + 期望的方向，不直接改规则代码
- **agent 职责**：
  1. 每次运行时检查 feedback.md 是否有未处理的反馈
  2. 自主决定如何调整记忆和策略
  3. 在 MEMORY.md 中记录"收到反馈 → 做了什么调整"
  4. 在 feedback.md 中对已消化的条目标注 `[已处理 YYYY-MM-DD]`

### 经验沉淀路径
每次交互中产生的经验，只有三个归宿：
1. **行为约束** → `.claude/rules/` 对应领域文件
2. **能力流程** → `.claude/skills/` 新建或更新
3. **全局总纲** → `CLAUDE.md`
不确定归哪？说明还不够成熟，等再出现几次再沉淀。

### 运行时
- `data/` — 运行时数据（日志、缓存等）
- `.claude/skills/` — Agent Skills
- `.claude/skills/common/` — 跨 skill 公用脚本库

### 系统组件 (`components/`)
- **常驻进程**：
  - `servers/feishu_gateway.py` — 飞书 WebSocket 网关，接收用户消息
  - `daemon/daemon.py` — cron 式调度器（30s 轮询），驱动 pipeline.sh 各模式
- **调度执行**：`scripts/pipeline.sh` — Claude CLI 调度执行器，所有定时/事件触发的 skill 统一入口

## 文件命名规范
- 项目名无空格，用 `_` 连接
- 文档：`YYYYMMDD-<主题>.md`

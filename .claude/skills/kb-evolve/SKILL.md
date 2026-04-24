---
name: kb-evolve
description: "知识库进化与代码自省。审计 memory/long 一致性、沉淀 scratch 到长期记忆、清理过期 todo、扫描代码 TODO/FIXME、分析 daemon 错误根因、发现外部 skills/MCP 工具。当用户提到知识进化、memory 审计、代码自省、知识整理、认知迭代、能力发现时触发此 skill。"
---

# kb-evolve — 知识审计、代码自省与能力发现

kb-evolve 负责认知迭代：检查知识质量、代码 TODO、过期 scratch、daemon 错误模式和可用能力。

## 触发时机

- 手动：`/kb-evolve`
- 自动：daemon 每周四 19:00 UTC（北京周五 03:00）

## 执行流程

### Step 1 — 知识库健康采集

```bash
python3 .claude/skills/kb-evolve/scripts/knowledge_audit.py
```

脚本输出 JSON，包含：
- `memory_long`: 每个文件的 age、size、lines
- `memory_scratch`: 总数 + 超 7 天的 stale 文件
- `agent_memory`: 各 agent 的 MEMORY.md 行数、最后修改天数
- `todo_inbox` / `todo_backlog`: done/open 数量、超 2 周未动项
- `error_patterns`: 最近 7 天 daemon 日志 ERROR/FAIL 去重聚合
- `code_todos`: `.claude/skills/` 和 `components/` 中的 TODO/FIXME/HACK

### Step 2 — 知识审计 & 执行修复

基于 Step 1 JSON 数据，执行以下检查和修复。重点：**做，不只是报告**。

#### 2a. 知识一致性检查

- 读 `memory/long/` 下的文件，对比实际代码状态（daemon 调度频率、skill 数量、架构信息）→ 直接修正过时信息
- 读各 `.claude/agent-memory/*/MEMORY.md`，检查数据是否与最新状态一致 → 标注不一致项
- 约束：只改事实性信息（数字、日期、技术细节），不改观点和策略

#### 2b. scratch 沉淀

- 超过 7 天的 scratch 文件 → 读取内容，提取有价值的认知写入 `memory/long/` 对应文件
- 提取完成后删除源 scratch 文件
- 跳过近期的 kb-evolve 报告（保留最近 2 份作为趋势对比基线）

#### 2c. todo 清理

- `todo/inbox.md` 中明显过期的任务（日期已过数周的事件性任务）→ 标记完成或移除
- 大量 `[x]` 已完成项 → 归档到 `knowledge/projects/` 对应目录或直接移除
- `todo/backlog.md` 中超过 2 周未动的 `[ ]` 项 → 评估是否仍有价值，标注或移至 discuss

### Step 3 — 代码自省 & 能力发现

#### 3a. 代码自省

- 聚合 Step 1 的 `error_patterns` → 分析根因，哪些是代码 bug vs 外部依赖问题
- 检查 agent-memory 中"已知缺陷"/"待办"/"TODO"段落 → 哪些已被修复但未更新记忆？
- 扫描 `code_todos` 列表 → 分类：
  - **可立即修**（简单 bug、过时注释、已完成的 TODO）→ 直接修复 + 记录
  - **需用户决策**（架构变更、策略调整）→ 列入报告建议
- 对"可立即修"的项，执行修复

#### 3b. 能力发现

使用 WebSearch 搜索以下关键词（每次运行选 1-2 个最相关的）：
- "claude code skills" + 当前年份
- "claude code MCP" + backlog 中的具体需求关键词

对每个发现项评估：
| 维度 | 评估标准 |
|------|----------|
| 来源可信度 | 官方 Anthropic / GitHub 高星 / 社区未知 |
| 安全风险 | 需要什么权限、是否要 API key、代码是否可审计 |
| 适用度 | 是否匹配 backlog 中的未完成需求 |

**安全边界：只输出推荐列表，绝不自动安装任何外部工具。**

推荐格式：`名称 | 来源 | 安全评级(高/中/低) | 匹配需求 | 安装方式`

### Step 4 — 输出报告 & 提交

#### 4a. 生成报告

报告写入 `memory/scratch/YYYYMMDD-kb-evolve.md`：

```markdown
# 知识进化报告 — YYYY-MM-DD

## 知识健康评分：N/10

## 本次修复
- [列出实际执行的修改，包括文件路径]

## 知识审计发现
- [过时/不一致的内容及处理方式]

## scratch 沉淀
- [提取了什么 → 写入哪个文件]
- [删除了哪些 scratch 文件]

## 代码改进
- [已修复] xxx（文件:行号）
- [建议] yyy（需用户决策，原因）

## 能力发现
| 名称 | 来源 | 安全 | 匹配需求 | 安装方式 |
|------|------|------|----------|----------|

## 下次关注
- [优先级排序的待办，最多 5 条]
```

报告控制在 100 行以内，用数据说话。

#### 4b. git commit

```bash
git add <本次修改的文件>
git commit -m "chore: kb-evolve MMDD — <一句话摘要>"
```

只 commit 本次知识进化涉及的文件，不捎带其他未关联变更。

## 约束

- 只做事实性调整，不改变用户的计划、策略和目标
- memory/long 中的领域知识只更新事实（数字、日期），不修改观点
- agent-memory 只标注不一致，不擅自修改策略权重
- 删除文件前必须说明理由
- 外部工具只搜索+推荐，**绝不自动安装**
- 报告控制在 100 行以内

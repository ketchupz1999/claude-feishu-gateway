---
name: health-check
description: "系统健康检查与自愈。定期审视进程/日志/data新鲜度/运行状态，自动修复不一致，追踪趋势并提出改进建议。当用户提到系统自检、健康检查、清理过时内容、系统维护时触发此 skill。"
---

# health-check — 系统健康检查与自愈

> 与 knowledge-evolve 的分工：health-check = 系统活着吗？knowledge-evolve = 系统变聪明了吗？

这个 skill 的目标不只是生成一份报告，而是让系统真正变好。每次运行后，系统应该比运行前更健康、更一致、更聪明。

## 触发时机

- 手动：`/health-check`
- 自动：daemon 每周一 03:00 调度
- 建议额外触发：重大变更后（新增/删除 skill、架构调整、服务器迁移）

## 执行流程

### Step 1: 自动收集指标

运行健康检查脚本，获取系统量化数据：

```bash
python3 .claude/skills/health-check/scripts/health_check.py
```

脚本会自动检查：
- skills 目录完整性（是否有 SKILL.md、scripts、evals）
- memory 健康度（scratch 过期文件、long 文件新鲜度）
- 最近 3 天 daemon 日志统计（成功/失败/超时）
- todo 状态（完成数、待办数）
- data 目录新鲜度（各目录最新文件时间）
- 历史自检报告列表

脚本输出 JSON，用它作为本次自检的数据基础，而不是逐个手动扫描文件。

### Step 2: 深度检查（基于脚本结果重点排查）

脚本提供了全景数据，现在聚焦异常项做深度检查。只检查有问题的部分，不要逐个列出所有正常的 skill。

#### 2a. 异常排查

- 脚本报告的 `fail > 0` 或 `timeout > 0` 的日志 → 读具体日志定位原因
- **极端指标交叉验证**：`success_rate` 为 0% 或 `fail` 占比 > 50% 时，先核实原始日志，再下结论——脚本本身可能有 bug
- `stale_scratch` 不为空 → 逐个判断是否沉淀到 long/ 或归档
- `data_freshness` 中 `newest_age_hours > 24` 的目录 → 可能有服务中断
- skills 中 `has_skill_md: false` → 异常，需修复
- todo 中 `done` 占比过高 → 可能需要清理已完成项
- **health_check.py 自身 bug**：若指标明显失真，检查脚本匹配逻辑，发现 bug 立即修复并说明原因

#### 2b. memory 生命周期管理

这是自进化的核心，不只是报告状态，要主动执行：

1. **scratch → long 沉淀**：超过 7 天的 scratch 文件，提取有价值的认知写入对应的 long/ 文件，然后删除或归档 scratch 文件
2. **long 文件校验**：检查 long/ 中的事实性信息是否仍然准确（服务器信息、skill 数量、架构变更等），如有变化直接更新
3. **auto-memory 同步**：检查 `~/.claude/projects/` 下的 MEMORY.md 是否需要更新

#### 2c. todo 维护

- inbox 中已完成但未标 `[x]` 的项 → 直接标记
- inbox 中超过 2 周未动的项 → 考虑移到 backlog 或标注原因
- backlog 中已完成的项 → 确认并标记

### Step 3: 趋势分析

读最近一份自检报告（`previous_reports` 字段中最新的文件），提取以下字段做对比：

| 提取项 | 上次值 | 本次值 | 变化 |
|--------|--------|--------|------|
| 健康评分 | N/10 | N/10 | ↑↓— |
| daemon 成功率 | % | % | ↑↓— |
| skill 数量 | N | N | ↑↓— |
| 建议列表 | 逐条列出 | 执行状态 | ✅/⏳/❌ |

重点关注：
- **同一错误反复出现** → 上次已发现但未修复的，本次必须修复或说明为何跳过
- **成功率下降** → 有新引入的不稳定因素
- **建议未执行** → 区分"已过时"和"遗漏"

如果是首次运行或没有历史报告，跳过此步。

### Step 4: 执行修复

直接执行能力范围内的修复，不要只提建议：

- 更新 long/ 中过时的信息
- 标记 inbox 中已完成的项
- 沉淀 scratch 中有价值的内容
- 删除确认无用的临时文件

对于需要用户决策的变更（删除文件、架构调整），列出但不执行。

### Step 4b: git commit

修复完成后，将所有变更统一提交：

```bash
git add memory/long/ memory/scratch/YYYYMMDD-health-check.md \
        .claude/skills/health-check/scripts/ \
        todo/inbox.md todo/backlog.md
git commit -m "chore: health-check MMDD — <一句话摘要修复内容>"
```

只 commit 本次自检涉及的文件，不捎带其他未关联变更。

### Step 5: 输出报告

报告要简洁，聚焦变化和行动，不重复列出所有正常的项目。

```markdown
# 健康检查报告 — YYYY-MM-DD

## 健康评分：N/10

## 本次修复
- [列出实际执行的修改，包括文件路径]

## 异常发现
- [仅列出需要关注的问题]

## 趋势观察
- [对比历史报告的变化]

## 上次建议跟进
| 建议 | 状态 |
|------|------|

## 新建议
- [P0/P1/P2 分级，每级最多 3 条]
```

报告写入 `memory/scratch/YYYYMMDD-health-check.md`。

## 约束

- 只做事实性调整，不擅自改变用户的计划和目标
- memory/long/ 中的领域知识只更新事实性信息（数字、日期），不修改观点和策略
- 删除文件前必须说明理由
- 报告控制在 80 行以内，用数据说话而不是铺表格
- health_check.py 脚本本身发现 bug，立即修复并在报告中注明；不能用有 bug 的数据作为结论依据

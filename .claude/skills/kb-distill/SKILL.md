---
name: kb-distill
description: "经验提炼。将会话中的调研结论、实测经验、踩坑记录、决策备忘沉淀到 knowledge/projects/ 或 knowledge/resources/。当用户说'沉淀'、'记录下来'、'存下来'、'总结会话'、'distill'、'kb-distill'时触发。"
---

# kb-distill — 经验提炼

## 你在做什么

把会话中产生的可复用信息提炼成结构化知识。这是知识库的供给侧：只保留一个月后仍有参考价值的结论、决策、踩坑和有效模式。

默认存储路径：

- 项目相关：`knowledge/projects/<project-name>/`
- 通用参考：`knowledge/resources/<scope>/`

## 触发时机

- 用户明确提到“沉淀”“记录下来”“存下来”“总结会话”“distill”“kb-distill”。
- 完成重要任务后，存在可复用的决策、坑点或实现模式。
- 对话中出现多轮实质性排障、调研或架构判断，且结论未来可能复用。

不需要为一次性简单答疑建知识文件。

## 执行流程

### Step 1 — 判断知识类型

| 类型 | 特征 |
|------|------|
| 调研结论 | 多渠道比较后的判断 |
| 实测记录 | 亲手验证的成功 / 失败案例 |
| 踩坑总结 | 问题 → 排查 → 根因 → 解法 |
| 决策备忘 | 选 A 不选 B 的理由 |
| 方法论 | 可复用的做事方式 |

### Step 2 — 选择存储位置

项目相关：

- 已有项目：追加到 `knowledge/projects/<project-name>/`
- 新项目：创建 `knowledge/projects/<project-name>/`
- 文件名：`YYYYMMDD-<topic-slug>.md`

通用参考：

- 存入 `knowledge/resources/shared/`、`knowledge/resources/work/` 或 `knowledge/resources/personal/`
- 文件名：`<topic-slug>.md`，已有同主题文件则更新而不是新建

### Step 3 — 提炼结构

```markdown
# <主题>

> 日期：YYYY-MM-DD
> 类型：调研结论 / 实测记录 / 踩坑总结 / 决策备忘 / 方法论

## 结论
- <3-5 条关键结论>

## 背景
<为什么这条经验值得记录>

## 详细内容
<决策、坑点、解法或方法论>

## 失效条件
<什么情况下需要重新验证>

## 参考
- <来源、链接、文件或命令>
```

### Step 4 — 去噪

- 只留结论，不留对话流水账。
- 只留差异和判断，不重复常识。
- 标注不确定性：已验证 / 较可靠 / 待验证。
- 保留反面案例和失败路径。

### Step 5 — 确认

输出给用户：

- 存储路径
- 提炼出的要点数量
- 待验证项
- 失效条件

## 不做什么

- 不修改 skill / rule / CLAUDE.md，那是能力维护工作。
- 不记录过程流水账。
- 不整理整个知识库，那是 kb-evolve 的事。

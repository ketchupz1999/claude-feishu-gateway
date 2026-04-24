---
name: sh-save
description: "保存当前工作的会话交接上下文（session handoff）。当用户说'保存上下文'、'先记一下'、'帮我做个 handoff'、'准备切会话'、'compact 前存一下'、'sh-save'时触发。适用于把当前进展整理成可恢复的短期 handoff。"
---

# sh-save — 保存会话交接

## 你在做什么

把“这次会话做到哪了，下一次应该怎么接上”整理成一份短期交接文件，写入本地 `memory/session-handoffs/`。

这不是项目知识沉淀，也不是完整对话归档。

- `sh-save` 负责短期 handoff
- `sh-load` 负责恢复 handoff
- `kb-distill` 负责把长期有效经验沉淀到 `knowledge/projects/` 或 `knowledge/resources/`

## 优先使用仓库脚本

先用仓库脚本落盘，再基于结果做必要说明：

```bash
python3 scripts/session_handoff_save.py --topic "gateway migration" --current-goal "..." --done "..." --decision "..." --risk "..." --next-step "..."
```

如果用户明确给了 scope，优先使用：

```bash
python3 scripts/session_handoff_save.py --scope opensource-gateway-phase2 --current-goal "..." --next-step "..."
```

只有在脚本无法覆盖当前场景时，才手动编辑 handoff 文件。

如果本次保存表示“切换到这个事项继续干”，显式带上 `--set-current yes`。
如果只是后台记录、验收、测试或不想抢占默认 `sh-load` 入口，带 `--set-current no`。

## 存储结构

按 scope 存储：

```text
memory/session-handoffs/
└── <scope>/
    ├── latest.md
    ├── meta.json
    └── history/
        └── YYYY-MM-DD-HHMM-<slug>.md
```

同时维护全局活跃事项索引：

```text
memory/session-handoffs/_active.json
```

`memory/session-handoffs/` 是本地短期状态，默认不提交到 Git。

## scope 规则

优先级从高到低：

1. 用户显式指定的 `--scope`
2. 用户显式指定的 `--topic`，自动生成 `ad-hoc_<topic-slug>`
3. 兼容旧习惯的 `--req-id`

`--scope` 会归一化成英文 slug；`--topic` 可以包含中文，无法转成英文 slug 时会自动追加短 hash，避免不同中文主题写进同一个 scope。

推荐格式：

- 项目：`opensource-gateway-phase2`
- 临时话题：`ad-hoc_session-handoff-skills`

## 输出目标

生成一份“最新稳定态” handoff，而不是流水账。

`latest.md` 只保留：

1. 当前目标
2. 已完成
3. 关键决策
4. 卡点/风险
5. 下一步
6. 相关文件
7. 失效条件

全文控制在 250-400 字；如果超过，主动压缩。

## latest.md 模板

```markdown
# Session Handoff

> scope: <scope>
> updated_at: <YYYY-MM-DD HH:MM local>
> status: active
> source: sh-save
> supersedes: <snapshot-id or none>

## Current Goal
<一句话说明当前正在推进什么>

## Done
- <已完成的关键进展>

## Decisions
- <当前仍影响后续判断的决策>

## Risks
- <当前主要卡点、风险、待确认项>

## Next
- <下次恢复时优先执行的 1-3 步>

## Related Files
- `<path>`

## Expire When
- <什么条件下这份 handoff 失效>
```

空节不要保留。

## 长期层升级规则

以下内容不应只停留在 handoff：

- 明确技术决策
- 新发现的约束 / 踩坑
- 阶段推进
- 完成 / 暂停状态

出现这些内容时，优先用 `kb-distill` 写入：

- 项目相关：`knowledge/projects/<project-name>/`
- 通用参考：`knowledge/resources/<scope>/`

不要在 `sh-save` 里定义第二套长期知识格式。

## 不该做什么

不要：

- 粘贴大段对话 transcript
- 复制完整命令输出
- 把“观察到的暂时数据”写成长期结论
- 在 scope 不明确时自动改长期知识文件
- 因为用户说“保存一下”就强行沉淀到 `knowledge/`

## 完成后输出

简要说明：

1. 写入了哪个 scope
2. 是否更新了 `latest.md`
3. 是否新增了 history 快照
4. 是否同步升级了长期层

示例：

```text
已保存 handoff 到 `memory/session-handoffs/opensource-gateway-phase2/`。

- 更新了 `latest.md`
- 新增 history 快照：`2026-04-24-2215-design-updated.md`
- 未同步长期层
```

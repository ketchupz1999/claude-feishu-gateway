---
name: sh-load
description: "加载当前工作的会话交接上下文（session handoff）。当用户说'加载上下文'、'恢复一下上次进度'、'我刚开新会话，接着做'、'帮我看下上次做到哪了'、'sh-load'时触发。适用于从本地 handoff 恢复可执行工作简报。"
---

# sh-load — 恢复会话交接

## 你在做什么

把用户从“新开会话”快速恢复到“可继续执行”的状态。

默认读取短期 handoff 的最新稳定态，再结合可选的项目上下文生成恢复简报。

这不是历史全文回放，也不是把所有相关文件塞进上下文。

## 优先使用仓库脚本

先用仓库脚本恢复，再在回复里转述核心结果：

```bash
python3 scripts/session_handoff_load.py --scope opensource-gateway-phase2
python3 scripts/session_handoff_load.py --query "gateway migration"
```

只有在脚本无法判定 scope 或输出明显不足时，才手动补充分析。

## 读取顺序

固定按以下顺序读取：

1. `memory/session-handoffs/_active.json`
2. 对应 scope 的 `memory/session-handoffs/<scope>/latest.md`
3. 对应项目的 `knowledge/projects/<scope>/CONTEXT.md` 或 `README.md`

只有在以下情况才允许回看 `history/` 最近 1 份：

- `latest.md` 缺失
- `latest.md` 已明显过期
- `latest.md` 的 `Expire When` 已触发

不要默认扫描整个 `history/` 目录。

## 先确定 scope

scope 优先级：

1. 用户显式指定 `--scope`
2. 用户显式指定 `--query` 且唯一命中 handoff
3. 最近更新、仍为 active 的 handoff
4. 若存在多个候选且无法判定，列出候选让用户选

`--scope` 会使用和 `sh-save` 相同的归一化规则。scope 不明确，或找不到对应 handoff / 项目上下文时，不要编造恢复结论。

## latest.md 是主入口

`sh-load` 默认读取的是 `<scope>/latest.md`，不是“时间最新的任意文件”。

原因：

- `latest.md` 表示当前可恢复状态
- `history/*.md` 只是阶段快照
- 最新快照未必是最适合恢复的入口

## 恢复简报输出格式

输出必须短、可执行、面向下一步。

建议结构：

```markdown
## 恢复简报

- 当前你在做：<当前目标>
- 上次已完成：<1-3 条关键进展>
- 仍然生效的决策：<1-3 条>
- 当前风险 / 待确认：<1-3 条>
- 建议下一步：<按优先级列 1-3 步>
- 先看文件：`<path>`、`<path>`
```

总长度尽量控制在 8 行内。

## 过期判断

以下任一条件命中时，降低 `latest.md` 权重或提示用户确认：

- handoff 已超过 7 天未更新
- `status` 不是 `active`
- `Expire When` 明确已满足

如果 handoff 过期，但项目上下文仍有效，可以继续基于项目上下文恢复，并明确说明 handoff 可能陈旧。

## 与长期层的关系

- `sh-load` 只读，不写
- 长期事实以 `knowledge/projects/` 或 `knowledge/resources/` 为准
- 短期 handoff 用于补充“上次做到哪了”和“下一步怎么接”

如果 handoff 与长期知识冲突：

1. 先提示冲突
2. 以更近期、且更明确的一侧为临时依据
3. 必要时建议后续执行 `kb-distill` 对齐长期层

## 不该做什么

不要：

- 读取整段 transcript
- 默认加载多个 scope
- 把全部历史快照串起来总结
- 在证据不足时臆造“上次状态”
- 因为没有 handoff 就输出空泛套话

## 没有 handoff 时的退化策略

如果 scope 下没有 `latest.md`：

1. 读取对应项目的 `CONTEXT.md` 或 `README.md`
2. 输出“基于长期上下文的恢复简报”
3. 明确说明：当前没有短期 handoff，建议本轮结束时执行一次 `sh-save`

## 完成后输出

说明：

1. 读取了哪个 scope
2. 用到了哪些来源
3. handoff 是否过期
4. 给出恢复简报

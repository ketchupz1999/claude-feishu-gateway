# 飞书消息卡片模板

## 1. Alert 告警卡片（红色）

用于重要事件的即时推送。

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": { "tag": "plain_text", "content": "🚨 告警" },
      "template": "red"
    },
    "elements": [
      {
        "tag": "markdown",
        "content": "**{title}**\n\n{detail}\n\n来源: {source}"
      },
      {
        "tag": "note",
        "elements": [
          { "tag": "plain_text", "content": "⏰ {timestamp}" }
        ]
      }
    ]
  }
}
```

## 2. Batch 批量更新卡片（橙色）

用于合并推送多条更新。

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": { "tag": "plain_text", "content": "📋 批量更新 ({count}条)" },
      "template": "orange"
    },
    "elements": [
      {
        "tag": "markdown",
        "content": "{items_markdown}"
      },
      {
        "tag": "note",
        "elements": [
          { "tag": "plain_text", "content": "汇总时间: {batch_time}" }
        ]
      }
    ]
  }
}
```

`{items_markdown}` 格式：
```
**1. {title}**
   {detail}

**2. {title}**
   {detail}
```

## 3. Brief 日报卡片（蓝色）

用于每日摘要推送。

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": { "tag": "plain_text", "content": "📊 {period}报 ({date})" },
      "template": "blue"
    },
    "elements": [
      {
        "tag": "markdown",
        "content": "{brief_content}"
      },
      {
        "tag": "hr"
      },
      {
        "tag": "note",
        "elements": [
          { "tag": "plain_text", "content": "生成时间: {date} | 来源: {filename}" }
        ]
      }
    ]
  }
}
```

`{period}` = 早 / 晚 / 日（根据文件名自动判断）
`{brief_content}` = 完整的 Markdown 摘要内容（飞书卡片支持 Markdown 子集）

## 4. Text 通用文本卡片（靛蓝色）

用于通用 Markdown / 纯文本推送。

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": { "tag": "plain_text", "content": "📨 {title}" },
      "template": "indigo"
    },
    "elements": [
      {
        "tag": "markdown",
        "content": "{content}"
      },
      {
        "tag": "hr"
      },
      {
        "tag": "note",
        "elements": [
          { "tag": "plain_text", "content": "发送时间: {datetime}" }
        ]
      }
    ]
  }
}
```

长内容会自动按段落拆分为多个 markdown 元素（飞书单元素最大约 4000 字符）。
表格超过 3 个会自动转为列表格式（飞书 v2 渲染限制）。

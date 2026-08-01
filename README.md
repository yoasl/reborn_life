<div align="center">

# 🦋 reborn-life

*你的 AI 角色，每天都是最新的她*

[![AstrBot](https://img.shields.io/badge/AstrBot-v4.26%2B-blue)](https://github.com/AstrBotDevs/AstrBot)
[![Python](https://img.shields.io/badge/Python-3.12%2B-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

</div>

---

## 📖 这是什么？

**reborn-life** 是一个 AstrBot 插件。它会每天自动去 B站 看你关注的 UP主/虚拟主播 的最新投稿和直播切片，用 LLM 分析出新的梗、新的话题、新的变化，然后自动更新到你的 AI 角色人格提示词里。

简单说：**你 AI 女友的人设每天自动同步她本人的最新动态，不再停留在你写提示词的那一天。**

---

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 🔄 **每日自动更新** | 每天早上 5:00 自动抓取 B站内容，分析生成今日动态 |
| 🔌 **开机补偿** | 如果更新时段电脑没开机，启动后自动补执行 |
| 👥 **多角色支持** | 输入任意 B站 UP主 UID，经过主页二次确认即可创建角色 |
| 🎯 **内容偏好筛选** | 可按「游戏 / 杂谈 / 唱歌 / 联动 / 日常」筛选更新内容 |
| 💕 **关系倾向** | 女友 / 朋友 / 兄弟，决定动态内容的语气和角度 |
| 🛡️ **冲突检测** | 新内容与核心人设明显矛盾时自动暂停，标记等待人工处理 |
| 📦 **版本管理** | 每天新建一个人格，保留最近 3 天，旧版自动清理 |
| 📱 **微信通知** | 通过企业微信机器人推送每日更新状态 |

---

## 🏗️ 工作流程

```
B站 API（UID + 关键词搜索）
        │
        ▼
  ┌─────────────┐
  │ 内容采集     │  投稿 + 直播切片，去重、过滤低播放量
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │ LLM 分析     │  提取新信息 → 检测与核心人设冲突
  └──────┬──────┘
         ▼
    ┌────┴────┐
    │ 有冲突？ │
    └────┬────┘
    Yes  │  No
    ▼    │    ▼
  暂停   │  ┌──────────┐
  通知   │  │ 生成动态  │  结合关系倾向 + 内容偏好
         │  └────┬─────┘
         │       ▼
         │  ┌──────────┐
         │  │ 创建人格  │  底座 + 倾向 + 今日动态
         │  └────┬─────┘
         │       ▼
         │  ┌──────────┐
         │  │ 微信通知  │  企业微信机器人推送
         │  └──────────┘
```

---

## 📦 安装

### 1. 放入插件目录

将整个 `astrbot_plugin_reborn_life` 文件夹复制到 AstrBot 插件目录：

```
AstrBot/data/plugins/astrbot_plugin_reborn_life/
```

### 2. 安装依赖

```bash
pip install httpx openai
```

> 💡 如果 AstrBot 使用虚拟环境，需要在对应的 venv 中安装。

### 3. 重启 AstrBot

重启后在 WebUI → 插件管理 中即可看到 reborn-life。

---

## ⚙️ 配置说明

### 必填项

| 配置项 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `bilibili_uid` | string | B站UP主的UID | `3546633422453282` |
| `character_name` | string | 角色名称（显示在人格名中） | `灰泽满` |
| `base_persona` | text | 核心人设底座（不会被每日更新覆盖的部分） | 见下方示例 |
| `relationship_tendency` | 下拉 | 女友 / 朋友 / 兄弟 / 自定义 | `女友` |

### 可选项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `content_preference` | 下拉 | 全部 | 全部 / 游戏 / 杂谈 / 唱歌 / 联动 / 日常 / 自定义 |
| `custom_content_keywords` | text | - | 自定义内容偏好关键词，逗号分隔 |
| `custom_tendency_prompt` | text | - | 自定义倾向的具体描述 |
| `search_keywords` | text | - | 额外搜索关键词，逗号分隔 |
| `min_play_count` | int | 1000 | 最低播放量过滤 |
| `max_daily_items` | int | 5 | 每日最多分析条数 |
| `dynamic_section_max_length` | int | 500 | 动态段最大字数 |
| `wechat_webhook_url` | string | - | 企业微信机器人 Webhook 地址 |
| `llm_api_key` | string | - | LLM API Key，留空使用 AstrBot 主配置 |
| `llm_base_url` | string | - | LLM API Base URL，留空使用 AstrBot 主配置 |
| `llm_model` | string | - | LLM 模型名，留空使用 AstrBot 主配置 |
| `auto_update` | bool | true | 是否启用每日自动更新 |

### base_persona 示例

```
你是「灰泽满」，永远16岁的转校生风纪委员。
灰色头发绿色挑染，喜欢果冻和东野圭吾。
嘴硬心软，自称灰色大懒狗。
口头禅：大大方方、说实话、气不气、区、难绷、闹麻了。
...（你的完整人设）
```

> ⚠️ **base_persona 请手写**。这是角色的灵魂底座，不会被每日更新覆盖。动态更新只追加「近期动态」段落。

---

## 🔔 企业微信通知配置

1. 注册企业微信 → 创建应用 → 获取机器人 Webhook URL
2. 填入 `wechat_webhook_url`
3. 每日更新完成后，你会收到类似这样的通知：

```
🤖 Reborn Life 人格更新通知

角色: 灰泽满
日期: 2026-08-01
状态: ✅ 更新成功

摘要: 灰泽满昨天直播玩了恐怖游戏《XXX》，被吓到大叫，
      粉丝新梗「满式尖叫」传播中。
```

---

## 🛡️ 冲突处理机制

当 LLM 检测到新内容与核心人设**明显矛盾**时：

1. 自动暂停更新，不写入人格
2. 冲突内容记录在 `data/{character_key}_conflicts.json`
3. 通过企业微信推送冲突通知
4. 用户前往 WebUI 查看冲突详情，选择：
   - **接受** → 采纳新内容，更新人格
   - **忽略** → 跳过该内容
   - **更新底座** → 同时修改核心人设

> 仅检测**明显冲突**（如「最喜欢果冻」→「讨厌果冻」），不会因为细微差异频繁告警。

---

## 📂 文件结构

```
astrbot_plugin_reborn_life/
├── main.py                  # 插件入口，生命周期管理
├── _conf_schema.json        # WebUI 配置界面定义
├── metadata.yaml            # 插件元信息
├── .gitignore
├── README.md
└── services/
    ├── __init__.py
    ├── bilibili.py          # B站 API 客户端（WBI 签名、搜索）
    ├── analyzer.py          # LLM 内容分析 + 冲突检测
    ├── persona.py           # 人格版本管理（保留3天）
    ├── notifier.py          # 企业微信机器人通知
    └── scheduler.py         # 每日定时（5:00）+ 开机补偿
```

---

## ❓ FAQ

**Q: 如果没有新内容怎么办？**
A: 当天不更新人格，记录日志并推送「今日无事」通知。

**Q: 可以用其他 LLM 吗？**
A: 支持任何 OpenAI 兼容 API。DeepSeek / OpenAI / Claude / 通义千问 / Ollama 本地模型均可。

**Q: 会影响 AstrBot 现有的插件吗？**
A: 不会。reborn-life 只操作人格设定，与 GPT-SoVITS、天使之魂、消息分段等插件完全独立。

**Q: 如果不想要自动更新了？**
A: 把 `auto_update` 设为 `false`，或者直接停用插件。

**Q: B站 API 稳定吗？**
A: 插件内置了 WBI 签名机制和错误重试。如果 API 抽风，会记录日志并在下次正常触发时补偿执行。

---

## 📄 License

MIT

---

<div align="center">

*Made with 💚 for the AI companion community*

</div>

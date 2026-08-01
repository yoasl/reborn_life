# Changelog

All notable changes to reborn-life will be documented in this file.

---

## [1.1.0] - 2026-08-01

### Added
- **Plugin Pages 控制台**：在 AstrBot WebUI → 插件 → reborn-life →「页面」中打开，包含四个面板：
  - 📊 状态概览：角色名、上次更新日期、冲突数、应用状态
  - 📝 今日动态：查看/编辑/应用每日生成的动态内容
  - ⚠️ 冲突处理：三选项（接受此更新 / 忽略 / 更新底座）
  - 📅 更新历史：查看历史人格更新记录
- **LLM 请求注入**：每次对话前自动将今日动态追加入系统提示词，不修改用户手写的核心人设底座
- **Web API 路由**：8 个 REST API 端点，支持前端控制台与后端交互
- **手动触发更新**：控制台内一键执行更新
- **动态编辑与应用**：可在控制台编辑生成的动态文本，手动点击应用后生效
- **冲突更新底座选项**：当角色核心人设发生永久变化时，可选择将新内容合并到底座

### Changed
- 主入口 `main.py` 从 ~290 行扩展至 ~490 行，新增 API 路由注册和 LLM 注入逻辑
- 运行时状态管理从纯文件存储改为内存+文件双轨

### Fixed
- 生命周期方法从 `__on_start__/__on_stop__` 改为 `initialize()/terminate()`，符合 AstrBot v4 插件规范（[#d7259c5](https://github.com/yoasl/reborn_life/commit/d7259c5)）
- `metadata.yaml` 中 `name` 从 `reborn-life` 改为 `reborn_life`，修复 Python 模块名非法字符问题（[#6713615](https://github.com/yoasl/reborn_life/commit/6713615)）
- 服务模块导入从绝对导入改为相对导入 `from .services.xxx`，修复 `No module named 'services'` 错误（[#12e5c15](https://github.com/yoasl/reborn_life/commit/12e5c15)）
- 新增根目录 `__init__.py`，使插件被 Python 正确识别为包
- 新增 `requirements.txt`，声明 `httpx>=0.28.0` 和 `openai>=2.0.0`

---

## [1.0.0] - 2026-07-31

### Added
- **每日自动更新人格**：基于 B站 UP主最新投稿和直播切片，每天早上 5:00 自动生成今日动态
- **开机补偿机制**：如果更新时段设备未运行，开机后自动补执行
- **多角色支持**：输入任意 B站 UP主 UID，通过主页信息二次确认
- **内容偏好筛选**：全部 / 游戏 / 杂谈 / 唱歌 / 联动 / 日常 / 自定义
- **关系倾向**：女友 / 朋友 / 兄弟 / 自定义，影响动态内容的语气
- **冲突检测**：LLM 分析新内容与核心人设是否明显矛盾，自动暂停并标记
- **版本管理**：每天新建人格，保留最近 3 天，旧版自动清理
- **企业微信通知**：通过 Webhook 推送每日更新状态
- **B站 API 集成**：WBI 签名认证、用户投稿列表、关键词搜索切片
- **WebUI 配置页**：12 个配置项，支持可视化参数调节

### Technical
- 项目架构：`Star` 基类插件，`services/` 模块化设计
- 技术栈：Python 3.12+、httpx、openai、FastAPI（AstrBot 内嵌）
- 数据存储：JSON 文件存储人格历史，`data/` 目录隔离运行时数据
- 调度器：基于 asyncio 的每日定时任务 + 开机补偿执行

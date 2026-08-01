"""
reborn-life —— 自动更新 AstrBot 人格提示词

基于B站UP主最新投稿和直播切片，每日同步角色最新动态到人格提示词。
"""

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path

from astrbot.api.event import AstrMessageEvent
from astrbot.api.event.filter import on_llm_request
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.web import json_response, error_response, request

from .services.bilibili import BilibiliClient
from .services.analyzer import ContentAnalyzer
from .services.persona import PersonaManager
from .services.notifier import WeChatNotifier
from .services.scheduler import DailyScheduler

PLUGIN_NAME = "reborn_life"


@register(
    PLUGIN_NAME,
    "jasen",
    "自动更新 AstrBot 人格提示词——基于B站UP主最新投稿和直播切片",
    "1.0.0",
)
class RebornLife(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)

        # ── 读取配置 ──
        self.bilibili_uid = config.get("bilibili_uid", "").strip()
        self.character_name = config.get("character_name", "").strip()
        self.base_persona = config.get("base_persona", "").strip()
        self.tendency = config.get("relationship_tendency", "女友")
        self.custom_tendency = config.get("custom_tendency_prompt", "").strip()
        self.preference = config.get("content_preference", "全部")
        self.custom_keywords = config.get("custom_content_keywords", "").strip()
        self.search_keywords_str = config.get("search_keywords", "").strip()
        self.min_play = int(config.get("min_play_count", 1000))
        self.max_items = int(config.get("max_daily_items", 5))
        self.dynamic_max_len = int(config.get("dynamic_section_max_length", 500))
        self.wechat_url = config.get("wechat_webhook_url", "").strip()
        self.auto_update = bool(config.get("auto_update", True))

        # ── LLM 配置 ──
        self.llm_api_key = config.get("llm_api_key", "").strip()
        self.llm_base_url = config.get("llm_base_url", "").strip()
        self.llm_model = config.get("llm_model", "").strip()

        if not self.llm_api_key:
            try:
                from astrbot.core.config import config as astr_config
                provider = astr_config.get("provider_settings", {}).get("default", {})
                self.llm_api_key = provider.get("api_key", "")
                self.llm_base_url = provider.get("api_base", "")
                self.llm_model = provider.get("model", "deepseek-chat")
            except Exception:
                pass

        # ── 数据目录 ──
        self.data_dir = Path(__file__).parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # ── 初始化服务 ──
        self.bilibili = BilibiliClient()
        self.persona_mgr = PersonaManager(self.data_dir)
        self.scheduler = DailyScheduler(self.data_dir)
        self.notifier = WeChatNotifier(self.wechat_url) if self.wechat_url else None

        self.analyzer = None
        if self.llm_api_key:
            self.analyzer = ContentAnalyzer(
                api_key=self.llm_api_key,
                base_url=self.llm_base_url or "https://api.deepseek.com/v1",
                model=self.llm_model or "deepseek-chat",
            )

        self._scheduler_task: asyncio.Task | None = None
        self.character_key = self._make_character_key()

        # ── 运行时状态 ──
        self._last_dynamic_text: str = ""
        self._last_dynamic_summary: str = ""
        self._last_dynamic_date: str = ""
        self._dynamic_applied: bool = False

        logger.info(f"[reborn-life] 插件已加载")
        logger.info(f"[reborn-life] 角色: {self.character_name} | UID: {self.bilibili_uid}")
        logger.info(f"[reborn-life] 倾向: {self.tendency} | 偏好: {self.preference}")
        logger.info(f"[reborn-life] 通知: {'已配置' if self.notifier else '未配置'}")
        logger.info(f"[reborn-life] LLM: {'已配置' if self.analyzer else '未配置'}")

    # ═══════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════

    def _make_character_key(self) -> str:
        """生成角色存储 key"""
        raw = f"{self.bilibili_uid}_{self.character_name}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _check_ready(self) -> bool:
        if not self.bilibili_uid:
            logger.warning("[reborn-life] 未配置 B站 UID，插件待机中")
            return False
        if not self.character_name:
            logger.warning("[reborn-life] 未配置角色名称，插件待机中")
            return False
        if not self.base_persona:
            logger.warning("[reborn-life] 未配置核心人设，插件待机中")
            return False
        if not self.analyzer:
            logger.warning("[reborn-life] LLM 未配置，插件待机中")
            return False
        return True

    # ═══════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════

    async def initialize(self):
        """插件启动时调用"""
        # 注册 Web API 路由
        self._register_web_apis()

        if not self._check_ready():
            return

        # 恢复上次已应用的动态内容
        latest = self.persona_mgr.get_latest_persona(self.character_key)
        if latest and latest.get("dynamic_text"):
            self._last_dynamic_text = latest["dynamic_text"]
            self._last_dynamic_summary = latest.get("summary", "")
            self._last_dynamic_date = latest.get("date", "")
            self._dynamic_applied = True
            logger.info(f"[reborn-life] 已恢复上次动态内容 ({self._last_dynamic_date})")

        # 开机补偿
        if self.auto_update and self.scheduler.should_run_today():
            logger.info("[reborn-life] 今日尚未更新，开机补偿执行...")
            await self._run_update_cycle()

        # 启动定时器
        if self.auto_update:
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())
            logger.info("[reborn-life] 调度器已启动，将在每日 5:00 执行更新")

    async def terminate(self):
        """插件停止时调用"""
        if self._scheduler_task:
            self._scheduler_task.cancel()
        await self.bilibili.close()

    # ═══════════════════════════════════════════════════
    # Web API 注册
    # ═══════════════════════════════════════════════════

    def _register_web_apis(self):
        """注册所有 Web API 路由"""
        ctx = self.context
        prefix = f"/{PLUGIN_NAME}"

        ctx.register_web_api(f"{prefix}/status", self.api_status, ["GET"], "获取当前状态")
        ctx.register_web_api(f"{prefix}/dynamic", self.api_get_dynamic, ["GET"], "获取今日动态内容")
        ctx.register_web_api(f"{prefix}/dynamic", self.api_update_dynamic, ["POST"], "编辑并保存动态内容")
        ctx.register_web_api(f"{prefix}/conflicts", self.api_get_conflicts, ["GET"], "获取待处理的冲突列表")
        ctx.register_web_api(f"{prefix}/conflicts/resolve", self.api_resolve_conflict, ["POST"], "处理冲突(accept/ignore/update_base)")
        ctx.register_web_api(f"{prefix}/history", self.api_get_history, ["GET"], "获取人格更新历史")
        ctx.register_web_api(f"{prefix}/rerun", self.api_rerun, ["POST"], "手动触发一次更新")
        ctx.register_web_api(f"{prefix}/apply", self.api_apply_dynamic, ["POST"], "应用当前动态到聊天中")

        logger.info(f"[reborn-life] Web API 路由已注册 ({prefix}/...)")

    # ═══════════════════════════════════════════════════
    # API: 状态
    # ═══════════════════════════════════════════════════

    async def api_status(self):
        """GET /reborn_life/status"""
        conflicts = self.persona_mgr.get_pending_conflicts(self.character_key)
        pending_conflicts = [c for c in conflicts if c.get("status") == "pending"]

        return json_response({
            "character_name": self.character_name,
            "bilibili_uid": self.bilibili_uid,
            "tendency": self.tendency,
            "preference": self.preference,
            "auto_update": self.auto_update,
            "today": datetime.now().strftime("%Y-%m-%d"),
            "last_dynamic_date": self._last_dynamic_date,
            "last_dynamic_summary": self._last_dynamic_summary,
            "dynamic_applied": self._dynamic_applied,
            "dynamic_available": bool(self._last_dynamic_text),
            "conflicts_pending": len(pending_conflicts),
            "analyzer_ready": self.analyzer is not None,
        })

    # ═══════════════════════════════════════════════════
    # API: 动态内容
    # ═══════════════════════════════════════════════════

    async def api_get_dynamic(self):
        """GET /reborn_life/dynamic"""
        return json_response({
            "date": self._last_dynamic_date,
            "summary": self._last_dynamic_summary,
            "text": self._last_dynamic_text,
            "applied": self._dynamic_applied,
        })

    async def api_update_dynamic(self):
        """POST /reborn_life/dynamic  ——  编辑动态文本"""
        try:
            body = await request.json()
        except Exception:
            return error_response("请求体不是有效的 JSON", 400)

        new_text = body.get("text", "").strip()
        if not new_text:
            return error_response("动态文本不能为空", 400)

        self._last_dynamic_text = new_text
        self._last_dynamic_summary = body.get("summary", "手动编辑")
        self._dynamic_applied = False

        logger.info("[reborn-life] 动态内容已手动编辑，待应用")

        return json_response({
            "ok": True,
            "message": "动态内容已保存，点击「应用」即可生效",
        })

    async def api_apply_dynamic(self):
        """POST /reborn_life/apply  ——  应用当前动态到聊天"""
        if not self._last_dynamic_text:
            return error_response("没有可应用的动态内容", 400)

        self._dynamic_applied = True

        # 更新 persona 存储
        today = datetime.now().strftime("%Y-%m-%d")
        self.persona_mgr.create_daily_persona(
            character_key=self.character_key,
            character_name=self.character_name,
            base_persona=self.base_persona,
            tendency=self.tendency,
            dynamic_text=self._last_dynamic_text,
            dynamic_summary=self._last_dynamic_summary,
        )
        self.persona_mgr.write_active_persona_file(self.character_key)
        self.scheduler.mark_completed()

        logger.info("[reborn-life] 动态内容已应用到聊天")

        return json_response({
            "ok": True,
            "message": "动态内容已应用，下次对话即可生效",
        })

    # ═══════════════════════════════════════════════════
    # API: 冲突
    # ═══════════════════════════════════════════════════

    async def api_get_conflicts(self):
        """GET /reborn_life/conflicts"""
        conflicts = self.persona_mgr.get_pending_conflicts(self.character_key)
        return json_response({"conflicts": conflicts, "total": len(conflicts)})

    async def api_resolve_conflict(self):
        """POST /reborn_life/conflicts/resolve  ——  body: {index, action}"""
        try:
            body = await request.json()
        except Exception:
            return error_response("请求体不是有效的 JSON", 400)

        idx = body.get("index", -1)
        action = body.get("action", "")

        if action not in ("accept", "ignore", "update_base"):
            return error_response("action 必须是 accept / ignore / update_base", 400)

        if action == "update_base":
            # 更新底座：把当前动态内容合并到 base_persona
            self._update_base_persona_with_conflict(idx)

        self.persona_mgr.resolve_conflict(self.character_key, idx, action)

        logger.info(f"[reborn-life] 冲突 #{idx} 已处理: {action}")

        return json_response({
            "ok": True,
            "action": action,
            "message": {
                "accept": "已接受此更新，下次更新时将纳入动态内容",
                "ignore": "已忽略此冲突",
                "update_base": "已将此内容合并到底座人设",
            }.get(action, f"已处理: {action}"),
        })

    def _update_base_persona_with_conflict(self, idx: int):
        """将冲突相关的新内容追加到底座"""
        conflicts = self.persona_mgr.get_pending_conflicts(self.character_key)
        if 0 <= idx < len(conflicts):
            conflict = conflicts[idx]
            detail = conflict.get("conflict_detail", "")
            # 追加到底座末尾
            append_note = f"\n\n[动态更新] {detail}"
            self.base_persona = self.base_persona.strip() + append_note
            logger.info(f"[reborn-life] 底座已更新，追加了冲突相关新内容")

    # ═══════════════════════════════════════════════════
    # API: 历史
    # ═══════════════════════════════════════════════════

    async def api_get_history(self):
        """GET /reborn_life/history"""
        history = self.persona_mgr.get_persona_history(self.character_key)
        # 只返回摘要，不返回完整人格文本
        simplified = []
        for entry in history:
            simplified.append({
                "date": entry.get("date", ""),
                "name": entry.get("name", ""),
                "summary": entry.get("summary", ""),
                "has_update": entry.get("has_update", False),
                "created_at": entry.get("created_at", ""),
            })
        return json_response({"history": simplified, "total": len(simplified)})

    # ═══════════════════════════════════════════════════
    # API: 手动触发
    # ═══════════════════════════════════════════════════

    async def api_rerun(self):
        """POST /reborn_life/rerun  ——  手动触发一次更新"""
        if not self._check_ready():
            return error_response("插件未就绪，请检查配置", 503)

        logger.info("[reborn-life] 收到手动触发更新请求")

        try:
            await self._run_update_cycle()
            return json_response({
                "ok": True,
                "message": "更新已完成",
                "summary": self._last_dynamic_summary,
            })
        except Exception as e:
            logger.error(f"[reborn-life] 手动更新失败: {e}")
            return error_response(f"更新失败: {str(e)[:200]}", 500)

    # ═══════════════════════════════════════════════════
    # LLM 请求注入（方案 A：安全注入，不碰原有人设）
    # ═══════════════════════════════════════════════════

    @on_llm_request
    async def on_llm_request_handler(self, event):
        """在每次 LLM 调用前，将今日动态追加入系统提示词"""
        if not self._dynamic_applied:
            return
        if not self._last_dynamic_text:
            return

        dynamic_block = f"\n\n# 近期动态（由 reborn-life 每日更新）\n{self._last_dynamic_text.strip()}\n\n# 时间感知\n当前日期：{datetime.now().strftime('%Y-%m-%d')}。请在对话中自然体现你对近期动态的了解。"

        # 尝试多种方式注入（兼容不同 AstrBot 版本）
        try:
            # 方式 1: 直接设置 system_prompt 属性
            if hasattr(event, "system_prompt"):
                event.system_prompt = (event.system_prompt or "") + dynamic_block
                return
        except Exception:
            pass

        try:
            # 方式 2: 通过 request 对象
            req = getattr(event, "req", None) or getattr(event, "request", None)
            if req and hasattr(req, "system_prompt"):
                req.system_prompt = (req.system_prompt or "") + dynamic_block
                return
        except Exception:
            pass

        try:
            # 方式 3: 通过 messages 列表
            messages = getattr(event, "messages", None)
            if messages and len(messages) > 0 and messages[0].get("role") == "system":
                messages[0]["content"] = (messages[0]["content"] or "") + dynamic_block
                return
        except Exception:
            pass

        logger.debug("[reborn-life] LLM 注入: 未找到可注入的 system_prompt 字段")

    # ═══════════════════════════════════════════════════
    # 调度循环
    # ═══════════════════════════════════════════════════

    async def _scheduler_loop(self):
        """调度主循环"""
        while True:
            try:
                triggered = await self.scheduler.wait_until_target_time(5, 0)
                if triggered and self.scheduler.should_run_today():
                    logger.info("[reborn-life] 到达更新时间，开始执行...")
                    await self._run_update_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[reborn-life] 调度器异常: {e}")
                await asyncio.sleep(600)

    # ═══════════════════════════════════════════════════
    # 核心更新逻辑
    # ═══════════════════════════════════════════════════

    async def _run_update_cycle(self):
        """执行一次完整的更新周期"""
        if not self._check_ready():
            return

        today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"[reborn-life] === {today} 更新开始 ===")

        # 1. 爬取内容
        search_kw = [k.strip() for k in self.search_keywords_str.split(",") if k.strip()]
        content_list = await self.bilibili.collect_daily_content(
            uid=self.bilibili_uid,
            character_name=self.character_name,
            extra_keywords=search_kw,
            min_play=self.min_play,
            max_items=self.max_items,
        )
        logger.info(f"[reborn-life] 爬取到 {len(content_list)} 条内容")

        if not content_list:
            await self._handle_no_content(today)
            return

        # 2. LLM 分析
        recent = self.persona_mgr.get_recent_dynamics(self.character_key)
        result = await self.analyzer.analyze(
            character_name=self.character_name,
            base_persona=self.base_persona,
            tendency=self.tendency,
            preference=self.preference,
            recent_dynamics=recent,
            content_list=content_list,
            custom_tendency_prompt=self.custom_tendency,
        )
        logger.info(f"[reborn-life] 分析完成: has_update={result.get('has_update')}")

        # 3. 冲突检测 —— 有了冲突暂停更新，等用户处理
        conflicts = result.get("conflicts", [])
        if conflicts:
            logger.warning(f"[reborn-life] 检测到 {len(conflicts)} 个冲突，暂停更新")
            self.persona_mgr.add_conflict(self.character_key, conflicts)

            # 仍然保存本次动态内容（但不自动应用）
            self._last_dynamic_text = result.get("dynamic_text", "")
            self._last_dynamic_summary = f"⚠️ 检测到 {len(conflicts)} 个冲突: {result.get('summary', '')}"
            self._last_dynamic_date = today
            self._dynamic_applied = False

            await self._notify(
                character_name=self.character_name,
                date=today,
                summary=f"检测到 {len(conflicts)} 个内容冲突，已暂停更新。请前往 WebUI → 插件 → reborn-life → 页面 处理。",
                dynamic_text="",
                has_conflict=True,
            )
            return

        # 4. 生成动态
        if not result.get("has_update") or not result.get("new_info"):
            await self._handle_no_content(today)
            return

        dynamic_text = await self.analyzer.generate_dynamic(
            character_name=self.character_name,
            tendency=self.tendency,
            new_info=result.get("new_info", []),
            max_length=self.dynamic_max_len,
        )

        # 5. 存储并自动应用
        self._last_dynamic_text = dynamic_text
        self._last_dynamic_summary = result.get("summary", "")
        self._last_dynamic_date = today
        self._dynamic_applied = True

        # 6. 写入 persona 存储
        self.persona_mgr.create_daily_persona(
            character_key=self.character_key,
            character_name=self.character_name,
            base_persona=self.base_persona,
            tendency=self.tendency,
            dynamic_text=dynamic_text,
            dynamic_summary=result.get("summary", ""),
        )
        self.persona_mgr.write_active_persona_file(self.character_key)

        # 7. 通知
        await self._notify(
            character_name=self.character_name,
            date=today,
            summary=result.get("summary", ""),
            dynamic_text=dynamic_text,
        )

        self.scheduler.mark_completed()
        logger.info(f"[reborn-life] === {today} 更新完成，已自动应用 ===")

    async def _handle_no_content(self, today: str):
        """无内容日"""
        logger.info(f"[reborn-life] {today} 今日无新内容，跳过更新")
        self.persona_mgr.create_daily_persona(
            character_key=self.character_key,
            character_name=self.character_name,
            base_persona=self.base_persona,
            tendency=self.tendency,
            dynamic_text="",
            dynamic_summary="今日无新内容",
        )
        await self._notify(
            character_name=self.character_name,
            date=today,
            summary="今日没有足够的新内容触发人格更新。",
            dynamic_text="",
        )
        self.scheduler.mark_completed()

    # ═══════════════════════════════════════════════════
    # 通知
    # ═══════════════════════════════════════════════════

    async def _notify(self, character_name: str, date: str, summary: str, dynamic_text: str, has_conflict: bool = False):
        """发送微信通知"""
        if self.notifier:
            try:
                await self.notifier.notify_update(
                    character_name=character_name,
                    date=date,
                    summary=summary,
                    dynamic_text=dynamic_text,
                    has_conflict=has_conflict,
                )
            except Exception as e:
                logger.error(f"[reborn-life] 通知发送失败: {e}")

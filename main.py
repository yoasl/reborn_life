"""
reborn-life —— 自动更新 AstrBot 人格提示词

基于B站UP主最新投稿和直播切片，每日同步角色最新动态到人格提示词。
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .services.bilibili import BilibiliClient
from .services.analyzer import ContentAnalyzer
from .services.persona import PersonaManager
from .services.notifier import WeChatNotifier
from .services.scheduler import DailyScheduler


@register(
    "reborn-life",
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

        # 如果没填 LLM 配置，尝试从 AstrBot 主配置中获取
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

        # 分析器在 LLM 配置就绪后初始化
        self.analyzer = None
        if self.llm_api_key:
            self.analyzer = ContentAnalyzer(
                api_key=self.llm_api_key,
                base_url=self.llm_base_url or "https://api.deepseek.com/v1",
                model=self.llm_model or "deepseek-chat",
            )

        self._scheduler_task: asyncio.Task | None = None
        self.character_key = self._make_character_key()

        logger.info(f"[reborn-life] 插件已加载")
        logger.info(f"[reborn-life] 角色: {self.character_name} | UID: {self.bilibili_uid}")
        logger.info(f"[reborn-life] 倾向: {self.tendency} | 偏好: {self.preference}")
        logger.info(f"[reborn-life] 通知: {'已配置' if self.notifier else '未配置'}")
        logger.info(f"[reborn-life] LLM: {'已配置' if self.analyzer else '未配置'}")

    def _make_character_key(self) -> str:
        """生成角色存储 key"""
        import hashlib
        raw = f"{self.bilibili_uid}_{self.character_name}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    # ═══════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════

    async def initialize(self):
        """插件启动时调用"""
        if not self._check_ready():
            return

        # 开机补偿：如果今天还没更新，立即执行
        if self.auto_update and self.scheduler.should_run_today():
            logger.info("[reborn-life] 今日尚未更新，开机补偿执行...")
            await self._run_update_cycle()

        # 启动定时器，等待明天早上 5 点
        if self.auto_update:
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())
            logger.info("[reborn-life] 调度器已启动，将在每日 5:00 执行更新")

    async def terminate(self):
        """插件停止时调用"""
        if self._scheduler_task:
            self._scheduler_task.cancel()
        await self.bilibili.close()

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
                await asyncio.sleep(600)  # 出错等10分钟再试

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

        # 3. 冲突检测
        conflicts = result.get("conflicts", [])
        if conflicts:
            logger.warning(f"[reborn-life] 检测到 {len(conflicts)} 个冲突")
            self.persona_mgr.add_conflict(self.character_key, conflicts)
            await self._notify(
                character_name=self.character_name,
                date=today,
                summary=f"检测到 {len(conflicts)} 个内容冲突，已暂停更新。请前往 WebUI 处理。",
                dynamic_text="",
                has_conflict=True,
            )
            self.scheduler.mark_completed()
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

        # 5. 创建人格
        entry = self.persona_mgr.create_daily_persona(
            character_key=self.character_key,
            character_name=self.character_name,
            base_persona=self.base_persona,
            tendency=self.tendency,
            dynamic_text=dynamic_text,
            dynamic_summary=result.get("summary", ""),
        )

        # 6. 输出激活文件
        self.persona_mgr.write_active_persona_file(self.character_key)

        # 7. 通知
        await self._notify(
            character_name=self.character_name,
            date=today,
            summary=result.get("summary", ""),
            dynamic_text=dynamic_text,
        )

        self.scheduler.mark_completed()
        logger.info(f"[reborn-life] === {today} 更新完成 ===")

    async def _handle_no_content(self, today: str):
        """无内容日：记录日志，不更新人格"""
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

    # ═══════════════════════════════════════════════════
    # 检查
    # ═══════════════════════════════════════════════════

    def _check_ready(self) -> bool:
        """检查配置是否就绪"""
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

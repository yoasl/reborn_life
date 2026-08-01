"""
人格版本管理模块
- 创建每日新人格
- 切换激活人格
- 清理过期人格（保留最近3天）
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class PersonaManager:
    """人格管理器 —— 通过文件系统管理人格数据"""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.persona_store = self.data_dir / "personas.json"
        self._ensure_store()

    def _ensure_store(self):
        if not self.persona_store.exists():
            self.persona_store.write_text("{}", encoding="utf-8")

    def _read_store(self) -> dict:
        try:
            return json.loads(self.persona_store.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_store(self, data: dict):
        self.persona_store.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_persona_history(self, character_key: str) -> list[dict]:
        """获取某角色的历史人格列表"""
        store = self._read_store()
        return store.get(character_key, [])

    def create_daily_persona(
        self,
        character_key: str,
        character_name: str,
        base_persona: str,
        tendency: str,
        dynamic_text: str,
        dynamic_summary: str,
    ) -> dict:
        """创建今天的完整人格"""
        today = datetime.now().strftime("%Y-%m-%d")

        # 倾向提示词映射
        tendency_prompts = {
            "女友": "\n\n# 关系定位\n你是对方的恋人。说话时带着亲密感和撒娇的意味，偶尔吃醋，会在意对方的一举一动。",
            "朋友": "\n\n# 关系定位\n你是对方的好朋友。说话轻松自然，可以开玩笑、吐槽，但保持朋友间的分寸感。",
            "兄弟": "\n\n# 关系定位\n你是对方的铁哥们/好兄弟。说话直来直去，可以互怼、互损，不拘小节。",
        }

        tendency_block = tendency_prompts.get(tendency, "")
        if tendency == "自定义":
            tendency_block = "\n\n# 关系定位\n（自定义倾向）"

        # 拼接完整人格
        dynamic_block = ""
        if dynamic_text.strip():
            dynamic_block = f"\n\n# 近期动态（更新于 {today}）\n{dynamic_text.strip()}"

        full_persona = f"""{base_persona.strip()}
{tendency_block.strip()}
{dynamic_block.strip()}

# 时间感知
当前日期：{today}。请在对话中自然体现你对近期动态的了解。"""

        persona_entry = {
            "date": today,
            "name": f"{character_name}_{today}",
            "summary": dynamic_summary,
            "dynamic_text": dynamic_text,
            "full_persona": full_persona,
            "has_update": bool(dynamic_text.strip()),
            "created_at": datetime.now().isoformat(),
        }

        # 写入存储
        store = self._read_store()
        history = store.get(character_key, [])
        history.insert(0, persona_entry)

        # 保留最近 3 天（+ 1 条无更新的记录）
        keep = []
        has_update_count = 0
        for entry in history:
            if entry["has_update"]:
                if has_update_count < 3:
                    keep.append(entry)
                    has_update_count += 1
            else:
                if len(keep) < 5:  # 无更新记录最多保留5条用于查日志
                    keep.append(entry)

        store[character_key] = keep
        self._write_store(store)

        return persona_entry

    def get_latest_persona(self, character_key: str) -> Optional[dict]:
        """获取最新人格"""
        history = self.get_persona_history(character_key)
        return history[0] if history else None

    def get_recent_dynamics(self, character_key: str) -> str:
        """获取近几天的动态摘要（用于分析时判断重复）"""
        history = self.get_persona_history(character_key)
        recent = []
        for entry in history[:3]:
            if entry.get("summary"):
                recent.append(f"[{entry['date']}] {entry['summary']}")
        return "\n".join(recent) if recent else ""

    def get_pending_conflicts(self, character_key: str) -> list[dict]:
        """获取待处理的冲突"""
        conflicts_file = self.data_dir / f"{character_key}_conflicts.json"
        if conflicts_file.exists():
            try:
                return json.loads(conflicts_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def add_conflict(self, character_key: str, conflicts: list[dict]):
        """添加冲突记录"""
        conflicts_file = self.data_dir / f"{character_key}_conflicts.json"
        existing = self.get_pending_conflicts(character_key)
        for c in conflicts:
            c["reported_at"] = datetime.now().isoformat()
            c["status"] = "pending"
        existing.extend(conflicts)
        conflicts_file.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def resolve_conflict(self, character_key: str, index: int, action: str):
        """处理冲突：accept / ignore / update_base"""
        conflicts = self.get_pending_conflicts(character_key)
        if 0 <= index < len(conflicts):
            conflicts[index]["status"] = action
            conflicts[index]["resolved_at"] = datetime.now().isoformat()
            conflicts_file = self.data_dir / f"{character_key}_conflicts.json"
            conflicts_file.write_text(
                json.dumps(conflicts, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def write_active_persona_file(self, character_key: str) -> Optional[Path]:
        """将最新人格写入一个固定文件，供 AstrBot 读取"""
        latest = self.get_latest_persona(character_key)
        if not latest:
            return None

        output_dir = self.data_dir / "active_personas"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"{character_key}.txt"
        output_file.write_text(latest["full_persona"], encoding="utf-8")
        return output_file

    def get_active_persona_text(self, character_key: str) -> Optional[str]:
        """获取当前激活人格的完整文本"""
        latest = self.get_latest_persona(character_key)
        return latest["full_persona"] if latest else None

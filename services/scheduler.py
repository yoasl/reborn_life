"""
每日调度模块
- 定时早上5点执行
- 开机补偿执行
- 避免重复执行
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path


class DailyScheduler:
    """每日任务调度器"""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "scheduler_state.json"
        self._running = False
        self._task: asyncio.Task | None = None

    def _read_state(self) -> dict:
        try:
            import json
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {"last_run_date": ""}

    def _write_state(self, state: dict):
        import json
        self.state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def should_run_today(self) -> bool:
        """检查今天是否已经执行过了"""
        state = self._read_state()
        today = datetime.now().strftime("%Y-%m-%d")
        return state.get("last_run_date") != today

    def mark_completed(self):
        """标记今日已执行"""
        self._write_state({"last_run_date": datetime.now().strftime("%Y-%m-%d")})

    async def wait_until_target_time(
        self,
        target_hour: int = 5,
        target_minute: int = 0,
        check_interval: int = 300,
    ) -> bool:
        """
        等待直到到达目标时间，或返回 False 表示被取消。
        如果在目标时间后启动，立即返回 True（补偿执行）。
        """
        now = datetime.now()
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

        if now >= target:
            # 今天的目标时间已过——如果在目标时间+1小时内，仍算正常窗口
            # 否则判断为「错过」，等明天
            diff_minutes = (now - target).total_seconds() / 60
            if diff_minutes <= 60 and self.should_run_today():
                return True  # 在窗口内，补偿执行
            # 已经过了窗口，等明天
            target = target.replace(day=target.day + 1)

        # 计算等待秒数
        wait_seconds = (target - datetime.now()).total_seconds()
        if wait_seconds <= 0:
            return self.should_run_today()

        # 分段等待，每 check_interval 秒检查一次
        while wait_seconds > 0:
            sleep_for = min(check_interval, int(wait_seconds))
            await asyncio.sleep(sleep_for)
            if not self._running:
                return False
            wait_seconds = (target - datetime.now()).total_seconds()

        return self.should_run_today()

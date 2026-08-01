"""
企业微信通知模块
"""

import httpx
import json


WECHAT_WEBHOOK_TEMPLATE = """## 🤖 Reborn Life 人格更新通知

**角色**: {character_name}
**日期**: {date}
**更新状态**: {status}

{details}

---
*reborn-life v1.0.0*"""


class WeChatNotifier:
    """企业微信机器人通知"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_markdown(self, content: str) -> bool:
        """发送 Markdown 格式消息"""
        if not self.webhook_url:
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                )
                return resp.json().get("errcode") == 0
        except Exception:
            return False

    async def send_text(self, content: str) -> bool:
        """发送纯文本消息（备用）"""
        if not self.webhook_url:
            return False

        payload = {
            "msgtype": "text",
            "text": {"content": content},
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                )
                return resp.json().get("errcode") == 0
        except Exception:
            return False

    async def notify_update(
        self,
        character_name: str,
        date: str,
        summary: str,
        dynamic_text: str,
        has_conflict: bool = False,
    ):
        """发送人格更新通知"""
        if has_conflict:
            status = "⚠️ 检测到冲突，已暂停更新"
            details = f"**摘要**: {summary}\n\n请前往 WebUI 查看并处理冲突内容。"
        elif not dynamic_text.strip():
            status = "📝 今日无事"
            details = "今日没有足够的新内容触发人格更新。"
        else:
            status = "✅ 更新成功"
            details = f"**摘要**: {summary}\n\n**今日动态**:\n{dynamic_text[:300]}"

        content = WECHAT_WEBHOOK_TEMPLATE.format(
            character_name=character_name,
            date=date,
            status=status,
            details=details,
        )

        # 先尝试 Markdown，失败则回退纯文本
        if not await self.send_markdown(content):
            plain = f"Reborn Life: {character_name} {date} {status}\n{summary}"
            await self.send_text(plain)

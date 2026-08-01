"""
B站数据采集模块
- 获取UP主投稿列表
- 搜索相关直播切片
- 过滤和排序内容
"""

import httpx
import hashlib
import time
import urllib.parse
from typing import Optional

BILIBILI_USER_VIDEOS = "https://api.bilibili.com/x/space/wbi/arc/search"
BILIBILI_SEARCH = "https://api.bilibili.com/x/web-interface/wbi/search/type"
BILIBILI_USER_INFO = "https://api.bilibili.com/x/space/wbi/acc/info"
BILIBILI_NAV = "https://api.bilibili.com/x/web-interface/wbi/index/top_feed"

# WBI 签名相关 —— 混音用的固定表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 52, 44, 34
]


def _get_mixin_key(raw_key: str) -> str:
    """根据原始 img_key + sub_key 计算 mixin key"""
    return "".join(raw_key[i] for i in MIXIN_KEY_ENC_TAB if i < len(raw_key))[:32]


def _wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    """对请求参数进行 WBI 签名"""
    mixin = _get_mixin_key(img_key + sub_key)
    params["wts"] = int(time.time())
    params = dict(sorted(params.items()))
    query = urllib.parse.urlencode(params)
    sign = hashlib.md5((query + mixin).encode()).hexdigest()
    params["w_rid"] = sign
    return params


class BilibiliClient:
    """B站 API 客户端"""

    def __init__(self):
        self._img_key: str = ""
        self._sub_key: str = ""
        self._key_ts: float = 0
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.bilibili.com",
                },
                timeout=30,
            )

    async def _refresh_wbi_keys(self):
        """刷新 WBI 签名密钥（每 4 小时更新一次）"""
        now = time.time()
        if now - self._key_ts < 14400 and self._img_key:
            return
        await self._ensure_client()
        try:
            resp = await self._client.get(BILIBILI_NAV)
            data = resp.json()["data"]
            self._img_key = data["wbi_img"]["img_url"].split("/")[-1].split(".")[0]
            self._sub_key = data["wbi_img"]["sub_url"].split("/")[-1].split(".")[0]
            self._key_ts = now
        except Exception:
            # 用一组备用 key
            self._img_key = "7cd084941338484aae1ad9425b84077c"
            self._sub_key = "4932caff0ff746eab6f01bf08b70ac45"

    async def get_user_info(self, uid: str) -> Optional[dict]:
        """获取用户基本信息（用于二次确认）"""
        await self._ensure_client()
        await self._refresh_wbi_keys()
        params = _wbi_sign({"mid": uid}, self._img_key, self._sub_key)
        try:
            resp = await self._client.get(BILIBILI_USER_INFO, params=params)
            data = resp.json()
            if data["code"] == 0:
                return data["data"]
        except Exception:
            pass
        return None

    async def get_user_videos(self, uid: str, page: int = 1, page_size: int = 10) -> list[dict]:
        """获取用户投稿视频列表"""
        await self._ensure_client()
        await self._refresh_wbi_keys()
        params = _wbi_sign(
            {"mid": uid, "ps": page_size, "pn": page, "order": "pubdate"},
            self._img_key,
            self._sub_key,
        )
        try:
            resp = await self._client.get(BILIBILI_USER_VIDEOS, params=params)
            data = resp.json()
            if data["code"] == 0:
                return data["data"]["list"]["vlist"]
        except Exception:
            pass
        return []

    async def search_clips(self, keyword: str, page: int = 1, page_size: int = 10) -> list[dict]:
        """搜索相关视频/切片"""
        await self._ensure_client()
        await self._refresh_wbi_keys()
        params = _wbi_sign(
            {
                "keyword": keyword,
                "search_type": "video",
                "page": page,
                "page_size": page_size,
                "order": "pubdate",
            },
            self._img_key,
            self._sub_key,
        )
        try:
            resp = await self._client.get(BILIBILI_SEARCH, params=params)
            data = resp.json()
            if data["code"] == 0:
                return data["data"]["result"]
        except Exception:
            pass
        return []

    async def collect_daily_content(
        self,
        uid: str,
        character_name: str,
        extra_keywords: list[str],
        min_play: int,
        max_items: int,
    ) -> list[dict]:
        """汇总每日内容：本人投稿 + 关键词搜索切片"""
        all_items: list[dict] = []

        # 1. 本人投稿
        videos = await self.get_user_videos(uid, page_size=max_items)
        for v in videos:
            if v.get("play", 0) >= min_play:
                all_items.append({
                    "title": v.get("title", ""),
                    "description": v.get("description", ""),
                    "play": v.get("play", 0),
                    "created": v.get("created", 0),
                    "type": "投稿",
                    "bvid": v.get("bvid", ""),
                })

        # 2. 搜索相关切片
        keywords = [character_name] + extra_keywords
        for kw in keywords:
            if not kw.strip():
                continue
            results = await self.search_clips(f"{kw.strip()} 切片", page_size=max_items)
            for r in results:
                if r.get("play", 0) >= min_play:
                    all_items.append({
                        "title": r.get("title", ""),
                        "description": r.get("description", ""),
                        "play": r.get("play", 0),
                        "created": r.get("pubdate", 0),
                        "type": "切片",
                        "bvid": r.get("bvid", ""),
                    })

        # 3. 去重 + 按时间排序 + 取前N条
        seen = set()
        unique = []
        for item in sorted(all_items, key=lambda x: x["created"], reverse=True):
            key = item["bvid"]
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique[:max_items]

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

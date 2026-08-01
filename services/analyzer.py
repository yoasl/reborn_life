"""
LLM 分析模块
- 分析B站内容，提取新信息
- 冲突检测
- 生成每日动态段
"""

import json
from typing import Optional
from openai import AsyncOpenAI


CONTENT_ANALYSIS_PROMPT = """你是一个角色信息分析师。你需要分析以下B站UP主/虚拟主播的最新内容，提取对角色扮演有价值的新信息。

## 角色
{character_name}

## 用户设定的关系倾向
{tendency}

## 用户设定的内容偏好
{preference}

## 当前核心人设（作为冲突检测基准）
{base_persona}

## 最近几天的动态（用于判断哪些是新信息）
{recent_dynamics}

## 今天爬取到的内容
{content_list}

## 任务
1. 判断今天的内容中，有哪些是**新的、值得更新到角色提示词中**的信息（新梗、新话题、新的联动、新的游戏、说话方式的变化等）
2. 检查这些新内容是否与**核心人设存在明显矛盾**（例如核心人设说喜欢果冻，但新内容中说讨厌果冻）
3. 如果没有有价值的更新，返回 has_update: false

## 输出格式（严格JSON）
```json
{
  "has_update": true/false,
  "summary": "一句话总结今日动态",
  "new_info": [
    "新信息1：具体描述",
    "新信息2：具体描述"
  ],
  "conflicts": [
    {
      "conflict_detail": "核心人设说XXX，但新内容显示YYY",
      "source_video": "冲突内容来源的视频标题"
    }
  ],
  "dynamic_text": "生成的今日动态段落，用于追加到人格提示词中。语气应符合关系倾向。约150-300字。"
}
```

只返回JSON，不要任何其他内容。"""


DYNAMIC_GENERATION_PROMPT = """你是一个角色提示词写手。请根据以下信息，生成一段简短的角色「近期动态」，用于追加到人格提示词中。

## 角色名
{character_name}

## 关系倾向
{tendency}

## 今日新信息
{new_info}

## 要求
- 约{max_length}字以内
- 用第一人称或符合角色的语气
- 自然融入角色的说话风格
- 只有真实的新信息，不要编造
- 如果信息不足以生成有意义的动态，返回空字符串

只返回动态文本，不要任何其他内容。"""


class ContentAnalyzer:
    """内容分析器"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = model

    async def analyze(
        self,
        character_name: str,
        base_persona: str,
        tendency: str,
        preference: str,
        recent_dynamics: str,
        content_list: list[dict],
        custom_tendency_prompt: str = "",
    ) -> dict:
        """分析内容，返回结构化结果"""
        # 格式化内容列表
        content_text = "\n".join(
            f"- [{item['type']}] {item['title']}\n  简介: {item['description'][:200]}\n  播放: {item['play']}"
            for item in content_list[:15]
        )

        tendency_full = tendency
        if tendency == "自定义" and custom_tendency_prompt:
            tendency_full = f"自定义: {custom_tendency_prompt}"

        prompt = CONTENT_ANALYSIS_PROMPT.format(
            character_name=character_name,
            tendency=tendency_full,
            preference=preference,
            base_persona=base_persona[-2000:],  # 截断以防过长
            recent_dynamics=recent_dynamics or "（无近期动态）",
            content_list=content_text or "（今日无新内容）",
        )

        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            raw = resp.choices[0].message.content or "{}"
            # 清理可能包裹的 markdown 代码块
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            return {
                "has_update": False,
                "summary": "分析解析失败",
                "new_info": [],
                "conflicts": [],
                "dynamic_text": "",
            }
        except Exception as e:
            return {
                "has_update": False,
                "summary": f"分析调用失败: {str(e)[:100]}",
                "new_info": [],
                "conflicts": [],
                "dynamic_text": "",
            }

    async def generate_dynamic(
        self,
        character_name: str,
        tendency: str,
        new_info: list[str],
        max_length: int = 500,
    ) -> str:
        """生成每日动态文本"""
        if not new_info:
            return ""

        tendency_full = tendency

        prompt = DYNAMIC_GENERATION_PROMPT.format(
            character_name=character_name,
            tendency=tendency_full,
            new_info="\n".join(f"- {info}" for info in new_info),
            max_length=max_length,
        )

        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=max_length * 2,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            return "\n".join(f"- {info}" for info in new_info)

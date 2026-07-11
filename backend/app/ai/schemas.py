"""各 AI 任务的结构化输出 Pydantic 模型。

约定（CLAUDE.md 硬性规则 5）：
- 所有 AI 输出必须定义 Pydantic schema，经 LLMClient.chat_structured 校验后才能使用；
- 一任务一模型，随对应里程碑添加（M4: AccountProfileOutput，M5: NextActionOutput，
  M6: ScriptRecommendOutput）。
"""

from typing import Literal

from pydantic import BaseModel, Field


class LeadScoringOutput(BaseModel):
    """线索 LLM 语义评分（映射为 0-60：intent 0-40 + 预算信号 10 + 紧迫度 0/5/10）。"""

    intent_score: int = Field(ge=0, le=40, description="意向强度 0-40")
    budget_signal: bool = Field(description="是否有明确预算信号")
    urgency: Literal["low", "medium", "high"] = Field(description="紧迫度")
    reasons: list[str] = Field(min_length=1, max_length=5, description="中文评分理由")

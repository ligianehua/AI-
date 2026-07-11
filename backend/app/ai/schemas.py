"""各 AI 任务的结构化输出 Pydantic 模型。

约定（CLAUDE.md 硬性规则 5）：
- 所有 AI 输出必须定义 Pydantic schema，经 LLMClient.chat_structured 校验后才能使用；
- 一任务一模型，随对应里程碑添加（M3: LeadScoreOutput，M4: AccountProfileOutput，
  M5: NextActionOutput，M6: ScriptRecommendOutput）。
"""

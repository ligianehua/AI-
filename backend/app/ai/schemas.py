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


class DecisionChainItem(BaseModel):
    contact: str = Field(description="联系人姓名（必须来自已知联系人列表）")
    role: str = Field(description="在采购决策中的角色")
    attitude: str = Field(description="对合作的态度判断")


class NextActionItem(BaseModel):
    action: str = Field(min_length=1, description="具体可执行的下一步动作")
    reason: str = Field(min_length=1, description="理由，必须引用真实跟进内容")
    suggested_script_scenario: (
        Literal["opening", "discovery", "objection", "pricing", "closing", "retention"] | None
    ) = Field(default=None, description="建议使用的话术场景（可跳转话术生成），无则为 null")


class NextActionOutput(BaseModel):
    """商机 AI 下一步建议：正好 3 条。"""

    actions: list[NextActionItem] = Field(min_length=3, max_length=3)


class AccountProfileOutput(BaseModel):
    """客户 AI 画像（PLAN §6.2 结构）。信息不足必须明说，禁止编造。"""

    company_overview: str = Field(min_length=1, description="公司概况")
    pain_points: list[str] = Field(description="痛点，无依据则为空列表")
    decision_chain: list[DecisionChainItem] = Field(description="决策链，只含已知联系人")
    cooperation_stage_analysis: str = Field(min_length=1, description="合作阶段分析")
    risks: list[str] = Field(description="风险")
    suggestions: list[str] = Field(min_length=1, description="行动建议")
    confidence_note: str = Field(min_length=1, description="置信说明，须注明依据的跟进记录条数")


class ContractExtractOutput(BaseModel):
    """合同要素抽取（M10）。全字符串字段：合同写法千奇百怪，不强行 parse 数字/日期；
    原文未提及的字段必须填「未提及」，禁止编造。"""

    party_a: str = Field(min_length=1, description="甲方名称，未提及填「未提及」")
    party_b: str = Field(min_length=1, description="乙方名称，未提及填「未提及」")
    amount: str = Field(
        min_length=1, description="合同金额原文（含币种/大小写），未提及填「未提及」"
    )
    period: str = Field(min_length=1, description="服务期/合同期限原文，未提及填「未提及」")
    sign_date: str = Field(min_length=1, description="签署日期原文，未提及填「未提及」")
    payment_terms: list[str] = Field(description="付款约定条目（原文措辞），无则空列表")
    other_key_terms: list[str] = Field(
        description="其他关键条款摘要（违约/保密/验收等），无则空列表"
    )
    confidence_note: str = Field(min_length=1, description="抽取置信说明，注明哪些字段原文未提及")


class ContractRiskItem(BaseModel):
    clause_quote: str = Field(min_length=1, description="风险条款原文引用（截取关键句）")
    level: Literal["high", "medium", "low"] = Field(description="风险等级")
    issue: str = Field(min_length=1, description="问题说明")
    suggestion: str = Field(min_length=1, description="修改建议")


class ContractReviewOutput(BaseModel):
    """合同风险审查（M10）：对照检查清单比对。输出是提示不是结论，不构成法律意见。"""

    risks: list[ContractRiskItem] = Field(description="发现的风险条款，无则空列表")
    missing_clauses: list[str] = Field(description="清单中缺失的关键条款（如「未约定违约责任」）")
    overall_note: str = Field(min_length=1, description="总体提示（一两句，须提醒经法务审核）")


class PerformanceInsightOutput(BaseModel):
    """业绩月度归因解读（M12）。只引用输入中的数字，数据不足必须明说。"""

    summary: str = Field(min_length=1, description="一段话总结本月表现（引用关键数字）")
    findings: list[str] = Field(min_length=1, max_length=5, description="归因发现，须引用输入数字")
    suggestions: list[str] = Field(min_length=1, max_length=4, description="下月行动建议")

"""领域枚举。数据库存字符串，边界（Pydantic/service）做校验。"""

from enum import StrEnum


class Role(StrEnum):
    SALES = "sales"
    MANAGER = "manager"
    ADMIN = "admin"


class LeadSource(StrEnum):
    WEBSITE = "website"
    EXHIBITION = "exhibition"
    REFERRAL = "referral"
    ADS = "ads"
    COLD_CALL = "cold_call"
    DISCOVERY = "discovery"  # 线索发现（M8：Places 抓取候选池领取）
    OTHER = "other"


class CandidateStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    IGNORED = "ignored"


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    INVALID = "invalid"


class OpportunityStage(StrEnum):
    INITIAL = "initial"
    NEED_CONFIRMED = "need_confirmed"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


# 阶段 → 默认赢单概率（可手改）
STAGE_DEFAULT_PROBABILITY: dict[OpportunityStage, int] = {
    OpportunityStage.INITIAL: 10,
    OpportunityStage.NEED_CONFIRMED: 30,
    OpportunityStage.PROPOSAL: 50,
    OpportunityStage.NEGOTIATION: 70,
    OpportunityStage.WON: 100,
    OpportunityStage.LOST: 0,
}


class ContactRoleInDeal(StrEnum):
    DECISION_MAKER = "decision_maker"
    INFLUENCER = "influencer"
    USER = "user"
    GATEKEEPER = "gatekeeper"


class ActivityRelatedType(StrEnum):
    LEAD = "lead"
    ACCOUNT = "account"
    OPPORTUNITY = "opportunity"


class ActivityType(StrEnum):
    CALL = "call"
    VISIT = "visit"
    WECHAT = "wechat"
    EMAIL = "email"
    MEETING = "meeting"
    OTHER = "other"


class ScriptCategory(StrEnum):
    OPENING = "opening"
    DISCOVERY = "discovery"
    OBJECTION = "objection"
    PRICING = "pricing"
    CLOSING = "closing"
    RETENTION = "retention"


class KnowledgeDocStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ContractStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ProductStatus(StrEnum):
    ACTIVE = "active"  # 在售
    EOL = "eol"  # 停产（替代挖掘的重点对象）
    DRAFT = "draft"  # 草稿（抽取入库待人工确认）


class LlmTaskType(StrEnum):
    PING = "ping"  # 冒烟
    LEAD_SCORING = "lead_scoring"
    ACCOUNT_PROFILE = "account_profile"
    NEXT_ACTION = "next_action"
    SCRIPT_GEN = "script_gen"
    CHAT = "chat"  # M9 通用助手
    CONTRACT_EXTRACT = "contract_extract"  # M10 合同要素抽取
    CONTRACT_REVIEW = "contract_review"  # M10 合同风险审查
    PERFORMANCE_INSIGHT = "performance_insight"  # M12 业绩归因解读
    PRODUCT_EXTRACT = "product_extract"  # M13 规格书结构化抽取
    PRODUCT_COMPARE = "product_compare"  # M13 产品对比差异总结
    PRODUCT_ADVISOR = "product_advisor"  # M14 产品咨询对话
    EMBEDDING = "embedding"


class LlmCallStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


class NotificationType(StrEnum):
    STALE_NO_FOLLOWUP = "stale_no_followup"
    STAGE_STUCK = "stage_stuck"
    NEXT_ACTION_DUE = "next_action_due"

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    """工作台摘要（按当前用户可见域统计）。金额单位 CNY。"""

    lead_count: int
    account_count: int
    opportunity_count: int
    pipeline_amount: float  # 在途商机金额（未赢单/输单）

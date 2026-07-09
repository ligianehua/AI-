"""种子数据：2 团队 + 4 用户（admin/manager/2×sales）+ 50 线索 + 客户/联系人/商机/跟进记录。

用法：uv run python -m scripts.seed（需先 make migrate）
幂等：users 表已有数据时直接跳过。
"""

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.core.security import hash_password
from app.models import Account, Activity, Contact, Lead, Opportunity, Team, User
from app.models.enums import (
    STAGE_DEFAULT_PROBABILITY,
    ActivityRelatedType,
    ActivityType,
    ContactRoleInDeal,
    LeadSource,
    LeadStatus,
    OpportunityStage,
    Role,
)

random.seed(42)

COMPANIES = [
    "杭州云帆科技",
    "上海蓝湾信息",
    "北京华创智联",
    "深圳启航软件",
    "广州潮流数码",
    "苏州恒星制造",
    "南京博远医疗",
    "成都天府物流",
    "武汉长江能源",
    "西安丝路教育",
    "重庆山城零售",
    "青岛海洋食品",
    "天津港湾贸易",
    "宁波东方模具",
    "无锡精工机械",
    "长沙星城传媒",
    "郑州中原建材",
    "合肥科大智能",
    "福州闽江电子",
    "厦门鹭岛旅游",
]
INDUSTRIES = ["制造业", "互联网", "金融", "医疗", "教育", "零售", "物流", "能源"]
REGIONS = ["华东", "华北", "华南", "西南", "华中"]
SIZES = ["1-50人", "51-200人", "201-500人", "500人以上"]
PERSONS = [
    "王伟",
    "李娜",
    "张磊",
    "刘洋",
    "陈静",
    "杨帆",
    "赵鑫",
    "黄丽",
    "周杰",
    "吴敏",
    "徐强",
    "孙芳",
    "马超",
    "朱婷",
    "郭涛",
    "何雪",
    "高翔",
    "林悦",
    "郑凯",
    "谢婷",
]
TITLES = ["总经理", "采购总监", "IT 经理", "运营总监", "财务经理", "技术负责人"]
REQUIREMENTS = [
    "希望上一套 CRM 系统管理销售过程，目前用 Excel 管理效率太低",
    "咨询销售数据分析方案，管理层需要看 pipeline 报表",
    "有 200 人的销售团队，需要线索分配和业绩考核工具",
    "对 AI 话术推荐感兴趣，想先试用",
    "需要客户管理 + 合同管理一体化方案，预算大概 20 万",
    "老系统要替换，正在对比几家供应商",
    "刚成立销售部门，想要一套轻量的管理工具",
    "总部要求数字化转型，销售管理是第一步",
]
ACTIVITY_CONTENTS = [
    "电话沟通了产品功能，客户对 AI 评分很感兴趣，约了下周演示",
    "上门拜访，见到了采购总监，对方要求提供详细报价单",
    "微信发送了产品资料和案例，客户说内部讨论后回复",
    "线上会议演示了系统，客户提出需要支持钉钉集成",
    "客户反馈价格偏高，希望有折扣，已上报审批",
    "跟进合同条款，法务提出两处修改意见",
    "客户老板出差，决策推迟到下月",
    "发送了 POC 测试账号，客户 IT 部门开始试用",
]

NOW = datetime.now(UTC)


def _phone() -> str:
    return "1" + random.choice("35789") + "".join(random.choices("0123456789", k=9))


async def seed(session: AsyncSession) -> None:
    settings = get_settings()

    user_count = await session.scalar(select(func.count()).select_from(User))
    if user_count:
        print(f"users 表已有 {user_count} 条数据，跳过 seed（如需重灌请先清库）")
        return

    team_east = Team(name="华东销售部")
    team_north = Team(name="华北销售部")
    session.add_all([team_east, team_north])
    await session.flush()

    default_hash = hash_password("password123")
    admin = User(
        name="系统管理员",
        email=settings.admin_email,
        hashed_password=hash_password(settings.admin_password),
        role=Role.ADMIN,
    )
    manager = User(
        name="张经理",
        email="manager@example.com",
        hashed_password=default_hash,
        role=Role.MANAGER,
        team_id=team_east.id,
    )
    sales1 = User(
        name="李小销",
        email="sales1@example.com",
        hashed_password=default_hash,
        role=Role.SALES,
        team_id=team_east.id,
    )
    sales2 = User(
        name="王大售",
        email="sales2@example.com",
        hashed_password=default_hash,
        role=Role.SALES,
        team_id=team_north.id,
    )
    session.add_all([admin, manager, sales1, sales2])
    await session.flush()
    sales_owners = [sales1, sales1, sales2]  # 华东数据多一些

    # 客户 + 联系人
    accounts: list[Account] = []
    for i, company in enumerate(COMPANIES[:12]):
        owner = sales_owners[i % len(sales_owners)]
        account = Account(
            name=company,
            industry=random.choice(INDUSTRIES),
            size=random.choice(SIZES),
            region=random.choice(REGIONS),
            website=f"https://www.example-{i}.cn",
            remark="种子数据",
            owner_id=owner.id,
        )
        accounts.append(account)
        session.add(account)
    await session.flush()

    for account in accounts:
        for _ in range(random.randint(1, 3)):
            session.add(
                Contact(
                    account_id=account.id,
                    name=random.choice(PERSONS),
                    title=random.choice(TITLES),
                    phone=_phone(),
                    wechat=f"wx_{uuid.uuid4().hex[:8]}",
                    email=f"{uuid.uuid4().hex[:8]}@corp.example.cn",
                    role_in_deal=random.choice(list(ContactRoleInDeal)).value,
                )
            )

    # 商机
    opportunities: list[Opportunity] = []
    for _ in range(15):
        account = random.choice(accounts)
        stage = random.choices(list(OpportunityStage), weights=[25, 20, 20, 15, 10, 10], k=1)[0]
        entered = NOW - timedelta(days=random.randint(5, 90))
        opp = Opportunity(
            account_id=account.id,
            name=f"{account.name}-销售管理系统采购",
            amount=Decimal(random.randrange(80_000, 1_500_000, 10_000)),
            stage=stage,
            probability=STAGE_DEFAULT_PROBABILITY[stage],
            expected_close_date=(NOW + timedelta(days=random.randint(10, 120))).date(),
            owner_id=account.owner_id,
            lost_reason="预算削减，明年再谈" if stage == OpportunityStage.LOST else None,
            stage_history=[
                {
                    "stage": stage.value,
                    "entered_at": entered.isoformat(),
                    "by": "seed",
                }
            ],
        )
        opportunities.append(opp)
        session.add(opp)
    await session.flush()

    # 线索（部分标记已转化并回链客户）
    leads: list[Lead] = []
    for i in range(50):
        owner = sales_owners[i % len(sales_owners)]
        status = random.choices(list(LeadStatus), weights=[40, 30, 15, 10, 5], k=1)[0]
        converted_account = random.choice(accounts) if status == LeadStatus.CONVERTED else None
        score = None if status == LeadStatus.NEW and i % 3 == 0 else random.randint(20, 92)
        lead = Lead(
            source=random.choice(list(LeadSource)).value,
            account_name=f"{random.choice(COMPANIES)}分公司{i + 1}",
            contact_name=random.choice(PERSONS),
            contact_phone=_phone(),
            contact_wechat=f"wx_{uuid.uuid4().hex[:8]}",
            industry=random.choice(INDUSTRIES),
            requirement_desc=random.choice(REQUIREMENTS),
            status=status,
            score=score,
            score_detail=(
                {
                    "rule_score": random.randint(10, 40),
                    "intent_score": random.randint(10, 52),
                    "reasons": ["信息完整度较高", "需求描述明确（种子数据示例）"],
                }
                if score is not None
                else None
            ),
            owner_id=owner.id,
            converted_account_id=converted_account.id if converted_account else None,
        )
        leads.append(lead)
        session.add(lead)
    await session.flush()

    # 跟进记录（挂 lead / account / opportunity）
    for _ in range(30):
        kind = random.choice(list(ActivityRelatedType))
        if kind == ActivityRelatedType.LEAD:
            target_id, owner_id = (lambda x: (x.id, x.owner_id))(random.choice(leads))
        elif kind == ActivityRelatedType.ACCOUNT:
            target_id, owner_id = (lambda x: (x.id, x.owner_id))(random.choice(accounts))
        else:
            target_id, owner_id = (lambda x: (x.id, x.owner_id))(random.choice(opportunities))
        has_next = random.random() < 0.5
        session.add(
            Activity(
                related_type=kind.value,
                related_id=target_id,
                type=random.choice(list(ActivityType)).value,
                content=random.choice(ACTIVITY_CONTENTS),
                next_action="电话回访确认进展" if has_next else None,
                next_action_date=(
                    (NOW + timedelta(days=random.randint(-3, 10))).date() if has_next else None
                ),
                owner_id=owner_id,
            )
        )

    await session.commit()
    print("seed 完成：")
    print("  团队 2 个：华东销售部 / 华北销售部")
    print(f"  admin:   {settings.admin_email} / {settings.admin_password}")
    print("  manager: manager@example.com / password123（华东）")
    print("  sales:   sales1@example.com / password123（华东）")
    print("  sales:   sales2@example.com / password123（华北）")
    print(f"  客户 {len(accounts)} / 商机 {len(opportunities)} / 线索 {len(leads)} / 跟进 30")


async def main() -> None:
    async with get_sessionmaker()() as session:
        await seed(session)
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())

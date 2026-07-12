"""灌入示例话术（12 条，六类各 2 条）——仅供演示。

上线硬性要求（PLAN §6.4 / §10）：业务方必须灌入 ≥50 条 top sales 真实话术，
垃圾进垃圾出，示例话术不能替代真实沉淀。

用法：uv run python -m scripts.seed_scripts
"""

import asyncio

from sqlalchemy import func, select

from app.core.db import get_engine, get_sessionmaker
from app.models.script import Script
from app.models.user import User
from app.tasks import dispatcher

SAMPLES: list[tuple[str, str, str, list[str]]] = [
    (
        "opening",
        "初次电话开场",
        "王总您好，我是XX科技的小李。占用您一分钟——我们最近帮几家和贵司同行业的企业把销售跟单效率提升了 30%，想约个 15 分钟给您看看他们具体怎么做的，您看本周四下午方便吗？",
        ["电话", "首次触达"],
    ),
    (
        "opening",
        "展会后微信破冰",
        "张总，我是昨天展会上聊 CRM 的小李。您提到销售过程不透明的问题我们回来讨论了下，有两个现成的解法案例，整理了一页纸发您，不打扰您开会～",
        ["微信", "展会"],
    ),
    (
        "discovery",
        "挖掘管理痛点",
        "冒昧问一下，咱们销售同事现在每天花在填报表、汇报进度上的时间大概多久？很多客户测算后发现这块能省出 1-2 小时——您觉得团队目前最大的时间黑洞在哪儿？",
        ["提问", "痛点"],
    ),
    (
        "discovery",
        "确认决策流程",
        "为了给您做一份贴合的方案，想确认下：这类工具的选型一般是您这边定，还是需要 IT 和财务一起评估？大概什么时间点希望用起来？",
        ["决策链", "预算"],
    ),
    (
        "objection",
        "客户嫌贵-价值拆解",
        "理解您的顾虑。咱们换个算法：按 20 个销售算，每人每天省 1 小时，一年就是 5000+ 小时——系统一年的费用还不到这些时间成本的十分之一。而且我们可以先小团队试点，效果达标再全面铺开，把风险降到最低。",
        ["价格异议", "ROI"],
    ),
    (
        "objection",
        "已有竞品-差异化",
        "您在用的那家其实不错，很多客户也是从那边过来的。他们迁移主要有两个原因：一是销售嫌录入麻烦不愿用，二是报表出不来管理层要的视角。这两点恰好是我们做得最重的地方，方便的话我 10 分钟给您演示下区别。",
        ["竞品", "替换"],
    ),
    (
        "pricing",
        "报价后跟进",
        "李总，报价单发您三天了，想听听您这边的真实反馈——如果是预算问题，我们可以聊聊分期或者裁剪模块；如果是功能顾虑，我约产品同事给您答疑。您更关心哪块？",
        ["报价", "跟进"],
    ),
    (
        "pricing",
        "折扣申请话术",
        "价格上我确实只有 5 个点的权限，不过如果您这边本月能定，我可以帮您向上申请一个年度客户的特殊价，再送 3 个月服务期。您看值得我去争取一下吗？",
        ["折扣", "促单"],
    ),
    (
        "closing",
        "推动签约",
        "王总，方案、价格咱们都对齐了，团队也试用满意。我建议这周把合同走起来——月底前签的话还能赶上这一期的实施排期，晚了就要等下个月了。我今天把合同发您法务？",
        ["签约", "临门一脚"],
    ),
    (
        "closing",
        "决策拖延-制造紧迫",
        "完全理解需要内部再对一轮。只是提醒下：您提到 9 月要用起来，倒推的话实施加培训要 4 周，本月中旬前定下来才来得及。需要我出一页给领导汇报用的决策摘要吗？",
        ["拖延", "时间线"],
    ),
    (
        "retention",
        "老客户续约",
        "陈总，咱们系统用了快一年，后台看您团队的活跃度在客户里排前 10%。续约期到了，今年续的话价格保持不变，另外新上的 AI 话术功能给您免费开通——约个时间给团队做个新功能培训？",
        ["续约", "增购"],
    ),
    (
        "retention",
        "沉默客户唤醒",
        "赵总，注意到咱们团队最近登录少了，是遇到什么使用问题了吗？我安排客户成功同事这周做一次免费的使用健康检查，顺便把你们没用起来的自动化功能配置好——很多客户配完活跃度直接翻倍。",
        ["唤醒", "客户成功"],
    ),
]


async def main() -> None:
    async with get_sessionmaker()() as session:
        existing = int(await session.scalar(select(func.count()).select_from(Script)) or 0)
        if existing:
            print(f"scripts 表已有 {existing} 条，跳过")
            return
        admin = await session.scalar(select(User).where(User.role == "admin"))
        if admin is None:
            print("请先运行 seed（需要 admin 用户）")
            return
        scripts = [
            Script(category=c, scenario=s, content=content, tags=tags, created_by=admin.id)
            for c, s, content, tags in SAMPLES
        ]
        session.add_all(scripts)
        await session.commit()
        for script in scripts:
            await dispatcher.enqueue("embed_script_task", str(script.id))
        # local 模式下等后台嵌入任务跑完（无 key 时会各自失败并留日志，不阻塞）
        await asyncio.sleep(2)
        print(f"已灌入 {len(scripts)} 条示例话术（嵌入任务已排队；无 API key 时走关键词检索）")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())

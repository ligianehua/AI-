"""菲律宾市场英文话术库（100 条）：场景标题中文（检索用），正文英文（直接发客户）。

用法：uv run python -m scripts.seed_scripts_ph
幂等：按场景标题查重，已存在跳过；插入后批量生成向量（标题+正文，与生产索引一致）。
"""
# ruff: noqa: E501  # 话术正文为完整英文段落，不做行宽切割

import asyncio

from sqlalchemy import func, select

from app.ai.client import LLMClient
from app.core.db import get_engine, get_sessionmaker
from app.models.script import Script
from app.models.user import User

# (category, 场景标题, 英文正文, tags)
PH_SCRIPTS: list[tuple[str, str, str, list[str]]] = [
    # ================= 开场破冰 opening（18） =================
    (
        "opening",
        "陌生电话开场-30秒破冰",
        "Hi Sir Miguel, this is Anna from BrightCRM. I know you're busy so I'll keep this under 30 seconds — we recently helped two distribution companies in Cebu cut missed follow-ups by half. Would you be open to a quick 15-minute call this week to see if it fits your team?",
        ["cold-call", "phone"],
    ),
    (
        "opening",
        "LinkedIn 破冰-同行案例",
        "Hi Ms. Reyes, I came across your post about scaling your sales team in NCR. We work with several retail suppliers here — one grew repeat orders 25% after fixing their follow-up process. Happy to share how they did it, no strings attached. Open to connect?",
        ["linkedin", "social-selling"],
    ),
    (
        "opening",
        "展会后跟进-Viber",
        "Hi Sir John, this is Paolo — we met at the Manila Business Expo yesterday, booth near the escalator. You mentioned your agents keep client records in notebooks. I put together a one-pager showing how similar teams went digital in 2 weeks. Sending it here on Viber, no pressure po.",
        ["viber", "event-followup"],
    ),
    (
        "opening",
        "转介绍开场",
        "Hi Ma'am Santos, Dennis Lim from Golden Harvest Trading suggested I reach out — he mentioned you're growing your dealer network this year. We helped his team track 300+ dealers without adding headcount. Would a short intro call make sense?",
        ["referral", "phone"],
    ),
    (
        "opening",
        "邮件开场-高管版",
        "Subject: Question about your sales team's follow-up rate\n\nDear Mr. Tan,\n\nMost sales directors we meet in Metro Manila tell us 30-40% of leads go cold simply because no one followed up on time. If that number sounds familiar, I'd like to show you how three companies in your industry fixed it — 20 minutes, your calendar. Would Tuesday or Thursday work?\n\nRespectfully,",
        ["email", "executive"],
    ),
    (
        "opening",
        "守门人沟通-争取转接",
        "Good morning po! This is Carla from BrightCRM. I'm hoping you can help me — I have a short note for Sir Ramon about the sales tracking issue his team raised at the industry forum last month. Would he prefer I send it through you, or is there a good time to catch him directly?",
        ["gatekeeper", "phone"],
    ),
    (
        "opening",
        "BPO 行业开场",
        "Hi Ms. Garcia, congrats on the new delivery site in Clark! Scaling client-facing teams that fast usually strains account tracking. We support several BPO account management teams — happy to share what works. Coffee or a quick video call next week?",
        ["bpo", "industry"],
    ),
    (
        "opening",
        "零售连锁行业开场",
        "Hi Sir Chua, I noticed you're opening two more branches in Visayas this quarter. Multi-branch sales visibility is exactly what we solve — one FMCG distributor now sees all branch pipelines in one screen, updated daily. 15 minutes to show you how?",
        ["retail", "industry"],
    ),
    (
        "opening",
        "地产行业开场",
        "Hi Ms. Villanueva, tripping schedules, agent follow-ups, buyer requirements — most developers we meet track all of this in group chats and it breaks past 50 units. We helped a Cavite developer cut booking-to-reservation time by a third. Worth a short demo?",
        ["real-estate", "industry"],
    ),
    (
        "opening",
        "华商企业开场-关系导向",
        "Hi Sir Go, my principal asked me to reach out personally — we've been working with a few family-run trading businesses in Binondo, and the owners like that the system lets them see every salesman's activity without asking. If you're open to it, I'd be glad to visit your office at your convenience. We can also converse in Mandarin or Hokkien if easier po.",
        ["chinese-filipino", "visit"],
    ),
    (
        "opening",
        "老客户推荐的新联系人",
        "Hi Ma'am Dela Cruz, your colleague Sir Marco from the Davao branch has been using our system for 8 months — he suggested you might want the same visibility for your Luzon team. He said, and I quote, 'ask her to see the Monday dashboard.' May I show you what he meant?",
        ["referral", "internal"],
    ),
    (
        "opening",
        "断联线索重新激活",
        "Hi Sir Bautista, we spoke back in March about sales tracking — you asked me to circle back after your peak season. Season's done (hope it was a good one!), so as promised: still happy to show you that 15-minute demo. This week or next?",
        ["reactivation", "phone"],
    ),
    (
        "opening",
        "WhatsApp 首触-简短版",
        "Hi Sir Cruz! Anna here from BrightCRM 😊 Saw your company's hiring post for 5 more sales staff — growing team, growing follow-ups! We help PH sales teams keep every lead tracked. OK to send a 1-minute video of how it works?",
        ["whatsapp", "short"],
    ),
    (
        "opening",
        "行业报告切入",
        "Hi Ms. Ramos, we just published a short study on why PH distributors lose repeat orders — the #1 reason surprised most of the 40 sales managers we surveyed (it's not price). Happy to send you the 2-page summary. If it resonates, let's talk; if not, keep it with my compliments.",
        ["content", "email"],
    ),
    (
        "opening",
        "Q4 预算季切入",
        "Hi Sir Fernandez, many of our clients finalize next year's tools budget before the 13th-month payout crunch in December. If upgrading your sales tracking is on the list, this is the right month to evaluate — implementation before January means your team starts the year on the new system. Shall I send a proposal outline?",
        ["budget-season", "timing"],
    ),
    (
        "opening",
        "跟进无回复的第二封邮件",
        "Subject: Re: Question about your sales team's follow-up rate\n\nHi Mr. Tan, I know inboxes get buried — no worries at all. One-line version of my last note: we help sales teams stop losing leads to missed follow-ups, and I'd love 15 minutes to show you how. If now's not the right time, just reply 'Q1' and I'll reach out then. Salamat po!",
        ["email", "followup"],
    ),
    (
        "opening",
        "活动邀约开场",
        "Hi Ms. Aquino, we're hosting a small breakfast roundtable in BGC next Thursday — 12 sales leaders from distribution and retail, sharing how they run their pipelines. No sales pitch, just practitioners talking. One seat left at the table; shall I reserve it for you?",
        ["event", "invitation"],
    ),
    (
        "opening",
        "食品分销行业开场",
        "Hi Sir Uy, between wet market accounts, supermarket chains, and food service clients, your salesmen probably juggle very different order cycles. We built route-and-account tracking that one Bulacan food distributor now uses across 18 salesmen. Can I show you their before-and-after?",
        ["food-distribution", "industry"],
    ),
    # ================= 需求挖掘 discovery（16） =================
    (
        "discovery",
        "确认决策流程",
        "Just so I prepare the right materials — for a tool like this, would the decision sit with you, or would Finance and IT also weigh in? And is there a target month you'd want the team fully onboarded?",
        ["qualification", "decision-process"],
    ),
    (
        "discovery",
        "现状痛点挖掘-跟进遗漏",
        "Walk me through what happens after a trade show: your team collects, say, 80 calling cards — where do those go, and how many would you estimate actually get a follow-up call within the week? ...And how many of those 80 would you guess turn into quotes today?",
        ["pain-discovery", "questioning"],
    ),
    (
        "discovery",
        "量化损失",
        "Let's put a number on it: if your average deal is ₱150K and even two leads a month slip through the cracks, that's ₱3.6M a year walking away — more than 10x the cost of fixing the process. Does that math track with what you're seeing?",
        ["quantify", "roi"],
    ),
    (
        "discovery",
        "现有工具摸底",
        "How does the team track deals today — Excel, Google Sheets, group chat, or the classic notebook? And when you need this month's pipeline total, how long does it take to get an answer you trust?",
        ["current-state", "tools"],
    ),
    (
        "discovery",
        "多分支可见度",
        "With branches in Manila, Cebu, and Davao — when the GM asks 'how's Visayas doing this month,' what does it take to answer? Real-time, or does someone have to make calls and consolidate a deck first?",
        ["multi-branch", "visibility"],
    ),
    (
        "discovery",
        "销售流失风险",
        "Sensitive question, but important: when a salesman resigns, what happens to his accounts? Have you ever lost customers because the relationships — and the records — walked out the door with him?",
        ["turnover-risk", "data-ownership"],
    ),
    (
        "discovery",
        "决策人痛点-老板视角",
        "As the owner, what keeps you up at night more: not knowing if the team is really making their calls, or knowing the calls happen but not what was promised to customers? Both are fixable — but the fix looks different.",
        ["owner", "pain-discovery"],
    ),
    (
        "discovery",
        "预算与时间预期",
        "To make sure I propose something realistic: do you have a range in mind for tools like this — say, per-user per-month? And is this a 'this quarter' decision or an 'after peak season' one? Honest answers save us both time po.",
        ["budget", "timeline"],
    ),
    (
        "discovery",
        "试探竞品评估",
        "Are you looking at other options as well? Totally fair if so — I'd rather help you compare properly than have you decide on incomplete information. What matters most in your shortlist: price, ease of use for the salesmen, or local support?",
        ["competition", "qualification"],
    ),
    (
        "discovery",
        "使用者阻力预判",
        "Your salesmen are the ones who'll live in this every day. Have they pushed back on tools before? The #1 killer of CRM projects here isn't the software — it's salesmen who feel it's surveillance. Let me show you how other PH teams got buy-in instead.",
        ["adoption", "change-management"],
    ),
    (
        "discovery",
        "客户报表需求",
        "When you report to your principal or the board, what numbers do they ask for that are painful to produce today? If I can show those exact reports generated in one click, would that move the discussion forward?",
        ["reporting", "stakeholder"],
    ),
    (
        "discovery",
        "旺季瓶颈挖掘",
        "During your peak months — Christmas season for you, right? — what breaks first: order taking, follow-ups, or collections? Peak season exposes the cracks; that's usually where we start.",
        ["peak-season", "bottleneck"],
    ),
    (
        "discovery",
        "增长计划对齐",
        "You mentioned adding 5 salesmen next year. At your current way of working, will the manager still be able to coach and check everyone weekly at 15 people? Most teams tell us the system breaks between 8 and 12.",
        ["scaling", "growth"],
    ),
    (
        "discovery",
        "催款流程摸底",
        "How do you track collections follow-ups today? A few of our clients found their DSO dropped by a week just because the system reminds salesmen which invoices to chase — is collections part of your sales team's job here?",
        ["collections", "process"],
    ),
    (
        "discovery",
        "需求优先级排序",
        "If I could only fix ONE thing for you in the next 30 days — missed follow-ups, pipeline visibility, or activity tracking — which one would make your December board meeting easier? Let's start there and expand later.",
        ["prioritization", "mvp"],
    ),
    (
        "discovery",
        "IT 顾虑预判",
        "Before your IT team asks: data is hosted securely, exportable anytime in Excel, and access is role-based — the owner sees everything, salesmen see only their own accounts. What else would IT want to know? I'd rather answer now than stall at the last step.",
        ["it-security", "objection-prevention"],
    ),
    # ================= 异议处理 objection（20） =================
    (
        "objection",
        "客户嫌贵-价值拆解",
        "I understand, Sir — let's do the math together. With 10 salesmen, if each saves just 30 minutes a day on updates and reminders, that's 100+ hours a month back into selling. The subscription costs less than one-tenth of that time's value. And we can start with just your 3 senior salesmen to prove it before you commit the whole team.",
        ["price", "value"],
    ),
    (
        "objection",
        "我们有Excel就够了",
        "Excel is honestly fine at 3 salesmen — most of our clients started there. The problem shows up when you're at 8+: files get overwritten, nobody updates on time, and you can't see who's slipping until month-end. What broke for the teams that switched wasn't Excel — it was waiting too long to leave it.",
        ["excel", "status-quo"],
    ),
    (
        "objection",
        "销售人员会抵触",
        "Valid concern — salesmen hate anything that feels like surveillance. Here's what changes their mind: the app reminds them who to call so they close more, and closers earn more commission. One client's top salesman went from resisting to demanding it when he realized he'd stopped losing repeat orders. Want me to do the team orientation myself? I do it in Taglish, keeps it light.",
        ["adoption", "resistance"],
    ),
    (
        "objection",
        "已在用竞品",
        "That's actually a good sign — it means your team already values tracking. May I ask what's working well and what's frustrating? Most who switch to us cite two things: our local support responds same-day, and salesmen actually use ours because it's simpler on mobile. If your current tool is doing its job, keep it — but a side-by-side demo costs you nothing.",
        ["competitor", "switching"],
    ),
    (
        "objection",
        "今年没预算了",
        "Understood — budgets are budgets. Two thoughts: first, if we sign within the year at this quarter's pricing, implementation can start January against next year's budget. Second, some clients start with a small pilot — 3 users — that fits under discretionary spending. Either path locks today's rate. Which is more workable?",
        ["budget", "timing"],
    ),
    (
        "objection",
        "要和合伙人商量",
        "Of course — decisions like this should be aligned. To help that conversation: would it be useful if I prepared a one-page summary in numbers your partner cares about — cost, payback period, and what two similar companies achieved? Even better, bring them to a 15-minute demo; I'll answer the hard questions directly so you don't have to relay.",
        ["decision-maker", "stall"],
    ),
    (
        "objection",
        "太忙没时间上系统",
        "That busyness is exactly the symptom, Sir. Teams that are 'too busy' are usually busy with chasing updates and rebuilding lost information. Setup takes our team 2 weeks, and yours spends maybe 3 hours total in orientation. One month later you get those hours back every single week. When's your least crazy week this month?",
        ["time", "implementation"],
    ),
    (
        "objection",
        "担心数据安全",
        "Fair question. Your data sits in an encrypted cloud database, backed up daily, and — this matters — it's YOUR data: export everything to Excel anytime, no lock-in, no hostage clause. Compare that to today: your customer records live in resigned employees' phones and personal notebooks. Which is riskier po?",
        ["security", "data"],
    ),
    (
        "objection",
        "以前上过系统失败了",
        "Thank you for telling me — that history matters. May I ask what killed it? (Usually: nobody enforced usage, or the tool was too complicated.) Our onboarding addresses both: we train the manager to run Monday meetings FROM the system, so usage isn't optional — it's how work happens. If the old wound was different, tell me and I'll address it straight.",
        ["past-failure", "trust"],
    ),
    (
        "objection",
        "菲律宾网络不稳定",
        "Totally real concern, especially for field salesmen in the provinces. The mobile app works offline — visits and orders sync automatically when signal returns. Your salesman in Batangas can log everything at the client's warehouse basement and it uploads on the drive back. Want me to demo airplane mode right now?",
        ["connectivity", "offline"],
    ),
    (
        "objection",
        "价格再打折才考虑",
        "I'll be straight with you, Sir: my discount authority is 5%, and I've given it. What I CAN do: if you decide within the month, I'll request annual-client pricing from my manager plus 3 months extended support — that's worth more than another 5%. But I need a real commitment to bring to him, not a maybe. Fair?",
        ["discount", "negotiation"],
    ),
    (
        "objection",
        "系统太复杂学不会",
        "The average age of salesmen at our Pampanga client is 47, and their adoption rate is 90% — because the daily flow is 3 taps: who to visit, what happened, next step. If your team can use Facebook and GCash, they can use this. And orientation is in Taglish, not tech-speak. Bring your most stubborn salesman to the demo — if he can't use it, I'll say so myself.",
        ["complexity", "usability"],
    ),
    (
        "objection",
        "先试用免费版再说",
        "We don't have a permanent free tier — honest reason: free users don't get onboarding, fail quietly, and blame the tool. What we do instead: 30-day pilot with full setup and training for 3 users, and if you don't continue, you pay nothing and keep your data export. Skin in the game on both sides. Deal?",
        ["free-trial", "pilot"],
    ),
    (
        "objection",
        "问了IT说自己能开发",
        "Your IT team probably can build a basic version — in 6-12 months, plus maintenance forever, plus the mobile app, plus offline sync... Most in-house CRM projects here die at 70% done when the developer resigns. Question for you: is building sales software your company's business? Buying takes 2 weeks and costs less than one month of a developer's salary per year.",
        ["build-vs-buy", "it"],
    ),
    (
        "objection",
        "经济不好要缩减开支",
        "Understood — everyone's tightening. Consider this angle though: in a slow market, you can't afford to lose the few leads you DO get. Our clients who kept the system through slow quarters say it paid for itself in saved leads alone. If cash flow is the issue, we can do quarterly billing instead of annual. Would that help?",
        ["economy", "cashflow"],
    ),
    (
        "objection",
        "客户资料不想放云端",
        "May I ask what specifically worries you — access, leakage, or government requests? Here's the reality check: your data currently lives in salesmen's personal Viber chats and home laptops, with zero audit trail. Our cloud gives you role-based access, activity logs, and instant lockout when someone resigns. The cloud isn't the risk — untracked copies are.",
        ["cloud", "security"],
    ),
    (
        "objection",
        "等新办公室搬迁后再说",
        "Makes sense to avoid chaos — but here's a thought: teams actually love launching the system DURING transitions, because the move already disrupts routines. New office, new system, one adjustment period instead of two. Plus your customer data stays stable while everything else moves. Can I pencil a setup for two weeks after your move date?",
        ["timing", "stall"],
    ),
    (
        "objection",
        "让我先和销售团队开会讨论",
        "Good instinct — forced tools fail. Suggestion: instead of describing it to them secondhand, give me 20 minutes at your next sales meeting. I'll demo the salesman's view — the part that helps THEM earn more — and take their hardest questions. If the team says no after that, I'll accept it gracefully. When's the next meeting?",
        ["team-buy-in", "stall"],
    ),
    (
        "objection",
        "报价比预算高出一截",
        "Thanks for the transparency — knowing your number helps. Three options: trim to core modules and add later (fits your budget now), keep full scope with quarterly payments, or start with 5 users instead of 10. What I'd rather not do is discount the full package below sustainable support levels — cheap and abandoned is worse than right-sized. Which option fits?",
        ["budget-gap", "options"],
    ),
    (
        "objection",
        "疫情后业务还没恢复",
        "Understood, and no pressure. One observation from clients in the same spot: recovery mode is when follow-up discipline matters most — fewer inquiries means each one is precious. That's why we built the 3-user starter plan. When business is back, you scale. Would a small start make sense, or shall I check back in a quarter — your call.",
        ["recovery", "empathy"],
    ),
    # ================= 价格谈判 pricing（16） =================
    (
        "pricing",
        "报价后跟进",
        "Hi Sir Lim, the proposal's been with you three days — I'd rather hear a hard question than silence po. If it's the price, let's talk structure — quarterly billing or trimmed modules. If it's a feature concern, I'll get you a direct answer from our product team. Which is it?",
        ["followup", "proposal"],
    ),
    (
        "pricing",
        "折扣申请话术",
        "Here's where I stand: 5% is my ceiling. But if you can commit within the month, I'll personally request our annual-client rate from management plus 3 months added support — worth about 12% in real terms. I can't promise they'll approve, but I've got a good record when the client is ready to sign. Are you?",
        ["discount", "urgency"],
    ),
    (
        "pricing",
        "对比竞品报价低",
        "Their quote is lower — true. Ask them two questions: is onboarding and training included (ours is), and what's their support response time (ours is same-day, Manila hours, in Taglish). Clients who switched to us from cheaper tools spent more in year one on 'consulting fees' than the price difference. Cheap software with no adoption is the most expensive kind.",
        ["competitor-price", "tco"],
    ),
    (
        "pricing",
        "打包年付优惠",
        "Two ways to structure this: monthly at ₱X per user, cancel anytime — or annual at 2 months free, effectively 17% off, plus priority support. 80% of our clients pick annual after the pilot proves out. Given you've already seen the pilot results, want me to draft the annual?",
        ["annual", "packaging"],
    ),
    (
        "pricing",
        "拆分模块降低门槛",
        "The full suite feels like a lot? Let's right-size: start with lead tracking and follow-up reminders — that's the part fixing your biggest leak. Skip the analytics module for now; add it when the data's flowing. That brings entry cost down 40% and you upgrade only when you see value. Sound fair?",
        ["modular", "downsize"],
    ),
    (
        "pricing",
        "涨价前锁定",
        "One transparency note: our pricing adjusts 8% for new contracts starting January — cloud costs, peso movement, the usual. Anyone who signs this quarter locks the current rate for 24 months. I'm not saying this to pressure you; I'm saying it because you'd be rightly annoyed if you found out after.",
        ["price-increase", "urgency"],
    ),
    (
        "pricing",
        "免费加送替代降价",
        "Instead of cutting price — which I honestly can't do further — let me add value: I'll include the WhatsApp integration module free for year one, plus two extra training sessions for new hires. That's ₱40K of value versus the ₱15K discount you're asking. Better deal, and my manager actually approves it. Yes?",
        ["value-add", "negotiation"],
    ),
    (
        "pricing",
        "分期付款方案",
        "Cash flow concern noted — common in distribution where your money sits in receivables. We can do quarterly billing at no premium, or monthly at 5%. One client pays quarterly timed to their collection cycles. What timing matches YOUR cash rhythm?",
        ["payment-terms", "cashflow"],
    ),
    (
        "pricing",
        "按人头计费的疑虑",
        "Fair question on per-user pricing 'punishing growth.' Flip it: you only pay for value received — 5 users today, not the 15 you might have someday. And volume discounts kick in at 10 and 20 users, so the per-head cost DROPS as you grow. Your finance team will like that the cost scales with revenue capacity.",
        ["per-user", "scaling"],
    ),
    (
        "pricing",
        "谈判僵局-暂缓策略",
        "We're ₱20K apart and both firm — rather than force it today, here's my suggestion: run the 30-day pilot at pilot pricing. If the results hit the targets we agree on paper, you sign at my number. If they don't, walk away clean. I'm betting on my product; all you're betting is 30 days. Deal?",
        ["deadlock", "pilot"],
    ),
    (
        "pricing",
        "采购部压价应对",
        "I respect that pressing suppliers is Procurement's job — you'd be failing yours if you didn't ask. Here's my honest floor: below this number, we make it up by cutting onboarding hours, and then adoption fails and you churn in a year. Nobody wins. What I CAN move: payment terms, extra licenses, training. Where would flexibility actually help you?",
        ["procurement", "negotiation"],
    ),
    (
        "pricing",
        "小客户预算方案",
        "For a 3-person sales team, the full package is overkill — honestly. Take the Starter plan: core tracking, mobile app, ₱X/month flat. It's what sari-sari-to-supermarket distributors start with. When you hit 8 salesmen, upgrade and your data carries over seamlessly. Start small, start now.",
        ["sme", "starter"],
    ),
    (
        "pricing",
        "价格保密请求",
        "Happy to sharpen the pencil for you, one ask in return: this rate stays between us. I'm giving you the best number in your industry segment because of the referral path you came through — if it circulates, I lose the ability to do special cases at all. Gentleman's agreement po?",
        ["confidential", "special-rate"],
    ),
    (
        "pricing",
        "ROI 计算展示",
        "Let's build your business case in 3 lines: (1) You quoted 4 lost deals a month at avg ₱120K — even saving HALF of that is ₱240K/month recovered. (2) System cost: ₱18K/month all-in. (3) Payback: first week of month one. I'll put this exact math in the proposal for your partner. Any number you'd challenge?",
        ["roi", "business-case"],
    ),
    (
        "pricing",
        "客户拿旧报价压价",
        "You're right that March's quote was lower — two things changed: that promo bundled fewer onboarding hours, and pricing adjusted in June. What I can do: honor the March onboarding hours at today's rate, splitting the difference. What I can't do is time-travel po. Shall we close it at that?",
        ["old-quote", "negotiation"],
    ),
    (
        "pricing",
        "预算周期错位处理",
        "Your fiscal year starts April — noted. Structure that works: sign now, we invoice 20% this quarter (fits discretionary), balance invoiced April 1 against the new budget. You get implementation done during your slow months and launch fully trained into the new fiscal year. Your finance head will appreciate the clean split.",
        ["fiscal-year", "structuring"],
    ),
    # ================= 促成交 closing（15） =================
    (
        "closing",
        "推动签约-排期紧迫",
        "Sir Ong, we've aligned on scope, price, and the pilot results — your team literally asked when they get their logins. Here's the practical bit: our January implementation slots are down to two. Sign this week and you're onboarded before Chinese New Year; wait, and we're looking at March. Shall I send the contract to your legal today?",
        ["urgency", "schedule"],
    ),
    (
        "closing",
        "决策拖延-制造紧迫",
        "Totally understand needing another internal round. One flag: you mentioned wanting the team live before June's trade show — working backwards, that means training in May, setup in April, signing this month. I can hold your slot until Friday. Want me to prepare a one-page decision summary for your boss to make the internal round faster?",
        ["stall", "deadline"],
    ),
    (
        "closing",
        "试点转正式",
        "The 30-day pilot numbers are in: follow-up rate went from 60% to 92%, and your senior salesman closed two reactivated accounts worth ₱380K. That's the proof you asked for. The pilot rate expires with the pilot — full contract at the agreed number, effective Monday. Ready to make it official?",
        ["pilot-conversion", "results"],
    ),
    (
        "closing",
        "假设成交法",
        "So for rollout: would you want all 10 salesmen onboarded in one batch, or start with the Luzon team first and Visayas two weeks after? Either way I'll assign Carla as your dedicated onboarding lead — she's handled three distribution clients. Which rollout suits your calendar?",
        ["assumptive", "rollout"],
    ),
    (
        "closing",
        "二选一成交法",
        "Two ways to start: Standard plan with annual billing — best economics — or Starter with quarterly billing if you want lighter commitment. Both include full onboarding. Honestly, for your team size I'd take Standard annual, but you know your cash flow. Which one do we paper?",
        ["alternative-close", "options"],
    ),
    (
        "closing",
        "打消最后顾虑",
        "Before you sign, let me name the risks out loud: if adoption fails, you're stuck paying — so we tied a 60-day adoption guarantee into the contract: under 70% weekly active use and you can exit with a refund of unused months. I want you renewing because it works, not because a contract traps you. Any other worry I should address in writing?",
        ["risk-reversal", "guarantee"],
    ),
    (
        "closing",
        "老板在场的临门一脚",
        "Sir, your sales manager has verified the product, your accountant has verified the math, and the pilot verified the results. The only signature that matters now is yours. What single question, answered right now, would let you sign today? Ask it — I'll answer it straight, and if my answer disappoints, we shake hands and part friends.",
        ["owner", "direct"],
    ),
    (
        "closing",
        "合同条款让步收尾",
        "Recap of where we landed: annual plan, quarterly billing, WhatsApp module free for year one, and the 60-day adoption guarantee. That's every concession I have — and honestly more than my manager was thrilled about. If this package works, let's sign before someone up there changes their mind. 😊 Send the contract?",
        ["final-terms", "close"],
    ),
    (
        "closing",
        "沉默施压后的收网",
        "I've said my piece, so I'll be quiet after this question: is there anything BETWEEN us and a signature today — or are we done deliberating and just need to do the paperwork? ...If it's the latter, the contract takes me 10 minutes to send and you 5 to sign po.",
        ["silence", "direct"],
    ),
    (
        "closing",
        "多决策人会签推进",
        "Since Sir Tan approves budget and Ma'am Lee owns operations, let's not relay through email chains — I'll host a 20-minute closing call with both, walk the final terms, answer everything live, and if all nods, DocuSign goes out same day. Their calendars: Thursday 10am or Friday 3pm?",
        ["multi-stakeholder", "closing-call"],
    ),
    (
        "closing",
        "年底冲刺优惠收尾",
        "December reality: my quarter closes on the 20th, and I want your logo in it — so here's my best-and-final, valid till then: 12 months for the price of 10, onboarding before New Year, training scheduled around your Christmas parties. After the 20th it reverts, not because I'm playing games but because Finance closes the promo. Your move, Sir. 🎄",
        ["year-end", "deadline"],
    ),
    (
        "closing",
        "从口头同意到书面",
        "I'm thrilled you're in, Sir — and I've learned the hard way that 'yes' without paper melts by next week (someone gets busy, priorities shift, we restart in March). Protect your own decision: 5 minutes now, DocuSign on your phone, and Carla starts your setup tomorrow morning. I'll send it while we're on the call.",
        ["verbal-yes", "paperwork"],
    ),
    (
        "closing",
        "竞争对手最后搅局",
        "So their last-minute counter is 20% below ours — classic end-game move, and honestly a compliment to how far we got. Ask yourself one thing: why is that price only appearing NOW, after months of you evaluating us? Desperate pricing predicts desperate support. Our pilot results are real and yours. I'll stand by my number — and by you, after the sale.",
        ["competitor", "last-minute"],
    ),
    (
        "closing",
        "小单快签策略",
        "For a starter deal this size, let's skip the ceremony: I'll send the standard agreement — same one our 60+ clients signed, no custom clauses needed — you DocuSign today, setup starts Wednesday, and your team is live before your month-end meeting. The best contracts are the boring ones. Go?",
        ["small-deal", "speed"],
    ),
    (
        "closing",
        "错过截止后的挽回",
        "The promo lapsed last Friday — but you're two signatures from done, so here's what I did: I asked my manager to extend YOUR rate (just yours) until Wednesday, citing the pilot success. He agreed, reluctantly. I won't get that favor twice. Can we finish this before Wednesday, Sir?",
        ["expired-deadline", "recovery"],
    ),
    # ================= 客户维系 retention（15） =================
    (
        "retention",
        "老客户续约",
        "Sir Chua, quick renewal note — your team's usage ranks in our top 10% (Carla shows me the dashboards, I brag about you internally po). Renewing at the same rate, no increase, plus the new AI follow-up assistant is included free this cycle. Shall I schedule a 30-minute new-features training with the renewal?",
        ["renewal", "loyalty"],
    ),
    (
        "retention",
        "沉默客户唤醒",
        "Hi Ma'am Reyes, noticed your team's logins dropped since last month — usually means either things got busy (good problem!) or something's frustrating them (fixable problem). Either way: our customer success team offers a free usage health-check. 30 minutes, we reconfigure what's not working. This week po?",
        ["silent-customer", "health-check"],
    ),
    (
        "retention",
        "续约前的价值回顾",
        "Before your renewal date, I prepared your Year-in-Review: 1,240 follow-ups completed, 89 deals tracked to close, ₱14.2M pipeline managed, and — the number I love — zero accounts lost to salesman turnover (you had 2 resignations, both handovers took a day). That's the story. Renewal papers attached; questions welcome.",
        ["renewal", "value-review"],
    ),
    (
        "retention",
        "升级增购推荐",
        "Your Luzon team's numbers since going live are strong — which makes the contrast with Visayas (still on Excel, right?) hard to ignore. Same setup, 6 more licenses, and your GM finally gets ONE dashboard for the whole country. Volume pricing kicks in at this size too. Want the expansion quote?",
        ["upsell", "expansion"],
    ),
    (
        "retention",
        "客户抱怨处理-响应慢",
        "You're right, and I won't defend it — two support tickets took 3 days when our standard is same-day. Here's what happened (short version: our Cebu engineer resigned mid-month) and what changed: you now have a named backup contact, and I've added my personal Viber to your escalation path. Test me on it. And the affected month's support fee is credited.",
        ["complaint", "recovery"],
    ),
    (
        "retention",
        "预警流失-使用率下降",
        "Ma'am, straight talk: your renewal is in 60 days, and if I look at your usage data honestly, you're not getting full value — three modules sit unused. Two options: we schedule proper training and make them earn their keep, or we downsize your plan and your bill. I'd rather shrink your contract than lose your trust. Which shall we do?",
        ["churn-risk", "honesty"],
    ),
    (
        "retention",
        "节日关怀-圣诞",
        "Merry Christmas, Sir Go! 🎄 No business in this message — just genuine thanks for a great year of partnership. Your team was a pleasure to support. Enjoy the Noche Buena, and may your January collections be swift and complete. 😄 See you in the new year po!",
        ["holiday", "relationship"],
    ),
    (
        "retention",
        "转介绍请求",
        "Sir, you've seen the results firsthand for 8 months now — may I ask a favor? If you know one other business owner (supplier, customer, kumpare from the business club) wrestling with sales tracking, an introduction from you is worth 100 cold calls from me. And yes — every successful referral earns you a free month. Anyone come to mind?",
        ["referral-ask", "advocacy"],
    ),
    (
        "retention",
        "新功能主动推送",
        "Hi Ma'am Santos, the offline mode you requested in March? It shipped this morning. Your field salesmen in Quezon province can now log visits without signal — everything syncs on reconnect. You were literally the second-loudest voice asking for this, so you get it before the announcement. Try it and tell me if it's what you meant po!",
        ["new-feature", "voice-of-customer"],
    ),
    (
        "retention",
        "季度业务回顾邀约",
        "Time for our quarterly review, Sir — 45 minutes: what the data says about your team's pipeline, which features you're underusing (I found two), and what's coming next quarter. Last QBR we found the Friday follow-up gap, remember? Your conference room or a video call?",
        ["qbr", "engagement"],
    ),
    (
        "retention",
        "客户团队换人衔接",
        "Heard your sales manager Ms. Cruz is moving on — transitions are exactly when systems prove their worth (all her accounts and notes are already in there, nothing walks out the door). Offer: free onboarding session for her replacement, first week on the job. Just send me the start date and I'll handle the rest.",
        ["turnover", "continuity"],
    ),
    (
        "retention",
        "涨价沟通-老客户",
        "Renewal note, and I'll be direct: rates rise 8% for new clients in January. For you — three years with us — I've locked a 3% cap, and if you renew for 24 months, zero increase. This isn't a pressure play; it's me spending my 'loyal client' credits with Finance on you. The lock expires with your current term, though. Renew early?",
        ["price-increase", "loyalty"],
    ),
    (
        "retention",
        "危机挽留-要求退订",
        "Before I process the cancellation, Sir — give me one honest conversation. If it's cost, I have downgrade options that keep your data live. If it's the product failing you somewhere, name it — some things I can fix in a week. And if you've truly outgrown us or found better, I'll process it same-day AND hand you your full data export myself. Which is it po?",
        ["cancellation", "save"],
    ),
    (
        "retention",
        "成功案例共创邀请",
        "Ma'am, your turnaround story — 60% to 92% follow-up rate in a quarter — is the best in our portfolio this year. Would you let us feature it as a case study? You review every word before publishing, your numbers stay approximate, and in exchange: 2 free months plus you look brilliant at industry events (because you were). Interested?",
        ["case-study", "advocacy"],
    ),
    (
        "retention",
        "休眠后赢回",
        "Hi Sir Bautista, it's been 6 months since your subscription lapsed — no pitch, just news: the two issues that made you leave (slow mobile app, no Viber integration) are both fixed. If you're still solving sales tracking some other way and it's not lovely, come back at your old rate — one migration call and your data's alive again, exactly as you left it.",
        ["win-back", "lapsed"],
    ),
]


async def main() -> None:
    maker = get_sessionmaker()
    llm = LLMClient()
    async with maker() as session:
        admin_id = await session.scalar(
            select(User.id).where(User.role == "admin", User.deleted_at.is_(None)).limit(1)
        )
        if admin_id is None:
            raise SystemExit("找不到 admin 用户，请先 seed")

        existing = set(
            await session.scalars(select(Script.scenario).where(Script.deleted_at.is_(None)))
        )
        fresh = [s for s in PH_SCRIPTS if s[1] not in existing]
        print(f"待插入 {len(fresh)} 条（已存在跳过 {len(PH_SCRIPTS) - len(fresh)} 条）")
        if not fresh:
            return

        # 与生产索引文本一致：标题+正文（客户端自动按 10 条分批）
        vectors = await llm.embed([f"{scenario}\n{content}" for _, scenario, content, _ in fresh])
        for (category, scenario, content, tags), vector in zip(fresh, vectors, strict=True):
            session.add(
                Script(
                    category=category,
                    scenario=scenario,
                    content=content,
                    tags=tags,
                    created_by=admin_id,
                    embedding=vector,
                )
            )
        await session.commit()
        total = await session.scalar(
            select(func.count()).select_from(Script).where(Script.deleted_at.is_(None))
        )
        print(f"完成。库内话术总数：{total}")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())

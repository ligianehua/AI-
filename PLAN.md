# AI 销售助手 — 开发计划（PLAN.md）

> 本文档是给 Claude Code 的执行蓝图。配套 `CLAUDE.md`（项目约定）。
> 版本：v1.0 ｜ 日期：2026-07-10 ｜ 决策人：Li Jianhua

---

## 0. 一句话定义

面向销售团队的 AI 工作台：用 LLM + 数据分析，覆盖 线索管理 → 客户洞察 → 商机跟进 → 话术推荐 →（P1）合同 / 预测 / 业绩 的全链路，把销售从"经验驱动"升级为"数据驱动"。

## 1. 第一性原理拆解

销售的本质只有两个变量：

1. **注意力分配** —— 有限时间投给谁（哪个线索、哪个商机）
2. **沟通质量** —— 每次接触说什么、怎么说

所有 7 个模块都是这两个变量的杠杆：

| 模块 | 作用于 | 本质 |
|---|---|---|
| 线索管理 + AI 评分 | 注意力分配 | 排序问题：谁最可能成交 |
| 客户洞察 | 沟通质量 | 压缩"理解客户"的时间成本 |
| 商机跟进 | 注意力分配 | 流程熵减：防遗忘、防停滞 |
| 话术推荐 | 沟通质量 | 复制 top sales 的经验，边际成本趋零 |
| 合同处理 | （非销售时间） | 压缩行政开销 |
| 销售预测 | 管理决策 | pipeline 的概率加权 |
| 业绩分析 | 管理决策 | 归因：什么行为导致成交 |

**推论（决定优先级）**：离成交越近、对历史数据依赖越少的模块越先做。预测和业绩分析需要数据积累才有意义——系统上线第一天就做预测是自欺欺人，所以放 P1。

**AI 的定位**：不替销售做决定，而是把"信息处理"和"经验获取"的成本打下来。每个 AI 输出必须附带理由（可解释），销售永远有最终否决权。

## 2. 范围切分

### P0 — 核心闭环（本计划主体，M0–M7）

1. **线索管理**：录入 / Excel 导入 / AI 评分 / 状态流转 / 分配 / 转商机
2. **客户洞察**：客户 360 档案、AI 画像、跟进时间线、AI 摘要
3. **商机跟进**：阶段看板、跟进记录、AI 下一步建议、风险提醒
4. **话术推荐**：话术库管理 + RAG 检索 + 基于客户上下文的实时生成

### P1 — 第二阶段（M8–M12）

5. **线索发现（东南亚）**（M8，已启动）：客户自选国家+城市+品类，系统调 Google Places API 拉取商户进候选池，销售领取转正式线索。详见 §6.6
6. **通用 AI 助手**（M9）：对话式查数（function calling 只读工具）。放 P1 的理由：它消费 P0 全部数据与工具，P0 没跑通它就是空壳
7. **合同处理**（M10）：模板生成、要素抽取、风险条款审查
8. **销售预测**（M11）：加权 pipeline 预测 + 趋势外推（标注置信度）
9. **业绩分析**（M12）：团队/个人仪表盘 + AI 归因解读

### P2 — 明确不做（现在）

企微/钉钉/CRM 双向同步（架构预留 connector 接口）、语音转写、自动外呼、移动端 App、多租户 SaaS 化、多币种。先让闭环跑通，再谈花活。

### 用户角色

- **销售（sales）**：主用户，管自己的线索/商机/客户
- **主管（manager）**：看团队全量数据 + 预测/业绩
- **管理员（admin)**：用户/团队管理、话术库/知识库维护（模型配置走 `providers.yaml` 文件，不做 UI）

## 3. 技术架构

```
┌─────────────────────────────────────────────────┐
│  Frontend: Next.js (App Router, 最新稳定版) + TS │
│  Tailwind + shadcn/ui + TanStack Query + ECharts│
└───────────────────┬─────────────────────────────┘
                    │ REST /api/v1 + SSE(流式)
┌───────────────────┴─────────────────────────────┐
│  Backend: FastAPI (Python 3.12+, async)         │
│  ├── api/      路由层（薄）                       │
│  ├── services/ 业务逻辑                          │
│  ├── ai/       LLM 抽象层 + prompts + RAG        │
│  └── tasks/    ARQ 异步任务（评分/画像/嵌入）      │
└──────┬──────────────────┬───────────────────────┘
       │                  │
┌──────┴───────┐   ┌──────┴──────┐
│ PostgreSQL 16│   │ Redis        │
│ + pgvector   │   │ 缓存+任务队列 │
└──────────────┘   └─────────────┘
```

### 技术选型与理由（决策记录，别翻案）

| 决策 | 选择 | 理由 |
|---|---|---|
| 后端 | FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + Alembic | AI/数据生态最全，async 原生支持 SSE 流式 |
| 前端 | Next.js（最新稳定版）+ TypeScript + shadcn/ui + ECharts | 组件生态成熟；ECharts 对中文图表场景友好 |
| 数据库 | PostgreSQL 16 + pgvector | 一库搞定关系 + 向量，MVP 阶段引入独立向量库是过度设计 |
| 队列 | Redis + ARQ | 比 Celery 轻，async 原生；AI 任务全部异步化 |
| LLM 网关 | **自建薄抽象层**（见 §5） | DeepSeek/Qwen/Kimi/GLM 全部 OpenAI 兼容协议，薄适配层足够；不直接依赖 LiteLLM（2026-03 其 PyPI 供应链攻击事件是警钟），但接口对齐，后期可换 Bifrost/Portkey |
| Agent 编排 | 不用重框架 | P0 场景全部是"prompt + structured output + function calling"，LangGraph 等到 P1 有多步工作流再说。克制是美德 |
| Embedding | Qwen text-embedding API（1024 维） | 中文质量好、免推理运维；MVP 不自托管嵌入模型 |
| 认证 | JWT + RBAC 三角色 | 标准做法 |
| 部署 | Docker Compose（dev/prod 同构） | 单机可跑，预留 K8s |

### 非功能要求

- **中文优先**：UI、AI 输出、错误信息全中文
- **数据安全**：API key 只走环境变量；选用国内模型时数据不出境；`.env` 永不入库
- **成本护栏**：所有 LLM 调用记账（`llm_calls` 表），支持每用户日 token 限额
- **可解释**：AI 评分/建议必须输出结构化理由
- **评测纪律**：每个 AI 场景建 golden set（≥20 条），prompt 改动必须跑回归；结构化字段用断言判分，生成质量用 LLM-as-judge。不做 eval 的 prompt 工程等于闭眼开车

## 4. 数据模型（核心表）

> 全部表带 `id (uuid pk)`, `created_at`, `updated_at`。软删除用 `deleted_at`。

```
users          id, name, email, hashed_password, role(sales|manager|admin), team_id, is_active
teams          id, name        # 主管 = role=manager 且 team_id 匹配，不另设字段

accounts       # 客户公司
  id, name, industry, size, region, website, remark, owner_id
  ai_profile jsonb        # AI 画像（结构见 §6.2）
  ai_profile_updated_at

contacts       # 联系人
  id, account_id, name, title, phone, wechat, email
  role_in_deal(decision_maker|influencer|user|gatekeeper), remark

leads          # 线索
  id, source(website|exhibition|referral|ads|cold_call|other), account_name, contact_name,
  contact_phone, contact_wechat, industry, requirement_desc,
  status(new|contacted|qualified|converted|invalid),
  score int, score_detail jsonb,   # AI 评分 + 理由
  owner_id, converted_account_id, converted_opportunity_id

opportunities  # 商机（金额单位固定 CNY，不做多币种字段）
  id, account_id, name, amount numeric,
  stage(initial|need_confirmed|proposal|negotiation|won|lost),
  probability int,   # 默认按阶段映射 10/30/50/70/100/0，可手改
  expected_close_date, owner_id, lost_reason,
  stage_history jsonb              # [{stage, entered_at, by}]

activities     # 跟进记录（多态挂载）
  id, related_type(lead|account|opportunity), related_id,
  type(call|visit|wechat|email|meeting|other),
  content text, next_action, next_action_date, owner_id

scripts        # 话术库
  id, category(opening|discovery|objection|pricing|closing|retention), scenario, content,
  tags text[], embedding vector(1024), usage_count, created_by, is_active

knowledge_docs # 企业知识库（产品资料/FAQ/案例）
  id, title, status(processing|ready|failed)
knowledge_chunks
  id, doc_id, chunk_index, content, embedding vector(1024)

llm_calls      # AI 调用审计（成本 + 可观测 + 反馈落点）
  id, user_id, task_type(lead_scoring|account_profile|next_action|
      script_gen|embedding), provider, model,
  tokens_in, tokens_out, cost_estimate numeric, latency_ms,
  status(ok|error|timeout), error_msg,
  feedback smallint null   # 1 赞 / -1 踩（生成类任务的用户反馈）

notifications  # 风险提醒（与 §6.3 三种风险一一对应）
  id, user_id, type(stale_no_followup|stage_stuck|next_action_due),
  title, body, related_type, related_id, read_at
```

P1 增表（M8 线索发现，已定稿）：

```
discovery_subscriptions   # 抓取订阅（客户自选目标市场）
  id, name, country, city, category,   # 品类=Places 文本查询关键词（如 manufacturing / restaurant）
  keyword null,                        # 补充关键词
  is_active bool, owner_id,
  last_run_at, last_run_new int null   # 最近一次抓取时间/新增候选数

discovery_candidates      # 候选池（不直接进 leads，避免污染线索）
  id, subscription_id, place_id unique,   # Google Place ID，幂等去重键
  name, address, phone, website,
  country, city, category,                # 冗余自订阅，便于筛选
  status(pending|claimed|ignored),
  duplicate_hint null,                     # 与库内线索/客户疑似重复的提示
  owner_id, claimed_lead_id null, raw jsonb
```

其余 P1 增表：`contracts`（合同 + 抽取要素 jsonb + 审查结果 jsonb）、`forecast_snapshots`（周度 pipeline 快照，预测的原料）。

**权限规则（RBAC，在 service 层统一实施）**：sales 只能读写 `owner_id = 自己` 的数据；manager 可读全团队、可改分配；admin 全量 + 配置。

## 5. LLM 多模型抽象层（`backend/app/ai/`）

这是全项目的地基，M2 单独实现并测试。设计原则：**协议统一（OpenAI 兼容）、配置驱动、按任务路由、每次调用记账**。

```
ai/
├── providers.yaml     # 模型注册表（不含密钥，密钥在 env）
├── client.py          # LLMClient：chat() / chat_stream() / embed()
├── router.py          # 任务类型 → 模型档位路由
├── prompts/           # 所有 prompt 模板（jinja2），一场景一文件
├── schemas.py         # 各任务的结构化输出 Pydantic 模型
└── rag.py             # 检索：向量 + 关键词混合
```

`providers.yaml` 示例：

```yaml
providers:
  deepseek:
    base_url: https://api.deepseek.com/v1
    api_key_env: DEEPSEEK_API_KEY
    models: { fast: deepseek-v4-flash, strong: deepseek-v4-pro }
  qwen:
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key_env: DASHSCOPE_API_KEY
    models: { fast: qwen-flash, strong: qwen3.7-max, embedding: text-embedding-v4 }
  # anthropic / openrouter 同构追加即可

routing:                # 任务 → 档位（省钱的关键：分类抽取用 fast，生成用 strong）
  lead_scoring:    { tier: fast,   temperature: 0.1, json: true }
  account_profile: { tier: strong, temperature: 0.3, json: true }
  next_action:     { tier: fast,   temperature: 0.3, json: true }
  script_gen:      { tier: strong, temperature: 0.7, stream: true }
  # P1 开通用助手时再追加 chat 路由

default_provider: deepseek
fallback_provider: qwen   # 主供应商 5xx/超时 → 自动降级重试一次
```

`client.py` 要求：统一用 `openai` SDK（改 `base_url`）；超时 60s、重试 2 次（指数退避）；结构化输出用 JSON mode + Pydantic 校验（校验失败自动重试一次并附错误提示）；每次调用写 `llm_calls`。Anthropic 原生协议留 adapter 接口，P0 不实现。

## 6. P0 模块详细规格

**API 通用约定**：列表接口统一支持 `page / page_size（默认 20，上限 100）/ sort（如 -score）`；错误响应统一 `{code, message, detail}`；时间 UTC 存储、前端按 Asia/Shanghai 展示；软删除数据默认过滤。

### 6.1 线索管理 + AI 评分（M3）

**用户故事**：销售每天打开系统，看到按分数排序的线索列表，知道先打给谁、为什么。

API：
```
POST   /api/v1/leads                    创建
GET    /api/v1/leads?status=&score_gte=&owner_id=&sort=-score   列表（分页）
GET    /api/v1/leads/{id}               详情（含评分理由、跟进记录）
PATCH  /api/v1/leads/{id}               更新/改状态
POST   /api/v1/leads/import             Excel 导入（模板下载 + 错误行报告）
POST   /api/v1/leads/{id}/score         触发/重算 AI 评分（异步）
POST   /api/v1/leads/{id}/convert       转化 → 创建 account+contact+opportunity（事务）
POST   /api/v1/leads/assign             批量分配（manager）
```

**查重（撞单防护）**：创建与导入时按 `contact_phone` / `account_name` 检测疑似重复，标记提示、不硬拦截（撞单裁决留给人）。

**AI 评分逻辑（两层，输出 0–100 + 理由）**：
- 规则层（0–40）：信息完整度（电话/微信/需求描述）、来源权重（转介绍 > 展会 > 广告）、行业匹配度——权重配置化，别写死
- LLM 层（0–60）：`requirement_desc` + 跟进记录做语义意向判断，输出 `{intent_score, budget_signal, urgency, reasons[]}`
- 触发时机：创建/导入后自动评分；线索新增跟进记录后自动重算；支持手动重算
- 冷启动的诚实说明：没有成交数据校准前，评分是"专家规则 + 语义判断"，UI 上标注"参考分"。有 ≥100 条转化数据后再做校准（P1 加简单逻辑回归对照）

验收标准：
- [ ] Excel 导入 500 行 < 10s，错误行给出行号和原因
- [ ] 评分异步完成后列表自动刷新（轮询即可，别为这个上 SSE）
- [ ] 每条评分可展开看 `score_detail` 理由
- [ ] 转化操作是事务：失败无脏数据
- [ ] sales 看不到别人的线索（RBAC 测试）

### 6.2 客户洞察 / 客户 360（M4）

**用户故事**：拜访前 5 分钟打开客户页，AI 画像 + 时间线让销售快速进入状态。

API：
```
GET    /api/v1/accounts / {id}          CRUD + 列表
GET    /api/v1/accounts/{id}/timeline   全部跟进记录聚合（跨 lead/opportunity）
POST   /api/v1/accounts/{id}/profile    生成/刷新 AI 画像（异步）
POST   /api/v1/contacts / ...           联系人 CRUD
```

**AI 画像 `ai_profile` 结构**（Pydantic 强校验）：
```json
{
  "company_overview": "…",
  "pain_points": ["…"],
  "decision_chain": [{"contact": "…", "role": "…", "attitude": "…"}],
  "cooperation_stage_analysis": "…",
  "risks": ["…"],
  "suggestions": ["…"],
  "confidence_note": "基于 N 条跟进记录，信息不足处已标注"
}
```
输入 = account 字段 + contacts + 全部 activities。数据少时 AI 必须明说"信息不足"，禁止编造（prompt 里写死，eval 里验证）。

验收标准：
- [ ] 画像生成 < 30s（异步 + 进度提示），结构化渲染非纯文本墙
- [ ] 时间线聚合正确（lead 转化前的记录也要挂进来）
- [ ] 跟进记录 < 3 条时，画像明确提示信息不足而非硬编

### 6.3 商机跟进（M5）

**用户故事**：主管和销售在看板上一眼看清 pipeline；系统主动提醒"这单要凉了"。

API：
```
GET    /api/v1/opportunities/kanban     按阶段分组（含金额汇总）
POST   /api/v1/opportunities / {id}     CRUD
PATCH  /api/v1/opportunities/{id}/stage 拖拽换阶段（记 stage_history；won/lost 必填原因/金额确认）
GET    /api/v1/opportunities/{id}/next-actions   AI 下一步建议（3 条，可一键转任务）
POST   /api/v1/activities               跟进记录 CRUD（挂 lead/account/opportunity）
GET    /api/v1/notifications            风险提醒列表
```

**AI 下一步建议**：输入 = 阶段 + 最近 10 条跟进 + 停滞天数 + 画像摘要；输出 3 条具体可执行动作（`{action, reason, suggested_script_scenario}`），可跳转话术生成。

**风险提醒（ARQ 定时任务，每日 08:00）**：
- 商机 > X 天无跟进（默认 7，配置化）
- 阶段停滞 > Y 天（默认 21）
- `next_action_date` 到期未完成
写入 `notifications` + 首页红点。

验收标准：
- [ ] 看板拖拽流畅，阶段金额/加权金额实时汇总
- [ ] won/lost 强制填写原因（这是未来预测和归因的数据原料，不能省）
- [ ] 停滞检测定时任务有单测（时间 mock）
- [ ] AI 建议引用的是真实跟进内容（eval 验证不幻觉）

### 6.4 话术推荐（M6）

**用户故事**：销售遇到"客户嫌贵"，10 秒拿到 3 条结合本客户上下文的应对话术，直接复制到微信。

API：
```
POST   /api/v1/scripts / CRUD           话术库管理（admin/manager）
POST   /api/v1/scripts/search           混合检索（向量 + 关键词）
POST   /api/v1/scripts/recommend        生成推荐：
       body: { opportunity_id?, account_id?, scenario, channel(wechat|email|phone), user_hint? }
       → SSE 流式返回 3 条候选 + 引用的库内话术来源
POST   /api/v1/knowledge/docs           知识库上传（txt/md/docx → 存本地卷 data/uploads → 分块 → 嵌入，异步）
```

**生成管线**：`检索(scripts top-5 + knowledge top-3，向量+BM25 混合) → 融合客户上下文（画像+最近跟进）→ strong 模型生成 → 附来源引用`。channel 决定文风：微信短句口语化、邮件正式结构化。

**冷启动硬性要求**：上线前必须由业务方灌入 ≥50 条真实优质话术。垃圾进垃圾出——这一条是项目成败点，写进上线 checklist。

验收标准：
- [ ] 推荐响应首 token < 3s（流式）
- [ ] 生成结果标注参考了哪几条库内话术（可解释）
- [ ] 无匹配话术时降级为纯生成并明示"库内无参考"
- [ ] 一键复制；赞/踩反馈写入 `llm_calls.feedback`

### 6.5 首页仪表盘 + 管理页（M7）

- 仪表盘：我的今日待办（next_action 到期）、风险提醒、漏斗概览、本月成交额（sales 看自己 / manager 看团队）——纯聚合查询，不过度设计
- 管理页（admin）：用户/团队管理 UI（话术库/知识库管理 UI 已在 M6 交付）

### 6.6 线索发现 — 东南亚（M8）

**用户故事**：销售/主管配置"印尼 雅加达 制造业"这样的订阅，点一下抓取，候选池里出现真实商户（名称/地址/电话/网站），逐条"领取"变成正式线索并自动 AI 评分。

**数据源决策**：Google Places API (New) Text Search（密钥 `GOOGLE_MAPS_API_KEY`，只走 .env）。不自建爬虫：合规（各国 PDPA）与数据质量都不可控；Places 是合法可用的商户数据，且天然支持"品类 + 城市"筛选。后续可扩 Apollo.io / 邓白氏，provider 接口预留。

API：
```
POST   /api/v1/discovery/subscriptions            创建订阅（country/city/category/keyword）
GET    /api/v1/discovery/subscriptions            列表（分页，RBAC）
PATCH  /api/v1/discovery/subscriptions/{id}       启停/修改
DELETE /api/v1/discovery/subscriptions/{id}       软删
POST   /api/v1/discovery/subscriptions/{id}/run   手动抓取（异步任务，202）
GET    /api/v1/discovery/candidates?status=&subscription_id=   候选池（分页）
POST   /api/v1/discovery/candidates/{id}/claim    领取 → 事务创建线索（source=discovery）+ 自动评分
POST   /api/v1/discovery/candidates/{id}/ignore   忽略
```

**抓取管线**：`textQuery = "{category} in {city}, {country}"` → Places searchText（FieldMask 限定 id/名称/地址/电话/网站/类型，单页 ≤20 条）→ `place_id` 幂等去重（已存在跳过）→ 与库内 leads/accounts 按电话/名称查重（只标 `duplicate_hint` 不拦截）→ 入候选池 → 更新订阅 `last_run_at/last_run_new`。

**约束**：
- 候选与订阅同 owner，RBAC 与线索一致（sales own / manager team / admin all）
- Key 未配置或 Places 报错 → 领域错误中文提示，不得 500
- 领取是事务：candidate 置 claimed + 创建 lead + 触发评分，重复领取被拦
- MVP 手动触发抓取；定时订阅抓取待 ARQ cron 扩展（与风险扫描同机制）

验收标准：
- [ ] 订阅 CRUD + 三角色 RBAC 测试（跨 owner 404）
- [ ] 同一订阅跑两次，place_id 不重复入池（幂等）
- [ ] 库内已有同电话线索时，候选带撞单提示
- [ ] 领取后线索出现在线索列表且自动评分（source=discovery）
- [ ] key 缺失时 run 返回可读中文错误
- [ ] 迁移可升可降；make lint && make test 全绿

### 6.7 通用 AI 助手（M9）

**用户故事**：销售在聊天框里问"我手上哪个商机风险最大？""帮我看看 XX 客户的情况""来一条催款话术"，助手先查真实数据再回答，全程可见它查了什么。

API：
```
POST /api/v1/assistant/chat    body: { message, history: [{role, content}] ≤10 轮 }
     → SSE：tool {name, label} → delta {text} → done {llm_call_id} → error {message}
```

**Function calling 循环**（服务端，上限 5 轮工具调用）：
`chat` 路由（strong 档）带 4 个只读工具 → LLM 决定调哪个 → 服务端执行（全部走
service 层查询，RBAC 天然继承当前用户）→ 结果以 tool 消息回填 → 循环；
无工具调用时流式输出最终回答（tool_choice=none 强制作答）。

**工具（全部只读，返回紧凑 JSON，单次 ≤20 条）**：
| 工具 | 参数 | 数据 |
|---|---|---|
| search_leads | status? / min_score? / keyword? / limit? | 线索列表（含分数、来源、状态） |
| search_opportunities | stage? / keyword? / limit? | 商机列表（含金额、阶段停留天数、距上次跟进天数——风险判断的原料） |
| get_account_360 | account_name | 客户档案 + AI 画像摘要 + 联系人 + 最近 5 条跟进 |
| recommend_scripts | query / category? | 话术库混合检索 top-5 |

**约束**：
- 工具只读；助手 prompt 写死"不能修改数据、不编造数字、回答引用查到的数据、全中文、金额 CNY"
- 每轮工具调用与最终生成各记一笔 `llm_calls`（task_type=chat），计入日 token 限额
- 对话历史不落库（P1 范围外）：前端 state 保存，刷新即清，随请求回传 ≤10 轮
- `routing` 追加 `chat` 档位；`LlmTaskType` 追加 CHAT

验收标准：
- [ ] "我手上哪个商机风险最大" → 调 search_opportunities → 回答引用真实商机名与停滞天数
- [ ] sales 问数只能得到自己的数据（工具层 RBAC 测试，三角色）
- [ ] 工具循环上限 5 轮，未知工具/参数错误容错（回填错误给 LLM 而非 500）
- [ ] SSE 事件序列完整，前端可见"正在查询 XX"过程
- [ ] 工具选择 eval ≥20 条（真实 LLM 断言首个工具与关键参数）
- [ ] make lint && make test 全绿

### 6.8 合同处理（M10）

**用户故事**：销售把客户发来的合同传进系统，1 分钟内拿到要素摘要和风险条款提示；要发合同时从商机一键生成标准草稿 docx。

API：
```
POST   /api/v1/contracts/upload          上传（docx/txt/md ≤10MB）→ 异步抽取+审查
GET    /api/v1/contracts                 列表（RBAC，含状态）
GET    /api/v1/contracts/{id}            详情（extracted + review）
POST   /api/v1/contracts/{id}/reprocess  失败重试
DELETE /api/v1/contracts/{id}            软删
POST   /api/v1/contracts/generate        body {opportunity_id, payment_terms?} → 标准草稿 docx 下载
```

**处理管线**（异步任务）：extract_text（复用知识库解析）→ LLM 结构化抽取
`{甲方, 乙方, 金额, 服务期, 签署日, 付款约定[], 其他关键条款[], confidence_note}`（fast 档，
全字符串字段——合同写法千奇百怪，不强行 parse 数字/日期）→ LLM 风险审查（strong 档）：
对照配置化清单（`contract_risk_rules.yaml`：违约责任/付款约定/验收标准/知识产权/保密/
争议解决/单方解除/自动续约）输出 `{risks[{条款引用, 等级, 问题, 建议}], missing_clauses[], overall_note}`。

**模板生成**：python-docx 代码生成标准销售合同草稿（甲乙方/金额/服务期/付款方式从商机与
客户带入），文首注明"AI 生成草稿，正式签署前须经法务审核"。

**红线**：所有 AI 输出是"提示"不是"结论"；UI 与生成文档均注明不构成法律意见。
`LlmTaskType` 加 contract_extract / contract_review；routing 同步追加。

验收标准：
- [ ] 上传 → 抽取要素与风险清单在详情页结构化展示（不是文本墙）
- [ ] 信息不足时抽取结果明示「未提及」而非编造（eval 验证）
- [ ] 风险审查按清单比对，缺失关键条款进 missing_clauses
- [ ] 从商机生成的 docx 可下载打开，变量填充正确，含法务审核声明
- [ ] sales 只能看自己的合同（三角色 RBAC 测试）
- [ ] 抽取 eval ≥20 条 + 审查 eval；make lint && make test 全绿

### 6.9 销售预测（M11）

**用户故事**：主管打开预测页，看到当前加权 pipeline（按阶段分解）和过去若干周的走势；数据攒够两个季度后自动出现下季度外推区间。

数据：`forecast_snapshots(id, snapshot_date, owner_id, total_amount, weighted_amount, open_count, by_stage jsonb)`，(owner_id, snapshot_date) 部分唯一——同日重跑覆盖（幂等）。

API：
```
GET  /api/v1/forecast            加权 pipeline + 近 26 周快照 + trend（可为 null）+ data_note
POST /api/v1/forecast/snapshot   手动生成今日快照（manager/admin；cron 每周一自动跑）
```

**口径**：加权 pipeline = Σ(进行中商机金额 × probability/100)，按阶段分组；快照按 owner
粒度存全量，读取时按可见域聚合（sales 自己 / manager 团队 / admin 全公司）。

**诚实红线**：快照数据 < 26 周（约 2 个完整季度）时 `trend=null`，UI 只展示 pipeline 与
历史走势 + 数据量提示；≥26 周才做线性外推（最小二乘 + 残差 95% 区间），
method/区间/数据量全部标注在响应里，不做黑盒预测。

验收标准：
- [ ] 加权金额 = 各阶段金额×概率之和（单测验证），won/lost 不计入
- [ ] 快照同日重跑幂等覆盖；cron 注册（每周一 UTC 01:00）
- [ ] 数据不足时 trend=null 且 data_note 说明；mock ≥26 周数据时外推给出区间（单测）
- [ ] RBAC：sales 只见自己聚合，manager 团队，admin 全公司（三角色测试）
- [ ] 前端预测页：pipeline 卡片 + 阶段分解 + 趋势线（轻量 SVG，数据规模大后可换 ECharts）
- [ ] make lint && make test 全绿（无 AI 场景，不涉 eval）

### 6.10 业绩分析（M12）

**用户故事**：月初复盘时打开业绩页，本月 vs 上月的关键指标一目了然，AI 用一段话讲清"为什么"，并给出下月着力点。

**指标口径**（本月 vs 上月，按可见域聚合，无新表纯聚合查询）：
- 成交额/赢单数：stage_history 中进入 won 的时间在当月的商机
- 赢率：当月关闭（won+lost）中 won 占比；无关闭单时明示"无关闭商机"
- 平均成交周期：当月赢单的 created_at → won entered_at 天数均值
- 活动量：当月跟进记录数；新增线索：当月创建的线索数

API：
```
GET  /api/v1/analytics/performance?month=YYYY-MM   本月+上月指标（默认当月）
POST /api/v1/analytics/insight                     LLM 归因解读（同步，strong 档）
```

**AI 归因**：输入两个月的指标 JSON → `{summary, findings[], suggestions[]}`
（PerformanceInsightOutput 强校验）。铁律：只引用输入中出现的数字，数据不足/无对比基础
必须明说，禁止编造归因。`LlmTaskType` 加 performance_insight。

验收标准：
- [ ] 指标口径单测（won 时间归属当月、赢率分母为当月关闭数、周期计算）
- [ ] RBAC 三角色（sales 自己 / manager 团队 / admin 全公司）
- [ ] AI 解读引用真实数字、无数据时明示（eval ≥20 条关键词断言）
- [ ] 前端业绩页：指标卡本月/上月对比 + AI 解读
- [ ] make lint && make test && make eval 全绿

### 6.11 AI 产品分析助手（M13）

**用户故事**：销售/售前把规格书扔进系统，参数自动变成结构化产品档案；要选型时用一句话
筛出候选，点两下拿到参数对比表；老型号停产时一键找出库里的在售替代——不再人工翻规格书，
不再重复造轮子。

数据（迁移 0007，产品库是公司公共资产：全员可读，admin/manager 可管理）：
```
products
  id, model_no（型号，部分唯一 where not deleted）, name, brand, category,
  status(active|eol|draft),   # eol=停产（替代挖掘的重点对象）
  specs jsonb,                # 参数键值对（LLM 抽取或手动维护）
  description text, source_doc_name,
  embedding vector(1024),     # 型号+名称+参数 语义向量
  created_by
```

API：
```
POST   /api/v1/products                    手动创建（admin/manager）
GET    /api/v1/products?status=&category=&keyword=   列表（全员）
GET    /api/v1/products/{id}               详情
PATCH  /api/v1/products/{id}               编辑（含改 status 标停产）
DELETE /api/v1/products/{id}               软删
POST   /api/v1/products/upload-spec        上传规格书（txt/md/docx）→ 异步抽取入库
POST   /api/v1/products/search             自然语言混合检索（向量+关键词）
POST   /api/v1/products/compare            body {product_ids: 2-4} → 参数对齐表 + LLM 差异总结
GET    /api/v1/products/{id}/alternatives  替代推荐（向量相似 top5，EOL 型号优先推在售替代）
```

**抽取管线**（异步任务）：extract_text → LLM 结构化抽取
`{model_no, name, brand, category, specs{参数名:值}, description, confidence_note}`
（fast 档；原文未提及的字段填「未提及」，specs 只收原文出现的参数，禁止编造）→
按 model_no 幂等 upsert → 嵌入（model_no+name+specs 拼接文本）。

**对比**：后端对齐 spec keys 生成矩阵（代码），LLM 生成
`{summary, key_differences[], recommendation}`（strong 档，只引用矩阵中的参数值）。

**替代挖掘**：pgvector 余弦相似 top5（排除自身与软删）；目标产品为 EOL 时默认只推
active 替代（可放开）；每条附相似度与关键参数差异。

`LlmTaskType` 追加 product_extract / product_compare。

验收标准：
- [ ] 上传规格书 → 结构化参数入库（未提及不编造，eval ≥20 条验证）
- [ ] 同型号重复上传幂等更新，不重复建档
- [ ] 自然语言检索命中目标产品（中文查询可召回英文规格）
- [ ] 对比表参数对齐正确；LLM 总结只引用真实参数（eval 验证）
- [ ] EOL 型号的替代推荐只返回在售产品，附相似度
- [ ] 全员可读、非管理角色不可写（RBAC 测试）；make lint && make test && make eval 全绿

### 6.12 AI 产品咨询助手（M14）

**用户故事**：客户问"你们这型号和 X 比有什么优势？""这设备报错 E03 怎么处理？"——销售
把问题丢给咨询助手，售前问题拿到带参数依据的卖点回答，售后问题拿到基于运维手册的排查步骤，
直接转发客户。虚拟销售专家 + 智能运维助手双角色。

API：
```
POST /api/v1/product-advisor/chat   body: { message, history ≤10 轮 }
     → SSE：tool {name, label} → delta {text} → done → error（协议同 M9 助手）
```

**实现**：复用 M9 chat_tools 循环框架（上限 5 轮），独立工具集与 system prompt：
| 工具 | 用途 |
|---|---|
| search_products | 按需求/参数找产品（售前选型） |
| get_product_detail | 型号完整参数（回答参数类问题） |
| compare_products | 与竞品/其他型号对比（卖点提炼） |
| search_knowledge | 知识库 RAG（FAQ/运维手册/案例——售后排查的依据） |

**双角色 prompt 铁律**：售前角色——基于真实参数讲卖点，参数库里没有的不承诺；售后角色——
排查步骤必须来自知识库检索结果，查不到就建议转人工工程师，禁止编造操作步骤（安全红线）；
自动按问题类型切换角色；用户要求英文时输出英文（便于直接转发客户）。

`LlmTaskType` 追加 product_advisor；`llm_calls` 记账与日限额沿用。

验收标准：
- [ ] 售前问题（选型/对比/参数）→ 调产品工具 → 回答引用真实参数
- [ ] 售后问题 → 调知识库 → 知识库无据时明确说"建议转人工"而非编造步骤
- [ ] 工具选择 eval ≥20 条；SSE 事件序列与容错测试（复用 M9 测试模式）
- [ ] 全员可用（产品库公共读）；make lint && make test && make eval 全绿

## 7. （P1 规格已全部细化，见 §6.6–§6.12）

## 8. 里程碑与执行顺序

> 每个 M 独立可验收、可运行。Claude Code 按顺序执行，**完成一个 M 的 DoD 才进入下一个**。

| M | 内容 | 交付物 | DoD（验收） |
|---|---|---|---|
| M0 | 脚手架 | monorepo（backend/ + frontend/）、docker-compose（pg16+pgvector、redis）、FastAPI 骨架 + /health、Next.js 骨架 + 登录页、JWT auth、`.env.example`（全部环境变量）、Makefile、CI（跑 make lint + make test） | `make dev` 一键起全栈；登录跑通；CI 绿 |
| M1 | 数据底座 | §4 全部 P0 表 + Alembic 迁移、通用 CRUD service 基类、RBAC 中间件、用户/团队管理 API（admin）、种子数据脚本（3 用户 ×2 团队 + 50 假线索/客户/商机） | 迁移可升可降；RBAC 三角色单测覆盖；seed 后前端能看到数据 |
| M2 | LLM 抽象层 | §5 全部：client/router/providers.yaml、llm_calls 记账、evals/ 骨架（pytest 驱动 golden set）、`POST /api/v1/ai/ping` 冒烟接口 | 切换 provider 只改配置；断网/超时降级单测通过；每次调用落审计表 |
| M3 | 线索管理 | §6.1 前后端 + 评分异步任务 + Excel 导入 | §6.1 验收清单全过 + 评分 eval ≥20 条 |
| M4 | 客户 360 | §6.2 前后端 + 画像生成 | §6.2 验收清单全过 + 画像 eval（含"信息不足不编造"用例） |
| M5 | 商机跟进 | §6.3 看板 + 跟进 + AI 建议 + 定时风险提醒 | §6.3 验收清单全过 |
| M6 | 话术推荐 | §6.4 话术库 + RAG + 生成 + 知识库上传 | §6.4 验收清单全过 + 检索质量抽查（top-5 命中人工评 ≥80%） |
| M7 | 打磨收尾 | 仪表盘、admin 用户管理页、E2E（Playwright 冒烟 5 条主流程）、部署文档 README + 生产初始化 admin 脚本 | 全量测试绿；docker compose prod 模式可部署；演示脚本可走通 |
| M8 | 线索发现（东南亚） | §6.6 前后端：订阅管理 + Places 抓取任务 + 候选池 + 领取转线索 | §6.6 验收清单全过 |
| M9 | 通用 AI 助手 | §6.7 前后端：SSE 对话 + 4 只读工具 function calling | §6.7 验收清单全过 |
| M10 | 合同处理 | §6.8 前后端：上传抽取审查 + 模板生成 | §6.8 验收清单全过 |
| M11 | 销售预测 | §6.9 前后端：加权 pipeline + 周度快照 + 外推守卫 | §6.9 验收清单全过 |
| M12 | 业绩分析 | §6.10 前后端：月度指标对比 + AI 归因解读 | §6.10 验收清单全过 |
| M13 | AI 产品分析助手 | §6.11 前后端：产品库 + 规格抽取 + 对比 + 替代挖掘 | §6.11 验收清单全过 |
| M14 | AI 产品咨询助手 | §6.12 前后端：双角色产品咨询对话 | §6.12 验收清单全过 |

## 9. 目录结构

```
ai-sales-assistant/
├── CLAUDE.md                  # 项目约定（Claude Code 必读）
├── PLAN.md                    # 本文档
├── docker-compose.yml         # pg + redis + backend + frontend
├── Makefile                   # dev / test / lint / seed / migrate
├── backend/
│   ├── pyproject.toml         # uv 管理依赖
│   ├── app/
│   │   ├── main.py
│   │   ├── core/              # config(pydantic-settings) / security / deps
│   │   ├── models/            # SQLAlchemy（一实体一文件）
│   │   ├── schemas/           # Pydantic（api 出入参）
│   │   ├── api/v1/            # 路由（薄，只做参数校验+调 service）
│   │   ├── services/          # 业务逻辑 + RBAC 检查
│   │   ├── ai/                # §5 抽象层 + prompts/ + rag.py + schemas.py
│   │   └── tasks/             # ARQ：scoring / profile / embedding / risk_scan
│   ├── alembic/
│   ├── tests/                 # pytest（单测 + API 测试，testcontainers 起 pg）
│   ├── evals/                 # golden sets + 评测脚本（pytest -m eval）
│   └── scripts/seed.py
└── frontend/
    ├── app/                   # (auth)/login、(main)/dashboard|leads|accounts|opportunities|scripts|admin
    ├── components/            # ui/(shadcn) + 业务组件
    ├── lib/                   # api client(openapi-typescript 生成) / hooks / stores
    └── e2e/                   # Playwright
```

## 10. 风险与实话（别跳过这节）

1. **AI 评分冷启动**：上线初期没有成交数据校准，评分只是"专家规则 + 语义判断"。UI 诚实标注"参考分"，别把它包装成魔法，销售被误导一次就再也不信了。
2. **话术库质量 = 项目生死线**：模型再强，库里没货就是无米之炊。上线 checklist 第一条：业务方灌 ≥50 条 top sales 真实话术。
3. **销售预测的诚实边界**：数据不足 2 个季度只做加权 pipeline。敢在没数据时给"AI 预测销售额"，等于给管理层递了一份占卜报告。
4. **成本失控**：全部调用走 router 分档（评分/抽取用 flash 档，生成用 strong 档）+ llm_calls 记账 + 日限额。粗算：1 个销售 1 天 ≈ 20 次评分(fast) + 10 次生成(strong) ≈ ¥0.5–2，可控，但必须有账可查。
5. **幻觉**：所有 AI 输出结构化 + 附来源/理由；画像和建议的 prompt 明确"信息不足就说不足"；evals 里放反幻觉用例。
6. **范围蔓延**：任何人（包括未来的你）想在 P0 加语音转写/自动外呼/移动端，一律先问：核心闭环跑通了吗？

## 11. 给 Claude Code 的启动指令

**首次启动（M0）**，在空目录下执行 `claude`，输入：

```
请先完整阅读 PLAN.md 和 CLAUDE.md。
执行 M0（脚手架）：按 PLAN.md §8 M0 的交付物清单实现，
完成后运行 make lint && make test，全绿后给我一份 M0 验收报告
（对照 DoD 逐条勾选），不要提前开始 M1。
```

**后续每个里程碑**（把 N 换成数字）：

```
阅读 PLAN.md §6/§8 中 M{N} 的规格与 DoD。
先列出你的实现清单让我确认，确认后再动手。
完成后：make lint && make test 全绿 + DoD 逐条自查报告。
遇到 PLAN 未覆盖的决策点，停下来问我，不要自作主张改架构。
```

**踩坑守则**（也写进了 CLAUDE.md）：一次只做一个 M；每个 M 结束提交 git；prompt 文件改动必须跑 `make eval`；不新增 PLAN 之外的依赖前先说明理由。

---
*本计划由 Claude 基于 2026-07 技术现状制定。DeepSeek V4 / Qwen3.7 定价与模型名以接入时官方文档为准。*

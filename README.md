# AI 销售助手

面向销售团队的 AI 工作台：线索管理 → 客户洞察 → 商机跟进 → 话术推荐（P0），合同 / 预测 / 业绩（P1）。

- 规格与里程碑：[PLAN.md](PLAN.md)
- 开发约定：[CLAUDE.md](CLAUDE.md)

## 技术栈

FastAPI (Python 3.12, uv) · Next.js + TypeScript + shadcn/ui · PostgreSQL 16 + pgvector · Redis + ARQ

## 快速开始

```bash
cp .env.example .env    # 按需填写密钥（LLM key M2 起才需要）
make dev                # docker compose 启动 pg + redis + 前后端（迁移自动执行）
# 首次启动后灌演示数据（默认账号来自这里）：
docker compose exec backend uv run python -m scripts.seed
docker compose exec backend uv run python -m scripts.seed_scripts
```

- 前端：http://localhost:3000 （默认账号 admin@example.com / admin123，见 .env）
- 后端 API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 不用 Docker 的本地开发

```bash
# 数据库（无 Docker 的临时方案：本地 PG16+pgvector，端口 55432）
cd backend && uv sync
uv run python -m scripts.local_pg start
# 把 .env 的 DATABASE_URL 改为 postgresql+asyncpg://postgres@127.0.0.1:55432/ai_sales
# 并设 TASK_MODE=local（无 Redis 时异步任务在进程内后台执行）

# 迁移 + 种子数据
uv run alembic upgrade head
uv run python -m scripts.seed

# 后端
uv run uvicorn app.main:app --reload

# 前端
cd frontend && npm install && npm run dev
```

种子账号：`admin@example.com / admin123`（管理员）、`manager@example.com`、`sales1@example.com`、`sales2@example.com`（后三个密码 `password123`）。

## 常用命令

| 命令 | 说明 |
|---|---|
| `make dev` | 一键起全栈（docker compose） |
| `make test` | backend pytest + frontend vitest |
| `make lint` | ruff + mypy + eslint + tsc |
| `make eval` | LLM golden set 回归（改 prompt 必跑） |
| `make migrate` | Alembic 迁移到最新 |
| `make seed` | 灌种子数据 |
| `make gen-api` | 后端 OpenAPI → 前端 TS client |
| `make e2e` | Playwright 冒烟（5 条主流程，需后端已起 + 已 seed） |
| `make prod` | 生产模式部署（docker compose prod） |

## 目录结构

```
backend/app/{core,models,schemas,api/v1,services,ai,tasks}
backend/{alembic,tests,evals,scripts}
frontend/{app,components,lib,e2e}
```

## 生产部署

```bash
cp .env.example .env
# 必改：SECRET_KEY（openssl rand -hex 32）、POSTGRES_PASSWORD、
#       DEEPSEEK_API_KEY / DASHSCOPE_API_KEY、PUBLIC_API_BASE_URL（浏览器可达的后端地址）

docker compose -f docker-compose.prod.yml up -d --build   # migrate 服务自动执行迁移

# 初始化管理员（幂等）
docker compose -f docker-compose.prod.yml exec backend \
  uv run python -m scripts.create_admin admin@yourcompany.com '强密码' 管理员
```

服务：前端 :3000 · 后端 :8000（`/docs` 为 API 文档）· 每日 08:00 worker 自动跑风险扫描。
上传的知识文档持久化在 `uploads` 卷，数据库在 `pgdata` 卷（请纳入备份）。

### 上线 checklist（PLAN §10，别跳过）

- [ ] **业务方灌入 ≥50 条 top sales 真实话术**（项目成败点；`scripts.seed_scripts` 的 12 条仅供演示）
- [ ] LLM API key 已配置，`POST /api/v1/ai/ping` 冒烟通过，`make eval` 全绿
- [ ] `providers.yaml` 模型名与价格表已按官方文档核对
- [ ] SECRET_KEY / 数据库密码已更换，`.env` 不入库
- [ ] 每用户日 token 限额（LLM_DAILY_TOKEN_LIMIT_PER_USER）已确认
- [ ] AI 评分在 UI 标注"参考分"已向销售团队宣导（冷启动无成交数据校准）

## 演示脚本（5 分钟）

1. `admin@example.com` 登录 → 管理页看用户/团队 → 话术页看话术库与知识库
2. 切 `sales1@example.com` → 工作台（统计/今日待办/漏斗/风险提醒）
3. 线索页：新建一条含预算与时间点的线索 → 观察评分从「评分中」到出分 → 点分数看理由
4. 转化该线索 → 客户页打开客户 360 → 生成 AI 画像 → 看时间线聚合
5. 商机看板：拖卡片换阶段 → 拖到赢单弹金额确认 → 卡片详情里记跟进、看 AI 下一步建议
6. 话术页：选场景 + 客户 → 生成 3 条候选（引用来源可见）→ 复制 → 赞/踩

对应自动化：`make e2e`（Playwright 覆盖上述主链路）。

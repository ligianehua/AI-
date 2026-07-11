# AI 销售助手

面向销售团队的 AI 工作台：线索管理 → 客户洞察 → 商机跟进 → 话术推荐（P0），合同 / 预测 / 业绩（P1）。

- 规格与里程碑：[PLAN.md](PLAN.md)
- 开发约定：[CLAUDE.md](CLAUDE.md)

## 技术栈

FastAPI (Python 3.12, uv) · Next.js + TypeScript + shadcn/ui · PostgreSQL 16 + pgvector · Redis + ARQ

## 快速开始

```bash
cp .env.example .env    # 按需填写密钥（LLM key M2 起才需要）
make dev                # docker compose 启动 pg + redis + 前后端（热重载）
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

## 目录结构

```
backend/app/{core,models,schemas,api/v1,services,ai,tasks}
backend/{alembic,tests,evals,scripts}
frontend/{app,components,lib,e2e}
```

生产部署文档将在 M7 交付。

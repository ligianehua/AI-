# AGENTS.md — AI 销售助手 项目约定

> Codex 在本仓库工作的规则。规格与里程碑见 PLAN.md，两者冲突时以 PLAN.md 为准并向用户报告。

## 项目

AI 销售助手：线索管理、客户洞察、商机跟进、话术推荐（P0），合同/预测/业绩（P1）。
栈：FastAPI (Python 3.12+) + Next.js 最新稳定版 (TS) + PostgreSQL 16/pgvector + Redis/ARQ。多 LLM 抽象层见 PLAN.md §5。

## 常用命令

```bash
make dev        # docker compose 起 pg+redis，前后端热重载
make test       # backend: pytest；frontend: vitest
make lint       # ruff check + ruff format --check + mypy；eslint + tsc --noEmit
make eval       # pytest -m eval（golden set 回归，改 prompt 后必跑）
make migrate    # alembic upgrade head
make seed       # 种子数据
make gen-api    # 后端 OpenAPI → 前端 TS client（openapi-typescript）
```

## 硬性规则

1. **一次只做一个里程碑（M）**，DoD 全过才进下一个。每个 M 完成后 git commit。
2. **禁止提交密钥**。一切密钥走 `.env`（有 `.env.example`）。发现密钥入库 = 事故。
3. **改 `backend/app/ai/prompts/` 下任何文件必须跑 `make eval`**，通过率下降就回滚或修。
4. **RBAC 在 service 层强制**：任何查询必须过 owner/team 过滤，禁止在路由层裸查。新增接口必须带三角色权限测试。
5. **AI 输出一律结构化**：Pydantic schema 校验，失败重试一次；禁止裸解析自由文本。
6. **不新增 PLAN.md 之外的重依赖**（框架/中间件级别）——先说明理由并征得用户同意。
7. 数据库变更只走 Alembic 迁移，禁止手改表；迁移必须可降级。
8. UI 与 AI 输出全部中文。金额单位默认 CNY。

## 代码规范

- Python：ruff（line-length 100）、全量类型标注、async 优先；service 抛领域异常，api 层统一转 HTTP 错误
- 路由薄、service 厚；一实体一 model 文件、一 schema 文件
- 前端：shadcn/ui 组件优先，不引新 UI 库；API client 由 openapi-typescript 从后端 OpenAPI 生成，禁止手写 fetch 散落各处
- 测试：pytest + testcontainers（真 pg，不 mock DB）；LLM 调用在单测中 mock，在 evals 中真调
- 命名：表/字段 snake_case，前端组件 PascalCase，API 路径 kebab 不用（用复数名词）

## 目录速查

```
backend/app/{core,models,schemas,api/v1,services,ai,tasks}
backend/{alembic,tests,evals,scripts}
frontend/{app,components,lib,e2e}
```

## 完成一个 M 的自查清单（DoD 模板）

- [ ] PLAN.md 对应 § 的验收标准逐条通过
- [ ] make lint && make test 全绿（涉及 prompt 则 + make eval）
- [ ] 新接口有 RBAC 测试
- [ ] Alembic 迁移可升可降
- [ ] git commit（信息格式：`M{N}: 摘要`）
- [ ] 向用户输出验收报告，等确认后再开始下一个 M

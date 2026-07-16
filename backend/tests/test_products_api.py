"""M13 产品库：CRUD/RBAC、规格书抽取幂等、检索、对比矩阵、替代推荐。"""

import io
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.client import LLMClient, get_llm_client
from app.main import app
from app.models import Product, User
from app.models.enums import ProductStatus
from app.tasks import dispatcher
from app.tasks.product import SPEC_UPLOAD_DIR, extract_product_task
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, completion, embedding_response

LoginFn = Callable[[str], Awaitable[dict[str, str]]]

EXTRACT_JSON = json.dumps(
    {
        "model_no": "VFD-750B",
        "name": "750W 通用变频器",
        "brand": "DeltaTech",
        "category": "变频器",
        "specs": {"额定功率": "750W", "输入电压": "380V±10%", "防护等级": "IP20"},
        "description": "面向中小型设备的通用变频器。",
        "confidence_note": "价格原文未提及",
    },
    ensure_ascii=False,
)


@pytest.fixture(autouse=True)
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_enqueue(task_name: str, *args: Any) -> bool:
        calls.append((task_name, args))
        return True

    monkeypatch.setattr(dispatcher, "enqueue", fake_enqueue)
    return calls


@pytest.fixture(autouse=True)
def _inject_llm(llm: LLMClient) -> Any:
    app.dependency_overrides[get_llm_client] = lambda: llm
    yield
    app.dependency_overrides.pop(get_llm_client, None)


async def _seed_product(
    session: AsyncSession,
    creator: User,
    model_no: str,
    *,
    status: ProductStatus = ProductStatus.ACTIVE,
    specs: dict[str, str] | None = None,
    embedding: list[float] | None = None,
) -> Product:
    product = Product(
        model_no=model_no,
        name=f"{model_no} 产品",
        category="变频器",
        status=status,
        specs=specs or {},
        created_by=creator.id,
        embedding=embedding,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def test_crud_rbac_and_duplicate_guard(
    client: AsyncClient,
    roles: RoleUsers,
    login: LoginFn,
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    headers_m = await login("manager_a@test.cn")
    headers_s = await login("sales_a@test.cn")

    # sales 不能建
    resp = await client.post(
        "/api/v1/products",
        json={"model_no": "X-1", "name": "测试产品"},
        headers=headers_s,
    )
    assert resp.status_code == 403

    # manager 建 → 自动排嵌入
    resp = await client.post(
        "/api/v1/products",
        json={"model_no": "X-1", "name": "测试产品", "specs": {"功率": "1kW"}},
        headers=headers_m,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    assert enqueued[-1] == ("embed_product_task", (pid,))

    # 同型号重复建被拦
    resp = await client.post(
        "/api/v1/products", json={"model_no": "X-1", "name": "重复"}, headers=headers_m
    )
    assert resp.status_code == 400

    # 全员可读
    resp = await client.get("/api/v1/products", headers=headers_s)
    assert resp.json()["total"] == 1

    # sales 不能改；manager 标停产
    resp = await client.patch(f"/api/v1/products/{pid}", json={"status": "eol"}, headers=headers_s)
    assert resp.status_code == 403
    resp = await client.patch(f"/api/v1/products/{pid}", json={"status": "eol"}, headers=headers_m)
    assert resp.status_code == 200
    assert resp.json()["status"] == "eol"

    # 改 specs → 重新排嵌入
    resp = await client.patch(
        f"/api/v1/products/{pid}", json={"specs": {"功率": "2kW"}}, headers=headers_m
    )
    assert enqueued[-1] == ("embed_product_task", (pid,))

    # 软删
    resp = await client.delete(f"/api/v1/products/{pid}", headers=headers_m)
    assert resp.status_code == 204
    resp = await client.get("/api/v1/products", headers=headers_s)
    assert resp.json()["total"] == 0


async def test_upload_spec_extract_and_upsert(
    client: AsyncClient,
    session: AsyncSession,
    engine: AsyncEngine,
    roles: RoleUsers,
    login: LoginFn,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    headers_m = await login("manager_a@test.cn")
    headers_s = await login("sales_a@test.cn")

    # sales 不能传
    resp = await client.post(
        "/api/v1/products/upload-spec",
        files={"file": ("vfd750.txt", io.BytesIO(b"spec text"), "text/plain")},
        headers=headers_s,
    )
    assert resp.status_code == 403

    resp = await client.post(
        "/api/v1/products/upload-spec",
        files={"file": ("vfd750.txt", io.BytesIO("VFD-750B 变频器规格…".encode()), "text/plain")},
        headers=headers_m,
    )
    assert resp.status_code == 202, resp.text
    task_name, args = enqueued[-1]
    assert task_name == "extract_product_task"
    token = args[0]
    assert (SPEC_UPLOAD_DIR / f"{token}.txt").exists()

    # 跑抽取任务：extract(json) + embed
    fakes["deepseek"].chat.completions.responses = [completion(EXTRACT_JSON)]
    fakes["qwen"].embeddings.responses = [embedding_response([[0.1] * 1024])]
    maker = async_sessionmaker(engine, expire_on_commit=False)
    await extract_product_task({"sessionmaker": maker, "llm": llm}, *args)

    product = await session.scalar(select(Product).where(Product.model_no == "VFD-750B"))
    assert product is not None
    assert product.specs["额定功率"] == "750W"
    assert product.embedding is not None
    assert product.source_doc_name == "vfd750"

    # 同型号再抽取（更新的规格书）→ upsert 不新建
    fakes["deepseek"].chat.completions.responses = [
        completion(EXTRACT_JSON.replace("750W", "800W"))
    ]
    fakes["qwen"].embeddings.responses = [embedding_response([[0.2] * 1024])]
    token2 = uuid.uuid4().hex
    (SPEC_UPLOAD_DIR / f"{token2}.txt").write_bytes(b"updated spec")
    await extract_product_task(
        {"sessionmaker": maker, "llm": llm}, token2, "vfd750-v2", str(roles.manager_a.id)
    )
    count = await session.scalar(
        select(func.count()).select_from(Product).where(Product.deleted_at.is_(None))
    )
    assert count == 1
    await session.refresh(product)
    assert product.specs["额定功率"] == "800W"
    assert product.source_doc_name == "vfd750-v2"


async def test_search_hybrid(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    fakes: dict[str, FakeOpenAI],
) -> None:
    near = [1.0] + [0.0] * 1023
    far = [0.0, 1.0] + [0.0] * 1022
    p1 = await _seed_product(session, roles.admin, "VFD-750B", embedding=near)
    await _seed_product(session, roles.admin, "SRV-200", embedding=far)

    fakes["qwen"].embeddings.responses = [embedding_response([near])]
    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/products/search", json={"query": "VFD-750B", "top_k": 2}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    hits = resp.json()
    assert hits[0]["product"]["model_no"] == p1.model_no  # 向量近 + 关键词命中型号


async def test_compare_matrix_and_llm_fallback(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    fakes: dict[str, FakeOpenAI],
) -> None:
    p1 = await _seed_product(session, roles.admin, "A-1", specs={"功率": "1kW", "电压": "220V"})
    p2 = await _seed_product(session, roles.admin, "B-2", specs={"功率": "2kW", "重量": "3kg"})

    compare_json = json.dumps(
        {
            "summary": "A-1 功率 1kW，B-2 功率 2kW。",
            "key_differences": ["功率：A-1 为 1kW，B-2 为 2kW"],
            "recommendation": "功率需求高选 B-2。",
        },
        ensure_ascii=False,
    )
    fakes["deepseek"].chat.completions.responses = [completion(compare_json)]
    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/products/compare",
        json={"product_ids": [str(p1.id), str(p2.id)]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    params = [r["param"] for r in body["matrix"]["rows"]]
    assert params == ["功率", "电压", "重量"]  # keys 并集保序
    volt_row = next(r for r in body["matrix"]["rows"] if r["param"] == "电压")
    assert volt_row["values"] == ["220V", "—"]  # 缺失参数用 —
    assert body["analysis"]["key_differences"][0].startswith("功率")

    # LLM 全挂 → 降级：矩阵可用 + analysis_note 说明
    import httpx
    import openai

    req = httpx.Request("POST", "https://fake.test/v1/chat/completions")
    fakes["deepseek"].chat.completions.responses = [
        openai.InternalServerError("x", response=httpx.Response(500, request=req), body=None)
    ]
    fakes["qwen"].chat.completions.responses = [
        openai.InternalServerError("y", response=httpx.Response(500, request=req), body=None)
    ]
    resp = await client.post(
        "/api/v1/products/compare",
        json={"product_ids": [str(p1.id), str(p2.id)]},
        headers=headers,
    )
    body = resp.json()
    assert body["analysis"] is None
    assert "暂不可用" in body["analysis_note"]
    assert len(body["matrix"]["rows"]) == 3

    # 数量守卫
    resp = await client.post(
        "/api/v1/products/compare", json={"product_ids": [str(p1.id)]}, headers=headers
    )
    assert resp.status_code == 422  # pydantic min_length=2


async def test_alternatives_eol_filter(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    base = [1.0] + [0.0] * 1023
    near_active = [0.98, 0.2] + [0.0] * 1022
    near_eol = [0.99, 0.1] + [0.0] * 1022
    target = await _seed_product(
        session,
        roles.admin,
        "OLD-100",
        status=ProductStatus.EOL,
        specs={"功率": "1kW"},
        embedding=base,
    )
    alt = await _seed_product(
        session,
        roles.admin,
        "NEW-200",
        specs={"功率": "1.2kW"},
        embedding=near_active,
    )
    await _seed_product(
        session, roles.admin, "OLD-90", status=ProductStatus.EOL, embedding=near_eol
    )

    headers = await login("sales_a@test.cn")
    resp = await client.get(f"/api/v1/products/{target.id}/alternatives", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    models = [a["model_no"] for a in body["alternatives"]]
    assert alt.model_no in models
    assert "OLD-90" not in models  # 默认过滤 EOL
    top = body["alternatives"][0]
    assert 0 < top["similarity"] <= 1
    assert any("功率" in d for d in top["spec_diffs"])

    # include_eol=true 时 EOL 也返回
    resp = await client.get(
        f"/api/v1/products/{target.id}/alternatives",
        params={"include_eol": "true"},
        headers=headers,
    )
    assert "OLD-90" in [a["model_no"] for a in resp.json()["alternatives"]]

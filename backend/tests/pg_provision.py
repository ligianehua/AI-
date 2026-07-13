"""测试 PostgreSQL 供给（tests 与 evals 共用）。

本模块必须保持无导入副作用：evals/conftest.py 会导入它，而 evals 需要
真实的 providers.yaml 与 .env 密钥（tests/conftest.py 顶层会覆盖这些环境变量，
因此 evals 绝不能导入 tests.conftest）。
"""

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_alembic(url: str, *args: str) -> None:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": url}
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True, cwd=BACKEND_DIR, env=env)


def _provision_pg() -> tuple[str, Callable[[], None]]:
    """测试库三级供给：TEST_DATABASE_URL > Docker testcontainers > 本地 PG 二进制。"""
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url, lambda: None

    if shutil.which("docker"):
        try:
            from testcontainers.postgres import PostgresContainer

            container = PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg")
            container.start()
            return container.get_connection_url(), lambda: container.stop()
        except Exception as exc:  # noqa: BLE001 - docker 不可用则回退本地
            print(f"testcontainers 不可用（{exc}），回退本地 PostgreSQL")

    from scripts import local_pg

    local_pg.ensure_binaries()
    datadir = Path(tempfile.mkdtemp(prefix="ai_sales_test_pg_"))
    local_pg.init_cluster(datadir)
    port = local_pg.free_port()
    local_pg.start(datadir, port)
    local_pg.ensure_database(port, "app_test")

    def cleanup() -> None:
        local_pg.stop(datadir)
        shutil.rmtree(datadir, ignore_errors=True)

    return local_pg.async_url(port, "app_test"), cleanup

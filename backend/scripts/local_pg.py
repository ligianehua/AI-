"""本机无 Docker 时的本地 PostgreSQL 管理（开发/测试的临时方案，装好 Docker 后弃用）。

PG16 + pgvector 二进制来自 pgserver wheel（dev 依赖），拷贝到纯 ASCII 路径后由本模块
自行 initdb / pg_ctl 管理——项目路径含中文时 initdb 会把 GBK 字节写进 UTF8 SQL 导致失败，
所以二进制必须放在 ASCII 路径（%LOCALAPPDATA%）。

CLI 用法：
    uv run python -m scripts.local_pg start   # 启动开发库（端口 55432，库 ai_sales）
    uv run python -m scripts.local_pg stop
    uv run python -m scripts.local_pg url     # 打印 DATABASE_URL
"""

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

DEV_PORT = 55432
DEV_DB = "ai_sales"

_EXE = ".exe" if os.name == "nt" else ""


def pg_home() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "ai_sales_pg16"


def dev_datadir() -> Path:
    return pg_home() / "devdata"


def ensure_binaries() -> Path:
    """确保 PG 二进制在 ASCII 路径下，返回 bin 目录。"""
    home = pg_home()
    bindir = home / "bin"
    if not (bindir / f"initdb{_EXE}").exists():
        import pgserver

        src = Path(pgserver.__file__).parent / "pginstall"
        print(f"复制 PostgreSQL 二进制 {src} -> {home}")
        shutil.copytree(src, home, dirs_exist_ok=True)
    return bindir


def init_cluster(datadir: Path) -> None:
    if (datadir / "PG_VERSION").exists():
        return
    bindir = ensure_binaries()
    datadir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(bindir / f"initdb{_EXE}"),
            "-D",
            str(datadir),
            "--auth=trust",
            "--encoding=utf8",
            "--locale=C",
            "-U",
            "postgres",
        ],
        check=True,
    )


def is_running(datadir: Path) -> bool:
    bindir = ensure_binaries()
    result = subprocess.run(
        [str(bindir / f"pg_ctl{_EXE}"), "-D", str(datadir), "status"],
        capture_output=True,
    )
    return result.returncode == 0


def start(datadir: Path, port: int) -> None:
    if is_running(datadir):
        return
    bindir = ensure_binaries()
    subprocess.run(
        [
            str(bindir / f"pg_ctl{_EXE}"),
            "-D",
            str(datadir),
            "-w",
            "-o",
            f"-p {port} -c listen_addresses=127.0.0.1",
            "-l",
            str(datadir / "server.log"),
            "start",
        ],
        check=True,
    )


def stop(datadir: Path) -> None:
    if not is_running(datadir):
        return
    bindir = ensure_binaries()
    subprocess.run(
        [str(bindir / f"pg_ctl{_EXE}"), "-D", str(datadir), "stop", "-m", "fast"],
        check=True,
    )


def psql(port: int, sql: str, db: str = "postgres") -> str:
    bindir = ensure_binaries()
    result = subprocess.run(
        [
            str(bindir / f"psql{_EXE}"),
            "-h",
            "127.0.0.1",
            "-p",
            str(port),
            "-U",
            "postgres",
            "-d",
            db,
            "-tAc",
            sql,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def ensure_database(port: int, name: str) -> None:
    exists = psql(port, f"SELECT 1 FROM pg_database WHERE datname='{name}'")
    if exists != "1":
        psql(port, f'CREATE DATABASE "{name}"')


def async_url(port: int, db: str) -> str:
    return f"postgresql+asyncpg://postgres@127.0.0.1:{port}/{db}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "start"
    datadir = dev_datadir()
    if command == "start":
        init_cluster(datadir)
        start(datadir, DEV_PORT)
        ensure_database(DEV_PORT, DEV_DB)
        print(f"PostgreSQL 已启动：{async_url(DEV_PORT, DEV_DB)}")
        print("将 .env 的 DATABASE_URL 指向上面的地址（或设同名环境变量）即可本地开发。")
    elif command == "stop":
        stop(datadir)
        print("PostgreSQL 已停止")
    elif command == "url":
        print(async_url(DEV_PORT, DEV_DB))
    else:
        print(f"未知命令：{command}（支持 start / stop / url）")
        sys.exit(1)


if __name__ == "__main__":
    main()

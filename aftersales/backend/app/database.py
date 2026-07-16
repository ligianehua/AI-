"""数据库引擎、会话与初始化（含 FTS5 虚表）"""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

settings.db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
  entry_id UNINDEXED, title_seg, question_seg, answer_seg, tokenize='unicode61'
);
"""

MANUAL_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS manual_fts USING fts5(
  chunk_id UNINDEXED, section_seg, content_seg, tokenize='unicode61'
);
"""


# 已有库的轻量迁移：给旧表补新列（SQLite 支持 ADD COLUMN）
MIGRATIONS = {
    "conversations": [("mode", "VARCHAR(10) DEFAULT 'ai'"),
                      ("assigned_agent", "VARCHAR(50)")],
    "messages": [("agent_name", "VARCHAR(50)"),
                 ("image_path", "VARCHAR(200)"),
                 ("feedback", "VARCHAR(4)")],
    "kb_entries": [("embedding", "TEXT")],
    "manual_chunks": [("embedding", "TEXT")],
}


def _migrate(conn):
    for table, columns in MIGRATIONS.items():
        try:
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
        except Exception:
            continue
        if not existing:
            continue
        for name, ddl in columns:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def init_db():
    from . import models  # noqa: F401  确保模型注册

    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text(FTS_DDL))
        conn.execute(text(MANUAL_FTS_DDL))
        _migrate(conn)
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

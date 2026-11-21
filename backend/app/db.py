from collections.abc import Generator
from pathlib import Path
from sqlite3 import Connection
from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import ConnectionPoolEntry
from sqlmodel import Session, SQLModel, create_engine
from . import models  # Register every table before create_all.
from .config import get_settings


def build_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.drivername == "sqlite" and url.database not in (None, ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args={"check_same_thread": False, "timeout": 5} if url.drivername == "sqlite" else {})
    if url.drivername == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection: Connection, _: ConnectionPoolEntry) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    if engine.dialect.name=='sqlite':
        from sqlalchemy import inspect, text
        existing={column['name'] for column in inspect(engine).get_columns('message')}
        case_columns={column['name'] for column in inspect(engine).get_columns('case')}
        with engine.begin() as connection:
            if 'owner_id' not in case_columns:
                connection.execute(text("ALTER TABLE \"case\" ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'owner'"))
            connection.execute(text('CREATE INDEX IF NOT EXISTS ix_case_owner_id ON \"case\" (owner_id)'))
            for name,sql in (('references_json',"JSON NOT NULL DEFAULT '[]'"),('gmail_thread_id','TEXT'),('match_method','TEXT')):
                if name not in existing: connection.execute(text(f'ALTER TABLE message ADD COLUMN {name} {sql}'))
    with Session(engine) as session:
        if session.get(models.Settings, 1) is None:
            session.add(models.Settings())
            session.commit()


def get_session() -> Generator[Session, None, None]:
    from .main import app
    with Session(app.state.engine) as session:
        yield session
